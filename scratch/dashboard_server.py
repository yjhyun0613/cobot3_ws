#!/usr/bin/env python3
import os
import psycopg2
import redis
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Coupang Warehouse Control Panel")

# DB 연결 헬퍼 함수
def get_db_connections():
    try:
        pg_conn = psycopg2.connect(
            host='localhost',
            port=5432,
            user='rokey',
            password='rokey_pass',
            database='warehouse_db'
        )
        pg_conn.autocommit = True
        
        redis_client = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True
        )
        return pg_conn, redis_client
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None, None

@app.get("/api/status")
def get_status():
    pg_conn, redis_client = get_db_connections()
    if not pg_conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    try:
        with pg_conn.cursor() as cursor:
            # 1. Fetch workstations
            cursor.execute("SELECT workstation_id, current_location, qr_id FROM workstations ORDER BY workstation_id;")
            ws_rows = cursor.fetchall()
            
            # 2. Fetch packages in workstations
            cursor.execute("""
                SELECT workstation_id, slot_number, customer_name 
                FROM packages 
                WHERE status = 'IN_WORKSTATION' AND workstation_id IS NOT NULL;
            """)
            pkg_rows = cursor.fetchall()
            ws_pkg_map = {}
            for ws_id, slot_num, customer in pkg_rows:
                if ws_id not in ws_pkg_map:
                    ws_pkg_map[ws_id] = {}
                ws_pkg_map[ws_id][slot_num] = customer
            
            workstations = []
            for row in ws_rows:
                ws_id = row[0]
                slots = []
                for s in range(1, 9):
                    customer = ws_pkg_map.get(ws_id, {}).get(s, None)
                    status = "FULL" if customer else "EMPTY"
                    slots.append({"slot_number": s, "customer": customer, "status": status})
                
                workstations.append({
                    "workstation_id": ws_id,
                    "current_location": row[1],
                    "qr_id": row[2],
                    "slots": slots
                })
            
            # 2. Warehouse Locations
            cursor.execute("""
                SELECT spot_id, workstation_id, status FROM warehouse_locations ORDER BY spot_id;
            """)
            spots = []
            for row in cursor.fetchall():
                spots.append({
                    "spot_id": row[0],
                    "workstation_id": row[1],
                    "status": row[2]
                })
                
            # 3. Packages
            cursor.execute("""
                SELECT package_id, customer_name, route_zone, status, outbound_id, workstation_id, slot_number, qr_id
                FROM packages ORDER BY package_id;
            """)
            packages = []
            for row in cursor.fetchall():
                packages.append({
                    "package_id": row[0],
                    "customer_name": row[1],
                    "route_zone": row[2],
                    "status": row[3],
                    "outbound_id": row[4],
                    "workstation_id": row[5],
                    "slot_number": row[6],
                    "qr_id": row[7]
                })
                
        # 4. Redis Active Queue Tasks
        redis_tasks = []
        if redis_client:
            try:
                # Redis 큐 'queue:amr_tasks' 에 쌓인 전체 데이터 조회 (비파괴적)
                tasks_raw = redis_client.lrange('queue:amr_tasks', 0, -1)
                for t in tasks_raw:
                    try:
                        redis_tasks.append(json.loads(t))
                    except:
                        redis_tasks.append({"raw_task": t})
            except Exception as re:
                print(f"Redis Queue Query Error: {re}")

        pg_conn.close()
        return {
            "workstations": workstations,
            "spots": spots,
            "packages": packages,
            "redis_tasks": redis_tasks
        }
    except Exception as e:
        if pg_conn:
            pg_conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reset")
def reset_db():
    pg_conn, redis_client = get_db_connections()
    if not pg_conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    try:
        # 1. PostgreSQL 초기화 실행
        init_sql_path = os.path.join(os.path.dirname(__file__), '../docker/init.sql')
        if not os.path.exists(init_sql_path):
            init_sql_path = 'docker/init.sql' # Fallback
            
        with open(init_sql_path, 'r') as f:
            sql_queries = f.read()
            
        with pg_conn.cursor() as cursor:
            cursor.execute(sql_queries)
            
        # 2. Redis 큐 초기화
        if redis_client:
            redis_client.delete('queue:amr_tasks')
            
        pg_conn.close()
        return {"success": True, "message": "데이터베이스가 성공적으로 초기화되었습니다."}
    except Exception as e:
        if pg_conn:
            pg_conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/simulate")
def simulate_inbound():
    pg_conn, redis_client = get_db_connections()
    if not pg_conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    try:
        with pg_conn.cursor() as cursor:
            # 1. 아직 적재되지 않은 대기 중인 상자 하나 선택
            cursor.execute("SELECT package_id, customer_name, route_zone, qr_id FROM packages WHERE status = 'WAITING' LIMIT 1;")
            pkg_row = cursor.fetchone()
            if not pkg_row:
                pg_conn.close()
                return {"success": False, "message": "더 이상 적재할 대기 패키지가 없습니다."}
            
            pkg_id, cust_name, zone, pkg_qr = pkg_row
            
            # 2. 현재 적재 대기 중인(예: sg2_in_01에 있는) 작업대 찾기
            # 만약 없으면 WS01을 강제로 임바운드에 매핑하고, 원래 있던 창고 주차 스팟을 비워줍니다.
            cursor.execute("SELECT workstation_id FROM workstations WHERE current_location = 'sg2_in_01' LIMIT 1;")
            ws_row = cursor.fetchone()
            ws_id = "WS01"
            if ws_row:
                ws_id = ws_row[0]
            else:
                # 원래 WS01이 위치하고 있던 창고 주차 스팟을 조회해 EMPTY로 비워줍니다.
                cursor.execute("SELECT spot_id FROM warehouse_locations WHERE workstation_id = 'WS01';")
                spot_row = cursor.fetchone()
                if spot_row:
                    spot_id = spot_row[0]
                    cursor.execute("UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;", (spot_id,))
                
                # WS01을 적재 라인으로 강제 매핑
                cursor.execute("UPDATE workstations SET current_location = 'sg2_in_01' WHERE workstation_id = 'WS01';")
                ws_id = "WS01"

            # 3. 해당 작업대의 다음 빈 슬롯 찾기
            cursor.execute("""
                SELECT slot_number FROM packages 
                WHERE workstation_id = %s AND status = 'IN_WORKSTATION';
            """, (ws_id,))
            filled_slots = {r[0] for r in cursor.fetchall()}
            
            slot_num = None
            for s in range(1, 9):
                if s not in filled_slots:
                    slot_num = s
                    break
            
            if slot_num is None:
                pg_conn.close()
                return {"success": False, "message": f"작업대 {ws_id}의 모든 슬롯이 찼습니다!"}
                
            # 4. 데이터베이스 업데이트 (패키지 정보)
            cursor.execute("""
                UPDATE packages 
                SET status = 'IN_WORKSTATION', workstation_id = %s, slot_number = %s
                WHERE package_id = %s;
            """, (ws_id, slot_num, pkg_id))
            
            # 5. 만약 3번째 슬롯에 상자가 올라갔다면 Redis 큐에 Look-ahead 작업 추가
            lookahead_triggered = False
            if slot_num == 7 and redis_client:
                # QR ID 구하기
                cursor.execute("SELECT qr_id FROM workstations WHERE workstation_id = %s;", (ws_id,))
                ws_qr = cursor.fetchone()[0]
                
                task_data = {
                    "task_type": "PRE_FETCH_EMPTY_WORKSTATION",
                    "target_robot": "sg2_in_01",
                    "description": f"Look-ahead: {ws_id} 7번째 슬롯 적재 감지로 예비 작업대 호출",
                    "workstation_qr_id": ws_qr
                }
                redis_client.lpush('queue:amr_tasks', json.dumps(task_data))
                lookahead_triggered = True

        pg_conn.close()
        msg = f"상자 {pkg_id}를 작업대 {ws_id}의 {slot_num}번 슬롯에 적재했습니다."
        if lookahead_triggered:
            msg += " (★ Look-ahead 예비 작업대 호출 트리거 발동!)"
            
        return {"success": True, "message": msg}
    except Exception as e:
        if pg_conn:
            pg_conn.close()
        raise HTTPException(status_code=500, detail=str(e))

# HTML 대시보드 마크업 제공
@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Coupang Control Center Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 28, 45, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --primary: #00f2fe;
            --secondary: #4facfe;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text: #e2e8f0;
            --text-muted: #64748b;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', sans-serif;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text);
            overflow-x: hidden;
            background-image: radial-gradient(circle at 10% 20%, rgba(0, 242, 254, 0.05) 0%, transparent 40%),
                              radial-gradient(circle at 90% 80%, rgba(79, 172, 254, 0.05) 0%, transparent 40%);
            background-attachment: fixed;
        }

        /* Layout */
        .container {
            max-width: 1440px;
            margin: 0 auto;
            padding: 2rem;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 2rem;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 2rem;
        }

        .logo-section h1 {
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }

        .logo-section p {
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-top: 2px;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: var(--success);
            padding: 8px 16px;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.85rem;
        }

        .status-badge .dot {
            width: 8px;
            height: 8px;
            background-color: var(--success);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--success);
            animation: pulse 2s infinite;
        }

        /* Buttons Control Panel */
        .controls {
            display: flex;
            gap: 12px;
            margin-bottom: 2rem;
        }

        button {
            padding: 12px 24px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .btn-simulate {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            border: none;
            color: #000;
            box-shadow: 0 4px 15px rgba(0, 242, 254, 0.25);
        }

        .btn-simulate:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 242, 254, 0.4);
        }

        .btn-reset {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: var(--danger);
        }

        .btn-reset:hover {
            background: var(--danger);
            color: #fff;
            box-shadow: 0 4px 15px rgba(239, 68, 68, 0.2);
            transform: translateY(-2px);
        }

        /* Grid sections */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
            margin-bottom: 2rem;
        }

        @media (max-width: 1024px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
        }

        .panel-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 1.5rem;
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        }

        .panel-card h2 {
            font-size: 1.25rem;
            font-weight: 700;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            color: #fff;
            border-left: 4px solid var(--primary);
            padding-left: 10px;
        }

        /* Warehouse spots styling */
        .spots-container {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
        }

        .spot-item {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 12px;
            text-align: center;
            transition: all 0.3s ease;
        }

        .spot-item.occupied {
            border-color: rgba(245, 158, 11, 0.3);
            background: rgba(245, 158, 11, 0.05);
            box-shadow: inset 0 0 12px rgba(245, 158, 11, 0.05);
        }

        .spot-item.empty {
            border-color: rgba(16, 185, 129, 0.3);
            background: rgba(16, 185, 129, 0.05);
        }

        .spot-id {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-weight: 600;
        }

        .spot-ws {
            font-size: 1.1rem;
            font-weight: 700;
            margin: 6px 0;
            color: var(--text);
        }

        .spot-status-badge {
            display: inline-block;
            font-size: 0.65rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 9999px;
        }

        .spot-item.occupied .spot-status-badge {
            background: rgba(245, 158, 11, 0.15);
            color: var(--warning);
        }

        .spot-item.empty .spot-status-badge {
            background: rgba(16, 185, 129, 0.15);
            color: var(--success);
        }

        /* Workstations styling */
        .workstations-container {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
            max-height: 480px;
            overflow-y: auto;
            padding-right: 4px;
        }

        .workstations-container::-webkit-scrollbar {
            width: 6px;
        }
        .workstations-container::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 99px;
        }

        .ws-card {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 14px;
            transition: all 0.3s ease;
        }

        .ws-card:hover {
            transform: translateY(-2px);
            border-color: rgba(0, 242, 254, 0.2);
        }

        .ws-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }

        .ws-id {
            font-size: 1rem;
            font-weight: 700;
            color: #fff;
        }

        .ws-loc {
            font-size: 0.75rem;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.05);
            color: var(--text);
        }

        .ws-loc.moving {
            background: rgba(0, 242, 254, 0.15);
            color: var(--primary);
            animation: pulse-border 1.5s infinite;
        }

        /* WS Slot visual */
        .ws-slots-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr); /* 2x4 Layout */
            gap: 6px;
        }

        .ws-slot {
            height: 38px;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            font-size: 0.7rem;
            font-weight: 600;
            border: 1px solid var(--border-color);
            background: rgba(255, 255, 255, 0.02);
            transition: all 0.2s ease;
            position: relative;
        }

        .ws-slot.full {
            background: rgba(0, 242, 254, 0.08);
            border-color: rgba(0, 242, 254, 0.3);
            color: var(--primary);
        }

        .ws-slot-name {
            font-size: 0.6rem;
            color: var(--text-muted);
            max-width: 90%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        /* Redis tasks */
        .tasks-list {
            margin-top: 10px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .task-item {
            background: rgba(79, 172, 254, 0.08);
            border: 1px solid rgba(79, 172, 254, 0.2);
            border-radius: 10px;
            padding: 10px 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.85rem;
        }

        .task-name {
            font-weight: 700;
            color: var(--primary);
        }

        .task-desc {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 2px;
        }

        /* Packages table */
        .table-wrapper {
            overflow-x: auto;
            max-height: 400px;
            overflow-y: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.85rem;
        }

        th {
            background: rgba(15, 23, 42, 0.8);
            padding: 12px;
            font-weight: 600;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
            position: sticky;
            top: 0;
            z-index: 10;
        }

        td {
            padding: 12px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text);
        }

        tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }

        .status-pill {
            display: inline-block;
            font-size: 0.7rem;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 9999px;
        }

        .status-pill.waiting {
            background: rgba(100, 116, 139, 0.15);
            color: var(--text-muted);
        }

        .status-pill.in_workstation {
            background: rgba(0, 242, 254, 0.15);
            color: var(--primary);
        }

        .status-pill.in_warehouse {
            background: rgba(245, 158, 11, 0.15);
            color: var(--warning);
        }

        .status-pill.completed {
            background: rgba(16, 185, 129, 0.15);
            color: var(--success);
        }

        /* Toast notification */
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid var(--primary);
            border-radius: 12px;
            padding: 16px 24px;
            color: #fff;
            font-weight: 600;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 999;
        }

        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }

        /* Keyframes */
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        @keyframes pulse-border {
            0%, 100% { border-color: rgba(0, 242, 254, 0.2); box-shadow: 0 0 0 0 rgba(0, 242, 254, 0.2); }
            50% { border-color: rgba(0, 242, 254, 0.8); box-shadow: 0 0 10px 0 rgba(0, 242, 254, 0.3); }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo-section">
                <h1>Coupang Control Center</h1>
                <p>PostgreSQL & Redis 실시간 모니터링 대시보드 (10 Workstations v1.2)</p>
            </div>
            <div class="status-badge">
                <span class="dot"></span>
                <span>SYSTEM LIVE</span>
            </div>
        </header>

        <div class="controls">
            <button class="btn-simulate" onclick="simulateInbound()">
                <span>⚡</span> 시뮬레이션 적재 발생
            </button>
            <button class="btn-reset" onclick="resetDatabase()">
                <span>🔄</span> 데이터베이스 초기화
            </button>
        </div>

        <div class="dashboard-grid">
            <!-- Left: Warehouse Parking spots -->
            <div class="panel-card">
                <h2>Warehouse Parking Spots (10 Slots) <span style="font-size: 0.8rem; color: var(--text-muted);">spot_01 ~ spot_10</span></h2>
                <div class="spots-container" id="spots-list">
                    <!-- Dynamic spots go here -->
                </div>
            </div>

            <!-- Right: Workstations Active slots -->
            <div class="panel-card">
                <h2>Workstations Active Status (10 Plates) <span style="font-size: 0.8rem; color: var(--text-muted);">2x4 Slots Layout</span></h2>
                <div class="workstations-container" id="ws-list">
                    <!-- Dynamic workstations go here -->
                </div>
            </div>
        </div>

        <!-- Redis Active commands queue -->
        <div class="panel-card" style="margin-bottom: 2rem;">
            <h2>Redis Command Queue <span style="font-size: 0.8rem; color: var(--text-muted); font-weight: normal; margin-left: 10px;" id="redis-count">0 tasks active</span></h2>
            <div class="tasks-list" id="tasks-list">
                <!-- Dynamic redis tasks -->
            </div>
        </div>

        <!-- Package tracking log -->
        <div class="panel-card">
            <h2>Package Tracking Log</h2>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Package ID</th>
                            <th>QR ID</th>
                            <th>수령인</th>
                            <th>배송 예정구역</th>
                            <th>진행 상태</th>
                            <th>적재 작업대</th>
                            <th>슬롯 번호</th>
                            <th>출고 바코드 ID</th>
                        </tr>
                    </thead>
                    <tbody id="package-tbody">
                        <!-- Dynamic packages go here -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <div class="toast" id="toast-message"></div>

    <script>
        // 토스트 알림 헬퍼
        function showToast(message) {
            const toast = document.getElementById('toast-message');
            toast.innerText = message;
            toast.classList.add('show');
            setTimeout(() => {
                toast.classList.remove('show');
            }, 3000);
        }

        // 1. 모의 적재 이벤트 트리거
        async function simulateInbound() {
            try {
                const response = await fetch('/api/simulate', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    showToast(data.message);
                    fetchStatus();
                } else {
                    showToast("❌ Error: " + data.message);
                }
            } catch (err) {
                showToast("❌ API 통신 오류 발생");
            }
        }

        // 2. DB 초기화 트리거
        async function resetDatabase() {
            if(!confirm("PostgreSQL과 Redis 큐를 초기상태로 완전히 리셋하시겠습니까?")) return;
            try {
                const response = await fetch('/api/reset', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    showToast("🔄 " + data.message);
                    fetchStatus();
                } else {
                    showToast("❌ 초기화 실패: " + data.message);
                }
            } catch (err) {
                showToast("❌ API 통신 오류 발생");
            }
        }

        // 3. 상태 실시간 페치 루프
        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                if (!response.ok) return;
                const data = await response.json();

                // 3-1. Render Warehouse spots
                const spotsContainer = document.getElementById('spots-list');
                spotsContainer.innerHTML = '';
                data.spots.forEach(spot => {
                    const isOccupied = spot.status === 'OCCUPIED';
                    const item = document.createElement('div');
                    item.className = `spot-item ${isOccupied ? 'occupied' : 'empty'}`;
                    item.innerHTML = `
                        <div class="spot-id">${spot.spot_id.toUpperCase()}</div>
                        <div class="spot-ws">${spot.workstation_id || '—'}</div>
                        <div class="spot-status-badge">${isOccupied ? 'OCCUPIED' : 'EMPTY'}</div>
                    `;
                    spotsContainer.appendChild(item);
                });

                // 3-2. Render Workstations
                const wsContainer = document.getElementById('ws-list');
                wsContainer.innerHTML = '';
                data.workstations.forEach(ws => {
                    const isMoving = ws.current_location.startsWith('MOVING_');
                    const card = document.createElement('div');
                    card.className = 'ws-card';
                    
                    let slotsHTML = '';
                    ws.slots.forEach(slot => {
                        const isFull = slot.status === 'FULL';
                        slotsHTML += `
                            <div class="ws-slot ${isFull ? 'full' : ''}">
                                <div>Slot ${slot.slot_number}</div>
                                <div class="ws-slot-name">${slot.customer || 'EMPTY'}</div>
                            </div>
                        `;
                    });

                    card.innerHTML = `
                        <div class="ws-header">
                            <span class="ws-id">${ws.workstation_id} (QR: ${ws.qr_id})</span>
                            <span class="ws-loc ${isMoving ? 'moving' : ''}">${ws.current_location}</span>
                        </div>
                        <div class="ws-slots-grid">
                            ${slotsHTML}
                        </div>
                    `;
                    wsContainer.appendChild(card);
                });

                // 3-3. Render Redis tasks queue
                const tasksContainer = document.getElementById('tasks-list');
                const redisCountEl = document.getElementById('redis-count');
                tasksContainer.innerHTML = '';
                
                const count = data.redis_tasks.length;
                redisCountEl.innerText = `${count} task${count !== 1 ? 's' : ''} active`;

                if (count === 0) {
                    tasksContainer.innerHTML = `
                        <div style="text-align: center; color: var(--text-muted); font-size: 0.85rem; padding: 10px;">
                            큐에 현재 대기 중인 AMR 이송 명령이 없습니다.
                        </div>
                    `;
                } else {
                    data.redis_tasks.forEach(task => {
                        const item = document.createElement('div');
                        item.className = 'task-item';
                        item.innerHTML = `
                            <div>
                                <div class="task-name">${task.task_type || 'TASK'}</div>
                                <div class="task-desc">${task.description || ''}</div>
                            </div>
                            <div style="font-size: 0.75rem; color: var(--text-muted);">
                                QR: ${task.workstation_qr_id || 'N/A'}
                            </div>
                        `;
                        tasksContainer.appendChild(item);
                    });
                }

                // 3-4. Render Packages table
                const tbody = document.getElementById('package-tbody');
                tbody.innerHTML = '';
                data.packages.forEach(pkg => {
                    const row = document.createElement('tr');
                    
                    let statusClass = pkg.status.toLowerCase();
                    row.innerHTML = `
                        <td style="font-weight: 600; color:#fff;">${pkg.package_id}</td>
                        <td>${pkg.qr_id || '—'}</td>
                        <td>${pkg.customer_name}</td>
                        <td>${pkg.route_zone}</td>
                        <td><span class="status-pill ${statusClass}">${pkg.status}</span></td>
                        <td>${pkg.workstation_id || '—'}</td>
                        <td>${pkg.slot_number || '—'}</td>
                        <td style="font-family: monospace; color: var(--primary); font-size: 0.75rem;">${pkg.outbound_id || '—'}</td>
                    `;
                    tbody.appendChild(row);
                });

            } catch (err) {
                console.error("Fetch status error:", err);
            }
        }

        // 최초 실행 및 1초 주기로 실시간 페치 진행
        fetchStatus();
        setInterval(fetchStatus, 1000);
    </script>
</body>
</html>
    """

if __name__ == "__main__":
    uvicorn.run("dashboard_server:app", host="0.0.0.0", port=8000, reload=True)


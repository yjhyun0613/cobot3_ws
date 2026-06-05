#!/usr/bin/env python3
import os
import psycopg2
import redis
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
import uvicorn
import csv
import io
from datetime import datetime

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

def get_task_priority(task_type):
    """태스크 종류별 우선순위 점수 반환"""
    if task_type in ['DIRECT_WAREHOUSE', 'RETRIEVE_FULL_WORKSTATION', 'ROTATE_WORKSTATION']:
        return 100
    elif task_type == 'DEPLOY_EMPTY_WORKSTATION':
        return 90
    elif task_type in ['DEPLOY_PACKAGING_WORKSTATION', 'FETCH_FOR_PACKAGING']:
        return 80
    elif task_type == 'PRE_FETCH_PACKAGING_WORKSTATION':
        return 70
    elif task_type == 'PRE_FETCH_EMPTY_WORKSTATION':
        return 50
    elif task_type == 'RETRIEVE_EMPTY_WORKSTATION':
        return 20
    return 30

def push_priority_task(redis_client, task_dict):
    """AMR 태스크를 Redis Sorted Set 기반 우선순위 큐에 추가"""
    import uuid
    task_dict['uuid'] = str(uuid.uuid4())
    task_type = task_dict.get('task_type', 'TASK')
    score = get_task_priority(task_type)
    if redis_client:
        try:
            redis_client.zadd('queue:amr_tasks', {json.dumps(task_dict): score})
        except Exception as e:
            if "WRONGTYPE" in str(e):
                redis_client.delete('queue:amr_tasks')
                redis_client.zadd('queue:amr_tasks', {json.dumps(task_dict): score})


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

            # 3.5. Fetch floor QR location mappings
            cursor.execute("""
                SELECT location_name, x_coord, y_coord, location_type 
                FROM floor_qr_map 
                WHERE location_name IS NOT NULL;
            """)
            locations = {}
            for loc_name, x, y, loc_type in cursor.fetchall():
                locations[loc_name] = {"x": x, "y": y, "type": loc_type}
                
        # 4. Redis Active Queue Tasks (Sorted Set, 내림차순 조회)
        redis_tasks = []
        if redis_client:
            try:
                tasks_raw = redis_client.zrevrange('queue:amr_tasks', 0, -1, withscores=True)
                for t_raw, score in tasks_raw:
                    try:
                        task_item = json.loads(t_raw)
                        task_item['priority_score'] = int(score)
                        redis_tasks.append(task_item)
                    except:
                        redis_tasks.append({"raw_task": t_raw, "priority_score": int(score)})
            except Exception as re:
                if "WRONGTYPE" in str(re):
                    redis_client.delete('queue:amr_tasks')
                print(f"Redis Queue Query Error: {re}")

        pg_conn.close()
        return {
            "workstations": workstations,
            "spots": spots,
            "packages": packages,
            "redis_tasks": redis_tasks,
            "locations": locations
        }
    except Exception as e:
        if pg_conn:
            pg_conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload_packages")
async def upload_packages(request: Request):
    try:
        content_bytes = await request.body()
        content = content_bytes.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        
        # 1. 컬럼 유효성 검사
        required_fields = ['package_id', 'customer_name', 'route_zone']
        if not csv_reader.fieldnames or not all(field in csv_reader.fieldnames for field in required_fields):
            raise HTTPException(
                status_code=400, 
                detail=f"CSV file must contain columns: {', '.join(required_fields)}"
            )
        
        pg_conn, _ = get_db_connections()
        if not pg_conn:
            raise HTTPException(status_code=500, detail="Database connection failed.")
            
        success_count = 0
        with pg_conn.cursor() as cursor:
            for row in csv_reader:
                pkg_id = row.get('package_id', '').strip()
                cust_name = row.get('customer_name', '').strip()
                route_zone = row.get('route_zone', '').strip()
                status = row.get('status', 'WAITING').strip() or 'WAITING'
                qr_id = row.get('qr_id', pkg_id).strip() or pkg_id
                
                if not pkg_id or not cust_name or not route_zone:
                    continue
                
                cursor.execute("""
                    INSERT INTO packages (package_id, customer_name, route_zone, status, qr_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (package_id) 
                    DO UPDATE SET 
                        customer_name = EXCLUDED.customer_name,
                        route_zone = EXCLUDED.route_zone,
                        status = EXCLUDED.status,
                        qr_id = EXCLUDED.qr_id;
                """, (pkg_id, cust_name, route_zone, status, qr_id))
                success_count += 1
                
        pg_conn.close()
        return {"success": True, "message": f"Successfully loaded {success_count} packages."}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process CSV file: {str(e)}")

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
            
            # 목적지 분류 날짜들을 동적으로 조회하여 인바운드 라인 매핑
            cursor.execute("SELECT DISTINCT route_zone FROM packages WHERE status != 'COMPLETED' ORDER BY route_zone;")
            active_dates = [r[0] for r in cursor.fetchall()]
            
            while len(active_dates) < 3:
                active_dates.append("9999-12-31") # 기본 패딩
                
            today_date = active_dates[0]
            tomorrow_date = active_dates[1]
            day_after_date = active_dates[2]

            # 목적지 분류에 따른 대상 로봇 결정
            if zone == today_date:
                target_robot = 'sg2_in_01'
            elif zone == tomorrow_date:
                target_robot = 'sg2_in_02'
            elif zone == day_after_date:
                target_robot = 'sg2_in_03'
            else:
                target_robot = 'sg2_in_01'

            target_loc = f"{target_robot}_A"
            
            # 2. 해당 로봇 라인에 연관된 작업대 찾기 (A구역 -> 회전중 -> A로 이동중 -> B구역 -> B로 이동중 순으로 선호)
            loc_a = f"{target_robot}_A"
            loc_a_rot = f"{target_robot}_A_ROTATING"
            loc_a_mov = f"MOVING_TO_{target_robot.upper()}_A"
            loc_b = f"{target_robot}_B"
            loc_b_mov = f"MOVING_TO_{target_robot.upper()}_B"
            
            cursor.execute("""
                SELECT workstation_id, current_location FROM workstations 
                WHERE current_location IN (%s, %s, %s, %s, %s)
                ORDER BY 
                    CASE current_location
                        WHEN %s THEN 1
                        WHEN %s THEN 2
                        WHEN %s THEN 3
                        WHEN %s THEN 4
                        WHEN %s THEN 5
                        ELSE 6
                    END
                LIMIT 1;
            """, (loc_a, loc_a_rot, loc_a_mov, loc_b, loc_b_mov, loc_a, loc_a_rot, loc_a_mov, loc_b, loc_b_mov))
            ws_row = cursor.fetchone()
            if ws_row:
                ws_id = ws_row[0]
            else:
                # 작업대가 없다면, 창고에서 비거나 대기중인 것 중 하나를 배정
                cursor.execute("""
                    SELECT workstation_id, current_location FROM workstations 
                    WHERE current_location LIKE 'spot_%%'
                    AND workstation_id NOT IN (
                        SELECT DISTINCT workstation_id FROM packages 
                        WHERE status = 'IN_WORKSTATION' AND workstation_id IS NOT NULL
                    ) LIMIT 1;
                """)
                empty_ws_row = cursor.fetchone()
                if empty_ws_row:
                    ws_id, current_loc = empty_ws_row
                    # 출발 창고 스팟 비우기
                    cursor.execute("UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;", (current_loc,))
                    # A 구역으로 강제 매핑
                    cursor.execute("UPDATE workstations SET current_location = %s WHERE workstation_id = %s;", (target_loc, ws_id))
                else:
                    pg_conn.close()
                    return {"success": False, "message": f"{target_robot}_A 에 배치할 빈 작업대가 없습니다."}

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
            
            # 5. 3번째 슬롯 적재 시 → Look-ahead: 다음 빈 작업대 사전 호출
            lookahead_triggered = False
            if slot_num == 3 and redis_client:
                cursor.execute("SELECT qr_id FROM workstations WHERE workstation_id = %s;", (ws_id,))
                ws_qr = cursor.fetchone()[0]
                
                task_data = {
                    "task_type": "PRE_FETCH_EMPTY_WORKSTATION",
                    "target_robot": target_robot,
                    "description": f"Look-ahead: {ws_id} 3번째 슬롯 적재 감지 → B구역 예비 작업대 호출",
                    "workstation_qr_id": ws_qr
                }
                push_priority_task(redis_client, task_data)
                lookahead_triggered = True

            # 5-1. 4번째 슬롯 적재 시 → 180도 회전 태스크 발행 및 로봇 대기 유도
            rotation_triggered = False
            if slot_num == 4 and redis_client:
                cursor.execute("SELECT qr_id FROM workstations WHERE workstation_id = %s;", (ws_id,))
                ws_qr = cursor.fetchone()[0]
                
                # DB 상태를 ROTATING으로 변경하여 로봇 대기 유도
                cursor.execute(
                    "UPDATE workstations SET current_location = %s WHERE workstation_id = %s;",
                    (f"{target_robot}_A_ROTATING", ws_id)
                )
                
                task_data = {
                    "task_type": "ROTATE_WORKSTATION",
                    "workstation_id": ws_id,
                    "from": f"{target_robot}_A_ROTATING",
                    "to": target_loc,
                    "description": f"제자리 회전: {ws_id} 4번째 슬롯 적재 완료 → 180도 회전",
                    "workstation_qr_id": ws_qr
                }
                push_priority_task(redis_client, task_data)
                rotation_triggered = True
            
            # 6. 8번째 슬롯 적재 시 → 완충 작업대 교체: 다 찬 작업대 회수 (포장존 또는 창고) + 새 작업대 교체 배치
            swap_triggered = False
            if slot_num == 8 and redis_client:
                cursor.execute("SELECT qr_id FROM workstations WHERE workstation_id = %s;", (ws_id,))
                ws_qr_row = cursor.fetchone()
                ws_qr = ws_qr_row[0] if ws_qr_row else ""
                
                if target_robot == 'sg2_in_01':
                    # 오늘 날짜 분류 라인 -> 포장존(sg2_out_00_A 또는 B)으로 이송
                    cursor.execute("""
                        SELECT COUNT(*) FROM workstations 
                        WHERE current_location = 'sg2_out_00_A' OR current_location = 'MOVING_TO_SG2_OUT_00_A';
                    """)
                    out_a_count = cursor.fetchone()[0]
                    target_out = 'sg2_out_00_A' if out_a_count == 0 else 'sg2_out_00_B'

                    cursor.execute(
                        "UPDATE workstations SET current_location = %s WHERE workstation_id = %s;",
                        (target_out, ws_id)
                    )
                    task_retrieve = {
                        "task_type": "RETRIEVE_FULL_WORKSTATION",
                        "workstation_id": ws_id,
                        "from": target_loc,
                        "to": target_out,
                        "description": f"완충 작업대 {ws_id} 회수 → 포장존({target_out}) 이동",
                        "workstation_qr_id": ws_qr
                    }
                else:
                    # 내일/모레 분류 라인 -> 창고(warehouse)로 이송
                    # 빈 창고 스팟 배정
                    cursor.execute("SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;")
                    empty_spot_row = cursor.fetchone()
                    target_spot = empty_spot_row[0] if empty_spot_row else "warehouse"
                    
                    if empty_spot_row:
                        cursor.execute(
                            "UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;",
                            (ws_id, target_spot)
                        )
                    
                    cursor.execute(
                        "UPDATE packages SET status = 'IN_WAREHOUSE' WHERE workstation_id = %s AND status = 'IN_WORKSTATION';",
                        (ws_id,)
                    )
                    cursor.execute(
                        "UPDATE workstations SET current_location = %s WHERE workstation_id = %s;",
                        (target_spot, ws_id)
                    )
                    
                    task_retrieve = {
                        "task_type": "RETRIEVE_FULL_WORKSTATION",
                        "workstation_id": ws_id,
                        "from": target_loc,
                        "to": target_spot,
                        "description": f"완충 작업대 {ws_id} 회수 → 창고 {target_spot} 입고",
                        "workstation_qr_id": ws_qr
                    }
                
                push_priority_task(redis_client, task_retrieve)
                
                # B구역에 대기 중인 작업대가 있다면 A구역으로 승격시키고 DEPLOY 태스크 발행
                cursor.execute("SELECT workstation_id, qr_id FROM workstations WHERE current_location = %s LIMIT 1;", (f"{target_robot}_B",))
                b_ws_row = cursor.fetchone()
                if b_ws_row:
                    b_ws_id, b_ws_qr = b_ws_row
                    b_ws_qr = b_ws_qr if b_ws_qr else ""
                    
                    cursor.execute("UPDATE workstations SET current_location = %s WHERE workstation_id = %s;", (target_loc, b_ws_id))
                    
                    task_deploy = {
                        "task_type": "DEPLOY_EMPTY_WORKSTATION",
                        "workstation_id": b_ws_id,
                        "from": f"{target_robot}_B",
                        "to": target_loc,
                        "description": f"대기 작업대 {b_ws_id} 배치 → {target_loc} (승격)",
                        "workstation_qr_id": b_ws_qr
                    }
                    push_priority_task(redis_client, task_deploy)
                else:
                    # B구역에 없다면 창고에서 직접 가져오기
                    cursor.execute("""
                        SELECT w.workstation_id, w.current_location, w.qr_id
                        FROM workstations w
                        WHERE w.current_location LIKE 'spot_%%'
                        AND w.workstation_id NOT IN (
                            SELECT DISTINCT workstation_id FROM packages
                            WHERE workstation_id IS NOT NULL AND status IN ('IN_WORKSTATION', 'IN_WAREHOUSE')
                        ) LIMIT 1;
                    """)
                    new_ws_row = cursor.fetchone()
                    if new_ws_row:
                        new_ws_id, new_ws_loc, new_ws_qr = new_ws_row
                        new_ws_qr = new_ws_qr if new_ws_qr else ""
                        
                        cursor.execute("UPDATE workstations SET current_location = %s WHERE workstation_id = %s;", (target_loc, new_ws_id))
                        cursor.execute("UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;", (new_ws_loc,))
                        
                        task_deploy = {
                            "task_type": "DEPLOY_EMPTY_WORKSTATION",
                            "workstation_id": new_ws_id,
                            "from": new_ws_loc,
                            "to": target_loc,
                            "description": f"새 빈 작업대 {new_ws_id} 배치 → {target_loc} (창고 직송)",
                            "workstation_qr_id": new_ws_qr
                        }
                        push_priority_task(redis_client, task_deploy)
                
                swap_triggered = True

        pg_conn.close()
        msg = f"상자 {pkg_id}를 {target_robot} 라인의 작업대 {ws_id} {slot_num}번 슬롯에 적재했습니다."
        if lookahead_triggered:
            msg += " (★ Look-ahead 예비 작업대 호출 트리거 발동!)"
        if rotation_triggered:
            msg += " (🔄 180도 회전 태스크 발행 및 로봇 대기 적용!)"
        if swap_triggered:
            msg += " (🔄 완충! 작업대 교체 수행: 회수 + 새 작업대 배치 완료)"
            
        return {"success": True, "message": msg}
    except Exception as e:
        if pg_conn:
            pg_conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simulate_packaging")
def simulate_packaging():
    """포장 시뮬레이션: 포장존(sg2_out_00_A)에 있는 작업대의 패키지를 하나씩 포장 완료 처리"""
    pg_conn, redis_client = get_db_connections()
    if not pg_conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with pg_conn.cursor() as cursor:
            # 오늘 출고 대상 날짜 동적 조회 (미완료 패키지 중 가장 오래된 날짜)
            cursor.execute("SELECT DISTINCT route_zone FROM packages WHERE status != 'COMPLETED' ORDER BY route_zone;")
            active_dates = [r[0] for r in cursor.fetchall()]
            today_date = active_dates[0] if active_dates else datetime.now().strftime('%Y-%m-%d')

            # 1. 활성 포장 구역(sg2_out_00_A)에 위치한 작업대 찾기
            cursor.execute("SELECT workstation_id, qr_id FROM workstations WHERE current_location = 'sg2_out_00_A' LIMIT 1;")
            ws_row = cursor.fetchone()
            
            if not ws_row:
                # 1-1. 포장 대기 구역(sg2_out_00_B)에 작업대가 있으면 A구역으로 승격 배치
                cursor.execute("SELECT workstation_id, qr_id FROM workstations WHERE current_location = 'sg2_out_00_B' LIMIT 1;")
                b_ws_row = cursor.fetchone()
                if b_ws_row:
                    ws_id, ws_qr = b_ws_row
                    ws_qr = ws_qr if ws_qr else ""
                    
                    cursor.execute("UPDATE workstations SET current_location = 'sg2_out_00_A' WHERE workstation_id = %s;", (ws_id,))
                    
                    # 대기 작업대가 활성화되었으므로 패키지들의 상태를 IN_WORKSTATION으로 전환
                    cursor.execute(
                        "UPDATE packages SET status = 'IN_WORKSTATION' WHERE workstation_id = %s AND status = 'IN_WAREHOUSE';",
                        (ws_id,)
                    )
                    
                    if redis_client:
                        task_deploy = {
                            "task_type": "DEPLOY_PACKAGING_WORKSTATION",
                            "workstation_id": ws_id,
                            "from": "sg2_out_00_B",
                            "to": "sg2_out_00_A",
                            "description": f"대기 작업대 {ws_id} 배치 → sg2_out_00_A (승격)",
                            "workstation_qr_id": ws_qr
                        }
                        push_priority_task(redis_client, task_deploy)
                        
                    pg_conn.close()
                    return {"success": True, "message": f"대기 중이던 작업대 {ws_id}를 활성 포장존(sg2_out_00_A)으로 승격 배치했습니다."}
                
                # 1-2. 포장 구역(A/B)에 작업대가 아예 없으면, 창고에서 완충된 작업대를 가져옴 (오늘 날짜 물량만)
                cursor.execute("""
                    SELECT DISTINCT w.workstation_id, w.current_location, w.qr_id
                    FROM workstations w
                    JOIN packages p ON w.workstation_id = p.workstation_id
                    WHERE p.status = 'IN_WAREHOUSE' AND p.route_zone = %s
                    LIMIT 1;
                """, (today_date,))
                warehouse_ws = cursor.fetchone()
                if not warehouse_ws:
                    pg_conn.close()
                    return {"success": False, "message": "포장할 작업대가 없습니다. 먼저 적재 시뮬레이션으로 작업대를 완충시켜 주세요."}
                
                ws_id, ws_loc, ws_qr = warehouse_ws
                ws_qr = ws_qr if ws_qr else ""
                
                # 창고 스팟 비우기
                if ws_loc.startswith('spot_'):
                    cursor.execute(
                        "UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;",
                        (ws_loc,)
                    )
                
                # 작업대를 활성 포장 구역(sg2_out_00_A)으로 즉시 이동
                cursor.execute("UPDATE workstations SET current_location = 'sg2_out_00_A' WHERE workstation_id = %s;", (ws_id,))
                
                # 패키지 상태를 IN_WORKSTATION으로 복원 (포장 대기 상태)
                cursor.execute(
                    "UPDATE packages SET status = 'IN_WORKSTATION' WHERE workstation_id = %s AND status = 'IN_WAREHOUSE';",
                    (ws_id,)
                )
                
                if redis_client:
                    task_fetch = {
                        "task_type": "FETCH_FOR_PACKAGING",
                        "workstation_id": ws_id,
                        "from": ws_loc,
                        "to": "sg2_out_00_A",
                        "description": f"포장용 작업대 {ws_id} 호출 → sg2_out_00_A",
                        "workstation_qr_id": ws_qr
                    }
                    push_priority_task(redis_client, task_fetch)
                
                pg_conn.close()
                return {"success": True, "message": f"작업대 {ws_id}를 창고({ws_loc})에서 활성 포장존(sg2_out_00_A)으로 이송했습니다."}
            
            ws_id, ws_qr = ws_row
            ws_qr = ws_qr if ws_qr else ""
            
            # 2. 해당 작업대에서 아직 포장 안 된(IN_WORKSTATION) 패키지 하나 선택
            cursor.execute("""
                SELECT package_id, slot_number, customer_name
                FROM packages
                WHERE workstation_id = %s AND status = 'IN_WORKSTATION'
                ORDER BY slot_number ASC
                LIMIT 1;
            """, (ws_id,))
            pkg_row = cursor.fetchone()
            
            if not pkg_row:
                pg_conn.close()
                return {"success": False, "message": f"작업대 {ws_id}에 포장할 패키지가 없습니다."}
            
            pkg_id, slot_num, cust_name = pkg_row
            
            # 3. 포장 완료 처리: 출고 ID 생성 및 상태 COMPLETED로 변경
            from datetime import datetime
            outbound_id = f"sg2_out_00_{ws_id}-{slot_num}-{datetime.now().strftime('%Y%m%d%H%M')}"
            cursor.execute("""
                UPDATE packages
                SET status = 'COMPLETED', outbound_id = %s
                WHERE package_id = %s;
            """, (outbound_id, pkg_id))
            
            # 4. 포장 완료된 슬롯 수 계산
            cursor.execute("""
                SELECT COUNT(*) FROM packages
                WHERE workstation_id = %s AND status = 'COMPLETED';
            """, (ws_id,))
            completed_count = cursor.fetchone()[0]
            
            # 5. 남은 미포장 패키지 수 확인
            cursor.execute("""
                SELECT COUNT(*) FROM packages
                WHERE workstation_id = %s AND status = 'IN_WORKSTATION';
            """, (ws_id,))
            remaining_count = cursor.fetchone()[0]
            
            # 6. 7번째 포장 완료 시 → Look-ahead: 다음 포장 대기 작업대 사전 호출 (B구역 대기존으로)
            lookahead_triggered = False
            if completed_count == 7 and redis_client:
                # 창고에 오늘 물량의 IN_WAREHOUSE 패키지가 있는 작업대 조회
                cursor.execute("""
                    SELECT DISTINCT w.workstation_id, w.current_location, w.qr_id
                    FROM workstations w
                    JOIN packages p ON w.workstation_id = p.workstation_id
                    WHERE p.status = 'IN_WAREHOUSE' AND p.route_zone = %s
                    AND w.workstation_id != %s
                    LIMIT 1;
                """, (today_date, ws_id))
                next_ws_row = cursor.fetchone()
                
                if next_ws_row:
                    next_ws_id, next_ws_loc, next_ws_qr = next_ws_row
                    next_ws_qr = next_ws_qr if next_ws_qr else ""
                    
                    # B구역에 대기중이거나 이동중인 작업대가 없을 때만 호출
                    cursor.execute("""
                        SELECT COUNT(*) FROM workstations 
                        WHERE current_location = 'sg2_out_00_B' OR current_location = 'MOVING_TO_SG2_OUT_00_B';
                    """)
                    b_occupy_count = cursor.fetchone()[0]
                    
                    if b_occupy_count == 0:
                        task_data = {
                            "task_type": "PRE_FETCH_PACKAGING_WORKSTATION",
                            "workstation_id": next_ws_id,
                            "from": next_ws_loc,
                            "to": "sg2_out_00_B",
                            "description": f"Look-ahead: {ws_id} 7번째 포장 완료 → 대기 작업대 {next_ws_id} 사전 호출",
                            "workstation_qr_id": next_ws_qr
                        }
                        push_priority_task(redis_client, task_data)
                        lookahead_triggered = True
            
            # 7. 8번째(마지막) 포장 완료 시 → 작업대 교체: 빈 작업대 회수 + 다음 작업대 배치 (승격 또는 직접배치)
            swap_triggered = False
            if remaining_count == 0 and redis_client:
                # 7-1. 포장 완료된 빈 작업대를 창고로 회수
                cursor.execute("SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;")
                empty_spot_row = cursor.fetchone()
                target_spot = empty_spot_row[0] if empty_spot_row else "warehouse"
                
                if empty_spot_row:
                    cursor.execute(
                        "UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;",
                        (ws_id, target_spot)
                    )
                
                # 패키지의 workstation 매핑 해제 (포장 완료 후 작업대에서 분리)
                cursor.execute(
                    "UPDATE packages SET workstation_id = NULL, slot_number = NULL WHERE workstation_id = %s AND status = 'COMPLETED';",
                    (ws_id,)
                )
                cursor.execute(
                    "UPDATE workstations SET current_location = %s WHERE workstation_id = %s;",
                    (target_spot, ws_id)
                )
                
                task_retrieve = {
                    "task_type": "RETRIEVE_EMPTY_WORKSTATION",
                    "workstation_id": ws_id,
                    "from": "sg2_out_00_A",
                    "to": target_spot,
                    "description": f"포장 완료 빈 작업대 {ws_id} 회수 → {target_spot}",
                    "workstation_qr_id": ws_qr
                }
                push_priority_task(redis_client, task_retrieve)
                
                # 7-2. B구역에 대기 중인 작업대가 있다면 A구역으로 즉시 승격 및 DEPLOY 태스크 발행
                cursor.execute("SELECT workstation_id, qr_id FROM workstations WHERE current_location = 'sg2_out_00_B' LIMIT 1;")
                b_ws_row = cursor.fetchone()
                if b_ws_row:
                    b_ws_id, b_ws_qr = b_ws_row
                    b_ws_qr = b_ws_qr if b_ws_qr else ""
                    
                    cursor.execute("UPDATE workstations SET current_location = 'sg2_out_00_A' WHERE workstation_id = %s;", (b_ws_id,))
                    cursor.execute(
                        "UPDATE packages SET status = 'IN_WORKSTATION' WHERE workstation_id = %s AND status = 'IN_WAREHOUSE';",
                        (b_ws_id,)
                    )
                    
                    task_deploy = {
                        "task_type": "DEPLOY_PACKAGING_WORKSTATION",
                        "workstation_id": b_ws_id,
                        "from": "sg2_out_00_B",
                        "to": "sg2_out_00_A",
                        "description": f"대기 작업대 {b_ws_id} 배치 → sg2_out_00_A (승격)",
                        "workstation_qr_id": b_ws_qr
                    }
                    push_priority_task(redis_client, task_deploy)
                else:
                    # B구역에 없다면 창고에서 직접 가져오기 (오늘 물량만)
                    cursor.execute("""
                        SELECT DISTINCT w.workstation_id, w.current_location, w.qr_id
                        FROM workstations w
                        JOIN packages p ON w.workstation_id = p.workstation_id
                        WHERE p.status = 'IN_WAREHOUSE' AND p.route_zone = %s
                        AND w.workstation_id != %s
                        LIMIT 1;
                    """, (today_date, ws_id))
                    next_ws_row = cursor.fetchone()
                    
                    if next_ws_row:
                        next_ws_id, next_ws_loc, next_ws_qr = next_ws_row
                        next_ws_qr = next_ws_qr if next_ws_qr else ""
                        
                        # 창고 스팟 비우기
                        if next_ws_loc.startswith('spot_'):
                            cursor.execute(
                                "UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;",
                                (next_ws_loc,)
                            )
                        
                        # 작업대를 포장존 A로 이동 + 패키지 상태 복원
                        cursor.execute("UPDATE workstations SET current_location = 'sg2_out_00_A' WHERE workstation_id = %s;", (next_ws_id,))
                        cursor.execute(
                            "UPDATE packages SET status = 'IN_WORKSTATION' WHERE workstation_id = %s AND status = 'IN_WAREHOUSE';",
                            (next_ws_id,)
                        )
                        
                        task_deploy = {
                            "task_type": "DEPLOY_PACKAGING_WORKSTATION",
                            "workstation_id": next_ws_id,
                            "from": next_ws_loc,
                            "to": "sg2_out_00_A",
                            "description": f"다음 포장 작업대 {next_ws_id} 배치 → sg2_out_00_A (교체)",
                            "workstation_qr_id": next_ws_qr
                        }
                        push_priority_task(redis_client, task_deploy)
                
                swap_triggered = True
        
        pg_conn.close()
        msg = f"📦 {pkg_id} (슬롯 {slot_num}, {cust_name}) 포장 완료! 출고ID: {outbound_id} [{completed_count}/8]"
        if lookahead_triggered:
            msg += " (★ Look-ahead: 다음 포장 작업대 사전 호출!)"
        if swap_triggered:
            msg += " (🔄 전체 포장 완료! 작업대 교체: 빈 작업대 회수 + 새 작업대 배치)"
        
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

        .btn-upload {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            color: #10b981;
        }

        .btn-upload:hover {
            background: #10b981;
            color: #000;
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.2);
            transform: translateY(-2px);
        }

        /* Grid sections */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 2rem;
            margin-bottom: 2rem;
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
            grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
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
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
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
            flex-direction: column;
            align-items: flex-start;
            margin-bottom: 12px;
            gap: 6px;
        }

        .ws-id {
            font-size: 1.25rem;
            font-weight: 800;
            color: #fff;
            letter-spacing: -0.5px;
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
            <button class="btn-packaging" onclick="simulatePackaging()" style="background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%); border: none; color: #000; box-shadow: 0 4px 15px rgba(245, 158, 11, 0.25);">
                <span>📦</span> 시뮬레이션 포장 수행
            </button>
            <button class="btn-upload" onclick="triggerCSVUpload()">
                <span>📥</span> CSV 입고 명단 업로드
            </button>
            <input type="file" accept=".csv" id="csv-file-input" style="display:none" onchange="uploadCSV()">
            <button class="btn-reset" onclick="resetDatabase()">
                <span>🔄</span> 데이터베이스 초기화
            </button>
        </div>

        <!-- Warehouse 2D Live Grid Map -->
        <div class="panel-card" style="margin-bottom: 2rem;">
            <h2>Warehouse 2D Live Grid Map (바둑판식 실시간 맵) <span style="font-size: 0.8rem; color: var(--text-muted); font-weight: normal; margin-left: 10px;">1.5m 격자 및 실시간 작업대 위치 시각화</span></h2>
            <div style="position: relative; width: 100%; height: 350px; background: rgba(10, 15, 30, 0.9); border-radius: 12px; overflow: hidden; border: 1px solid var(--border-color);">
                <canvas id="map-canvas" style="display: block; width: 100%; height: 100%;"></canvas>
            </div>
            <div style="display: flex; gap: 20px; margin-top: 10px; font-size: 0.8rem; color: var(--text-muted); justify-content: center; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="display: inline-block; width: 12px; height: 12px; border: 1.5px solid rgba(0, 242, 254, 0.4); background: rgba(0, 242, 254, 0.05); border-radius: 2px;"></span>
                    <span>작업대 주차 구역 (Parking)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="display: inline-block; width: 12px; height: 12px; border: 1.5px solid rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.05); border-radius: 2px;"></span>
                    <span>인바운드 적재 (Inbound A/B)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="display: inline-block; width: 12px; height: 12px; border: 1.5px solid rgba(245, 158, 11, 0.4); background: rgba(245, 158, 11, 0.05); border-radius: 2px;"></span>
                    <span>아웃바운드 포장 (Outbound A/B)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="display: inline-block; width: 12px; height: 12px; background: #00f2fe; border-radius: 50%; box-shadow: 0 0 8px #00f2fe;"></span>
                    <span>실시간 작업대 (Workstation)</span>
                </div>
            </div>
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

        // 2D Live Grid Map State & Logic
        let locationsData = null;
        let workstationsData = [];
        const wsPositions = {}; // Smoothly interpolated workstation positions

        function initCanvas() {
            const canvas = document.getElementById('map-canvas');
            if (!canvas) return;
            
            function resize() {
                canvas.width = canvas.clientWidth * window.devicePixelRatio;
                canvas.height = canvas.clientHeight * window.devicePixelRatio;
                drawMap();
            }
            window.addEventListener('resize', resize);
            resize();
            
            // Start rendering animation loop (60 FPS interpolation)
            function animate() {
                drawMap();
                requestAnimationFrame(animate);
            }
            requestAnimationFrame(animate);
        }

        function drawMap() {
            const canvas = document.getElementById('map-canvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // Coordinate range boundaries based on warehouse.yaml
            const minX = -40;
            const maxX = 40;
            const minY = -40;
            const maxY = 30;
            
            function toCanvas(x, y) {
                const cx = ((x - minX) / (maxX - minX)) * canvas.width;
                const cy = canvas.height - ((y - minY) / (maxY - minY)) * canvas.height;
                return { x: cx, y: cy };
            }
            
            // 1. Draw Checkerboard Grid (바둑판)
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.035)';
            ctx.lineWidth = 1;
            
            // Vertical grid lines (every 1.5m)
            for (let x = -38.0; x <= 38.0; x += 1.5) {
                const p1 = toCanvas(x, -36.08);
                const p2 = toCanvas(x, 25.0);
                ctx.beginPath();
                ctx.moveTo(p1.x, p1.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.stroke();
            }
            // Horizontal grid lines (every 1.5m)
            for (let y = -36.08; y <= 25.0; y += 1.5) {
                const p1 = toCanvas(-38.0, y);
                const p2 = toCanvas(38.0, y);
                ctx.beginPath();
                ctx.moveTo(p1.x, p1.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.stroke();
            }
            
            // Outer boundaries of warehouse
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
            ctx.lineWidth = 2;
            const borderLeftTop = toCanvas(-38.0, 25.0);
            const borderRightBottom = toCanvas(38.0, -36.08);
            ctx.beginPath();
            ctx.rect(borderLeftTop.x, borderLeftTop.y, borderRightBottom.x - borderLeftTop.x, borderRightBottom.y - borderLeftTop.y);
            ctx.stroke();
            
            if (!locationsData) return;
            
            // 2. Draw logical spots
            for (const [name, loc] of Object.entries(locationsData)) {
                const cp = toCanvas(loc.x, loc.y);
                let color = 'rgba(255, 255, 255, 0.2)';
                let bg = 'rgba(255, 255, 255, 0.01)';
                
                if (loc.type === 'PARKING_SPOT') {
                    color = 'rgba(0, 242, 254, 0.4)';
                    bg = 'rgba(0, 242, 254, 0.03)';
                } else if (loc.type === 'LOADING_SPOT' || loc.type === 'STANDBY_SPOT') {
                    color = 'rgba(16, 185, 129, 0.4)';
                    bg = 'rgba(16, 185, 129, 0.03)';
                } else if (loc.type === 'PACKAGING_SPOT') {
                    color = 'rgba(245, 158, 11, 0.4)';
                    bg = 'rgba(245, 158, 11, 0.03)';
                }
                
                const size = Math.max(8, canvas.width * 0.012);
                ctx.strokeStyle = color;
                ctx.fillStyle = bg;
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.rect(cp.x - size/2, cp.y - size/2, size, size);
                ctx.fill();
                ctx.stroke();
                
                // Label text
                ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
                ctx.font = `${Math.max(7, canvas.width * 0.009)}px Outfit`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'top';
                
                let label = name;
                if (name.startsWith('spot_')) label = 'S' + name.substring(5);
                else if (name.startsWith('sg2_in_')) {
                    const parts = name.split('_');
                    label = 'I' + parseInt(parts[2]) + parts[3];
                } else if (name.startsWith('sg2_out_')) {
                    const parts = name.split('_');
                    label = 'O' + parts[3];
                }
                ctx.fillText(label, cp.x, cp.y + size/2 + 2);
            }
            
            // 3. Draw Workstations (with LERP interpolation)
            const norm_locs = {};
            for (const [key, val] of Object.entries(locationsData)) {
                norm_locs[key.toUpperCase()] = val;
            }
            
            workstationsData.forEach(ws => {
                let targetKey = ws.current_location.toUpperCase();
                let isMoving = false;
                
                if (targetKey.startsWith('MOVING_TO_')) {
                    targetKey = targetKey.replace('MOVING_TO_', '');
                    isMoving = true;
                } else if (targetKey.endsWith('_ROTATING')) {
                    targetKey = targetKey.replace('_ROTATING', '');
                }
                
                const targetCoords = norm_locs[targetKey];
                if (!targetCoords) return;
                
                if (!wsPositions[ws.workstation_id]) {
                    wsPositions[ws.workstation_id] = { x: targetCoords.x, y: targetCoords.y };
                } else {
                    const pos = wsPositions[ws.workstation_id];
                    pos.x += (targetCoords.x - pos.x) * 0.08;
                    pos.y += (targetCoords.y - pos.y) * 0.08;
                }
                
                const currentPos = wsPositions[ws.workstation_id];
                const cp = toCanvas(currentPos.x, currentPos.y);
                
                if (isMoving) {
                    ctx.strokeStyle = 'rgba(0, 242, 254, 0.15)';
                    ctx.lineWidth = 1.5;
                    ctx.setLineDash([4, 4]);
                    const destCp = toCanvas(targetCoords.x, targetCoords.y);
                    ctx.beginPath();
                    ctx.moveTo(cp.x, cp.y);
                    ctx.lineTo(destCp.x, destCp.y);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }
                
                const radius = Math.max(6, canvas.width * 0.009);
                
                ctx.shadowColor = '#00f2fe';
                ctx.shadowBlur = isMoving ? 18 : 8;
                ctx.fillStyle = '#00f2fe';
                ctx.beginPath();
                ctx.arc(cp.x, cp.y, radius, 0, 2 * Math.PI);
                ctx.fill();
                ctx.shadowBlur = 0;
                
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 1.5;
                ctx.stroke();
                
                ctx.fillStyle = '#090d16';
                ctx.beginPath();
                ctx.arc(cp.x, cp.y, radius * 0.4, 0, 2 * Math.PI);
                ctx.fill();
                
                ctx.fillStyle = '#ffffff';
                ctx.font = `bold ${Math.max(8, canvas.width * 0.01)}px Outfit`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'bottom';
                ctx.fillText(ws.workstation_id, cp.x, cp.y - radius - 3);
            });
        }

        // Initialize map canvas after DOM load
        setTimeout(initCanvas, 100);

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

        // 1-2. 모의 포장 이벤트 트리거
        async function simulatePackaging() {
            try {
                const response = await fetch('/api/simulate_packaging', { method: 'POST' });
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

        function triggerCSVUpload() {
            document.getElementById('csv-file-input').click();
        }

        async function uploadCSV() {
            const fileInput = document.getElementById('csv-file-input');
            if (fileInput.files.length === 0) return;

            const file = fileInput.files[0];
            const reader = new FileReader();

            reader.onload = async function(e) {
                const textContent = e.target.result;
                showToast("⏳ CSV 파일을 업로드하는 중...");

                try {
                    const response = await fetch('/api/upload_packages', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'text/plain; charset=utf-8'
                        },
                        body: textContent
                    });
                    const data = await response.json();
                    if (response.ok && data.success) {
                        showToast("✅ " + data.message);
                        fetchStatus();
                    } else {
                        showToast("❌ 업로드 실패: " + (data.detail || data.message || "알 수 없는 오류"));
                    }
                } catch (err) {
                    showToast("❌ API 통신 오류 발생");
                } finally {
                    fileInput.value = "";
                }
            };

            reader.readAsText(file);
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

                // Update global data for map canvas
                locationsData = data.locations;
                workstationsData = data.workstations;

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
                            <span class="ws-id">${ws.workstation_id}</span>
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
                        
                        const score = task.priority_score || 0;
                        let badgeBg = 'rgba(255,255,255,0.1)';
                        let badgeColor = 'var(--text-muted)';
                        if (score >= 90) {
                            badgeBg = 'rgba(239, 68, 68, 0.2)';
                            badgeColor = '#ef4444';
                        } else if (score >= 80) {
                            badgeBg = 'rgba(245, 158, 11, 0.2)';
                            badgeColor = '#f59e0b';
                        } else if (score >= 50) {
                            badgeBg = 'rgba(59, 130, 246, 0.2)';
                            badgeColor = '#3b82f6';
                        }

                        item.innerHTML = `
                            <div>
                                <div class="task-name" style="display: flex; align-items: center; gap: 6px;">
                                    ${task.task_type || 'TASK'}
                                    <span style="font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; background: ${badgeBg}; color: ${badgeColor}; font-weight: 700;">
                                        P-${score}
                                    </span>
                                </div>
                                <div class="task-desc">${task.description || ''}</div>
                            </div>
                            <div style="font-size: 0.72rem; color: var(--text-muted); text-align: right;">
                                <div>QR: ${task.workstation_qr_id || 'N/A'}</div>
                                <div style="font-size: 0.55rem; opacity: 0.7; margin-top: 2px;">UUID: ${task.uuid ? task.uuid.substring(0, 8) : 'N/A'}</div>
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


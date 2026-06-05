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

        # Day transition 상태 조회
        day_status = 'RUNNING'
        completed_day = ''
        if redis_client:
            try:
                val = redis_client.get('system:day_status')
                if val:
                    day_status = val.decode('utf-8')
                val_comp = redis_client.get('system:completed_day')
                if val_comp:
                    completed_day = val_comp.decode('utf-8')
            except Exception as e:
                print(f"Redis day status read error: {e}")

        pg_conn.close()
        return {
            "workstations": workstations,
            "spots": spots,
            "packages": packages,
            "redis_tasks": redis_tasks,
            "locations": locations,
            "day_status": day_status,
            "completed_day": completed_day
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

@app.post("/api/start_next_day")
def start_next_day():
    pg_conn, redis_client = get_db_connections()
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis connection failed")
    try:
        redis_client.set('system:day_status', 'RUNNING')
        redis_client.delete('system:completed_day')
        if pg_conn:
            pg_conn.close()
        return {"success": True, "message": "성공적으로 다음 영업일로 전환되었습니다."}
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
                        WHERE status IN ('IN_WORKSTATION', 'IN_WAREHOUSE') AND workstation_id IS NOT NULL
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
                    # 오늘 날짜 분류 라인 -> 포장존(sg2_out_00_A 또는 B) 또는 창고(warehouse)로 이송
                    cursor.execute("""
                        SELECT COUNT(*) FROM workstations 
                        WHERE current_location = 'sg2_out_00_A' OR current_location = 'MOVING_TO_SG2_OUT_00_A';
                    """)
                    out_a_count = cursor.fetchone()[0]

                    cursor.execute("""
                        SELECT COUNT(*) FROM workstations 
                        WHERE current_location = 'sg2_out_00_B' OR current_location = 'MOVING_TO_SG2_OUT_00_B';
                    """)
                    out_b_count = cursor.fetchone()[0]
                    
                    if out_a_count == 0:
                        target_out = 'sg2_out_00_A'
                    elif out_b_count == 0:
                        target_out = 'sg2_out_00_B'
                    else:
                        # 포장존이 모두 찬 경우 창고로 회수 보관
                        cursor.execute("BEGIN;")
                        cursor.execute("SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1 FOR UPDATE;")
                        empty_spot_row = cursor.fetchone()
                        target_out = empty_spot_row[0] if empty_spot_row else "warehouse"
                        
                        if empty_spot_row:
                            cursor.execute(
                                "UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;",
                                (ws_id, target_out)
                            )
                        cursor.execute("COMMIT;")
                        
                        cursor.execute(
                            "UPDATE packages SET status = 'IN_WAREHOUSE' WHERE workstation_id = %s AND status = 'IN_WORKSTATION';",
                            (ws_id,)
                        )

                    cursor.execute(
                        "UPDATE workstations SET current_location = %s WHERE workstation_id = %s;",
                        (target_out, ws_id)
                    )
                    task_retrieve = {
                        "task_type": "RETRIEVE_FULL_WORKSTATION",
                        "workstation_id": ws_id,
                        "from": target_loc,
                        "to": target_out,
                        "description": f"완충 작업대 {ws_id} 회수 → {target_out} 이동",
                        "workstation_qr_id": ws_qr
                    }
                else:
                    # 내일/모레 분류 라인 -> 창고(warehouse)로 이송
                    # 빈 창고 스팟 배정
                    cursor.execute("BEGIN;")
                    cursor.execute("SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1 FOR UPDATE;")
                    empty_spot_row = cursor.fetchone()
                    target_spot = empty_spot_row[0] if empty_spot_row else "warehouse"
                    
                    if empty_spot_row:
                        cursor.execute(
                            "UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;",
                            (ws_id, target_spot)
                        )
                    cursor.execute("COMMIT;")
                    
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
                cursor.execute("BEGIN;")
                cursor.execute("SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1 FOR UPDATE;")
                empty_spot_row = cursor.fetchone()
                target_spot = empty_spot_row[0] if empty_spot_row else "warehouse"
                
                if empty_spot_row:
                    cursor.execute(
                        "UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;",
                        (ws_id, target_spot)
                    )
                cursor.execute("COMMIT;")
                
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

        @keyframes pulse-border-orange {
            0%, 100% { border-color: rgba(245, 158, 11, 0.3); box-shadow: 0 8px 32px 0 rgba(245, 158, 11, 0.15); }
            50% { border-color: rgba(245, 158, 11, 0.8); box-shadow: 0 8px 32px 0 rgba(245, 158, 11, 0.35); }
        }

        @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-6px); }
        }

        /* === Floor Plan Styles === */
        .conveyor-line {
            background: rgba(16, 185, 129, 0.04);
            border: 1px solid rgba(16, 185, 129, 0.12);
            border-radius: 10px;
            padding: 8px 12px;
            transition: all 0.3s ease;
        }
        .conveyor-line:hover {
            border-color: rgba(16, 185, 129, 0.35);
            background: rgba(16, 185, 129, 0.08);
        }
        .conveyor-arrow {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .conveyor-label {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            background: linear-gradient(135deg, #10b981, #059669);
            color: #fff;
            font-weight: 800;
            font-size: 0.85rem;
            border-radius: 8px;
            flex-shrink: 0;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
        }
        .conveyor-bar {
            flex: 1;
            height: 4px;
            background: linear-gradient(90deg, rgba(16, 185, 129, 0.6), rgba(16, 185, 129, 0.15));
            border-radius: 2px;
            min-width: 30px;
        }
        .conveyor-line.right .conveyor-bar {
            background: linear-gradient(270deg, rgba(16, 185, 129, 0.6), rgba(16, 185, 129, 0.15));
        }
        .robot-dot {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            font-size: 0.55rem;
            font-weight: 800;
            flex-shrink: 0;
            cursor: default;
            transition: all 0.3s ease;
        }
        .robot-dot.sg2 {
            background: rgba(59, 130, 246, 0.8);
            color: #fff;
            box-shadow: 0 0 10px rgba(59, 130, 246, 0.4);
        }
        .robot-dot.sg2:hover {
            box-shadow: 0 0 18px rgba(59, 130, 246, 0.6);
            transform: scale(1.1);
        }
        .amr-dot {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 44px;
            height: 44px;
            border-radius: 50%;
            background: rgba(239, 68, 68, 0.7);
            color: #fff;
            font-size: 0.55rem;
            font-weight: 800;
            text-align: center;
            line-height: 1.2;
            box-shadow: 0 0 14px rgba(239, 68, 68, 0.35);
            cursor: default;
            transition: all 0.3s ease;
            animation: amr-idle 3s ease-in-out infinite;
        }
        .amr-dot:hover {
            box-shadow: 0 0 22px rgba(239, 68, 68, 0.6);
            transform: scale(1.1);
        }
        @keyframes amr-idle {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-3px); }
        }
        .ws-slot-mini {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 28px;
            border-radius: 5px;
            background: rgba(156, 163, 175, 0.15);
            border: 1.5px solid rgba(156, 163, 175, 0.35);
            color: rgba(156, 163, 175, 0.7);
            font-size: 0.7rem;
            font-weight: 700;
            flex-shrink: 0;
            transition: all 0.3s ease;
            cursor: default;
        }
        .ws-slot-mini.standby {
            border-style: dashed;
            opacity: 0.5;
        }
        .ws-slot-mini.occupied {
            background: rgba(0, 242, 254, 0.15);
            border-color: rgba(0, 242, 254, 0.5);
            color: #00f2fe;
            box-shadow: 0 0 8px rgba(0, 242, 254, 0.15);
        }
        .ws-slot-mini.occupied.standby {
            opacity: 0.8;
        }
        .ws-slot-mini.pack {
            background: rgba(245, 158, 11, 0.1);
            border-color: rgba(245, 158, 11, 0.35);
            color: rgba(245, 158, 11, 0.8);
        }
        .ws-slot-mini.pack.occupied {
            background: rgba(245, 158, 11, 0.2);
            border-color: rgba(245, 158, 11, 0.6);
            color: #f59e0b;
            box-shadow: 0 0 8px rgba(245, 158, 11, 0.2);
        }
        .packaging-zone {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            padding: 16px 28px;
            background: rgba(245, 158, 11, 0.04);
            border: 1px solid rgba(245, 158, 11, 0.15);
            border-radius: 14px;
            transition: all 0.3s ease;
        }
        .packaging-zone:hover {
            border-color: rgba(245, 158, 11, 0.35);
            background: rgba(245, 158, 11, 0.08);
        }
        .pack-header {
            font-size: 0.8rem;
            font-weight: 700;
            color: rgba(245, 158, 11, 0.8);
            letter-spacing: 1px;
        }
        .pack-arrow {
            font-size: 0.75rem;
            color: rgba(16, 185, 129, 0.6);
            font-weight: 700;
            animation: pack-pulse 2s ease-in-out infinite;
        }
        @keyframes pack-pulse {
            0%, 100% { opacity: 0.6; }
            50% { opacity: 1; }
        }
        .pack-robot {
            width: 28px !important;
            height: 28px !important;
        }
        .warehouse-spot-cell {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 6px 4px;
            border-radius: 8px;
            background: rgba(0, 242, 254, 0.03);
            border: 1px solid rgba(0, 242, 254, 0.12);
            text-align: center;
            transition: all 0.3s ease;
            min-height: 52px;
        }
        .warehouse-spot-cell.occupied {
            border-color: rgba(245, 158, 11, 0.35);
            background: rgba(245, 158, 11, 0.06);
        }
        .warehouse-spot-cell.empty {
            border-color: rgba(16, 185, 129, 0.2);
            background: rgba(16, 185, 129, 0.03);
        }
        .warehouse-spot-cell .spot-name {
            font-size: 0.55rem;
            color: var(--text-muted);
            font-weight: 600;
        }
        .warehouse-spot-cell .spot-ws-id {
            font-size: 0.75rem;
            font-weight: 800;
            color: #fff;
            margin: 2px 0;
        }
        .warehouse-spot-cell.empty .spot-ws-id {
            color: rgba(16, 185, 129, 0.5);
            font-size: 0.6rem;
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

        <!-- Day Transition Banner (Hidden by default) -->
        <div id="day-transition-banner" style="display: none; background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(239, 68, 68, 0.15) 100%); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 16px; padding: 20px; margin-bottom: 2rem; align-items: center; justify-content: space-between; backdrop-filter: blur(12px); box-shadow: 0 8px 32px 0 rgba(245, 158, 11, 0.15); animation: pulse-border-orange 2s infinite;">
            <div style="display: flex; align-items: center; gap: 16px;">
                <div style="font-size: 2.2rem; animation: bounce 2s infinite;">🎉</div>
                <div>
                    <h3 style="margin: 0; color: #fff; font-size: 1.15rem; font-weight: 700; display: flex; align-items: center; gap: 8px;">
                        오늘 영업일 운영 마감 완료! <span id="completed-day-badge" style="font-size: 0.75rem; background: #f59e0b; color: #000; padding: 2px 8px; border-radius: 9999px; font-weight: 800;">—</span>
                    </h3>
                    <p style="margin: 4px 0 0 0; color: var(--text-muted); font-size: 0.88rem;">오늘 물량의 모든 포장 공정이 성공적으로 종료되었습니다. 일자별 통계 보고서가 로컬 서버에 저장되었습니다. 다음 영업일의 물류 및 이송 처리를 승인하십시오.</p>
                </div>
            </div>
            <button onclick="startNextDay()" style="background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%); border: none; color: #000; font-weight: 800; padding: 14px 28px; border-radius: 12px; box-shadow: 0 4px 15px rgba(245, 158, 11, 0.4); display: flex; align-items: center; gap: 8px; font-size: 0.95rem; cursor: pointer; transition: all 0.3s ease;">
                <span>🚀</span> 다음 영업일 개시 (Next Day Transition)
            </button>
        </div>

        <!-- Warehouse 2D Live Grid Map -->
        <div class="panel-card" style="margin-bottom: 2rem;">
            <h2>Warehouse 2D Live Floor Plan <span style="font-size: 0.8rem; color: var(--text-muted); font-weight: normal; margin-left: 10px;">실시간 물류 창고 배치도 (49×37 격자, 1.5m 간격)</span></h2>
            <div id="floor-plan" style="position: relative; width: 100%; background: rgba(8, 12, 24, 0.95); border-radius: 16px; overflow: hidden; border: 1px solid var(--border-color); padding: 20px;">
                
                <!-- === 보관 창고 (Storage Area) (상단) === -->
                <div style="text-align: center; margin-bottom: 6px;">
                    <span style="font-size: 0.9rem; font-weight: 700; color: rgba(0, 242, 254, 0.75); letter-spacing: 4px;">◆ 보관 창고 (Storage Area) ◆</span>
                </div>
                <div id="warehouse-spots-map" style="display: grid; grid-template-columns: repeat(10, 1fr); gap: 6px; max-width: 700px; margin: 0 auto 12px auto; padding: 12px; background: rgba(0, 242, 254, 0.03); border: 1px solid rgba(0, 242, 254, 0.15); border-radius: 12px;">
                    <!-- Populated by JS -->
                </div>

                <!-- === 출고 대기 구역 (Staging Area) (중단) === -->
                <div style="text-align: center; margin-bottom: 6px; margin-top: 12px;">
                    <span style="font-size: 0.9rem; font-weight: 700; color: rgba(245, 158, 11, 0.75); letter-spacing: 4px;">◆ 출고 대기 구역 (Staging Area) ◆</span>
                </div>
                <div id="staging-spots-map" style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; max-width: 420px; margin: 0 auto 12px auto; padding: 12px; background: rgba(245, 158, 11, 0.03); border: 1px solid rgba(245, 158, 11, 0.15); border-radius: 12px;">
                    <!-- Populated by JS -->
                </div>

                <div style="border-top: 1px dashed rgba(255,255,255,0.1); margin: 10px 0;"></div>

                <!-- === 인바운드 적재 라인 (상단 세트) === -->
                <div style="display: flex; justify-content: space-between; align-items: stretch; margin: 16px 0; gap: 20px;">
                    <!-- 좌측 라인 세트 (←진입) -->
                    <div style="flex: 1; display: flex; flex-direction: column; gap: 8px;">
                        <div class="conveyor-line" id="line-left-1" data-robot="sg2_in_01">
                            <div class="conveyor-arrow" style="justify-content: flex-end;">
                                <span class="conveyor-label">1</span>
                                <span class="conveyor-bar"></span>
                                <span class="robot-dot sg2" title="sg2_in_01">SG2</span>
                                <div class="ws-slot-mini" id="ws-slot-sg2_in_01_A" title="A구역">A</div>
                                <div class="ws-slot-mini standby" id="ws-slot-sg2_in_01_B" title="B구역">B</div>
                            </div>
                        </div>
                        <div class="conveyor-line" id="line-left-2" data-robot="sg2_in_02">
                            <div class="conveyor-arrow" style="justify-content: flex-end;">
                                <span class="conveyor-label">2</span>
                                <span class="conveyor-bar"></span>
                                <span class="robot-dot sg2" title="sg2_in_02">SG2</span>
                                <div class="ws-slot-mini" id="ws-slot-sg2_in_02_A" title="A구역">A</div>
                                <div class="ws-slot-mini standby" id="ws-slot-sg2_in_02_B" title="B구역">B</div>
                            </div>
                        </div>
                        <div class="conveyor-line" id="line-left-3" data-robot="sg2_in_03">
                            <div class="conveyor-arrow" style="justify-content: flex-end;">
                                <span class="conveyor-label">3</span>
                                <span class="conveyor-bar"></span>
                                <span class="robot-dot sg2" title="sg2_in_03">SG2</span>
                                <div class="ws-slot-mini" id="ws-slot-sg2_in_03_A" title="A구역">A</div>
                                <div class="ws-slot-mini standby" id="ws-slot-sg2_in_03_B" title="B구역">B</div>
                            </div>
                        </div>
                    </div>

                    <!-- 중앙 AMR 영역 -->
                    <div style="flex: 1.2; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 14px; padding: 10px; background: rgba(255,255,255,0.015); border-radius: 12px; border: 1px dashed rgba(255,255,255,0.06);">
                        <span style="font-size: 0.7rem; color: rgba(255,255,255,0.3); letter-spacing: 2px;">AMR 주행 영역</span>
                        <div id="amr-area" style="display: flex; gap: 20px; flex-wrap: wrap; justify-content: center;">
                            <div class="amr-dot" title="AMR_01">AMR<br>01</div>
                            <div class="amr-dot" title="AMR_02">AMR<br>02</div>
                            <div class="amr-dot" title="AMR_03">AMR<br>03</div>
                            <div class="amr-dot" title="AMR_04">AMR<br>04</div>
                            <div class="amr-dot" title="AMR_05">AMR<br>05</div>
                        </div>
                        <!-- 바둑판 격자 미니맵 -->
                        <div style="font-size: 0.6rem; color: rgba(255,255,255,0.2);">49열 × 37행 = 1,813 QR격자</div>
                    </div>

                    <!-- 우측 라인 세트 (→진입) -->
                    <div style="flex: 1; display: flex; flex-direction: column; gap: 8px;">
                        <div class="conveyor-line right" id="line-right-1">
                            <div class="conveyor-arrow">
                                <div class="ws-slot-mini standby" title="B구역">B</div>
                                <div class="ws-slot-mini" title="A구역">A</div>
                                <span class="robot-dot sg2" title="sg2_in_01 (R)">SG2</span>
                                <span class="conveyor-bar"></span>
                                <span class="conveyor-label">1</span>
                            </div>
                        </div>
                        <div class="conveyor-line right" id="line-right-2">
                            <div class="conveyor-arrow">
                                <div class="ws-slot-mini standby" title="B구역">B</div>
                                <div class="ws-slot-mini" title="A구역">A</div>
                                <span class="robot-dot sg2" title="sg2_in_02 (R)">SG2</span>
                                <span class="conveyor-bar"></span>
                                <span class="conveyor-label">2</span>
                            </div>
                        </div>
                        <div class="conveyor-line right" id="line-right-3">
                            <div class="conveyor-arrow">
                                <div class="ws-slot-mini standby" title="B구역">B</div>
                                <div class="ws-slot-mini" title="A구역">A</div>
                                <span class="robot-dot sg2" title="sg2_in_03 (R)">SG2</span>
                                <span class="conveyor-bar"></span>
                                <span class="conveyor-label">3</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div style="border-top: 1px dashed rgba(255,255,255,0.1); margin: 10px 0;"></div>

                <!-- === 포장 라인 (하단) === -->
                <div style="display: flex; justify-content: center; gap: 40px; margin-top: 16px;">
                    <div class="packaging-zone" id="pack-zone-a">
                        <div class="pack-header">포장 라인 A</div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div class="ws-slot-mini pack" id="ws-slot-sg2_out_00_A" title="sg2_out_00_A 구역">A</div>
                            <span class="robot-dot sg2 pack-robot" title="sg2_out_00">SG2</span>
                        </div>
                        <div class="pack-arrow">▼ 출고</div>
                    </div>
                    <div class="packaging-zone" id="pack-zone-b">
                        <div class="pack-header">포장 라인 B</div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div class="ws-slot-mini pack standby" id="ws-slot-sg2_out_00_B" title="sg2_out_00_B 구역">B</div>
                            <span class="robot-dot sg2 pack-robot" title="sg2_out_00 (B)">SG2</span>
                        </div>
                        <div class="pack-arrow">▼ 출고</div>
                    </div>
                </div>
            </div>

            <!-- 범례 -->
            <div style="display: flex; gap: 20px; margin-top: 12px; font-size: 0.78rem; color: var(--text-muted); justify-content: center; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="display: inline-block; width: 14px; height: 14px; background: rgba(59, 130, 246, 0.8); border-radius: 50%;"></span>
                    <span>SG2 적재/포장 로봇</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="display: inline-block; width: 14px; height: 14px; background: rgba(239, 68, 68, 0.8); border-radius: 50%;"></span>
                    <span>AMR 이송 로봇</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="display: inline-block; width: 14px; height: 14px; background: rgba(156, 163, 175, 0.4); border: 1.5px solid rgba(156, 163, 175, 0.6); border-radius: 3px;"></span>
                    <span>작업대 칸 (A/B)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="display: inline-block; width: 14px; height: 6px; background: linear-gradient(90deg, #10b981, #10b981); border-radius: 2px;"></span>
                    <span>컨베이어 벨트 (1=첫째날, 2=둘째날, 3=셋째날)</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="display: inline-block; width: 14px; height: 14px; background: rgba(0, 242, 254, 0.15); border: 1.5px solid rgba(0, 242, 254, 0.4); border-radius: 3px;"></span>
                    <span>창고 주차 스팟</span>
                </div>
            </div>
        </div>

        <div class="dashboard-grid">
            <!-- Left: Warehouse Parking spots -->
            <div class="panel-card">
                <h2>Warehouse Parking Spots (10 Slots) <span style="font-size: 0.8rem; color: rgba(0, 242, 254, 0.7); font-weight: normal; margin-left: 10px;">spot_01 ~ spot_10 (보관 영역)</span></h2>
                <div class="spots-container" id="spots-list">
                    <!-- Dynamic spots go here -->
                </div>
            </div>

            <!-- Left 2: Outbound Staging spots -->
            <div class="panel-card">
                <h2>Outbound Staging Spots (6 Slots) <span style="font-size: 0.8rem; color: rgba(245, 158, 11, 0.7); font-weight: normal; margin-left: 10px;">stage_01 ~ stage_06 (출고 대기 영역)</span></h2>
                <div class="spots-container" id="staging-list">
                    <!-- Dynamic staging spots go here -->
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

        // 2D Floor Plan State & Update Logic
        let locationsData = null;
        let workstationsData = [];

        function updateFloorPlan(data) {
            // 1. Update warehouse parking spots and staging spots in the floor plan
            const spotsMap = document.getElementById('warehouse-spots-map');
            const stagingMap = document.getElementById('staging-spots-map');
            
            if (data.spots) {
                if (spotsMap) spotsMap.innerHTML = '';
                if (stagingMap) stagingMap.innerHTML = '';
                
                data.spots.forEach(spot => {
                    const isOcc = spot.status === 'OCCUPIED';
                    const cell = document.createElement('div');
                    cell.className = `warehouse-spot-cell ${isOcc ? 'occupied' : 'empty'}`;
                    cell.innerHTML = `
                        <div class="spot-name">${spot.spot_id.toUpperCase()}</div>
                        <div class="spot-ws-id">${spot.workstation_id || '—'}</div>
                    `;
                    
                    if (spot.spot_id.startsWith('spot_')) {
                        if (spotsMap) spotsMap.appendChild(cell);
                    } else if (spot.spot_id.startsWith('stage_')) {
                        if (stagingMap) stagingMap.appendChild(cell);
                    }
                });
            }

            // 2. Update conveyor line workstation A/B slots
            if (data.workstations) {
                // Build a map: location -> workstation info
                const locWsMap = {};
                data.workstations.forEach(ws => {
                    const loc = ws.current_location.toLowerCase();
                    locWsMap[loc] = ws;
                    // Also handle MOVING_TO and ROTATING states
                    if (loc.startsWith('moving_to_')) {
                        const target = loc.replace('moving_to_', '');
                        if (!locWsMap[target]) locWsMap[target] = ws;
                    }
                    if (loc.endsWith('_rotating')) {
                        const target = loc.replace('_rotating', '');
                        if (!locWsMap[target]) locWsMap[target] = ws;
                    }
                });

                // Inbound slots (sg2_in_01_A/B through sg2_in_03_A/B)
                const inboundSlots = [
                    'sg2_in_01_a', 'sg2_in_01_b',
                    'sg2_in_02_a', 'sg2_in_02_b',
                    'sg2_in_03_a', 'sg2_in_03_b',
                ];
                inboundSlots.forEach(slotKey => {
                    const el = document.getElementById(`ws-slot-${slotKey.replace(/_a$/, '_A').replace(/_b$/, '_B')}`);
                    if (!el) return;
                    const ws = locWsMap[slotKey];
                    if (ws) {
                        el.classList.add('occupied');
                        el.title = `${ws.workstation_id} @ ${ws.current_location}`;
                        const filledCount = ws.slots.filter(s => s.status === 'FULL').length;
                        el.textContent = `${ws.workstation_id.replace('WS','')}`;
                    } else {
                        el.classList.remove('occupied');
                        el.title = slotKey.includes('_b') ? 'B구역 (대기)' : 'A구역 (활성)';
                        el.textContent = slotKey.includes('_b') ? 'B' : 'A';
                    }
                });

                // Outbound packing slots
                const outboundSlots = ['sg2_out_00_a', 'sg2_out_00_b'];
                outboundSlots.forEach(slotKey => {
                    const el = document.getElementById(`ws-slot-${slotKey.replace(/_a$/, '_A').replace(/_b$/, '_B')}`);
                    if (!el) return;
                    const ws = locWsMap[slotKey];
                    if (ws) {
                        el.classList.add('occupied');
                        el.title = `${ws.workstation_id} @ ${ws.current_location}`;
                        el.textContent = `${ws.workstation_id.replace('WS','')}`;
                    } else {
                        el.classList.remove('occupied');
                        el.title = slotKey.includes('_b') ? 'B구역 (대기)' : 'A구역 (활성)';
                        el.textContent = slotKey.includes('_b') ? 'B' : 'A';
                    }
                });
            }
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

        // 1.5. 다음 영업일 개시 트리거
        async function startNextDay() {
            try {
                const response = await fetch('/api/start_next_day', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    showToast("🚀 " + data.message);
                    fetchStatus();
                } else {
                    showToast("❌ 개시 실패: " + data.message);
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

                // Update global data for map canvas
                locationsData = data.locations;
                workstationsData = data.workstations;

                // Update the 2D floor plan
                updateFloorPlan(data);

                // Update day transition banner visibility
                const banner = document.getElementById('day-transition-banner');
                if (banner) {
                    if (data.day_status === 'PENDING_TRANSITION') {
                        banner.style.display = 'flex';
                        const badge = document.getElementById('completed-day-badge');
                        if (badge) badge.innerText = data.completed_day || '—';
                    } else {
                        banner.style.display = 'none';
                    }
                }

                // 3-1. Render Warehouse spots & Staging spots
                const spotsContainer = document.getElementById('spots-list');
                const stagingContainer = document.getElementById('staging-list');
                
                if (spotsContainer) spotsContainer.innerHTML = '';
                if (stagingContainer) stagingContainer.innerHTML = '';
                
                data.spots.forEach(spot => {
                    const isOccupied = spot.status === 'OCCUPIED';
                    const item = document.createElement('div');
                    item.className = `spot-item ${isOccupied ? 'occupied' : 'empty'}`;
                    item.innerHTML = `
                        <div class="spot-id">${spot.spot_id.toUpperCase()}</div>
                        <div class="spot-ws">${spot.workstation_id || '—'}</div>
                        <div class="spot-status-badge">${isOccupied ? 'OCCUPIED' : 'EMPTY'}</div>
                    `;
                    
                    if (spot.spot_id.startsWith('spot_')) {
                        if (spotsContainer) spotsContainer.appendChild(item);
                    } else if (spot.spot_id.startsWith('stage_')) {
                        if (stagingContainer) stagingContainer.appendChild(item);
                    }
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
    uvicorn.run("dashboard_server:app", host="0.0.0.0", port=8009, reload=True)


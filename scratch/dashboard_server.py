#!/usr/bin/env python3
import os
import psycopg2
import redis
import json
import csv
import io
import asyncio
import re
from datetime import datetime, timedelta
from typing import List

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from psycopg2 import pool

# ----------------------------------------------------
# 1. 웹소켓 커넥션 매니저 클래스
# ----------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()
app = FastAPI(title="Coupang Warehouse Control Panel")

# DB 정적 데이터 캐시 (서버 시작 후 1회만 쿼리하여 부하 감소)
_grid_cells_cache = None
_locations_cache = None

db_pool = None
global_redis = None

def normalize_qr_id(qr_id: str) -> str:
    if not qr_id or not qr_id.startswith("FLOOR_X_"):
        return qr_id
    try:
        match = re.match(r"FLOOR_X_(-?\d+\.?\d*)_Y_(-?\d+\.?\d*)", qr_id)
        if match:
            x_val = float(match.group(1))
            y_val = float(match.group(2))
            return f"FLOOR_X_{x_val:.1f}_Y_{y_val:.1f}"
    except Exception:
        pass
    return qr_id

def get_db_connections():
    global db_pool, global_redis
    if db_pool is None:
        try:
            db_pool = pool.ThreadedConnectionPool(1, 20, host='localhost', port=5432, user='rokey', password='rokey_pass', database='warehouse_db')
        except Exception as e:
            print(f"DB Pool Error: {e}")
            
    if global_redis is None:
        try:
            global_redis = redis.Redis(host='localhost', port=6379, decode_responses=True)
        except Exception as e:
            print(f"Redis Error: {e}")
            
    pg_conn = None
    if db_pool:
        try:
            pg_conn = db_pool.getconn()
            pg_conn.autocommit = True
        except Exception as e:
            print(f"Get Conn Error: {e}")
    return pg_conn, global_redis

def release_db_connection(pg_conn):
    global db_pool
    if db_pool and pg_conn:
        try:
            db_pool.putconn(pg_conn)
        except:
            pass

def get_active_dates(redis_client):
    today_date = redis_client.get('system:today_date')
    if not today_date:
        today_date = '2026-06-06'
        redis_client.set('system:today_date', today_date)
    try:
        t_dt = datetime.strptime(today_date, '%Y-%m-%d')
    except ValueError:
        try:
            t_dt = datetime.strptime(today_date, '%Y%m%d')
            today_date = t_dt.strftime('%Y-%m-%d')
            redis_client.set('system:today_date', today_date)
        except Exception:
            today_date = '2026-06-06'
            t_dt = datetime.strptime(today_date, '%Y-%m-%d')
            redis_client.set('system:today_date', today_date)
    tomorrow_dt = t_dt + timedelta(days=1)
    day_after_dt = t_dt + timedelta(days=2)
    return today_date, tomorrow_dt.strftime('%Y-%m-%d'), day_after_dt.strftime('%Y-%m-%d')

def get_task_priority(task_type):
    """태스크 종류별 우선순위 점수 반환"""
    if task_type in ['DIRECT_WAREHOUSE', 'RETRIEVE_FULL_WORKSTATION', 'ROTATE_WORKSTATION', 'PRE_FETCH_WORKSTATION']:
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
            cursor.execute("SELECT spot_id, workstation_id, status FROM warehouse_locations ORDER BY spot_id;")
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
            global _locations_cache
            if _locations_cache is None:
                cursor.execute("""
                    SELECT qr_id, location_name, x_coord, y_coord, location_type 
                    FROM floor_qr_map 
                    WHERE location_name IS NOT NULL;
                """)
                _locations_cache = {}
                for qr, loc_name, x, y, loc_type in cursor.fetchall():
                    _locations_cache[loc_name] = {"x": x, "y": y, "type": loc_type, "qr_id": qr}
            locations = _locations_cache
                
        # 4. Redis Active Queue Tasks (Sorted Set)
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
                if "WRONGTYPE" in str(e):
                    redis_client.delete('queue:amr_tasks')
                print(f"Redis Queue Query Error: {re}")

        # Day transition 상태 조회
        day_status = 'RUNNING'
        completed_day = ''
        if redis_client:
            try:
                val = redis_client.get('system:day_status')
                if val:
                    day_status = val if isinstance(val, str) else val.decode('utf-8')
                val_comp = redis_client.get('system:completed_day')
                if val_comp:
                    completed_day = val_comp if isinstance(val_comp, str) else val_comp.decode('utf-8')
            except Exception as e:
                print(f"Redis day status read error: {e}")

        # AMR 상태 조회 추가
        amr_states = {}
        if redis_client:
            try:
                keys = redis_client.keys("amr:*")
                for key in keys:
                    parts = key.split(":")
                    if len(parts) > 1:
                        amr_id = parts[1]
                        val = redis_client.hgetall(key)
                        if val:
                            amr_states[amr_id] = {
                                "state": val.get("state", "IDLE"),
                                "current_qr_id": normalize_qr_id(val.get("current_qr_id", "")),
                                "target_qr_id": normalize_qr_id(val.get("target_qr_id", "")),
                                "carrying_workstation_id": val.get("carrying_workstation_id", "") or "",
                                "battery": val.get("battery", "100.0")
                            }
            except Exception as e:
                print(f"AMR query error: {e}")

        if not amr_states:
            moving_ws = [w for w in workstations if w["current_location"].lower().startswith("moving_to_") or w["current_location"].lower().endswith("_rotating")]
            for idx, ws in enumerate(moving_ws):
                amr_name = f"AMR_{idx+1:02d}"
                amr_states[amr_name] = {
                    "state": "BUSY",
                    "current_qr_id": ws["current_location"],
                    "target_qr_id": "",
                    "carrying_workstation_id": ws["workstation_id"],
                    "battery": "95"
                }
            if "AMR_01" not in amr_states:
                amr_states["AMR_01"] = {
                    "state": "IDLE",
                    "current_qr_id": "QR_0030",
                    "target_qr_id": "",
                    "carrying_workstation_id": "",
                    "battery": "88"
                }
            if "AMR_02" not in amr_states:
                amr_states["AMR_02"] = {
                    "state": "IDLE",
                    "current_qr_id": "QR_0031",
                    "target_qr_id": "",
                    "carrying_workstation_id": "",
                    "battery": "91"
                }

        # grid_cells 캐시 활용
        global _grid_cells_cache
        if _grid_cells_cache is None:
            try:
                with pg_conn.cursor() as cursor:
                    cursor.execute("SELECT qr_id, x_coord, y_coord, location_name, location_type FROM floor_qr_map;")
                    _grid_cells_cache = []
                    for qr, x, y, loc_name, loc_type in cursor.fetchall():
                        _grid_cells_cache.append({
                            "qr_id": qr,
                            "x": x,
                            "y": y,
                            "location_name": loc_name or "",
                            "location_type": loc_type or ""
                        })
                    print(f"Grid cells cached: {len(_grid_cells_cache)} cells")
            except Exception as ge:
                print(f"Grid query error: {ge}")
                _grid_cells_cache = []
        grid_cells = _grid_cells_cache

        device_status = {
            "bg2": True, "sg2_in_01": True, "sg2_in_02": True, "sg2_in_03": True, "sg2_out_00": True, "amr": False
        }
        if redis_client:
            try:
                amr_keys = redis_client.keys("amr:*")
                device_status["amr"] = len([k for k in amr_keys if k != "queue:amr_tasks"]) > 0
            except Exception as de:
                print(f"Device status check error: {de}")

        release_db_connection(pg_conn)
        return {
            "workstations": workstations, "spots": spots, "packages": packages,
            "redis_tasks": redis_tasks, "locations": locations, "day_status": day_status,
            "completed_day": completed_day, "amr_states": amr_states, "grid_cells": grid_cells,
            "device_status": device_status
        }
    except Exception as e:
        if pg_conn:
            release_db_connection(pg_conn)
        raise HTTPException(status_code=500, detail=str(e))

async def status_broadcast_loop():
    while True:
        if manager.active_connections:
            try:
                loop = asyncio.get_event_loop()
                status_data = await loop.run_in_executor(None, get_status)
                # 대역폭 절약을 위해 grid_cells는 브로드캐스트에서 제외
                broadcast_data = {k: v for k, v in status_data.items() if k != 'grid_cells'}
                await manager.broadcast(broadcast_data)
            except Exception as e:
                print(f"Broadcast loop error: {e}")
        await asyncio.sleep(1.5)

# 서버 시작 시 실시간 브로드캐스트 비동기 루프 구동
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(status_broadcast_loop())

# 웹소켓 라우트 핸들러 정상 정의
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        loop = asyncio.get_event_loop()
        status_data = await loop.run_in_executor(None, get_status)
        await websocket.send_json(status_data)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

@app.post("/api/upload_packages")
async def upload_packages(request: Request):
    try:
        content_bytes = await request.body()
        content = content_bytes.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        
        required_fields = ['package_id', 'customer_name', 'route_zone']
        if not csv_reader.fieldnames or not all(field in csv_reader.fieldnames for field in required_fields):
            raise HTTPException(status_code=400, detail=f"CSV file must contain columns: {', '.join(required_fields)}")
        
        pg_conn, redis_client = get_db_connections()
        if not pg_conn:
            raise HTTPException(status_code=500, detail="Database connection failed.")
            
        if redis_client:
            redis_client.set('system:inbound_started', 'true')
            
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
                    DO UPDATE SET customer_name = EXCLUDED.customer_name, route_zone = EXCLUDED.route_zone, status = EXCLUDED.status, qr_id = EXCLUDED.qr_id;
                """, (pkg_id, cust_name, route_zone, status, qr_id))
                success_count += 1
                
        release_db_connection(pg_conn)
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
        import subprocess
        import sys
        ws_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        reset_script = os.path.join(ws_root, "scratch", "reset_db.py")
        result = subprocess.run([sys.executable, reset_script], cwd=ws_root, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise Exception(f"reset_db.py 실행 실패: {result.stderr}")

        if redis_client:
            redis_client.set('system:today_date', '2026-06-06')
            redis_client.set('system:day_status', 'WAITING_FOR_START')

        global _grid_cells_cache
        _grid_cells_cache = None
            
        release_db_connection(pg_conn)
        return {"success": True, "message": "데이터베이스와 바닥 QR 격자 맵이 성공적으로 초기화 및 복구되었습니다."}
    except Exception as e:
        if pg_conn:
            release_db_connection(pg_conn)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/start_next_day")
def start_next_day():
    pg_conn, redis_client = get_db_connections()
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis connection failed")
    try:
        today_date = redis_client.get('system:today_date')
        if not today_date:
            today_date = '2026-06-06'
        try:
            t_dt = datetime.strptime(today_date, '%Y-%m-%d')
        except ValueError:
            t_dt = datetime.strptime(today_date, '%Y%m%d')
        next_date = (t_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        redis_client.set('system:today_date', next_date)
        
        shift_count = 0
        if pg_conn:
            with pg_conn.cursor() as cursor:
                cursor.execute("""
                    SELECT workstation_id, current_location, qr_id FROM workstations
                    WHERE (current_location ILIKE '%sg2_in_01%' OR current_location ILIKE '%sg2_in_02%' OR current_location ILIKE '%sg2_in_03%')
                      AND workstation_id NOT IN (
                          SELECT DISTINCT workstation_id FROM packages WHERE status IN ('IN_WORKSTATION', 'IN_WAREHOUSE') AND workstation_id IS NOT NULL
                      );
                """)
                empty_ws_to_return = cursor.fetchall()
                for ws_id, curr_loc, qr_id in empty_ws_to_return:
                    cursor.execute("SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' AND spot_id LIKE 'spot_%%' ORDER BY spot_id ASC LIMIT 1;")
                    spot_row = cursor.fetchone()
                    if not spot_row:
                        cursor.execute("SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' AND spot_id LIKE 'stage_%%' ORDER BY spot_id ASC LIMIT 1;")
                        spot_row = cursor.fetchone()
                    if spot_row:
                        target_spot = spot_row[0]
                        cursor.execute("UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;", (ws_id, target_spot))
                        
                        task_data = {
                            "task_type": "PRE_FETCH_WORKSTATION", "workstation_id": ws_id, "from": curr_loc, "to": target_spot,
                            "description": f"영업일 전환: 빈 작업대 반납 ({curr_loc} ➡️ {target_spot})", "workstation_qr_id": qr_id if qr_id else ""
                        }
                        push_priority_task(redis_client, task_data)
                        shift_count += 1

                cursor.execute("SELECT workstation_id, current_location, qr_id FROM workstations WHERE current_location ILIKE '%sg2_in_02%' OR current_location ILIKE '%sg2_in_03%';")
                ws_rows = cursor.fetchall()
                for ws_id, curr_loc, qr_id in ws_rows:
                    ws_qr = qr_id if qr_id else ""
                    target_loc = None
                    
                    if "sg2_in_02" in curr_loc: target_loc = curr_loc.replace("sg2_in_02", "sg2_in_01")
                    elif "SG2_IN_02" in curr_loc: target_loc = curr_loc.replace("SG2_IN_02", "SG2_IN_01")
                    elif "sg2_in_03" in curr_loc: target_loc = curr_loc.replace("sg2_in_03", "sg2_in_02")
                    elif "SG2_IN_03" in curr_loc: target_loc = curr_loc.replace("SG2_IN_03", "SG2_IN_02")
                    
                    if target_loc:
                        task_data = {
                            "task_type": "PRE_FETCH_WORKSTATION", "workstation_id": ws_id, "from": curr_loc, "to": target_loc,
                            "description": f"영업일 전환 (대안 A): {ws_id} ({curr_loc} ➡️ {target_loc})", "workstation_qr_id": ws_qr
                        }
                        push_priority_task(redis_client, task_data)
                        shift_count += 1

        redis_client.set('system:day_status', 'WAITING_FOR_START')
        redis_client.delete('system:completed_day')
        redis_client.set('system:inbound_started', 'false')
        
        if pg_conn:
            release_db_connection(pg_conn)
            
        msg = f"성공적으로 다음 영업일({next_date})로 전환되었습니다."
        if shift_count > 0:
            msg += f" (작업대 {shift_count}개 물리 이송 태스크 발행 완료)"
        return {"success": True, "message": msg}
    except Exception as e:
        if pg_conn:
            release_db_connection(pg_conn)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/start_business")
def start_business():
    pg_conn, redis_client = get_db_connections()
    if not redis_client:
        raise HTTPException(status_code=500, detail="Redis connection failed")
    try:
        today_date = redis_client.get('system:today_date')
        if not today_date:
            today_date = '2026-06-06'

        has_packages = False
        if pg_conn:
            with pg_conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM packages WHERE status = 'WAITING';")
                count = cursor.fetchone()[0]
                has_packages = count > 0
            release_db_connection(pg_conn)

        if not has_packages:
            return {"success": False, "message": "오늘 분류할 대기 패키지가 존재하지 않습니다. 먼저 CSV 입고 명단을 업로드해 주세요."}

        redis_client.set('system:day_status', 'RUNNING')
        redis_client.set('system:inbound_started', 'true')
        
        return {"success": True, "message": f"성공적으로 영업일({today_date})의 분류 및 이송 작업을 개시했습니다!"}
    except Exception as e:
        if pg_conn:
            release_db_connection(pg_conn)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/simulate")
def simulate_inbound():
    pg_conn, redis_client = get_db_connections()
    if not pg_conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    try:
        with pg_conn.cursor() as cursor:
            cursor.execute("SELECT package_id, customer_name, route_zone, qr_id FROM packages WHERE status = 'WAITING' LIMIT 1;")
            pkg_row = cursor.fetchone()
            if not pkg_row:
                release_db_connection(pg_conn)
                return {"success": False, "message": "더 이상 적재할 대기 패키지가 없습니다."}
            
            pkg_id, cust_name, zone, pkg_qr = pkg_row
            today_date, tomorrow_date, day_after_date = get_active_dates(redis_client)

            if zone == today_date: target_robot = 'sg2_in_01'
            elif zone == tomorrow_date: target_robot = 'sg2_in_02'
            elif zone == day_after_date: target_robot = 'sg2_in_03'
            else: target_robot = 'sg2_in_01'

            target_loc = f"{target_robot}_A"
            
            loc_a, loc_a_rot, loc_a_mov = f"{target_robot}_A", f"{target_robot}_A_ROTATING", f"MOVING_TO_{target_robot.upper()}_A"
            
            cursor.execute("""
                SELECT workstation_id, current_location FROM workstations 
                WHERE current_location IN (%s, %s, %s)
                ORDER BY CASE current_location
                    WHEN %s THEN 1 WHEN %s THEN 2 WHEN %s THEN 3 ELSE 4
                END LIMIT 1;
            """, (loc_a, loc_a_rot, loc_a_mov, loc_a, loc_a_rot, loc_a_mov))
            ws_row = cursor.fetchone()
            if ws_row:
                ws_id = ws_row[0]
            else:
                cursor.execute("""
                    SELECT workstation_id, current_location FROM workstations 
                    WHERE current_location LIKE 'spot_%%'
                    AND workstation_id NOT IN (
                        SELECT DISTINCT workstation_id FROM packages WHERE status IN ('IN_WORKSTATION', 'IN_WAREHOUSE') AND workstation_id IS NOT NULL
                    ) LIMIT 1;
                """)
                empty_ws_row = cursor.fetchone()
                if empty_ws_row:
                    ws_id, current_loc = empty_ws_row
                    cursor.execute("UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;", (current_loc,))
                    cursor.execute("SELECT qr_id FROM workstations WHERE workstation_id = %s;", (ws_id,))
                    ws_qr = cursor.fetchone()[0] or ""
                    task_deploy = {
                        "task_type": "DEPLOY_EMPTY_WORKSTATION", "workstation_id": ws_id, "from": current_loc, "to": target_loc,
                        "description": f"인바운드 호출: 빈 작업대 {ws_id} 배치 → {target_loc} (창고 직송)", "workstation_qr_id": ws_qr
                    }
                    push_priority_task(redis_client, task_deploy)
                else:
                    release_db_connection(pg_conn)
                    return {"success": False, "message": f"{target_robot}_A 에 배치할 빈 작업대가 없습니다."}

            cursor.execute("SELECT slot_number FROM packages WHERE workstation_id = %s AND status = 'IN_WORKSTATION';", (ws_id,))
            filled_slots = {r[0] for r in cursor.fetchall()}
            
            slot_num = None
            for s in range(1, 9):
                if s not in filled_slots:
                    slot_num = s
                    break
            
            if slot_num is None:
                release_db_connection(pg_conn)
                return {"success": False, "message": f"작업대 {ws_id}의 모든 슬롯이 찼습니다!"}
                
            cursor.execute("UPDATE packages SET status = 'IN_WORKSTATION', workstation_id = %s, slot_number = %s WHERE package_id = %s;", (ws_id, slot_num, pkg_id))
            
            lookahead_triggered = False

            rotation_triggered = False
            if slot_num == 4 and redis_client:
                cursor.execute("SELECT qr_id FROM workstations WHERE workstation_id = %s;", (ws_id,))
                ws_qr = cursor.fetchone()[0]
                task_data = {
                    "task_type": "ROTATE_WORKSTATION", "workstation_id": ws_id, "from": f"{target_robot}_A_ROTATING", "to": target_loc,
                    "description": f"제자리 회전: {ws_id} 4번째 슬롯 적재 완료 → 180도 회전", "workstation_qr_id": ws_qr
                }
                push_priority_task(redis_client, task_data)
                rotation_triggered = True
            
            swap_triggered = False
            if slot_num == 8 and redis_client:
                cursor.execute("SELECT qr_id FROM workstations WHERE workstation_id = %s;", (ws_id,))
                ws_qr = cursor.fetchone()[0] or ""
                
                if target_robot == 'sg2_in_01':
                    cursor.execute("SELECT COUNT(*) FROM workstations WHERE current_location = 'sg2_out_00_A' OR current_location = 'MOVING_TO_SG2_OUT_00_A';")
                    if cursor.fetchone()[0] == 0: target_out = 'sg2_out_00_A'
                    else:
                        cursor.execute("SELECT spot_id FROM warehouse_locations WHERE spot_id LIKE 'stage_%%' AND status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;")
                        row = cursor.fetchone()
                        target_out = row[0] if row else "staging"
                        if row: cursor.execute("UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;", (ws_id, target_out))
                        cursor.execute("UPDATE packages SET status = 'IN_WAREHOUSE' WHERE workstation_id = %s AND status = 'IN_WORKSTATION';", (ws_id,))
                else:
                    prefix = 'stage_%%' if target_robot == 'sg2_in_02' else 'spot_%%'
                    cursor.execute(f"SELECT spot_id FROM warehouse_locations WHERE spot_id LIKE '{prefix}' AND status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;")
                    row = cursor.fetchone()
                    target_out = row[0] if row else "warehouse"
                    if row: cursor.execute("UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;", (ws_id, target_out))
                    cursor.execute("UPDATE packages SET status = 'IN_WAREHOUSE' WHERE workstation_id = %s AND status = 'IN_WORKSTATION';", (ws_id,))

                task_retrieve = {
                    "task_type": "RETRIEVE_FULL_WORKSTATION", "workstation_id": ws_id, "from": target_loc, "to": target_out,
                    "description": f"완충 작업대 {ws_id} 회수 → {target_out} 이동", "workstation_qr_id": ws_qr
                }
                push_priority_task(redis_client, task_retrieve)
                
                cursor.execute("SELECT workstation_id, current_location, qr_id FROM workstations WHERE current_location LIKE 'spot_%%' AND workstation_id NOT IN (SELECT DISTINCT workstation_id FROM packages WHERE workstation_id IS NOT NULL AND status IN ('IN_WORKSTATION', 'IN_WAREHOUSE')) LIMIT 1;")
                new_row = cursor.fetchone()
                if new_row:
                    cursor.execute("UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;", (new_row[1],))
                    task_deploy = {
                        "task_type": "DEPLOY_EMPTY_WORKSTATION", "workstation_id": new_row[0], "from": new_row[1], "to": target_loc,
                        "description": f"새 빈 작업대 {new_row[0]} 배치 → {target_loc} (창고 직송)", "workstation_qr_id": new_row[2] or ""
                    }
                    push_priority_task(redis_client, task_deploy)
                swap_triggered = True

        release_db_connection(pg_conn)
        msg = f"상자 {pkg_id}를 {target_robot} 라인의 작업대 {ws_id} {slot_num}번 슬롯에 적재했습니다."
        if lookahead_triggered: msg += " (★ Look-ahead 예비 작업대 호출 트리거 발동!)"
        if rotation_triggered: msg += " (🔄 180도 회전 태스크 발행 및 로봇 대기 적용!)"
        if swap_triggered: msg += " (🔄 완충! 작업대 교체 수행 완료)"
        return {"success": True, "message": msg}
    except Exception as e:
        if pg_conn: release_db_connection(pg_conn)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/simulate_packaging")
def simulate_packaging():
    pg_conn, redis_client = get_db_connections()
    if not pg_conn: raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        with pg_conn.cursor() as cursor:
            today_date = get_active_dates(redis_client)[0]
            cursor.execute("SELECT workstation_id, qr_id FROM workstations WHERE current_location = 'sg2_out_00_A' LIMIT 1;")
            ws_row = cursor.fetchone()
            
            if not ws_row:
                cursor.execute("SELECT workstation_id, qr_id FROM workstations WHERE current_location = 'sg2_out_00_B' LIMIT 1;")
                b_ws_row = cursor.fetchone()
                if b_ws_row:
                    ws_id, ws_qr = b_ws_row
                    cursor.execute("UPDATE packages SET status = 'IN_WORKSTATION' WHERE workstation_id = %s AND status = 'IN_WAREHOUSE';", (ws_id,))
                    if redis_client:
                        push_priority_task(redis_client, {"task_type": "DEPLOY_PACKAGING_WORKSTATION", "workstation_id": ws_id, "from": "sg2_out_00_B", "to": "sg2_out_00_A", "description": f"대기 작업대 {ws_id} 배치 → sg2_out_00_A (승격)", "workstation_qr_id": ws_qr or ""})
                    release_db_connection(pg_conn)
                    return {"success": True, "message": f"대기 작업대 {ws_id}를 활성 포장존(sg2_out_00_A)으로 승격 배치했습니다."}
                
                cursor.execute("SELECT w.workstation_id, w.current_location, w.qr_id FROM workstations w WHERE w.workstation_id IN (SELECT DISTINCT p.workstation_id FROM packages p WHERE p.status = 'IN_WAREHOUSE' AND p.route_zone = %s) ORDER BY CASE WHEN w.current_location LIKE 'stage_%%' THEN 0 ELSE 1 END ASC, w.current_location ASC LIMIT 1;", (today_date,))
                wh_row = cursor.fetchone()
                if not wh_row:
                    release_db_connection(pg_conn)
                    return {"success": False, "message": "포장할 작업대가 없습니다."}
                
                ws_id, ws_loc, ws_qr = wh_row
                if ws_loc.startswith('spot_') or ws_loc.startswith('stage_'):
                    cursor.execute("UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;", (ws_loc,))
                cursor.execute("UPDATE packages SET status = 'IN_WORKSTATION' WHERE workstation_id = %s AND status = 'IN_WAREHOUSE';", (ws_id,))
                if redis_client:
                    push_priority_task(redis_client, {"task_type": "FETCH_FOR_PACKAGING", "workstation_id": ws_id, "from": ws_loc, "to": "sg2_out_00_A", "description": f"포장용 작업대 {ws_id} 호출 → sg2_out_00_A", "workstation_qr_id": ws_qr or ""})
                release_db_connection(pg_conn)
                return {"success": True, "message": f"작업대 {ws_id}를 창고({ws_loc})에서 활성 포장존(sg2_out_00_A)으로 이송했습니다."}
            
            ws_id, ws_qr = ws_row
            cursor.execute("SELECT package_id, slot_number, customer_name FROM packages WHERE workstation_id = %s AND status = 'IN_WORKSTATION' ORDER BY slot_number ASC LIMIT 1;", (ws_id,))
            pkg_row = cursor.fetchone()
            if not pkg_row:
                release_db_connection(pg_conn)
                return {"success": False, "message": f"작업대 {ws_id}에 포장할 패키지가 없습니다."}
            
            pkg_id, slot_num, cust_name = pkg_row
            outbound_id = f"sg2_out_00_{ws_id}-{slot_num}-{datetime.now().strftime('%Y%m%d%H%M')}"
            cursor.execute("UPDATE packages SET status = 'COMPLETED', outbound_id = %s WHERE package_id = %s;", (outbound_id, pkg_id))
            
            cursor.execute("SELECT COUNT(*) FROM packages WHERE workstation_id = %s AND status = 'COMPLETED';", (ws_id,))
            completed_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM packages WHERE workstation_id = %s AND status = 'IN_WORKSTATION';", (ws_id,))
            remaining_count = cursor.fetchone()[0]
            
            # Event-Driven Redis counter system 적용
            if redis_client:
                try:
                    comp_count = redis_client.incrby('system:today_completed_count', 1)
                    total_str = redis_client.get('system:today_total_packages')
                    if not total_str or int(total_str) == 0:
                        cursor.execute("SELECT COUNT(*) FROM packages WHERE route_zone = %s;", (today_date,))
                        total_count = cursor.fetchone()[0]
                        redis_client.set('system:today_total_packages', total_count)
                    else:
                        total_count = int(total_str)
                    
                    if total_count > 0 and comp_count >= total_count:
                        redis_client.set('system:day_status', 'PENDING_TRANSITION')
                        redis_client.set('system:completed_day', today_date)
                except Exception as redis_err:
                    print(f"Redis EOD Check error in dashboard: {redis_err}")

            lookahead_triggered = False
            
            swap_triggered = False
            if remaining_count == 0 and redis_client:
                cursor.execute("SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;")
                spot_row = cursor.fetchone()
                target_spot = spot_row[0] if spot_row else "warehouse"
                if spot_row: cursor.execute("UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;", (ws_id, target_spot))
                cursor.execute("UPDATE packages SET workstation_id = NULL, slot_number = NULL WHERE workstation_id = %s AND status = 'COMPLETED';", (ws_id,))
                
                push_priority_task(redis_client, {"task_type": "RETRIEVE_EMPTY_WORKSTATION", "workstation_id": ws_id, "from": "sg2_out_00_A", "to": target_spot, "description": f"포장 완료 빈 작업대 {ws_id} 회수 → {target_spot}", "workstation_qr_id": ws_qr or ""})
                
                cursor.execute("SELECT w.workstation_id, w.current_location, w.qr_id FROM workstations w WHERE w.workstation_id IN (SELECT DISTINCT p.workstation_id FROM packages p WHERE p.status = 'IN_WAREHOUSE' AND p.route_zone = %s) AND w.workstation_id != %s LIMIT 1;", (today_date, ws_id))
                next_row = cursor.fetchone()
                if next_row:
                    if next_row[1].startswith('spot_'): cursor.execute("UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;", (next_row[1],))
                    cursor.execute("UPDATE packages SET status = 'IN_WORKSTATION' WHERE workstation_id = %s AND status = 'IN_WAREHOUSE';", (next_row[0],))
                    push_priority_task(redis_client, {"task_type": "DEPLOY_PACKAGING_WORKSTATION", "workstation_id": next_row[0], "from": next_row[1], "to": "sg2_out_00_A", "description": f"다음 포장 작업대 {next_row[0]} 배치 → sg2_out_00_A (교체)", "workstation_qr_id": next_row[2] or ""})
                swap_triggered = True
        
        release_db_connection(pg_conn)
        msg = f"📦 {pkg_id} (슬롯 {slot_num}, {cust_name}) 포장 완료! [{completed_count}/8]"
        if lookahead_triggered: msg += " (★ Look-ahead: 다음 포장 작업대 사전 호출!)"
        if swap_triggered: msg += " (🔄 전체 포장 완료! 작업대 교체 수행)"
        return {"success": True, "message": msg}
    except Exception as e:
        if pg_conn: release_db_connection(pg_conn)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>Coupang Control Center Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19; --card-bg: rgba(22, 28, 45, 0.6); --border-color: rgba(255, 255, 255, 0.08);
            --primary: #00f2fe; --secondary: #4facfe; --success: #10b981; --warning: #f59e0b; --danger: #ef4444; --text: #e2e8f0; --text-muted: #64748b;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Outfit', sans-serif; }
        body { background-color: var(--bg-color); color: var(--text); overflow-x: hidden; background-image: radial-gradient(circle at 10% 20%, rgba(0, 242, 254, 0.05) 0%, transparent 40%), radial-gradient(circle at 90% 80%, rgba(79, 172, 254, 0.05) 0%, transparent 40%); background-attachment: fixed; }
        .container { max-width: 1440px; margin: 0 auto; padding: 2rem; }
        header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 2rem; border-bottom: 1px solid var(--border-color); margin-bottom: 2rem; }
        .logo-section h1 { font-size: 1.8rem; font-weight: 800; background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .logo-section p { font-size: 0.9rem; color: var(--text-muted); margin-top: 2px; }
        .status-badge { display: flex; align-items: center; gap: 8px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.2); color: var(--success); padding: 8px 16px; border-radius: 9999px; font-weight: 600; font-size: 0.85rem; }
        .status-badge .dot { width: 8px; height: 8px; background-color: var(--success); border-radius: 50%; box-shadow: 0 0 10px var(--success); animation: pulse 2s infinite; }
        .controls { display: flex; gap: 12px; margin-bottom: 2rem; }
        button { padding: 12px 24px; border-radius: 12px; font-weight: 600; font-size: 0.9rem; cursor: pointer; transition: all 0.3s ease; display: flex; align-items: center; gap: 8px; }
        .btn-simulate { background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%); border: none; color: #000; box-shadow: 0 4px 15px rgba(0, 242, 254, 0.25); }
        .btn-simulate:hover { transform: translateY(-2px); }
        .btn-reset { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); color: var(--danger); }
        .btn-reset:hover { background: var(--danger); color: #fff; transform: translateY(-2px); }
        .btn-upload { background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.2); color: #10b981; }
        .btn-upload:hover { background: #10b981; color: #000; transform: translateY(-2px); }
        .dashboard-grid { display: grid; grid-template-columns: 1fr; gap: 2rem; margin-bottom: 2rem; }
        .panel-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 20px; padding: 1.5rem; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3); }
        .panel-card h2 { font-size: 1.25rem; font-weight: 700; margin-bottom: 1.25rem; border-left: 4px solid var(--primary); padding-left: 10px; color: #fff; }
        .spots-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 12px; }
        .spot-item { background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-color); border-radius: 14px; padding: 12px; text-align: center; }
        .spot-item.occupied { border-color: rgba(245, 158, 11, 0.3); background: rgba(245, 158, 11, 0.05); }
        .spot-item.empty { border-color: rgba(16, 185, 129, 0.3); background: rgba(16, 185, 129, 0.05); }
        .spot-id { font-size: 0.75rem; color: var(--text-muted); font-weight: 600; }
        .spot-ws { font-size: 1.1rem; font-weight: 700; margin: 6px 0; }
        .spot-status-badge { display: inline-block; font-size: 0.65rem; font-weight: 700; padding: 2px 8px; border-radius: 9999px; }
        .spot-item.occupied .spot-status-badge { background: rgba(245, 158, 11, 0.15); color: var(--warning); }
        .spot-item.empty .spot-status-badge { background: rgba(16, 185, 129, 0.15); color: var(--success); }
        .workstations-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; }
        .ws-card { background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-color); border-radius: 16px; padding: 14px; }
        .ws-header { display: flex; flex-direction: column; margin-bottom: 12px; }
        .ws-id { font-size: 1.25rem; font-weight: 800; color: #fff; }
        .ws-loc { font-size: 0.75rem; color: var(--text-muted); font-weight: 600; }
        .ws-loc.moving { color: var(--primary); animation: pulse-border 1.5s infinite; }
        .ws-slots-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
        .ws-slot { height: 38px; border-radius: 8px; display: flex; flex-direction: column; justify-content: center; align-items: center; font-size: 0.7rem; border: 1px solid var(--border-color); background: rgba(255, 255, 255, 0.02); }
        .ws-slot.full { background: rgba(0, 242, 254, 0.08); border-color: rgba(0, 242, 254, 0.3); color: var(--primary); }
        .ws-slot-name { font-size: 0.6rem; color: var(--text-muted); max-width: 90%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .tasks-list { display: flex; flex-direction: column; gap: 8px; }
        .task-item { background: rgba(79, 172, 254, 0.08); border: 1px solid rgba(79, 172, 254, 0.2); border-radius: 10px; padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; }
        .task-name { font-weight: 700; color: var(--primary); }
        .task-desc { font-size: 0.75rem; color: var(--text-muted); }
        .table-wrapper { overflow-x: auto; max-height: 400px; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.85rem; }
        th { background: rgba(15, 23, 42, 0.8); padding: 12px; color: var(--text-muted); border-bottom: 1px solid var(--border-color); position: sticky; top: 0; }
        td { padding: 12px; border-bottom: 1px solid var(--border-color); }
        .status-pill { display: inline-block; font-size: 0.7rem; font-weight: 700; padding: 4px 10px; border-radius: 9999px; }
        .status-pill.waiting { background: rgba(100, 116, 139, 0.15); color: var(--text-muted); }
        .status-pill.in_workstation { background: rgba(0, 242, 254, 0.15); color: var(--primary); }
        .status-pill.in_warehouse { background: rgba(245, 158, 11, 0.15); color: var(--warning); }
        .status-pill.completed { background: rgba(16, 185, 129, 0.15); color: var(--success); }
        .toast { position: fixed; bottom: 24px; right: 24px; background: rgba(15, 23, 42, 0.9); border: 1px solid var(--primary); border-radius: 12px; padding: 16px 24px; color: #fff; opacity: 0; transform: translateY(100px); transition: all 0.3s ease; z-index: 999; }
        .toast.show { transform: translateY(0); opacity: 1; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        @keyframes pulse-border { 0%, 100% { border-color: rgba(0, 242, 254, 0.2); } 50% { border-color: rgba(0, 242, 254, 0.8); } }
        
        /* 🗺️ 2D 그리드 레이아웃 (새로운 존 하이라이팅 및 셀 병합 포함) */
        .grid-map-container { position: relative; width: 272px; height: 392px; border: 2px solid rgba(255, 255, 255, 0.12); background-color: rgba(10, 15, 30, 0.9); border-radius: 14px; margin: 0 auto; overflow: hidden; }
        .grid-loc { position: absolute; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: 5px; font-size: 0.55rem; font-weight: 700; color: rgba(255, 255, 255, 0.8); text-align: center; }
        
        /* 기본 맵 요소 스타일 */
        .grid-loc.spot { border: 1.5px solid rgba(59, 130, 246, 0.6); background: rgba(59, 130, 246, 0.15); }
        .grid-loc.stage { border: 1.5px solid rgba(245, 158, 11, 0.6); background: rgba(245, 158, 11, 0.15); }
        .grid-loc.charging { border: 1.5px solid rgba(168, 85, 247, 0.6); background: rgba(168, 85, 247, 0.15); }
        .grid-loc.conveyor { border: 1.5px solid rgba(16, 185, 129, 0.6); background: rgba(16, 185, 129, 0.15); }
        .grid-loc.conveyor-belt { border: 1.5px solid rgba(6, 182, 212, 0.7); background: rgba(6, 182, 212, 0.25); color: transparent; font-weight: bold; }
        .grid-loc.packaging { border: 1.5px solid rgba(236, 72, 153, 0.75); background: rgba(236, 72, 153, 0.18); }
        
        /* SG2 로봇 렌더링 및 존 하이라이트 스타일 (통일) */
        .grid-loc.fixed-sg2-robot { border: 2px solid rgba(14, 165, 233, 0.8) !important; background: rgba(14, 165, 233, 0.35) !important; color: #38bdf8 !important; font-weight: bold; }
        .grid-loc.zone-sg2-in, .grid-loc.zone-sg2-out { border: 2px solid rgba(14, 165, 233, 0.8) !important; background: rgba(14, 165, 233, 0.25) !important; color: #38bdf8 !important; font-weight: 900; box-shadow: 0 0 10px rgba(14, 165, 233, 0.3); }

        /* 범례 스타일 */
        .map-legend { display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 20px; padding: 12px 16px; background: rgba(15, 23, 42, 0.5); border-radius: 8px; border: 1px solid var(--border-color); justify-content: center; }
        .legend-item { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; color: #cbd5e1; font-weight: 500; }
        .legend-box { width: 14px; height: 14px; border-radius: 3px; }

        .grid-loc.has-ws { background: #1e1b4b !important; border: 2px solid #eab308 !important; color: #fde047 !important; font-weight: 900; font-size: 0.52rem; z-index: 5; }
        .grid-loc.path-active { background: rgba(255, 0, 127, 0.05); box-shadow: inset 0 0 8px rgba(255, 0, 127, 0.35); }
        .amr-icon { position: absolute; width: 26px; height: 26px; border-radius: 50%; border: 2px solid #fff; display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 900; color: #fff; z-index: 20; transform: translate(-50%, -50%); transition: left 0.3s linear, top 0.3s linear; }
        .btn-start-business { background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); color: #10b981; opacity: 0.6; cursor: not-allowed; padding: 12px 24px; border-radius: 12px; font-weight: 700; }
        .btn-start-business.ready { background: linear-gradient(135deg, #10b981 0%, #059669 100%); border: none; color: #0b0f19; opacity: 1; cursor: pointer; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }
        .btn-start-business.running { background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); color: #3b82f6; opacity: 0.9; cursor: default; }
        .dev-badge { padding: 4px 10px; border-radius: 8px; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); color: var(--danger); font-size: 0.75rem; display: inline-flex; align-items: center; font-family: monospace; }
        .dev-badge.online { background: rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.35); color: var(--success); }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo-section">
                <h1>Coupang Control Center</h1>
                <p>PostgreSQL & Redis 실시간 모니터링 대시보드 (10 Workstations v1.2)</p>
            </div>
            <div class="status-badge"><span class="dot"></span><span>SYSTEM LIVE</span></div>
        </header>

        <div class="controls" style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 2rem;">
            <div style="display: flex; gap: 12px; flex-wrap: wrap; align-items: center;">
                <button id="btn-start-business" class="btn-start-business" onclick="startBusiness()" disabled>영업 시작</button>
                <button class="btn-upload" onclick="triggerCSVUpload()">📥 CSV 입고 명단 업로드</button>
                <input type="file" accept=".csv" id="csv-file-input" style="display:none" onchange="uploadCSV()">
                <button class="btn-simulate" onclick="simulateInbound()">⚡ 시뮬레이션 적재 발생</button>
                <button class="btn-packaging" onclick="simulatePackaging()" style="background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%); border: none; color: #000;">📦 시뮬레이션 포장 수행</button>
                <button class="btn-reset" onclick="resetDatabase()">🔄 데이터베이스 초기화</button>
            </div>
            <div id="device-status-strip" style="display: flex; gap: 8px; padding: 10px 16px; background: rgba(22, 28, 45, 0.4); border: 1px solid var(--border-color); border-radius: 12px; font-size: 0.78rem; font-weight: 600; align-items: center;">
                <span style="color: var(--text-muted); margin-right: 4px;">📡 기기 상태:</span>
                <span id="dev-bg2" class="dev-badge">bg2</span>
                <span id="dev-sg2-in-01" class="dev-badge">sg2_in_01</span>
                <span id="dev-sg2-in-02" class="dev-badge">sg2_in_02</span>
                <span id="dev-sg2-in-03" class="dev-badge">sg2_in_03</span>
                <span id="dev-sg2-out-00" class="dev-badge">sg2_out_00</span>
                <span id="dev-amr" class="dev-badge">AMR</span>
            </div>
        </div>

        <div id="day-transition-banner" style="display: none; background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(239, 68, 68, 0.15) 100%); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 16px; padding: 20px; margin-bottom: 2rem; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 16px;">
                <div style="font-size: 2.2rem;">🎉</div>
                <div>
                    <h3 style="margin: 0; color: #fff; font-size: 1.15rem; font-weight: 700;">오늘 영업일 운영 마감 완료! <span id="completed-day-badge">—</span></h3>
                    <p style="margin: 4px 0 0 0; color: var(--text-muted); font-size: 0.88rem;">모든 포장 공정이 종료되었습니다. 통계 보고서가 생성되었습니다.</p>
                </div>
            </div>
            <button onclick="startNextDay()" style="background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%); border: none; color: #000; font-weight: 800; padding: 14px 28px; border-radius: 12px;">🚀 다음 영업일 개시</button>
        </div>

        <div class="panel-card" style="margin-bottom: 2rem;">
            <h2>Warehouse 2D Live Grid Plan</h2>
            <div class="map-legend">
                <div class="legend-item"><div class="legend-box" style="border: 2px solid #eab308; background: #1e1b4b;"></div><span>작업대 (WS)</span></div>
                <div class="legend-item"><div class="legend-box" style="border: 2px solid #fff; background: #ff007f; border-radius: 50%;"></div><span>AMR 로봇</span></div>
                <div class="legend-item"><div class="legend-box" style="border: 1.5px solid rgba(59, 130, 246, 0.6); background: rgba(59, 130, 246, 0.15);"></div><span>주차 스팟</span></div>
                <div class="legend-item"><div class="legend-box" style="border: 1.5px solid rgba(245, 158, 11, 0.6); background: rgba(245, 158, 11, 0.15);"></div><span>대기 스팟</span></div>
                <div class="legend-item"><div class="legend-box" style="border: 1.5px solid rgba(168, 85, 247, 0.6); background: rgba(168, 85, 247, 0.15);"></div><span>충전 스팟</span></div>
                <div class="legend-item"><div class="legend-box" style="border: 1.5px solid rgba(16, 185, 129, 0.6); background: rgba(16, 185, 129, 0.15);"></div><span>입고 버퍼</span></div>
                <div class="legend-item"><div class="legend-box" style="border: 1.5px solid rgba(236, 72, 153, 0.75); background: rgba(236, 72, 153, 0.18);"></div><span>출고 버퍼</span></div>
                <div class="legend-item"><div class="legend-box" style="border: 1.5px solid rgba(6, 182, 212, 0.7); background: rgba(6, 182, 212, 0.25);"></div><span>컨베이어</span></div>
                <div class="legend-item"><div class="legend-box" style="border: 2px solid rgba(14, 165, 233, 0.8); background: rgba(14, 165, 233, 0.35);"></div><span>SG2 로봇 구역</span></div>
            </div>
            <div id="floor-plan-container" style="background: rgba(15, 23, 42, 0.45); border-radius: 16px; padding: 20px; display: flex; justify-content: center;">
                <div id="grid-map-panel" class="grid-map-container"></div>
            </div>
        </div>

        <div class="dashboard-grid">
            <div class="panel-card">
                <h2>Warehouse Parking Spots (10 Slots)</h2>
                <div class="spots-container" id="spots-list"></div>
            </div>
            <div class="panel-card">
                <h2>Outbound Staging Spots (4 Slots)</h2>
                <div class="spots-container" id="staging-list"></div>
            </div>
            <div class="panel-card">
                <h2>Workstations Active Status (10 Plates)</h2>
                <div class="workstations-container" id="ws-list"></div>
            </div>
        </div>

        <div class="panel-card" style="margin-bottom: 2rem;">
            <h2>Redis Command Queue <span id="redis-count">0 tasks active</span></h2>
            <div class="tasks-list" id="tasks-list"></div>
        </div>

        <div class="panel-card">
            <h2>Package Tracking Log</h2>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Package ID</th><th>QR ID</th><th>수령인</th><th>배송 예정구역</th><th>진행 상태</th><th>적재 작업대</th><th>슬롯 번호</th><th>출고 바코드 ID</th></tr>
                    </thead>
                    <tbody id="package-tbody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <div class="toast" id="toast-message"></div>

    <script>
        function showToast(message) {
            const toast = document.getElementById('toast-message');
            toast.innerText = message;
            toast.classList.add('show');
            setTimeout(() => { toast.classList.remove('show'); }, 3000);
        }

        let gridInitialized = false;
        let pathTraceQueue = [];
        let locCellMap = {};
        const X_MIN = -3.0; const Y_MAX = 9.0; const GRID_STEP = 1.5; const CELL_PX = 30;

        function xToPx(x) { return Math.round((x - X_MIN) / GRID_STEP) * CELL_PX + 1; }
        function yToPx(y) { return Math.round((Y_MAX - y) / GRID_STEP) * CELL_PX + 1; }

        function initGridMap(gridCells) {
            if (gridInitialized) return;
            const container = document.getElementById('grid-map-panel');
            if (!container) return;
            container.innerHTML = '';

            if (gridCells) {
                // 🛠️ 병합되어 화면에서 렌더링되지 않아야 할 나머지 여분 타일들의 정확한 좌표 필터링
                const skipCoords = [
                    '7.5,3.0', '7.5,-1.5', '7.5,-6.0',     // SG2_IN 로봇 오른쪽 절반 타일 (가로 2칸 병합용)
                    '-1.5,9.0', '-3.0,7.5', '-1.5,7.5'     // SG2_OUT 로봇 3개 타일 (2x2 정사각형 병합용)
                ];

                const renderLocations = gridCells.filter(cell => {
                    const coordKey = `${cell.x.toFixed(1)},${cell.y.toFixed(1)}`;
                    if (skipCoords.includes(coordKey)) return false; // 렌더링 스킵
                    return cell.location_name || cell.location_type === 'STATIC_OBSTACLE' || coordKey === '-3.0,9.0';
                });

                renderLocations.forEach(cell => {
                    const name = (cell.location_name || '').toLowerCase();
                    const type = cell.location_type;
                    const coordKey = `${cell.x.toFixed(1)},${cell.y.toFixed(1)}`;
                    const el = document.createElement('div');
                    el.className = 'grid-loc';
                    let labelText = ''; 
                    let w = '28px'; 
                    let h = '28px';

                    // 1. 기본 구역 할당
                    if (name.startsWith('spot_')) { el.classList.add('spot'); labelText = 'S' + name.replace('spot_', ''); }
                    else if (name.startsWith('stage_')) { el.classList.add('stage'); labelText = 'ST' + name.replace('stage_', ''); }
                    else if (name.startsWith('charging_')) { el.classList.add('charging'); labelText = 'C' + name.replace('charging_', ''); }
                    else if (name.startsWith('sg2_in_0')) { el.classList.add('conveyor'); labelText = 'I' + name.replace('sg2_in_0', '').replace('_a','A').replace('_b','B').toUpperCase(); }
                    else if (name.startsWith('sg2_out_0')) { el.classList.add('packaging'); labelText = 'O' + name.replace('sg2_out_00_', '').toUpperCase(); }
                    else if (type === 'STATIC_OBSTACLE' || coordKey === '-3.0,9.0') {
                        // 🛠️ SG2_IN (입고 로봇 영역 3개) - 가로 2칸 병합
                        if (['6.0,3.0', '6.0,-1.5', '6.0,-6.0'].includes(coordKey)) {
                            el.classList.add('fixed-sg2-robot');
                            labelText = 'SG2';
                            w = '58px'; // 가로 넓이 두 배 + gap
                        }
                        // 🛠️ SG2_OUT (포장 로봇 영역 1개) - 2x2 정사각형 병합
                        else if (coordKey === '-3.0,9.0') {
                            el.classList.add('fixed-sg2-robot');
                            labelText = 'SG2';
                            w = '58px';
                            h = '58px';
                        }
                        // 그 외 (X=9.0 컨베이어 벨트 라인)
                        else {
                            el.classList.add('conveyor-belt');
                            labelText = ''; // 텍스트 숨김 (CV 제거)
                        }
                    }

                    // 🚀 특정 구역(존) 좌표 감지하여 강력한 CSS 덧붙이기 (기존 클래스 유지)
                    const outCoords = ['0.0,9.0', '0.0,7.5', '-3.0,9.0']; // 포장 작업대 버퍼 + SG2_OUT 로봇 영역
                    const inCoords = ['6.0,3.0', '7.5,3.0', '6.0,-1.5', '7.5,-1.5', '6.0,-6.0', '7.5,-6.0'];

                    if (outCoords.includes(coordKey)) {
                        el.classList.add('zone-sg2-out'); 
                        if (!labelText && !el.classList.contains('conveyor-belt')) labelText = 'OUT';
                    } else if (inCoords.includes(coordKey)) {
                        el.classList.add('zone-sg2-in'); 
                        if (!labelText && !el.classList.contains('conveyor-belt')) labelText = 'IN';
                    }

                    // 투명 컨베이어 벨트는 텍스트 공백 유지
                    if (el.classList.contains('conveyor-belt')) { labelText = ''; }
                    
                    el.textContent = labelText;
                    el.style.left = `${xToPx(cell.x)}px`; el.style.top = `${yToPx(cell.y)}px`;
                    el.style.width = w; el.style.height = h;
                    container.appendChild(el);
                    
                    if (cell.location_name) locCellMap[name] = el;
                    locCellMap[cell.qr_id] = el;
                });
            }
            gridInitialized = true;
        }

        function updateFloorPlan(data) {
            if (data.grid_cells && !gridInitialized) initGridMap(data.grid_cells);
            if (!gridInitialized) return;

            Object.keys(locCellMap).forEach(key => {
                const el = locCellMap[key];
                if (el) el.classList.remove('has-ws');
            });

            if (!window.amrDomElements) window.amrDomElements = {};

            if (data.workstations) {
                data.workstations.forEach(ws => {
                    const loc = ws.current_location.toLowerCase();
                    let cellEl = locCellMap[loc];
                    if (cellEl) {
                        cellEl.classList.add('has-ws');
                        cellEl.textContent = ws.workstation_id.replace('WS0', 'W').replace('WS', 'W');
                    }
                });
            }

            if (data.amr_states) {
                const panel = document.getElementById('grid-map-panel');
                Object.keys(data.amr_states).forEach(amrId => {
                    const amr = data.amr_states[amrId];
                    let qrId = amr.current_qr_id;
                    const cellEl = locCellMap[qrId];
                    if (cellEl) {
                        let amrEl = window.amrDomElements[amrId];
                        if (!amrEl) {
                            amrEl = document.createElement('div');
                            amrEl.className = 'amr-icon';
                            panel.appendChild(amrEl);
                            window.amrDomElements[amrId] = amrEl;
                        }
                        amrEl.style.left = `${parseFloat(cellEl.style.left) + 14}px`;
                        amrEl.style.top = `${parseFloat(cellEl.style.top) + 14}px`;
                        amrEl.style.backgroundColor = '#ff007f';
                        amrEl.textContent = amrId.replace('AMR_', '');
                    }
                });
            }
        }

        async function simulateInbound() {
            const res = await fetch('/api/simulate', { method: 'POST' });
            const d = await res.json();
            showToast(d.message);
        }

        async function simulatePackaging() {
            const res = await fetch('/api/simulate_packaging', { method: 'POST' });
            const d = await res.json();
            showToast(d.message);
        }

        function triggerCSVUpload() { document.getElementById('csv-file-input').click(); }
        
        async function uploadCSV() {
            const fileInput = document.getElementById('csv-file-input');
            if (fileInput.files.length === 0) return;
            const reader = new FileReader();
            reader.onload = async function(e) {
                const res = await fetch('/api/upload_packages', { method: 'POST', body: e.target.result });
                const d = await res.json();
                showToast(d.message);
            };
            reader.readAsText(fileInput.files[0]);
        }

        async function startNextDay() {
            const res = await fetch('/api/start_next_day', { method: 'POST' });
            const d = await res.json();
            showToast(d.message);
        }

        async function resetDatabase() {
            if(!confirm("DB를 리셋하시겠습니까?")) return;
            const res = await fetch('/api/reset', { method: 'POST' });
            const d = await res.json();
            showToast(d.message);
            lastDataHash = { spots: '', workstations: '', redis_tasks: '', packages: '' };
        }

        async function startBusiness() {
            const res = await fetch('/api/start_business', { method: 'POST' });
            const d = await res.json();
            showToast(d.message);
        }

        let lastDataHash = { spots: '', workstations: '', redis_tasks: '', packages: '' };

        function updateUI(data) {
            updateFloorPlan(data);
            const banner = document.getElementById('day-transition-banner');
            if (banner) banner.style.display = data.day_status === 'PENDING_TRANSITION' ? 'flex' : 'none';

            const devices = ['bg2', 'sg2-in-01', 'sg2-in-02', 'sg2-in-03', 'sg2-out-00', 'amr'];
            devices.forEach(dev => {
                const dataKey = dev.replace(/-/g, '_'); 
                const el = document.getElementById(`dev-${dev}`);
                if (el) {
                    if (data.device_status && data.device_status[dataKey]) {
                        el.classList.add('online');
                    } else {
                        el.classList.remove('online');
                    }
                }
            });

            const startBtn = document.getElementById('btn-start-business');
            if (startBtn) {
                const systemRunning = data.day_status === 'RUNNING';
                const packagesWaiting = (data.packages || []).some(pkg => pkg.status === 'WAITING');
                const ready = packagesWaiting && !systemRunning && data.day_status !== 'PENDING_TRANSITION';

                if (systemRunning) {
                    startBtn.classList.remove('ready');
                    startBtn.classList.add('running');
                    startBtn.textContent = '영업 중';
                    startBtn.disabled = true;
                } else if (ready) {
                    startBtn.classList.add('ready');
                    startBtn.classList.remove('running');
                    startBtn.textContent = '영업 시작';
                    startBtn.disabled = false;
                } else {
                    startBtn.classList.remove('ready', 'running');
                    startBtn.textContent = '영업 시작';
                    startBtn.disabled = true;
                }
            }

            const spotsStr = JSON.stringify(data.spots || []);
            if (spotsStr !== lastDataHash.spots) {
                const sc = document.getElementById('spots-list');
                const stc = document.getElementById('staging-list');
                if (sc) sc.innerHTML = ''; if (stc) stc.innerHTML = '';
                
                (data.spots || []).forEach(spot => {
                    const el = document.createElement('div');
                    el.className = `spot-item ${spot.status === 'OCCUPIED' ? 'occupied' : 'empty'}`;
                    el.innerHTML = `<div class="spot-id">${spot.spot_id}</div><div class="spot-ws">${spot.workstation_id || '—'}</div>`;
                    if (spot.spot_id.startsWith('spot_') && sc) sc.appendChild(el);
                    else if (spot.spot_id.startsWith('stage_') && stc) stc.appendChild(el);
                });
                lastDataHash.spots = spotsStr;
            }

            const wsStr = JSON.stringify(data.workstations || []);
            if (wsStr !== lastDataHash.workstations) {
                const wc = document.getElementById('ws-list');
                if (wc) {
                    wc.innerHTML = '';
                    (data.workstations || []).forEach(ws => {
                        const el = document.createElement('div');
                        el.className = 'ws-card';
                        el.innerHTML = `<div class="ws-header"><span class="ws-id">${ws.workstation_id}</span><span class="ws-loc">${ws.current_location}</span></div>`;
                        if (wc) wc.appendChild(el);
                    });
                }
                lastDataHash.workstations = wsStr;
            }

            const pkgsStr = JSON.stringify(data.packages || []);
            if (pkgsStr !== lastDataHash.packages || (data.packages && data.packages.length > 0 && document.getElementById('package-tbody').children.length === 0)) {
                const tbody = document.getElementById('package-tbody');
                if (tbody) {
                    tbody.innerHTML = '';
                    (data.packages || []).forEach(pkg => {
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
                            <td style="font-family: monospace; color: #00f2fe; font-size: 0.75rem;">${pkg.outbound_id || '—'}</td>
                        `;
                        tbody.appendChild(row);
                    });
                }
                lastDataHash.packages = pkgsStr;
            }
        }

        let ws;
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            ws = new WebSocket(wsUrl);
            ws.onopen = function() { showToast("⚡ 실시간 WebSocket 관제 연결 완료"); };
            ws.onmessage = function(event) { updateUI(JSON.parse(event.data)); };
            ws.onclose = function() { setTimeout(connectWebSocket, 3000); };
        }
        connectWebSocket();
    </script>
</body>
</html>
    """

if __name__ == "__main__":
    uvicorn.run("dashboard_server:app", host="0.0.0.0", port=8009, reload=True)
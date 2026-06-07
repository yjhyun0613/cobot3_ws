#!/usr/bin/env python3
import os
import sys
import time
import psycopg2
import redis
import json

# 1. Start Isaac Sim headless/GUI (headless=False so user can see it)
print("=== [Isaac Sim Connector] Omniverse Kit 엔진 초기화 중... ===")
from omni.isaac.kit import SimulationApp
simulation_app = SimulationApp({"headless": False})

from pxr import Usd, UsdGeom, Sdf, Gf, UsdShade

# 2. USD Stage 로드
usd_path = "/home/rokey/cobot3_ws/src/cobot3/resource/map.usd"
usd_context = omni.usd.get_context()
opened = usd_context.open_stage(usd_path)
if not opened:
    print(f"[ERROR] USD 맵 파일을 열 수 없습니다: {usd_path}")
    simulation_app.close()
    sys.exit(1)

stage = usd_context.get_stage()
print(f"[SUCCESS] USD 스테이지 오픈 완료: {usd_path}")

# 3. 데이터베이스 및 캐시 연결 설정
try:
    pg_conn = psycopg2.connect(
        host="localhost",
        database="warehouse_db",
        user="rokey",
        password="rokey_pass",
        port=5432
    )
    pg_conn.autocommit = True
    print("[SUCCESS] PostgreSQL 연결 완료.")
except Exception as e:
    print(f"[ERROR] PostgreSQL 연결 실패: {e}")
    simulation_app.close()
    sys.exit(1)

try:
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
    print("[SUCCESS] Redis 연결 완료.")
except Exception as e:
    print(f"[ERROR] Redis 연결 실패: {e}")
    simulation_app.close()
    sys.exit(1)

# 4. floor_qr_map 테이블로부터 물리적 위치 좌표 맵 동적 빌드
location_coords = {}
try:
    with pg_conn.cursor() as cursor:
        cursor.execute("SELECT location_name, x_coord, y_coord FROM floor_qr_map WHERE location_name IS NOT NULL;")
        rows = cursor.fetchall()
        for loc_name, x, y in rows:
            location_coords[loc_name.lower()] = (x, y)
    print(f"[INFO] floor_qr_map에서 {len(location_coords)}개의 주요 물리 위치 좌표를 로드했습니다.")
except Exception as e:
    print(f"[ERROR] 위치 좌표 로드 실패: {e}")

# 5. 3D 형상 모델 정의 유틸리티 (AMR 및 작업대)
SIM_ROOT = "/World/Simulation"
if not stage.GetPrimAtPath(SIM_ROOT):
    UsdGeom.Xform.Define(stage, Sdf.Path(SIM_ROOT))

def create_amr_prim(path_str):
    """AMR을 시안색(Cyan) 실린더로 생성"""
    if stage.GetPrimAtPath(path_str):
         return UsdGeom.Cylinder(stage.GetPrimAtPath(path_str))
    
    geom = UsdGeom.Cylinder.Define(stage, Sdf.Path(path_str))
    geom.CreateRadiusAttr(0.35) # 지름 70cm
    geom.CreateHeightAttr(0.25) # 높이 25cm
    geom.CreateAxisAttr("Z")
    
    # Cyan 색상 재질 적용
    geom.CreateDisplayColorAttr([(0.0, 0.7, 1.0)])
    print(f"Created AMR 3D Model: {path_str}")
    return geom

def create_workstation_prim(path_str):
    """작업대(Rack)를 오렌지색 큐브로 생성"""
    if stage.GetPrimAtPath(path_str):
         return UsdGeom.Cube(stage.GetPrimAtPath(path_str))
    
    geom = UsdGeom.Cube.Define(stage, Sdf.Path(path_str))
    # 큐브 기본 크기가 2.0이므로 1.3m * 1.3m * 1.0m에 맞춰 스케일링 설정
    xform = UsdGeom.XformCommonAPI(geom)
    xform.SetScale(Gf.Vec3d(1.3/2.0, 1.3/2.0, 0.8/2.0))
    
    # Orange 색상 재질 적용
    geom.CreateDisplayColorAttr([(0.9, 0.45, 0.1)])
    print(f"Created Workstation 3D Model: {path_str}")
    return geom

# 6. AMR 및 작업대 3D 모델 인스턴스 초기 생성
amr_paths = {}
for i in range(1, 6):
    amr_id = f"AMR_{i:02d}"
    path = f"{SIM_ROOT}/AMR_{amr_id}"
    create_amr_prim(path)
    amr_paths[amr_id] = path

ws_paths = {}
for i in range(1, 11):
    ws_id = f"WS{i:02d}"
    path = f"{SIM_ROOT}/Workstation_{ws_id}"
    create_workstation_prim(path)
    ws_paths[ws_id] = path

print("\n=== [Isaac Sim Connector] 시뮬레이션 동기화 루프 시작 ===")
print("힌트: CTRL+C를 누르면 안전하게 종료됩니다.\n")

# 7. 실시간 동기화 루프
try:
    while simulation_app.is_running():
        # Redis에서 5대 AMR 상태 조회 및 3D 텔레포트 이동
        carried_workstations = {}
        for amr_id, path_str in amr_paths.items():
            amr_key = f"amr:{amr_id}"
            state_data = r.hgetall(amr_key)
            
            if state_data:
                try:
                    x = float(state_data.get("x", 0.0))
                    y = float(state_data.get("y", 0.0))
                    carrying = state_data.get("carrying_workstation", "")
                    
                    # AMR 이동 적용
                    prim = stage.GetPrimAtPath(path_str)
                    if prim:
                        xform = UsdGeom.XformCommonAPI(prim)
                        # AMR은 지면에 밀착 (Z = 0.125)
                        xform.SetTranslate(Gf.Vec3d(x, y, 0.125))
                    
                    # 만약 작업대를 들고 이동 중이라면 기록
                    if carrying and carrying != "None" and carrying != "":
                        carried_workstations[carrying] = (x, y)
                except Exception as val_err:
                    pass

        # PostgreSQL에서 10개 작업대 위치 조회 및 3D 이동 적용
        try:
            with pg_conn.cursor() as cursor:
                cursor.execute("SELECT workstation_id, current_location FROM workstations;")
                rows = cursor.fetchall()
                for ws_id, cur_loc in rows:
                    path_str = ws_paths.get(ws_id)
                    if not path_str:
                        continue
                    
                    prim = stage.GetPrimAtPath(path_str)
                    if not prim:
                        continue
                    
                    xform = UsdGeom.XformCommonAPI(prim)
                    
                    # Case A: AMR이 현재 작업대를 들어 올린 상태
                    if ws_id in carried_workstations:
                        ax, ay = carried_workstations[ws_id]
                        # AMR 위에 얹어서 이동 (Z = 0.55m 높이로 리프트)
                        xform.SetTranslate(Gf.Vec3d(ax, ay, 0.55))
                    
                    # Case B: 특정 장소(Spot/Inbound/Outbound 등)에 주차된 상태
                    elif cur_loc:
                        loc_key = cur_loc.lower()
                        if loc_key in location_coords:
                            lx, ly = location_coords[loc_key]
                            # 바닥에 주차 (Z = 0.40m)
                            xform.SetTranslate(Gf.Vec3d(lx, ly, 0.40))
                        else:
                            # 좌표 해석 실패 시 디폴트 보이지 않는 영역으로 대기
                            xform.SetTranslate(Gf.Vec3d(0.0, 0.0, -10.0))
        except Exception as db_err:
            print(f"[WARNING] 작업대 위치 조회 실패: {db_err}")

        # 3D 렌더링 프레임 갱신
        simulation_app.update()
        time.sleep(0.033) # 약 30Hz 주기로 상태 갱신

except KeyboardInterrupt:
    print("\n사용자에 의해 종료 요청됨.")

finally:
    pg_conn.close()
    print("=== [Isaac Sim Connector] 안전하게 접속 종료 처리 완료. ===")
    simulation_app.close()

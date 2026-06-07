#!/usr/bin/env python3
"""
NVIDIA Isaac Sim ↔ 물류창고 관제 시스템 실시간 3D 동기화 커넥터
================================================================
사용법:  isaac-python scratch/isaac_amr_connector.py
맵 파일: src/cobot3/resource/floor_with_con,storage.usd
         (바닥 QR 격자, 컨베이어, 입출고 스토리지, 작업대(custom_rack) 기설치)

역할:
  - Redis에서 5대 AMR의 실시간 (x, y) 위치를 읽어 3D 씬에 반영
  - PostgreSQL에서 10대 작업대(WS01~WS10)의 주차 위치를 읽어 3D 씬에 반영
  - AMR이 작업대를 들어올리면(carrying) 작업대가 AMR 위로 리프트
"""
import os
import sys
import time

# ──────────────────────────────────────────────
# 1. Isaac Sim 엔진 초기화 (GUI 모드)
# ──────────────────────────────────────────────
print("=== [Isaac Sim Connector] Omniverse Kit 엔진 초기화 중... ===")
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": False})

import omni.usd
from pxr import Usd, UsdGeom, Sdf, Gf

# DB 모듈은 Isaac Sim 초기화 후 임포트
import psycopg2
import redis

# ──────────────────────────────────────────────
# 2. 기설정된 USD 맵 스테이지 로드
# ──────────────────────────────────────────────
USD_MAP_PATH = "/home/rokey/cobot3_ws/src/cobot3/resource/floor_with_con,storage.usd"

usd_context = omni.usd.get_context()
opened = usd_context.open_stage(USD_MAP_PATH)
if not opened:
    print(f"[ERROR] USD 맵 파일을 열 수 없습니다: {USD_MAP_PATH}")
    simulation_app.close()
    sys.exit(1)

stage = usd_context.get_stage()
print(f"[SUCCESS] USD 스테이지 오픈 완료: {USD_MAP_PATH}")
print("  └─ 바닥 QR 격자, 컨베이어, 입출고 스토리지, 작업대(custom_rack) 이미 세팅됨")

# ──────────────────────────────────────────────
# 3. 데이터베이스 연결 (PostgreSQL + Redis)
# ──────────────────────────────────────────────
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

# ──────────────────────────────────────────────
# 4. DB에서 물리적 위치 좌표 맵 로드
# ──────────────────────────────────────────────
location_coords = {}
try:
    with pg_conn.cursor() as cursor:
        cursor.execute("SELECT location_name, x_coord, y_coord FROM floor_qr_map WHERE location_name IS NOT NULL;")
        rows = cursor.fetchall()
        for loc_name, x, y in rows:
            location_coords[loc_name.lower()] = (float(x), float(y))
    print(f"[INFO] floor_qr_map에서 {len(location_coords)}개의 주요 물리 위치 좌표를 로드했습니다.")
except Exception as e:
    print(f"[ERROR] 위치 좌표 로드 실패: {e}")

# ──────────────────────────────────────────────
# 5. AMR 로봇 3D 모델 동적 생성 (5대)
#    - 기존 맵에 AMR은 없으므로 새로 추가
#    - 시안색 실린더 (반지름 0.35m, 높이 0.25m)
# ──────────────────────────────────────────────
AMR_ROOT = "/World/AMRs"
if not stage.GetPrimAtPath(AMR_ROOT):
    UsdGeom.Xform.Define(stage, Sdf.Path(AMR_ROOT))

def create_amr_prim(path_str):
    """AMR을 시안색(Cyan) 실린더로 생성"""
    if stage.GetPrimAtPath(path_str):
        return stage.GetPrimAtPath(path_str)

    geom = UsdGeom.Cylinder.Define(stage, Sdf.Path(path_str))
    geom.CreateRadiusAttr(0.35)   # 지름 70cm
    geom.CreateHeightAttr(0.25)   # 높이 25cm
    geom.CreateAxisAttr("Z")
    geom.CreateDisplayColorAttr([(0.0, 0.7, 1.0)])  # Cyan
    print(f"  [AMR] 3D 모델 생성 완료: {path_str}")
    return geom.GetPrim()

amr_paths = {}
print("\n[Step 5] AMR 로봇 5대 3D 모델 생성:")
for i in range(1, 6):
    amr_id = f"AMR_{i:02d}"
    path = f"{AMR_ROOT}/{amr_id}"
    create_amr_prim(path)
    amr_paths[amr_id] = path

# ──────────────────────────────────────────────
# 6. 작업대(Workstation/Rack) 3D 모델 동적 생성 (10대)
#    - 맵에 이미 custom_rack 들이 있지만 이것은 고정 스토리지 배경
#    - 10대의 이동 가능 작업대를 별도로 생성 (오렌지색 큐브)
# ──────────────────────────────────────────────
WS_ROOT = "/World/Workstations"
if not stage.GetPrimAtPath(WS_ROOT):
    UsdGeom.Xform.Define(stage, Sdf.Path(WS_ROOT))

def create_workstation_prim(path_str):
    """이동 가능한 작업대를 오렌지색 큐브로 생성"""
    if stage.GetPrimAtPath(path_str):
        return stage.GetPrimAtPath(path_str)

    geom = UsdGeom.Cube.Define(stage, Sdf.Path(path_str))
    xform = UsdGeom.XformCommonAPI(geom)
    xform.SetScale(Gf.Vec3d(1.3 / 2.0, 1.3 / 2.0, 0.8 / 2.0))
    geom.CreateDisplayColorAttr([(0.9, 0.45, 0.1)])  # Orange
    print(f"  [WS] 3D 모델 생성 완료: {path_str}")
    return geom.GetPrim()

ws_paths = {}
print("\n[Step 6] 이동식 작업대 10대 3D 모델 생성:")
for i in range(1, 11):
    ws_id = f"WS{i:02d}"
    path = f"{WS_ROOT}/{ws_id}"
    create_workstation_prim(path)
    ws_paths[ws_id] = path

# ──────────────────────────────────────────────
# 7. 실시간 동기화 메인 루프 (약 30Hz)
# ──────────────────────────────────────────────
print("\n=== [Isaac Sim Connector] 실시간 3D 동기화 루프 시작 ===")
print("  └─ 브라우저 대시보드(http://localhost:8009)와 병행하여 사용 가능")
print("  └─ 종료: CTRL+C\n")

frame_count = 0
try:
    while simulation_app.is_running():
        # ── A. Redis에서 5대 AMR 상태 조회 ──
        carried_workstations = {}  # AMR이 들고 있는 작업대 추적

        for amr_id, path_str in amr_paths.items():
            state_data = r.hgetall(f"amr:{amr_id}")
            if not state_data:
                continue

            try:
                x = float(state_data.get("x", 0.0))
                y = float(state_data.get("y", 0.0))
                carrying = state_data.get("carrying_workstation", "")

                # AMR 위치 갱신 (지면 밀착 Z=0.125)
                prim = stage.GetPrimAtPath(path_str)
                if prim:
                    xform = UsdGeom.XformCommonAPI(prim)
                    xform.SetTranslate(Gf.Vec3d(x, y, 0.125))

                # 작업대 상차 상태 기록
                if carrying and carrying not in ("None", ""):
                    carried_workstations[carrying] = (x, y)
            except Exception:
                pass

        # ── B. PostgreSQL에서 10대 작업대 위치 조회 ──
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

                    # Case A: AMR이 작업대를 들어올린 상태 → 리프트
                    if ws_id in carried_workstations:
                        ax, ay = carried_workstations[ws_id]
                        xform.SetTranslate(Gf.Vec3d(ax, ay, 0.55))

                    # Case B: 특정 장소에 주차된 상태
                    elif cur_loc:
                        loc_key = cur_loc.lower()
                        if loc_key in location_coords:
                            lx, ly = location_coords[loc_key]
                            xform.SetTranslate(Gf.Vec3d(lx, ly, 0.40))
                        else:
                            # 좌표 미확인 → 씬 밖으로 숨김
                            xform.SetTranslate(Gf.Vec3d(0.0, 0.0, -10.0))
        except Exception as db_err:
            if frame_count % 300 == 0:
                print(f"[WARNING] 작업대 위치 조회 실패: {db_err}")

        # ── C. Isaac Sim 렌더 프레임 갱신 ──
        simulation_app.update()
        frame_count += 1

        # 상태 요약 로그 (10초마다)
        if frame_count % 300 == 0:
            amr_active = sum(1 for a in amr_paths if r.exists(f"amr:{a}"))
            ws_carried = len(carried_workstations)
            print(f"[SYNC #{frame_count}] AMR 활성: {amr_active}/5대, 이송 중 작업대: {ws_carried}대")

        time.sleep(0.033)  # 약 30Hz

except KeyboardInterrupt:
    print("\n사용자에 의해 종료 요청됨.")

finally:
    pg_conn.close()
    print("=== [Isaac Sim Connector] 안전하게 접속 종료 처리 완료. ===")
    simulation_app.close()

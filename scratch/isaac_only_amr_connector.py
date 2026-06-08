#!/usr/bin/env python3
"""
NVIDIA Isaac Sim ↔ 물류창고 관제 시스템 실시간 3D 동기화 커넥터 (AMR 전용 버전)
================================================================
사용법:  isaac-python scratch/isaac_only_amr_connector.py
맵 파일: src/cobot3/resource/floor_with_con,storage.usd

역할:
  - PostgreSQL 연결 없이 **Redis 전용**으로 동작 (가볍고 빠름)
  - Redis에서 5대 AMR의 실시간 (x, y) 위치를 읽어 3D 씬에 반영 (AMR_01 ~ AMR_05)
  - QR ID("FLOOR_X_{x}_Y_{y}") 파싱을 통해 좌표를 즉시 추출하여 3D 씬 업데이트
"""
import os
import sys
import time

# ──────────────────────────────────────────────
# 1. Isaac Sim 엔진 초기화 (GUI 모드)
# ──────────────────────────────────────────────
print("=== [Isaac Sim AMR-Only Connector] Omniverse Kit 엔진 초기화 중... ===")
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": False})

import omni.usd
from pxr import Usd, UsdGeom, Sdf, Gf
import redis

# ──────────────────────────────────────────────
# 2. 기설정된 USD 맵 스테이지 로드
# ──────────────────────────────────────────────
USD_MAP_PATH = "/home/rokey/cobot3_ws/src/cobot3/resource/Small_map/World3.usd"

usd_context = omni.usd.get_context()
opened = usd_context.open_stage(USD_MAP_PATH)
if not opened:
    print(f"[ERROR] USD 맵 파일을 열 수 없습니다: {USD_MAP_PATH}")
    simulation_app.close()
    sys.exit(1)

stage = usd_context.get_stage()
print(f"[SUCCESS] USD 스테이지 오픈 완료: {USD_MAP_PATH}")
print("  └─ 바닥 QR 격자, 컨베이어, 입출고 스토리지가 세팅된 맵 로드 완료")

# ──────────────────────────────────────────────
# 3. Redis 캐시 데이터베이스 연결
# ──────────────────────────────────────────────
try:
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
    print("[SUCCESS] Redis 연결 완료 (AMR 상태 동기화용).")
except Exception as e:
    print(f"[ERROR] Redis 연결 실패: {e}")
    simulation_app.close()
    sys.exit(1)

# ──────────────────────────────────────────────
# 4. AMR 로봇 3D 모델 동적 생성 (5대)
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
print("\n[AMR Setup] AMR 로봇 5대 3D 모델 생성:")
for i in range(1, 6):
    amr_id = f"AMR_{i:02d}"
    path = f"{AMR_ROOT}/{amr_id}"
    create_amr_prim(path)
    amr_paths[amr_id] = path

# ──────────────────────────────────────────────
# 5. 실시간 동기화 메인 루프 (약 30Hz)
# ──────────────────────────────────────────────
print("\n=== [Isaac Sim AMR-Only Connector] 실시간 3D 동기화 루프 시작 ===")
print("  └─ PostgreSQL 연결 및 Workstation 렌더링 배제")
print("  └─ 종료: CTRL+C\n")

frame_count = 0
try:
    while simulation_app.is_running():
        # Redis에서 5대 AMR 상태 조회
        for amr_id, path_str in amr_paths.items():
            state_data = r.hgetall(f"amr:{amr_id}")
            if not state_data:
                continue

            try:
                # current_qr_id 형식: "FLOOR_X_-25.775_Y_-2.025"
                qr_id = state_data.get("current_qr_id", "")

                # QR ID에서 X, Y 좌표 추출
                x, y = 0.0, 0.0
                if qr_id and qr_id.startswith("FLOOR_X_"):
                    parts = qr_id.replace("FLOOR_X_", "").split("_Y_")
                    if len(parts) == 2:
                        x = float(parts[0])
                        y = float(parts[1])

                # AMR 위치 갱신 (지면 밀착 Z=0.125)
                prim = stage.GetPrimAtPath(path_str)
                if prim:
                    xform = UsdGeom.XformCommonAPI(prim)
                    xform.SetTranslate(Gf.Vec3d(x, y, 0.125))

            except Exception as e:
                pass

        # Isaac Sim 렌더 프레임 갱신
        simulation_app.update()
        frame_count += 1

        # 상태 요약 로그 (10초마다)
        if frame_count % 300 == 0:
            amr_active = sum(1 for a in amr_paths if r.exists(f"amr:{a}"))
            print(f"[AMR SYNC #{frame_count}] AMR 활성 상태: {amr_active}/5대 동기화 중")

        time.sleep(0.033)  # 약 30Hz

except KeyboardInterrupt:
    print("\n사용자에 의해 종료 요청됨.")

finally:
    print("=== [Isaac Sim AMR-Only Connector] 안전하게 종료 완료. ===")
    simulation_app.close()

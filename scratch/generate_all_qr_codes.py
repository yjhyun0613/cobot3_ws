#!/usr/bin/env python3
import os
import sys
import yaml
import cv2
import qrcode
import argparse

def generate_qr(data_str, output_path, box_size=10, border=4):
    """
    지정한 문자열을 담은 QR코드 이미지를 생성하여 지정된 경로에 저장합니다.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(output_path)

def load_map_info(yaml_path):
    """
    yaml 파일 정보와 맵 이미지 크기를 계산하여 맵의 실제 범위 물리 정보를 반환합니다.
    """
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    resolution = data['resolution']
    origin = data['origin']
    img_filename = data['image']
    img_path = os.path.join(os.path.dirname(yaml_path), img_filename)
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Could not load map image at {img_path}")
    height, width = img.shape[:2]
    return {
        "resolution": resolution,
        "origin_x": origin[0],
        "origin_y": origin[1],
        "width_px": width,
        "height_px": height,
        "width_m": width * resolution,
        "height_m": height * resolution
    }

def main():
    parser = argparse.ArgumentParser(description="물류창고 자산용 통합 QR코드 생성기")
    parser.add_argument("--all-floor", action="store_true", help="1,813개의 모든 바닥 격자 QR코드를 생성합니다 (시간이 다소 걸립니다)")
    args = parser.parse_args()

    print("=== 물류창고 통합 QR코드 자산 빌더 구동 ===")
    
    home_dir = os.path.expanduser('~')
    yaml_path = os.path.join(home_dir, "cobot3_ws/src/cobot3/resource/map/warehouse.yaml")
    if not os.path.exists(yaml_path):
        yaml_path = os.path.join(os.getcwd(), "src/cobot3/resource/map/warehouse.yaml")
    try:
        map_info = load_map_info(yaml_path)
        print(f"맵 정보 로드 성공:")
        print(f"  - 원점(Origin): [{map_info['origin_x']}, {map_info['origin_y']}]")
        print(f"  - 해상도: {map_info['resolution']} m/px")
        print(f"  - 크기: {map_info['width_m']:.2f}m x {map_info['height_m']:.2f}m ({map_info['width_px']}x{map_info['height_px']} px)")
    except Exception as e:
        print(f"맵 정보를 불러오지 못했습니다: {e}")
        return

    output_dir = "scratch/qr_assets"
    os.makedirs(os.path.join(output_dir, "robots"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "workstations"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "floor"), exist_ok=True)

    # 1. 로봇 QR코드 생성
    robots = [
        "ROBOT_bg2",
        "ROBOT_sg2_in_01",
        "ROBOT_sg2_in_02",
        "ROBOT_sg2_in_03",
        "ROBOT_sg2_out_00",
        "ROBOT_AMR_01",
        "ROBOT_AMR_02",
        "ROBOT_AMR_03",
        "ROBOT_AMR_04",
        "ROBOT_AMR_05",
    ]
    print("\n[1] 로봇 식별 QR코드 생성 중...")
    for robot in robots:
        path = os.path.join(output_dir, "robots", f"{robot}.png")
        generate_qr(robot, path)
        print(f"  └─ 생성 완료: {path}")

    # 2. 작업대 및 슬롯 QR코드 생성
    print("\n[2] 작업대 및 슬롯 식별 QR코드 생성 중...")
    os.makedirs(os.path.join(output_dir, "workstations", "slots"), exist_ok=True)
    for i in range(1, 11):
        ws_id = f"WS{i:02d}"
        ws = f"WORKSTATION_{ws_id}"
        path = os.path.join(output_dir, "workstations", f"{ws}.png")
        generate_qr(ws, path)
        print(f"  ├─ 작업대 생성 완료: {path}")
        
        # 각 작업대별 8개 슬롯 QR코드 생성
        for slot in range(1, 9):
            slot_str = f"WORKSTATION_{ws_id}_SLOT_{slot}"
            slot_path = os.path.join(output_dir, "workstations", "slots", f"{slot_str}.png")
            generate_qr(slot_str, slot_path)
            # 로그 줄이기 위해 요약 출력 또는 매번 출력
        print(f"  │  └─ 슬롯 1~8 QR코드 생성 완료: {ws_id}")


    # 3. 바닥 격자 QR코드 생성 및 데이터베이스 연동
    print("\n[3] PostgreSQL floor_qr_map 테이블 연동 및 바닥 QR코드 생성...")
    db_conn = None
    pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
    try:
        import psycopg2
        db_conn = psycopg2.connect(
            host=pg_host,
            port=5432,
            user='rokey',
            password='rokey_pass',
            database='warehouse_db'
        )
        print("  - PostgreSQL 데이터베이스 연결 성공.")
    except Exception as db_err:
        print(f"  - [에러] 데이터베이스 연결 실패 (컨테이너 구동 또는 환경변수 확인 필요): {db_err}")
        return

    floor_qrs = []
    try:
        with db_conn.cursor() as cursor:
            cursor.execute("SELECT qr_id FROM floor_qr_map;")
            floor_qrs = [row[0] for row in cursor.fetchall()]
        print(f"  - floor_qr_map 테이블에서 총 {len(floor_qrs)}개의 바닥 QR ID를 조회했습니다.")
    except Exception as query_err:
        print(f"  - [에러] floor_qr_map 조회 실패: {query_err}")
        db_conn.close()
        return
    finally:
        if db_conn:
            db_conn.close()

    # 4. QR코드 이미지 파일 생성 및 동기화 (불필요한 파일 삭제)
    print("\n[4] 바닥 QR코드 이미지 파일 생성 및 동기화...")
    # 이미지 생성
    for qr_id in floor_qrs:
        path = os.path.join(output_dir, "floor", f"{qr_id}.png")
        generate_qr(qr_id, path)
    print(f"  └─ 총 {len(floor_qrs)}개의 바닥 QR코드 이미지 생성 완료.")

    # 미사용 파일 제거 (동기화)
    floor_dir = os.path.join(output_dir, "floor")
    existing_files = os.listdir(floor_dir)
    deleted_count = 0
    for filename in existing_files:
        if filename.endswith(".png"):
            qr_name = filename[:-4]
            if qr_name not in floor_qrs:
                file_path = os.path.join(floor_dir, filename)
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"    [경고] 파일 삭제 실패 ({filename}): {e}")

    if deleted_count > 0:
        print(f"  └─ 레이아웃에 존재하지 않는 미사용 바닥 QR코드 {deleted_count}개 삭제 완료.")

    print(f"\n=== 모든 자산 QR코드 생성 프로세스 종료! 저장 폴더: {output_dir} ===")

if __name__ == "__main__":
    main()

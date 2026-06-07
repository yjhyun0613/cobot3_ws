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
        "ROBOT_amr_01",
        "ROBOT_amr_02",
        "ROBOT_amr_03",
        "ROBOT_amr_04",
        "ROBOT_amr_05",
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


    # 3. 바닥 격자 QR코드 생성
    print("\n[3] 바닥 격자 QR코드 생성 중...")
    margin = 2.0
    spacing = 1.5
    
    x_start = map_info['origin_x'] + margin
    y_start = map_info['origin_y'] + margin
    x_end = map_info['origin_x'] + map_info['width_m'] - margin
    y_end = map_info['origin_y'] + map_info['height_m'] - margin

    # 좌표 리스트 계산 (사용자 요청에 따른 창고 영역 크기 필터 적용)
    x_min, x_max = -38.0, 38.0
    y_min, y_max = -36.08472, 25.0

    x_coords = []
    x = x_start
    while x <= x_end:
        rx = round(x, 3)
        if x_min <= rx <= x_max:
            x_coords.append(rx)
        x += spacing

    y_coords = []
    y = y_start
    while y <= y_end:
        ry = round(y, 3)
        if y_min <= ry <= y_max:
            y_coords.append(ry)
        y += spacing

    total_points = len(x_coords) * len(y_coords)
    print(f"  - 격자 크기: {len(x_coords)}열 x {len(y_coords)}행 = 총 {total_points}개 노드")
    print(f"  - 범위: X [{x_coords[0]} ~ {x_coords[-1]}], Y [{y_coords[0]} ~ {y_coords[-1]}]")

    # 4. 데이터베이스 floor_qr_map 테이블 연동 및 데이터 적재
    print("\n[4] PostgreSQL floor_qr_map 테이블 연동 및 데이터 적재 시작...")
    db_conn = None
    try:
        import psycopg2
        db_conn = psycopg2.connect(
            host='localhost',
            port=5432,
            user='rokey',
            password='rokey_pass',
            database='warehouse_db'
        )
        db_conn.autocommit = True
        print("  - PostgreSQL 데이터베이스 연결 성공.")
    except Exception as db_err:
        print(f"  - [경고] 데이터베이스 연결 실패 (psycopg2 미설치 또는 컨테이너 미구동): {db_err}")
        print("    (격자 맵 파일 생성을 계속 진행합니다)")

    if db_conn:
        try:
            with db_conn.cursor() as cursor:
                # 테이블 비우기
                cursor.execute("TRUNCATE TABLE floor_qr_map CASCADE;")
                
                # 논리 스팟 정의
                logical_spots = {}
                
                # 1) 주차 구역 (spot_01 ~ spot_12)
                parking_coords = [
                    (-10.775, -9.525), (-9.275, -9.525),
                    (-10.775, -6.525), (-9.275, -6.525),
                    (-10.775, -3.525), (-9.275, -3.525),
                    (-10.775, -0.525), (-9.275, -0.525),
                    (-10.775, 2.475),  (-9.275, 2.475),
                    (-10.775, 5.475),  (-9.275, 5.475)
                ]
                for idx, (px, py) in enumerate(parking_coords, 1):
                    spot_name = f"spot_{idx:02d}"
                    logical_spots[(px, py)] = {
                        "name": spot_name,
                        "type": "PARKING_SPOT",
                        "desc": f"Warehouse workstation parking slot {idx:02d}"
                    }
                
                # 2) 입고 로봇 구역 (sg2_in_01_A/B ~ sg2_in_03_A/B)
                inbound_coords = [
                    ((-24.275, -11.025), (-25.775, -11.025)),  # Line 1 (오늘)
                    ((-24.275, -6.525), (-25.775, -6.525)),  # Line 2 (내일)
                    ((-24.275, -2.025), (-25.775, -2.025)) # Line 3 (모레)
                ]
                for robot_idx, (a_coord, b_coord) in enumerate(inbound_coords, 1):
                    # A구역 (Loading)
                    logical_spots[a_coord] = {
                        "name": f"sg2_in_{robot_idx:02d}_A",
                        "type": "LOADING_SPOT",
                        "desc": f"Inbound {robot_idx:02d} A-buffer (Loading)"
                    }
                    # B구역 (Standby)
                    logical_spots[b_coord] = {
                        "name": f"sg2_in_{robot_idx:02d}_B",
                        "type": "STANDBY_SPOT",
                        "desc": f"Inbound {robot_idx:02d} B-buffer (Standby)"
                    }
                
                # 3) 출고 포장 구역 (sg2_out_00_A/B)
                logical_spots[(-3.275, -23.025)] = {
                    "name": "sg2_out_00_A",
                    "type": "PACKAGING_SPOT",
                    "desc": "Outbound packing zone A (Active)"
                }
                logical_spots[(-3.275, -24.525)] = {
                    "name": "sg2_out_00_B",
                    "type": "PACKAGING_SPOT",
                    "desc": "Outbound packing zone B (Standby)"
                }

                # 4) 출고 대기 구역 (stage_01 ~ stage_06)
                staging_coords = [
                    (-18.275, -23.025), (-18.275, -21.525),
                    (-21.275, -23.025), (-21.275, -21.525),
                    (-24.275, -23.025), (-24.275, -21.525)
                ]
                for idx, (sx, sy) in enumerate(staging_coords, 1):
                    spot_name = f"stage_{idx:02d}"
                    logical_spots[(sx, sy)] = {
                        "name": spot_name,
                        "type": "STAGING_SPOT",
                        "desc": f"Outbound staging slot {idx:02d}"
                    }

                # 5) AMR 충전 구역 (charging_01 ~ charging_05)
                charging_coords = [
                    (-10.775, 23.475),
                    (-12.275, 23.475),
                    (-13.775, 23.475),
                    (-15.275, 23.475),
                    (-16.775, 23.475)
                ]
                for idx, (cx, cy) in enumerate(charging_coords, 1):
                    spot_name = f"charging_{idx:02d}"
                    logical_spots[(cx, cy)] = {
                        "name": spot_name,
                        "type": "CHARGING_SPOT",
                        "desc": f"AMR charging slot {idx:02d}"
                    }


                # 대량 삽입용 쿼리 리스트
                insert_data = []
                inserted_logical_spots = set()
                
                for xc in x_coords:
                    for yc in y_coords:
                        qr_id = f"FLOOR_X_{xc}_Y_{yc}"
                        spot_info = logical_spots.get((xc, yc))
                        if spot_info:
                            loc_name = spot_info["name"]
                            loc_type = spot_info["type"]
                            desc = spot_info["desc"]
                            inserted_logical_spots.add((xc, yc))
                        else:
                            loc_name = None
                            loc_type = "PATHWAY"
                            desc = "Warehouse floor grid pathway"
                        
                        insert_data.append((qr_id, xc, yc, 0.0, loc_name, loc_type, desc))

                # 격자에 포함되지 않은 논리 스팟 추가 삽입 (예: offset 배치된 출고 대기 창고 등)
                for (l_x, l_y), spot_info in logical_spots.items():
                    if (l_x, l_y) not in inserted_logical_spots:
                        qr_id = f"FLOOR_X_{l_x}_Y_{l_y}"
                        loc_name = spot_info["name"]
                        loc_type = spot_info["type"]
                        desc = spot_info["desc"]
                        insert_data.append((qr_id, l_x, l_y, 0.0, loc_name, loc_type, desc))

                # Bulk insert using executemany
                cursor.executemany(
                    "INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, z_coord, location_name, location_type, description) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s);",
                    insert_data
                )
                print(f"  - floor_qr_map 테이블에 총 {len(insert_data)}개 레코드 적재 완료!")
        except Exception as insert_err:
            print(f"  - [에러] floor_qr_map 데이터 적재 중 오류 발생: {insert_err}")
        finally:
            db_conn.close()

    # 모든 격자점을 파일로 출력할지 결정
    if args.all_floor:
        print(f"  - 모든 {total_points}개의 격자점 QR코드 생성을 시작합니다. 잠시만 기다려주세요...")
        count = 0
        for xc in x_coords:
            for yc in y_coords:
                floor_str = f"FLOOR_X_{xc}_Y_{yc}"
                path = os.path.join(output_dir, "floor", f"{floor_str}.png")
                generate_qr(floor_str, path)
                count += 1
                if count % 200 == 0:
                    print(f"    - 진행률: {count}/{total_points}개 생성 완료...")
        print(f"  └─ 모든 {total_points}개 바닥 QR코드 생성 완료!")
    else:
        print("  - [안내] 디스크 공간과 시간 절약을 위해 대표 노드(모퉁이 4개 및 중심부) 샘플만 생성합니다.")
        print("    (전체 생성을 원하시면 `python3 scratch/generate_all_qr_codes.py --all-floor` 명령어를 실행하세요)")
        
        # 샘플 노드 목록 지정
        corners = [
            (x_coords[0], y_coords[0]),  # 좌하단
            (x_coords[-1], y_coords[0]), # 우하단
            (x_coords[0], y_coords[-1]), # 좌상단
            (x_coords[-1], y_coords[-1]),# 우상단
            (x_coords[len(x_coords)//2], y_coords[len(y_coords)//2]) # 중심부
        ]
        
        for xc, yc in corners:
            floor_str = f"FLOOR_X_{xc}_Y_{yc}"
            path = os.path.join(output_dir, "floor", f"{floor_str}.png")
            generate_qr(floor_str, path)
            print(f"  └─ 샘플 생성 완료: {path}")

    print(f"\n=== 모든 자산 QR코드 생성 프로세스 종료! 저장 폴더: {output_dir} ===")

if __name__ == "__main__":
    main()

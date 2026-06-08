#!/usr/bin/env python3
import os
import sys
import qrcode
import psycopg2

def generate_qr(data_str, output_path, box_size=10, border=4):
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

def main():
    print("=== [20x20m 개편 맵 전용] 격자 QR코드 및 DB 적재 빌더 구동 ===")
    
    output_dir = "/home/rokey/cobot3_ws/scratch/qr_assets"
    os.makedirs(os.path.join(output_dir, "floor"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "robots"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "workstations", "slots"), exist_ok=True)

    # 1. 20x20m 맵의 1.5m 간격 전체 물리 좌표 대역 (이미지 생성용)
    coords_all = []
    val = -9.0
    while val <= 9.01:
        coords_all.append(round(val, 2))
        val += 1.5
    
    # 2. 이미지 생성 (기존 169개 바닥 QR코드 파일 유지/재생성)
    print("\n[1] 169개 바닥 QR코드 이미지 생성 시작...")
    for xc in coords_all:
        for yc in coords_all:
            floor_str = f"FLOOR_X_{xc}_Y_{yc}"
            path = os.path.join(output_dir, "floor", f"{floor_str}.png")
            if not os.path.exists(path):
                generate_qr(floor_str, path)
    print("  └─ 모든 바닥 QR코드 PNG 생성 완료.")

    # 3. 로봇 및 작업대 QR코드 재생성
    robots = [
        "ROBOT_bg2", "ROBOT_sg2_in_01", "ROBOT_sg2_in_02", "ROBOT_sg2_in_03",
        "ROBOT_sg2_out_00", "ROBOT_AMR_01", "ROBOT_AMR_02", "ROBOT_AMR_03",
        "ROBOT_AMR_04", "ROBOT_AMR_05"
    ]
    for robot in robots:
        path = os.path.join(output_dir, "robots", f"{robot}.png")
        generate_qr(robot, path)

    for i in range(1, 11):
        ws_id = f"WS{i:02d}"
        ws = f"WORKSTATION_{ws_id}"
        path = os.path.join(output_dir, "workstations", f"{ws}.png")
        generate_qr(ws, path)
        for slot in range(1, 9):
            slot_str = f"WORKSTATION_{ws_id}_SLOT_{slot}"
            slot_path = os.path.join(output_dir, "workstations", "slots", f"{slot_str}.png")
            generate_qr(slot_str, slot_path)
    print("  └─ 로봇 및 작업대/슬롯 QR코드 PNG 생성 완료.")

    # 4. PostgreSQL floor_qr_map 테이블 갱신 (활성 격자 대역 X: -3.0 ~ 9.0, Y: -9.0 ~ 9.0)
    print("\n[2] PostgreSQL 데이터베이스 적재 시작...")
    try:
        db_conn = psycopg2.connect(
            host='localhost',
            port=5432,
            user='rokey',
            password='rokey_pass',
            database='warehouse_db'
        )
        db_conn.autocommit = True
        print("  - PostgreSQL 연결 성공.")
    except Exception as e:
        print(f"  - [에러] PostgreSQL 연결 실패: {e}")
        return

    # 활성 격자 범위 산출 (X: -3.0 ~ 9.0, Y: -9.0 ~ 9.0)
    coords_x = []
    val = -3.0
    while val <= 9.01:
        coords_x.append(round(val, 2))
        val += 1.5

    coords_y = []
    val = -9.0
    while val <= 9.01:
        coords_y.append(round(val, 2))
        val += 1.5

    logical_spots = {}
    
    # 1) 주차 구역 (spot_01 ~ spot_10)
    parking_coords = [
        (1.5, 3.0), (0.0, 3.0),   # spot_01, spot_02
        (1.5, 0.0), (0.0, 0.0),   # spot_03, spot_04
        (1.5, -3.0), (0.0, -3.0), # spot_05, spot_06
        (1.5, -6.0), (0.0, -6.0), # spot_07, spot_08
        (1.5, -9.0), (0.0, -9.0)  # spot_09, spot_10
    ]
    for idx, (px, py) in enumerate(parking_coords, 1):
        logical_spots[(px, py)] = {
            "name": f"spot_{idx:02d}",
            "type": "PARKING_SPOT",
            "desc": f"Warehouse workstation parking slot {idx:02d}"
        }

    # 2) 입고 로봇 구역 (sg2_in_01_A/B ~ sg2_in_03_A/B)
    inbound_coords = [
        ((7.5, 1.5), (6.0, 1.5)),    # Line 1 (오늘)
        ((7.5, -3.0), (6.0, -3.0)),  # Line 2 (내일)
        ((7.5, -7.5), (6.0, -7.5))   # Line 3 (모레)
    ]
    for robot_idx, (a_coord, b_coord) in enumerate(inbound_coords, 1):
        logical_spots[a_coord] = {
            "name": f"sg2_in_{robot_idx:02d}_A",
            "type": "LOADING_SPOT",
            "desc": f"Inbound {robot_idx:02d} A-buffer (Loading)"
        }
        logical_spots[b_coord] = {
            "name": f"sg2_in_{robot_idx:02d}_B",
            "type": "STANDBY_SPOT",
            "desc": f"Inbound {robot_idx:02d} B-buffer (Standby)"
        }

    # 3) 출고 포장 구역 (sg2_out_00_A/B) - 신규 좌표 반영 (0.0, 7.5) 및 (0.0, 9.0)
    logical_spots[(0.0, 7.5)] = {
        "name": "sg2_out_00_A",
        "type": "PACKAGING_SPOT",
        "desc": "Outbound packing zone A (Active)"
    }
    logical_spots[(0.0, 9.0)] = {
        "name": "sg2_out_00_B",
        "type": "PACKAGING_SPOT",
        "desc": "Outbound packing zone B (Standby)"
    }

    # 4) 출고 대기 구역 (stage_01 ~ stage_04 - st05/st06 제외 반영)
    staging_coords = [
        (4.5, 9.0), (4.5, 7.5),  # stage_01, stage_02
        (7.5, 9.0), (7.5, 7.5)   # stage_03, stage_04
    ]
    for idx, (sx, sy) in enumerate(staging_coords, 1):
        logical_spots[(sx, sy)] = {
            "name": f"stage_{idx:02d}",
            "type": "STAGING_SPOT",
            "desc": f"Outbound staging slot {idx:02d}"
        }

    # 5) AMR 충전 구역 (charging_01 ~ charging_05)
    charging_coords = [
        (-3.0, -9.0),
        (-3.0, -7.5),
        (-3.0, -6.0),
        (-3.0, -4.5),
        (-3.0, -3.0)
    ]
    for idx, (cx, cy) in enumerate(charging_coords, 1):
        logical_spots[(cx, cy)] = {
            "name": f"charging_{idx:02d}",
            "type": "CHARGING_SPOT",
            "desc": f"AMR charging slot {idx:02d}"
        }

    # 6) SG2 로봇 구역 (장애물, 대시보드 겹침 방지 대표 명칭 처리)
    # SG2_IN_x는 2칸 너비 직사각형 1개로 합쳐서 중심에 라벨링 처리
    sg2_robot_named = {
        (6.0, 3.0): "SG2_IN_1",
        (6.0, -1.5): "SG2_IN_2",
        (6.0, -6.0): "SG2_IN_3",
        (-3.0, 9.0): "SG2_OUT"
    }
    
    # 7.5 라인의 인접한 칸들은 이름 없는 정적 장애물로 처리 (가시성 증대 및 글씨 겹침 방지)
    sg2_robot_unnamed = {
        # SG2_IN 2번째 칸들
        (7.5, 3.0), (7.5, -1.5), (7.5, -6.0),
        # SG2_OUT 나머지 3칸
        (-1.5, 7.5), (-3.0, 7.5), (-1.5, 9.0)
    }

    # 7) 컨베이어벨트 구역 (AMR 진입 불가 정적 장애물)
    conveyor_coords = [
        (9.0, 9.0), (9.0, 7.5), (9.0, 6.0), (9.0, 4.5), (9.0, 3.0),
        (9.0, 1.5), (9.0, 0.0), (9.0, -1.5), (9.0, -3.0), (9.0, -4.5),
        (9.0, -6.0), (9.0, -7.5), (9.0, -9.0)
    ]

    insert_data = []
    
    for xc in coords_x:
        for yc in coords_y:
            qr_id = f"FLOOR_X_{xc}_Y_{yc}"
            
            # 1. 특수 작업 스팟 매핑
            if (xc, yc) in logical_spots:
                spot_info = logical_spots[(xc, yc)]
                loc_name = spot_info["name"]
                loc_type = spot_info["type"]
                desc = spot_info["desc"]
                
            # 2. SG2 로봇 대표 명칭 장애물
            elif (xc, yc) in sg2_robot_named:
                loc_name = sg2_robot_named[(xc, yc)]
                loc_type = "STATIC_OBSTACLE"
                desc = f"SG2 robot position area (AMR Keepout)"
                
            # 3. SG2 로봇 무명 장애물 (글씨 겹침 회피 및 2칸 가시성 확보)
            elif (xc, yc) in sg2_robot_unnamed:
                loc_name = ""
                loc_type = "STATIC_OBSTACLE"
                desc = f"SG2 robot helper area (AMR Keepout)"
                
            # 4. 컨베이어벨트 장애물 구역
            elif (xc, yc) in conveyor_coords:
                loc_name = "CONVEYOR_BELT"
                loc_type = "STATIC_OBSTACLE"
                desc = f"Conveyor belt area (AMR Keepout)"
                
            # 5. 일반 통로
            else:
                loc_name = None
                loc_type = "PATHWAY"
                desc = "Warehouse floor grid pathway"
            
            insert_data.append((qr_id, xc, yc, 0.0, loc_name, loc_type, desc))

    try:
        with db_conn.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE floor_qr_map CASCADE;")
            cursor.executemany(
                "INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, z_coord, location_name, location_type, description) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s);",
                insert_data
            )
            print(f"  - floor_qr_map 테이블에 총 {len(insert_data)}개 격자 노드 적재 완료!")
    except Exception as e:
        print(f"  - [에러] floor_qr_map 테이블 데이터 적재 중 오류: {e}")
    finally:
        db_conn.close()
        print("=== 격자 생성 및 DB 적재 완료! ===")

if __name__ == "__main__":
    main()

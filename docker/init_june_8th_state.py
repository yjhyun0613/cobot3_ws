#!/usr/bin/env python3
import psycopg2
import redis

def init_june_8th_simulation():
    print("=== 🚀 6월 8일 오전 09:00 관제탑 초기 상태 마스킹 시작 ===")
    
    # 1. DB 및 Redis 연결 설정 (파트너님의 환경 정보 반영)
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            user="rokey",
            password="rokey_pass",
            database="warehouse_db"
        )
        cursor = conn.cursor()
        r_client = redis.Redis(host='localhost', port=6379, db=0)
    except Exception as e:
        print(f"❌ 서비스 연결 실패 (도커 컨테이너 구동 확인 필요): {e}")
        return

    # 2. Redis 오늘 날짜 고정 및 초기화
    r_client.set("system:today_date", "2026-06-08")
    r_client.set("system:inbound_started", "false")
    print("📅 [Redis] system:today_date ➔ '2026-06-08' 동기화 완료")

    # 3. PostgreSQL 기존 가동 데이터 리셋 (기본 QR 격자 맵 데이터 제외)
    cursor.execute("UPDATE warehouse_locations SET workstation_id = NULL, status = 'EMPTY';")
    cursor.execute("DELETE FROM packages;")
    cursor.execute("DELETE FROM workstations;")
    print("🧹 [PostgreSQL] 기존 가동 상태 및 패키지 데이터 초기화 완료")

    # 4. 파트너님 규칙 반영: 총 10대 작업대 고정 주차 레이아웃 주입
    workstation_positions = [
        ('WS01', 'stage_01', 'WORKSTATION_WS01'),       # 출고 대기 창고 (8칸 완충 상태 보관)
        ('WS02', 'sg2_in_01_A', 'WORKSTATION_WS02'),    # 1번 입고 Active (오늘 물량 5칸 차 있음)
        ('WS03', 'sg2_in_02_A', 'WORKSTATION_WS03'),    # 2번 입고 Active (내일 물량 5칸 차 있음)
        ('WS04', 'sg2_in_03_A', 'WORKSTATION_WS04'),    # 3번 입고 Active (모레 물량 0칸 비어 있음)
        ('WS05', 'spot_01', 'WORKSTATION_WS05'),        # 메인 창고 주차장 정렬 예비대
        ('WS06', 'spot_02', 'WORKSTATION_WS06'),
        ('WS07', 'spot_03', 'WORKSTATION_WS07'),
        ('WS08', 'spot_04', 'WORKSTATION_WS08'),
        ('WS09', 'spot_05', 'WORKSTATION_WS09'),
        ('WS10', 'spot_06', 'WORKSTATION_WS10')
    ]

    for ws_id, loc, qr in workstation_positions:
        # workstations 테이블 등록
        cursor.execute(
            "INSERT INTO workstations (workstation_id, current_location, qr_id, status) VALUES (%s, %s, %s, 'WAITING');",
            (ws_id, loc, qr)
        )
        # warehouse_locations 주차장 맵 업데이트
        cursor.execute(
            "UPDATE warehouse_locations SET workstation_id = %s, status = 'OCCUPIED' WHERE spot_id = %s;",
            (ws_id, loc)
        )
    print("📍 [PostgreSQL] 총 10대 작업대 정밀 오와 열 배치 완료")

    # 5. 과거 잔여 이월 재고 데이터 (총 18개 패키지) 슬롯 상세 주입
    # [WS01 - 8칸 완충 / 6월 8일 출고분]
    ws01_pkgs = [
        ('PKG_20260606_001', '신민준', '2026-06-08'), ('PKG_20260606_002', '임서현', '2026-06-08'),
        ('PKG_20260606_004', '오예준', '2026-06-08'), ('PKG_20260606_007', '박윤서', '2026-06-08'),
        ('PKG_20260606_020', '신윤서', '2026-06-08'), ('PKG_20260607_003', '윤서현', '2026-06-08'),
        ('PKG_20260607_005', '이서준', '2026-06-08'), ('PKG_20260607_007', '강민준', '2026-06-08')
    ]
    # [WS02 - 5칸 누적 / 6월 8일 출고분]
    ws02_pkgs = [
        ('PKG_20260607_008', '오주원', '2026-06-08'), ('PKG_20260607_009', '최지민', '2026-06-08'),
        ('PKG_20260607_017', '박윤서', '2026-06-08'), ('PKG_20260607_018', '정민준', '2026-06-08'),
        ('PKG_20260607_020', '최지후', '2026-06-08')
    ]
    # [WS03 - 5칸 누적 / 6월 9일 출고분]
    ws03_pkgs = [
        ('PKG_20260607_001', '정서준', '2026-06-09'), ('PKG_20260607_006', '박민서', '2026-06-09'),
        ('PKG_20260607_011', '홍하은', '2026-06-09'), ('PKG_20260607_014', '황하준', '2026-06-09'),
        ('PKG_20260607_019', '강다은', '2026-06-09')
    ]

    def insert_packages(pkg_list, target_ws):
        for idx, (p_id, c_name, r_zone) in enumerate(pkg_list):
            slot = idx + 1
            cursor.execute(
                """INSERT INTO packages (package_id, customer_name, route_zone, status, workstation_id, slot_number, qr_id) 
                   VALUES (%s, %s, %s, 'IN_WORKSTATION', %s, %s, %s);""",
                (p_id, c_name, r_zone, target_ws, slot, f"QR_{p_id}")
            )

    insert_packages(ws01_pkgs, 'WS01')
    insert_packages(ws02_pkgs, 'WS02')
    insert_packages(ws03_pkgs, 'WS03')
    
    conn.commit()
    cursor.close()
    conn.close()
    print("📦 [PostgreSQL] 18개 이월 상품 'IN_WORKSTATION' 상태 주입 성공!")
    print("=== ✨ 발표 데모용 기동 준비 완료! ===\n")

if __name__ == "__main__":
    init_june_8th_simulation()
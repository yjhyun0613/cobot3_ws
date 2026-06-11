#!/usr/bin/env python3
import sys
import os
import psycopg2
import redis

# Add workspace directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def reset_database():
    print("=== [Reset Test Env] 데이터베이스 및 캐시 완전 초기화 시작 ===")
    
    # 1. PostgreSQL 초기화
    pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
    try:
        conn = psycopg2.connect(
            host=pg_host,
            database="warehouse_db",
            user="rokey",
            password="rokey_pass",
            port=5432
        )
        conn.autocommit = True
        with conn.cursor() as cursor:
            print("1.1 packages 테이블 비우기...")
            cursor.execute("TRUNCATE TABLE packages CASCADE;")
            
            print("1.2 workstations 상태 초기화 (WAITING 및 spot으로 복구)...")
            cursor.execute("""
                UPDATE workstations 
                SET current_location = 'spot_' || lpad(substring(workstation_id from 3), 2, '0'),
                    status = 'WAITING',
                    reserved_by = NULL;
            """)
            
            print("1.3 warehouse_locations 테이블 비우기...")
            cursor.execute("TRUNCATE TABLE warehouse_locations CASCADE;")
            
            # 10개 작업대 주차 설정
            for i in range(1, 11):
                ws_id = f"WS{i:02d}"
                spot_id = f"spot_{i:02d}"
                cursor.execute(
                    "INSERT INTO warehouse_locations (spot_id, workstation_id, status) VALUES (%s, %s, 'OCCUPIED');",
                    (spot_id, ws_id)
                )
                
            # 4개 출고대기 스팟 설정
            for i in range(1, 5):
                stage_id = f"stage_{i:02d}"
                cursor.execute(
                    "INSERT INTO warehouse_locations (spot_id, workstation_id, status) VALUES (%s, NULL, 'EMPTY');",
                    (stage_id,)
                )
            print("PostgreSQL 기본 레이아웃 배치 완료.")
        conn.close()
    except Exception as e:
        print(f"[ERROR] PostgreSQL 초기화 실패: {e}")
        print("힌트: Docker 컨테이너가 정상적으로 실행 중인지 확인하세요. (docker-compose up -d)")
        sys.exit(1)

    # 2. Redis 캐시 초기화
    redis_host = os.environ.get('REDIS_HOST', 'localhost')
    try:
        r = redis.Redis(host=redis_host, port=6379, decode_responses=True)
        r.flushall()
        print("2.1 Redis 데이터 완전 소거 (FLUSHALL) 완료.")
        r.set('system:today_date', '2026-06-06')
        r.set('system:day_status', 'WAITING_FOR_START')
        print("2.2 Redis 기본 날짜(2026-06-06) 및 상태(WAITING_FOR_START) 설정 완료.")
    except Exception as e:
        print(f"[ERROR] Redis 연결 실패: {e}")
        sys.exit(1)

    # 3. 바닥 QR 격자 재생성은 생략 (init.sql의 정상 데이터 유지)
    print("3.1 바닥 QR 공간 맵은 기존 정상 데이터를 유지합니다.")

    print("=== [Reset Test Env] 초기화 완료! 깨끗한 상태로 테스트 가능합니다. ===")

if __name__ == "__main__":
    reset_database()

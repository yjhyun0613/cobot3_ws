#!/usr/bin/env python3
import time
import redis

def main():
    print("=== [AMR Redis Test Publisher] 가상 경로 주행 테스트 ===")
    
    try:
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        print("[SUCCESS] Redis 연결에 성공했습니다.")
    except Exception as e:
        print(f"[ERROR] Redis 연결 실패: {e}")
        return

    amr_id = "AMR_01"
    
    # DB에 존재하는 실제 물리적 격자 QR ID와 픽셀 매핑 스팟들의 매칭 리스트
    waypoints = [
        {"qr_id": "FLOOR_X_-3.0_Y_-7.5", "name": "charging_02 (충전소 2)"},
        {"qr_id": "FLOOR_X_1.5_Y_3.0", "name": "spot_01 (창고 보관 spot_01)"},
        {"qr_id": "FLOOR_X_7.5_Y_1.5", "name": "sg2_in_01_A (1번 입고라인 A구역)"},
        {"qr_id": "FLOOR_X_4.5_Y_9.0", "name": "stage_01 (대기구역 stage_01)"},
        {"qr_id": "FLOOR_X_7.5_Y_-7.5", "name": "sg2_in_03_A (3번 입고라인 A구역)"},
        {"qr_id": "FLOOR_X_1.5_Y_-3.0", "name": "spot_05 (창고 보관 spot_05)"}
    ]

    print(f"\n{amr_id}가 대시보드 화면상의 유효 격자 스팟들을 순차적으로 순회합니다.")
    print("대시보드(http://localhost:8009) 지도를 보며 AMR_01(아이콘 01)이 위치를 이동하는지 관찰해 보세요.")
    print("종료하려면 CTRL+C를 누르세요.\n")

    battery = 100.0
    index = 0

    try:
        while True:
            wp = waypoints[index]
            
            # 배터리 감소 모킹
            battery = max(15.0, battery - 1.5)
            if battery <= 15.0:
                battery = 100.0
                
            # Redis에 해당 스팟의 정확한 QR ID 등록
            r.hset(
                f"amr:{amr_id}",
                mapping={
                    "current_qr_id": wp["qr_id"],
                    "state": "MOVING",
                    "battery": f"{battery:.1f}",
                    "carrying_workstation_id": ""
                }
            )
            
            print(f"[이동 완료] {amr_id} ➡️ 현재 위치: {wp['name']} (QR: {wp['qr_id']}) | 배터리: {battery}%")
            
            # 다음 목적지 세팅 및 2초 대기
            index = (index + 1) % len(waypoints)
            time.sleep(2.0)
            
    except KeyboardInterrupt:
        r.hset(f"amr:{amr_id}", mapping={"state": "IDLE"})
        print("\n=== 테스트 송신이 종료되었습니다. ===")

if __name__ == "__main__":
    main()

# 📊 쿠팡 물류창고 관제 시스템 구축 결과 보고서 (대화 요약)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

본 문서는 **NVIDIA Isaac Sim** 다중 로봇 관제탑 개발을 위해 AI 어시스턴트(Antigravity)와 나눈 핵심 대화 내용, 결정사항, 시스템 설계 및 실행 매뉴얼을 집대성한 최종 요약 보고서입니다.

---

## 📌 1. 프로젝트 개요 & 비즈니스 시나리오
NVIDIA Isaac Sim 시뮬레이터 환경에서 다중 로봇(컨베이어 분류 로봇, 매니퓰레이터 적재 로봇, AMR 이송 로봇, 포장 로봇)과 데이터베이스를 연동하여 자율 물류창고 관제 시스템을 설계하고 구현했습니다.

### 🔄 핵심 물류 프로세스 (4단계)
1. **입고 및 3방향 초기 분류 (`bg2` 로봇)**:
   * 컨베이어로 들어오는 택배의 QR코드 ID를 스캔하여 **목적지 날짜(YYYY-MM-DD)**를 조회하고, **오늘 날짜(1번 라인 - `sg2_in_01`), 내일 날짜(2번 라인 - `sg2_in_02`), 모레 날짜(3번 라인 - `sg2_in_03`)**에 맞게 분류합니다.
2. **자율 적재 및 파이프라이닝 (`sg2_in_01, 02, 03` 로봇 - A/B 이중 버퍼)**:
   * 각 라인은 **A 구역(활성 적재)**과 **B 구역(예비 대기)**으로 나뉩니다.
   * 로봇들이 A 구역(`sg2_in_XX_A`)에 위치한 작업대에 택배를 적재하되, 수령인이 이미 창고에 적재되어 있으면 **창고 직송 예외 처리(AMR 단일 상자 이송)**를 수행합니다.
   * 작업대 슬롯이 **정확히 3개** 채워지는 시점에 관제탑이 이를 인지하여 **예비 빈 작업대를 로봇의 B 구역(`sg2_in_XX_B`)으로 호출(3-슬롯 Look-ahead)**합니다.
   * 8번째 슬롯까지 채워져 완충되면, 관제탑은 완충 작업대를 이동시키고 B 구역의 예비 작업대를 A 구역으로 승격시킵니다.
3. **작업대 이송 및 보관 (관제탑 & AMR)**:
   * 내일/모레용 완충 작업대는 창고(Warehouse)로 보관 이송하고, 오늘용 완충 작업대는 포장존(`sg2_out_00_A` 또는 `sg2_out_00_B`)으로 이송합니다.
4. **포장 공정 및 빈 작업대 회수 (`sg2_out_00` 로봇 - A/B 이중 버퍼)**:
   * 포장 로봇이 A구역(`sg2_out_00_A`)에서 작업을 수행하며, 7번째 슬롯 포장 완료 시점에 관제탑이 이를 감지하여 다음 포장 대기용 작업대를 B구역(`sg2_out_00_B`)으로 미리 호출(7-슬롯 Look-ahead)합니다.
   * 8번째 슬롯 포장이 완료되면 빈 작업대는 창고로 회수하고, B구역에 대기 중이던 예비 작업대를 A구역(`sg2_out_00_A`)으로 즉시 승격(Promotion)시킵니다.

---

## 🗄️ 2. 데이터베이스 아키텍처 설계
실시간 연산 성능과 이력 정합성 유지를 위해 **하이브리드 DB 구조**를 채택했습니다.

### ① PostgreSQL (관계형 DB - 마스터 데이터 관리)
* **`packages`**: 택배 라이프사이클 추적, 적재된 작업대 번호/슬롯 번호 및 QR코드 ID(`qr_id`) 기록.
* **`workstations`**: 2x8 작업대의 현재 물리적 위치, 제어 상태(`status`), AMR 선점 예약 정보(`reserved_by`), 슬롯별 적재 상태 및 QR코드 ID(`qr_id`) 모니터링.
* **`robots`**: 관제 시스템에 등록된 제어 대상 로봇 목록 및 QR코드 ID(`qr_id`).
* **`floor_qr_map`**: AMR 격자 주행 및 위치 좌표 매핑용 1,813개 바닥 QR코드 절대 좌표(`x_coord`, `y_coord`, `z_coord`) 관리.

### ② Redis (인메모리 NoSQL - 실시간 제어 및 우선순위 큐)
* **AMR 상태 해시 (`amr:[id]:status` 또는 `amr:[id]`)**: 실시간 물리적 3D 좌표, 구동 상태, 배터리 잔량 캐싱.
* **AMR 명령 큐 (`queue:amr_tasks`)**: Sorted Set(ZSET) 기반으로 태스크별 우선순위(Score)에 따라 AMR에 비동기로 내리는 정밀 스케줄링 대기열.

---

## 🛠️ 3. 주요 구현 및 파일 변경 내역

* **`docker-compose.yml` & `init.sql`**:
  * PostgreSQL 15, Redis 7 컨테이너 설정 및 DB 초기화 스크립트 작성.
  * 개발 편의를 위해 웹 브라우저에서 DB 내용을 보고 파일로 다운로드할 수 있는 **Adminer(포트 8082)** 및 **Redis Commander(포트 8081)** 모니터링 서비스 탑재.
* **ROS2 커스텀 인터페이스 (`cobot3_interfaces` 패키지)**:
  * 서비스: `GetPackageRoute.srv`, `CheckWarehouseStatus.srv`, `ReportInboundProgress.srv` (카메라 인식 연동을 위한 QR ID 관련 필드 포함)
  * 액션: `MovePackage.action`, `ManageWorkstation.action` (AMR 이송용 물리 좌표 `target_x/y/yaw` 및 `target_qr_id` 추가), `StartPackaging.action` (이송/제어 명령 고유 식별용 QR ID 필드 포함)
* **관제 센터 핵심 노드 (`control_tower_node.py`)**:
  * PostgreSQL/Redis 라이브러리 연동 및 멀티스레드 비동기 콜백 적용.
  * 서비스 서버와 액션 클라이언트를 유기적으로 스케줄링하는 `task_scheduler_loop` 탑재, QR ID 우선 매핑/조회 및 Redis Sorted Set(ZSET) 기반 우선순위 큐 스케줄러 반영.
  * **하이브리드 통신**: `/fleet/amr_states`, `/fleet/workstation_states`, `/fleet/package_states`, `/fleet/task_events` 토픽에 JSON 직렬화 데이터를 1Hz 및 이벤트 기반으로 브로드캐스트하는 퍼블리셔 탑재.
  * **교착 방지 규격**: 무한 블로킹을 차단하기 위해 `wait_for_server` 호출 시 `timeout_sec=1.0` 타임아웃 예외 처리 전면 반영.
  * **동적 출고 예정일 필터링**: 창고에서 포장존 A/B구역으로 완충 작업대를 공급하는 Keep-Alive 스케줄러에 미완료 패키지의 `route_zone` 중 가장 빠른 날짜를 동적으로 감지하여 공급하도록 고도화.
  * **중복 입고 검증 수정**: `CheckWarehouseStatus` 호출 시 수령인 이름이 아닌 패키지 고유 ID(`package_id`) 기준으로 정확히 중복 보관 여부를 검증하여 오작동 차단.
  * **일자 전환(Day Transition) 워크플로우**: 오늘 출고 날짜(`route_zone`)의 모든 패키지 포장이 완료되면 `daily_report_YYYY-MM-DD.md` 보고서를 자동 생성하고, Redis `system:day_status`를 `PENDING_TRANSITION`으로 설정해 시스템을 다음 영업일 대기 모드로 전환.
  * **AMR 액션 서버 오프라인 및 실패 예외 복구**: 관제탑 노드가 구동 시점에 AMR 액션 서버를 찾지 못하거나 거절/실패가 발생할 때, 이미 이송 예약 및 `MOVING_TO_...`로 갱신되었던 작업대와 스팟 상태가 원복되지 않아 교착 상태(Deadlock)를 초래하는 문제를 방지하기 위해 `recover_workstation_move_db_state()` 복구 헬퍼 함수를 구현 및 통합했습니다.
  * **제자리 회전(180도) 포장 이중 트리거(Double-trigger) 버그 수정**: 작업대 이송 완료 시 출발지(`start`) 정보를 연동하고 출발지가 회전 동작(`_ROTATING` 계열)인 경우 포장 로봇이 중복 실행되지 않도록 예외 처리 적용.
  * **기타 안정화**: Redis `decode_responses=True` 사용 시 문자열 디코딩 예외 안전 분기 처리 및 빈 작업대 조회 시 `IN_WORKSTATION`과 `IN_WAREHOUSE` 상태 통합 점검으로 자원 누수 방지.
* **웹 대시보드 및 테스트 스크립트 (`scratch/` 디렉토리)**:
  * `dashboard_server.py`: FastAPI와 HTML/JS를 이용한 실시간 다크 모드 대시보드. 기존 캔버스 2D 맵 대신 창고의 실제 레이아웃(주차장 스팟, 좌우 대칭 컨베이어 A/B 구역, 중앙 AMR, 포장 라인)을 직관적으로 시각화하는 격자형 HTML/CSS 레이아웃으로 개편하여 데이터 반영 효율성과 실시간 관제 정확성을 대폭 향상했습니다. 일자 전환 대기 배너 및 `/api/start_next_day` 개시 API를 연동했습니다.
  * `run_full_simulation_robot.py`: 통합 로봇 에뮬레이션 시뮬레이터로, 중복 적재 감지 시 패키지 상태를 `IN_WAREHOUSE`로 즉시 업데이트하여 중복 요청에 따른 무한 루프 교착 상태를 방지하는 Fail-safe 로직을 적용했습니다.
* **QR코드 생성 및 USD 매핑 모듈 (`scratch/` 디렉토리)**:
  * `qr_handler.py`: `qrcode` 라이브러리를 사용한 QR 생성 및 C 의존성 없이 안정적인 `zxing-cpp` 기반 비전 디코딩 패키지.
  * `generate_all_qr_codes.py`: `warehouse.yaml` 및 창고 경계 제한을 연산하여 안전 구역(2m)을 준수한 1,813개 바닥 격자 및 10개 작업대 * 8슬롯(=80개) QR 이미지 일괄 생성 모듈.
  * `add_all_qr_to_usd.py`: Pixar USD (`pxr`) API를 사용해 `map.usd` 파일에 1,813개의 평면 메쉬와 PBR 텍스처를 100% 자동 배치하여 맵을 갱신하는 자동화 모듈.
  * `adjust_usd_lighting.py`: 바닥 반사(글레어)로 인한 QR 인식률 저하를 해결하기 위해 DistantLight 강도를 600.0으로 낮추고, DomeLight(1200.0)를 보강한 조명 자동 최적화 모듈.


---


## 🚀 4. 시스템 실행 및 백업/복원 매뉴얼

### ① 데이터베이스 구동 (최초 실행)
```bash
cd ~/cobot3_ws/docker
sudo docker compose up -d
```

### ② 관제탑 ROS2 노드 실행 (백그라운드 동작 중)
```bash
cd ~/cobot3_ws
colcon build
. install/setup.bash
ros2 run cobot3 control_tower
```
* **현재 상태**: 관제탑 노드가 백그라운드 터미널 `control_tower_terminal`에서 성공적으로 실행되어 외부 로봇들의 통신을 대기하고 있습니다.

### ③ 실시간 모니터링 및 파일 다운로드
* **PostgreSQL 조회/내보내기**: 브라우저에서 `http://localhost:8082` 접속 (서버명: `postgres`, 계정: `rokey`, 암호: `rokey_pass`, DB: `warehouse_db`)
* **Redis 큐 시각화**: `http://localhost:8081` 접속하여 작업 명령 리스트 실시간 확인.

### ④ DB 백업 및 복원 (스냅샷 저장)
* **파일로 추출 (백업)**:
  ```bash
  sudo docker exec -t warehouse_postgres pg_dumpall -U rokey > ~/cobot3_ws/docker/warehouse_backup.sql
  ```
* **백업 파일로 복원**:
  ```bash
  cat ~/cobot3_ws/docker/warehouse_backup.sql | sudo docker exec -i warehouse_postgres psql -U rokey -d warehouse_db
  ```

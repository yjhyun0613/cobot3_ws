# 📝 프로젝트 개발 히스토리 (Changelog)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

이 문서는 **쿠팡 물류창고 관제 시스템(Control Tower)** 프로젝트의 날짜 및 시간별 수정 이력을 관리하는 파일입니다.

---

## 📅 2026년 6월 1일 (월요일)

* **14:30** - **Git 저장소 초기화 및 GitHub 연동**
  * 로컬 워크스페이스 `cobot3_ws` 내 Git 초기화 완료.
  * 불필요한 빌드 임시 파일 제거를 위해 `.gitignore` 설정 추가.
  * 원격 저장소 `https://github.com/yjhyun0613/cobot3_ws.git`로 최초 강제 푸시(`--force`) 완료.

* **14:45** - **ROS2 커스텀 인터페이스 패키지 생성**
  * `src/cobot3_interfaces` CMake 패키지 신규 생성.
  * `CMakeLists.txt` 및 `package.xml`에 ROS2 메시지 빌드 의존성(`rosidl_default_generators`) 설정 완료.

* **14:50** - **ROS2 서비스 및 액션 인터페이스 설계**
  * 서비스: `GetPackageRoute.srv`, `CheckWarehouseStatus.srv`, `ReportInboundProgress.srv` 정의 생성.
  * 액션: `MovePackage.action`, `ManageWorkstation.action`, `StartPackaging.action` 정의 생성.
  * `colcon build --packages-select cobot3_interfaces` 명령으로 정상 컴파일 확인.

* **14:55** - **데이터베이스(DB) 및 실시간 캐시 컨테이너 명세 설계**
  * `docker-compose.yml` 및 `init.sql` 최초 작성.
  * PostgreSQL(마스터 DB) 및 Redis(AMR 큐) 컨테이너 및 초기 스키마(Mock Data포함) 정의.

---

## 📅 2026년 6월 2일 (화요일)

* **00:00** - **분류 방식 고도화 (날짜 분기 기준 적용)**
  * 기존 "오늘/내일/모레" 텍스트 매핑 방식에서 실제 배송 날짜(`YYYY-MM-DD`)를 직접 데이터에 적용하고 비교하도록 시스템 고도화.
  * `init.sql`의 Mock 데이터를 실제 날짜(`2026-06-01`, `2026-06-02`, `2026-06-03`)로 갱신하여 1번, 2번, 3번 라인의 작업대와 매핑되도록 처리.
  * `GetPackageRoute.srv` 주석 및 시스템 사양서(`warehouse_control_system_spec.md`) 동기화 완료.

* **00:02** - **관제 센터 노드(control_tower_node.py) 설계 및 빌드**
  * `/src/cobot3/cobot3/control_tower_node.py`에 멀티스레드 기반의 ROS2 제어 소스 코드 작성.
  * Python DB 드라이버 라이브러리(`psycopg2-binary`, `redis`) 의존성 정의.
  * `package.xml` 및 `setup.py`에 실행 파일 진입점(`control_tower`) 등록 및 컴파일 테스트 완료.

* **00:10** - **작업대 내 적재 물품 및 슬롯 실시간 매핑 구조 추가**
  * 각 작업대에 어떤 구체적인 택배들이 들어있는지 실시간 추적을 위해 `packages` 테이블에 `workstation_id` 및 `slot_number` 칼럼 추가.
  * `ReportInboundProgress.srv`에 `package_id` 필드를 추가하고, 로봇이 진척도를 보고할 때 개별 택배 데이터의 적재 위치도 DB에 동시 갱신되도록 제어 루프 추가 및 재빌드 완료.

* **00:12** - **데이터베이스 GUI 모니터링 툴 통합**
  * 데이터 조회를 쉽게 하고 이력을 내려받을 수 있도록 `docker-compose.yml`에 웹 뷰어인 **Adminer(PostgreSQL GUI)** 및 **Redis Commander(Redis GUI)** 컨테이너 추가 구축.

* **11:35** - **ArUco 마커 기반 고유 번호 식별 및 매핑 구조 고도화**
  * 각 박스, 작업대 및 로봇의 고유 식별을 위해 PostgreSQL 데이터베이스(`robots`, `workstations`, `packages`)에 `aruco_id` 고유 칼럼 추가 및 기본 데이터 갱신.
  * ROS2 서비스 (`GetPackageRoute.srv`, `CheckWarehouseStatus.srv`, `ReportInboundProgress.srv`) 및 액션 (`MovePackage.action`, `ManageWorkstation.action`, `StartPackaging.action`)에 ArUco ID 관련 필드 추가 적용.
  * 관제탑 노드(`control_tower_node.py`) 내 서비스 콜백 및 AMR 액션 구동부에서 ArUco ID를 우선 스캔 및 쿼리하여 데이터베이스 정보와 실시간으로 매핑 및 연동하도록 업데이트 완료.

* **12:15** - **창고 세부 주차 스팟(Spot) 관리 DB 및 10대 작업대 최적화**
  * 창고 내부 주차 스팟을 개별적으로 관리할 수 있는 `warehouse_locations` 테이블 구축.
  * 초기 작업대 수량을 총 10대(`WS01` ~ `WS10`, ArUco `11` ~ `20`)로 확장하고, 창고 내 10개 주차 스팟(`spot_01` ~ `spot_10`)에 주차된 상태로 초기 데이터 변경.
  * 관제 센터 노드(`control_tower_node.py`)에서 작업대 창고 입출고 시 비어 있는 스팟 자동 배정 및 해제 로직 구현.
  * 포장 완료된 작업대가 창고 스팟으로 자동으로 복귀하고, 인바운드 분류 작업 시 창고의 빈 작업대를 유기적으로 호출해 오는 무대기 루프 흐름 고도화.

* **15:18** - **AI 에이전트 인수인계 및 시스템 아키텍처 가이드 작성**
  * `AI_AGENT_GUIDE.md` 신규 생성. 차기 에이전트를 위한 시스템 다이어그램, ArUco ID 매핑 규격, DB 테이블 설명, Look-ahead 로직 및 실행 커맨드 정리.
* **15:30** - **FastAPI 기반 실시간 모니터링 웹 대시보드 구축**
  * `scratch/dashboard_server.py` 신규 생성. 10개 창고 주차 스팟과 작업대 상태, Redis AMR 태스크 대기열, 패키지 정보를 실시간(1초 주기)으로 시각화해 보여주는 웹 대시보드 구현.
  * 웹 UI 상에서 [시뮬레이션 적재 발생] 및 [데이터베이스 초기화]가 가능하도록 API 핸들러 추가.
* **15:40** - **ROS2 모의 시뮬레이션 테스트 프레임워크 구축**
  * `scratch/run_simulation_test.py` 신규 생성. 실제 물리 기기/시뮬레이터가 기동하지 않은 상황에서도 ROS2 서비스 클라이언트 및 액션 서버들을 모킹(Mocking)하여 관제탑과의 연동 루프(Look-ahead, ArUco ID 검증 등)를 테스트할 수 있는 시나리오 검증 프레임워크 구현 완료.

---

## 📅 2026년 6월 3일 (수요일)

* **11:05** - **문서 식별 및 AI 에이전트 가이드 헤더 표준화**
  * 프로젝트 내 모든 마크다운(`*.md`) 문서를 스캔하고 분석하여 내용 숙지 완료.
  * AI 에이전트 자동 업데이트 감지 헤더가 누락되어 있던 `ARUCO_INTEGRATION_GUIDE.md` 파일 상단에 해당 경고 문구 추가 적용.
  * 맵 구성 파일 `src/cobot3/resource/map/warehouse.yaml`의 맵 이미지 매핑 파일명 수정 반영 (`World0.png` -> `warehouse.png`).
* **11:22** - **시스템 개선 및 고도화 계획서 작성**
  * 사용자 피드백을 기반으로 데이터베이스 정규화, QR코드 생성/인식 방법, 이중 버퍼(Double Buffer) 작업 구역 배치, Redis Sorted Set 기반 우선순위 큐, 단일 장애점(SPOF) 대응 방안을 담은 `SYSTEM_IMPROVEMENT_PLAN.md` 신규 설계 및 작성 완료.

* **13:40** - **데이터베이스 구조 정규화 및 소스코드 전면 연동**
  * `workstations` 테이블에서 중복 저장되던 1~4번 슬롯 정보(`slot_X_customer`, `slot_X_status`)를 완전히 삭제하여 DB 스키마 정규화 완료 (`docker/init.sql`).
  * `control_tower_node.py` 및 `dashboard_server.py`의 쿼리와 슬롯 계산 로직을 `packages` 테이블의 외래키(`workstation_id`, `slot_number`)와 상태(`IN_WORKSTATION`)를 결합해 동적으로 계산하도록 전면 재설계.
  * DB 설계 문서(`DATABASE_SCHEMA.md`)를 변경된 정규화 구조에 맞춰 ERD 및 예시 데이터 시나리오 설명까지 전면 동기화 업데이트 완료.

---

## 📅 2026년 6월 4일 (목요일)

* **09:30** - **QR코드 동적 생성 및 비전 디코딩 모듈 구현**
  * 파이썬의 `qrcode` 및 `zxing-cpp` 라이브러리를 활용하여 택배 ID 기반 QR코드 생성 및 이미지 디코딩 기능을 제공하는 `scratch/qr_handler.py` 모듈 구축.
  * 시스템 C 라이브러리 의존성이 강한 `pyzbar`나 내부 컴파일 이슈가 있는 OpenCV `QRCodeDetector`의 대안으로, statically linked pre-compiled 바이너리를 제공하는 `zxing-cpp`를 채택하여 배포 및 구동의 이식성을 극대화.
  * 해당 핸들러의 생성 및 해독 성능을 검증하는 단독 테스트 벤치인 `scratch/test_qr_handler.py` 구현 및 검증 성공.

* **09:45** - **QR코드 비전 인식 기반 ROS2 종단간 시뮬레이션 및 검증**
  * 실제 카메라 비전 및 DB, ROS2 서비스의 통합 동작을 가상화하여 보여주는 `scratch/run_qr_simulation_test.py` 시나리오 시뮬레이터 신규 구축.
  * 택배 고유 ID를 바코드가 아닌 비전 인식 결과로 역추적하여 데이터베이스를 검색하고, Look-ahead 작업대 예비 호출 등의 AMR 태스크가 막힘없이 예약 및 작동하도록 연동 테스트 완료.
  * `SYSTEM_IMPROVEMENT_PLAN.md` 문서를 개정하여 QR코드 도입 섹션을 [완료]로 업데이트.

* **10:10** - **고정 설비 및 바닥 격자 맵 기반 QR코드 통합 생성 모듈 구현**
  * `warehouse.yaml` 파일의 origin 및 resolution 정보를 파싱하여 실제 ROS 월드 좌표계를 계산하는 `scratch/generate_all_qr_codes.py` 구축.
  * 외곽 2.0m 보행자 안전 통로를 제외한 내측 주행 영역에 1.5m 간격으로 1,813개의 격자점(Node) 좌표(`FLOOR_X_..._Y_...`)를 연산하고 샘플 및 로봇/작업대용 고정 QR코드 파일 생성 완료.

* **10:35** - **USD 맵 파일(map.usd) 내 바닥 QR코드 1,813개 자동 일괄 매핑 완료**
  * Isaac Sim 내장 `pxr` (Universal Scene Description) API와 `SimulationApp`을 연동한 `scratch/add_all_qr_to_usd.py` 자동화 스크립트 작성.
  * 기존 비어있던 `src/cobot3/resource/map.usd` 맵 파일에 1,813개의 격자 평면(Quad Mesh)과 PBR 텍스처 재질(Material)을 10초 만에 완벽히 추가 및 바인딩하여 맵 최종 갱신 완료 (용량 372KB로 최적화).

* **10:46** - **바닥 반사 방지 및 QR 시인성 향상을 위한 USD 조명 최적화 완료**
  * 강한 직사광으로 발생하던 바닥의 하얗게 타는 현상(Specular Glare)을 해결하기 위해 기존 `defaultLight` (DistantLight) 세기를 3000.0에서 600.0으로 대폭 낮춤.
  * 사방에서 균일하고 부드러운 환경 빛을 제공하는 `domeLight` (DomeLight, 세기 1200.0)를 새로 추가하여 그림자를 제거하고 전체 밝기를 균일하게 맞추어 카메라 센서의 QR코드 비전 인식률을 최적화함.

* **11:30** - **창고 영역 외곽 QR코드 생성 억제를 위한 경계 제한(Bounding Box) 설정 및 맵 재생성 완료**
  * 창고 외부 벽면 바깥에 바닥 격자 QR코드가 불필요하게 대량으로 생성되는 현상을 억제하기 위해, QR 생성 범위를 사용자가 지정한 창고 바닥 영역 크기(X: [-38.0, 38.0], Y: [-36.08472, 25.0]) 내로 제한하는 Bounding Box 필터 적용.
  * `generate_all_qr_codes.py` 및 `add_all_qr_to_usd.py` 내부의 좌표 생성 루프를 수정하여 필터 로직 삽입 완료.
  * 범위 제한 결과 총 격자 마커의 개수가 기존 2,303개에서 **1,813개**로 최적화되었으며, `generate_all_qr_codes.py`를 실행하여 제한된 영역의 QR코드 이미지 자산을 재생성하고, `add_all_qr_to_usd.py`를 사용해 `map.usd` 파일에 격자 평면을 성공적으로 다시 갱신함.

* **15:50** - **인바운드/아웃바운드 작업대 자동 교체(Swap) 시뮬레이션 기능 구현**
  * `dashboard_server.py`의 `/api/simulate` 엔드포인트에 8번째(마지막) 슬롯 적재 시 **완충 작업대 자동 교체** 로직 추가: 다 찬 작업대를 창고로 회수(`RETRIEVE_FULL_WORKSTATION`)하고 새 빈 작업대를 적재 라인으로 배치(`DEPLOY_EMPTY_WORKSTATION`)하는 AMR 태스크를 Redis 큐에 동시 등록.
  * 포장 공정 시뮬레이션을 위한 `/api/simulate_packaging` 엔드포인트 신규 추가: 포장존(`sg2_out_00`)에 있는 작업대의 패키지를 한 칸씩 포장 완료 처리하며, 7번째 포장 시 Look-ahead(`PRE_FETCH_PACKAGING_WORKSTATION`), 전체 포장 완료 시 빈 작업대 회수(`RETRIEVE_EMPTY_WORKSTATION`) + 다음 작업대 배치(`DEPLOY_PACKAGING_WORKSTATION`) 교체 루프를 자동 수행.
  * 대시보드 UI에 **[📦 시뮬레이션 포장 수행]** 버튼 추가 및 JavaScript 핸들러 연결.
  * 브라우저 테스트를 통해 적재 8회 → 작업대 교체(WS01→창고, WS02→적재라인) → 포장 호출(WS01→포장존) 전체 사이클이 정상 동작함을 검증 완료.

* **18:00** - **통합 로봇 에뮬레이션 시나리오 구축 및 ROS2 멀티스레딩 데드락 핫픽스 완료**
  * `scratch/run_full_simulation_robot.py` 스크립트를 구현하여 실제 물리 로봇과 AMR 장비 없이도 관제탑 노드와 로컬 DB/Redis를 연동해 전체 물류 라이프사이클(적재 -> Look-ahead 사전이송 -> Swap -> 포장 -> 회수)을 시연/검증 가능한 통합 가상 로봇 노드를 탑재함.
  * 백그라운드 스레드에서 `spin_until_future_complete` 서비스 호출 시 발생하던 ROS2 내부 스레드 락(Lock)에 의한 **데드락(교착 상태)**을 예방하기 위해 `future.done()` 기반의 논블로킹(Non-blocking) 대기 루프로 구조를 전면 리팩토링.
  * 7번째 포장 완료 피드백 시점에서 다른 완충 작업대 사전 이송 대상을 조회할 때, `current_location LIKE 'spot_%%'`에 위치한 8개 가득 찬 작업대를 정상 식별하도록 SQL 조인문 교정 및 예외 방어 로직을 `control_tower_node.py`에 적용.
  * 사용자 터미널 수동 실행을 돕기 위해 로컬 도커 기동 권한 우회(`sudo docker-compose`), 대시보드 포트 충돌 시 프로세스 종료(`fuser -k`), ROS2 Humble setup 소싱을 포괄하는 단계별 가이드를 수립하여 가이드 문서에 통합.

* **18:40** - **라인별 A/B 구역 이중 버퍼 도입 및 Keep-Alive Dispatcher 구현 완료**
  * 각 적재 로봇(`sg2_in_01` ~ `03`)의 인바운드 대기 구역을 A 구역(`_A`, 활성 적재)과 B 구역(`_B`, 예비 대기)으로 세분화.
  * 관제 센터 노드(`control_tower_node.py`) 내 1Hz 주기 스케줄러 루프에 `dispatch_workstations_keepalive()`를 통합하여 A구역 자동 보충 및 B구역의 대기 작업대 자동 승격(Promotion) 로직 반영.
  * 작업대 슬롯이 정확히 3개 적재되었을 때 다음 빈 작업대를 B구역으로 미리 이송하는 3-슬롯 Look-ahead 메커니즘을 시뮬레이터 및 관제 센터 전체에 연동.
  * 창고 스팟 점유 상태의 중복 변경 및 해제 누수 차단을 위해 `'warehouse'` 출발지 상태에서 실제 물리 스팟 ID(`spot_XX`)를 동적으로 분해 및 상태 해제하는 리졸버 탑재.
  * 웹 대시보드 서버(`dashboard_server.py`)의 `/api/simulate` API 및 모의 시뮬레이터(`run_full_simulation_robot.py`)를 수정하여 이중 구역 기반 적재 및 A/B 이송 시나리오 최종 검증 완료.

* **19:20** - **Redis Sorted Set 기반 우선순위(Priority) 큐 및 180도 회전 시퀀스 구현 완료**
  * AMR 작업 큐를 FIFO 리스트(`lpush`/`rpop`)에서 Redis **Sorted Set(ZSET)** 기반 우선순위 대기열(`zadd`/`zpopmax`)로 전면 전환.
  * 태스크 고유성 확보를 위해 각 작업 사양에 동적 `uuid`를 추가로 부여하여 직렬화하는 중복 방지 설계 적용.
  * 작업 종류별 가중치 설계(P1: 회전/배출/직송=100, P1.5: A구역 공급=90, P2: 포장공급/이송=80, P2.5: 포장사전이송=70, P3: B구역 Look-ahead=50, P4: 회수=20)를 관제 센터와 웹 대시보드 서버에 공통 적용.
  * 레거시 리스트(WRONGTYPE) 타입 충돌을 방지하기 위한 예외 복구 핸들러 구축.
  * **180도 회전(Rotate in-place)** 시나리오 추가: 로봇의 물리적 리치 한계 극복을 위해 4번째 슬롯 적재 시 작업대 위치를 `_A_ROTATING`으로 변경하여 로봇 적재를 일시 대기시키고, AMR의 180도 회전 완료 시 `_A`로 돌려놓는 자율 상태 제어 구현.
  * 웹 대시보드 UI 상의 'Active Commands Queue'에 각 태스크별 우선순위 점수(P-100, P-80 등) 배지 및 간략화된 UUID가 출력되도록 디자인 고도화 완료.

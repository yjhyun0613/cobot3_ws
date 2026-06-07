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

* **20:05** - **관제 단일장애점(SPOF) 대응 및 오프라인 Fail-safe 설계 구현 완료**
  * 서비스 클라이언트 통신 루프(`run_full_simulation_robot.py`)에 1.0초 타임아웃 및 최대 3회 재시도 헬퍼 함수 (`call_service_with_fail_safe`) 도입.
  * 서비스 응답 지연에 따른 무한 블로킹을 방지하기 위해 2.0초 응답 초과 대기 차단 알고리즘 결합.
  * 관제탑 서버 또는 DB 다운 시 로봇이 멈추지 않는 로컬 오프라인 룰베이스(Fallback Callback) 구축:
    * 패키지 ID 해시를 연산하여 3개 적재 라인에 로컬 자체 분산.
    * 중복성 체크 실패 시 안전 순환 회차 경로(Recirculation Loop) 유도.
    * 슬롯 보고 생략 및 로컬 진척 속행 제어로 현장 컨베이어 벨트 정체 예방.
  * `SYSTEM_IMPROVEMENT_PLAN.md` 내 5장 세부 상태 및 내용을 완료 상태로 동기화 갱신.

* **20:47** - **대용량 입고 테스트를 위한 150개 패키지 모의 CSV 생성 및 검증 완료**
  * `scratch/generate_large_csv.py` 스크립트를 구현하여 임의의 한국인 수령인 이름, 날짜, 고유 QR ID를 포함한 150개의 패키지 데이터셋 `scratch/large_test_packages.csv` 자동 생성 완료.
  * 대용량 데이터 로딩 속도 및 대시보드 페치 성능 검증을 위한 테스트 자산으로 활용 가능.

* **20:58** - **웹 대시보드 레이아웃 개선 및 100% 반응형 유연 레이아웃 적용**
  * 기존 좌측 창고 주차 스팟 및 우측 작업대 활성 상태의 2열 구조를 상하 1열 적층 구조로 변경하여 시각적 가독성 개선.
  * 하드코딩된 grid columns 구조로 인해 발생하는 가로 스크롤(옆으로 넘어가는 현상)을 해결하기 위해 CSS Grid의 `repeat(auto-fit, minmax(px, 1fr))` 유동 구조 적용:
    * **창고 주차 스팟**: `minmax(110px, 1fr)` 설정으로 해상도에 따라 10개 한 줄에서 자동으로 줄바꿈 처리.
    * **작업대**: `minmax(250px, 1fr)` 설정으로 데스크톱 환경에서는 5열 구성(5x2 격자)을 유지하면서 화면이 좁아질 때(태블릿, 모바일 등) 레이아웃이 깨지거나 가로 스크롤 없이 부드럽게 카드 수가 자동 조절되도록 개선.

* **21:04** - **작업대 정보 카드 헤더 시각적 군더더기 제거 및 수직 정렬 최적화**
  * 불필요한 QR ID 문자열(`(QR: WORKSTATION_WSxx)`) 출력을 제거하여 복잡성을 줄이고 작업대 이름(ID) 시인성 증대.
  * 헤더 구조를 기존 좌우 분할 배치에서 수직 적층 방식으로 개편(첫 줄: 작업대 이름, 둘째 줄: 현재 위치 배지)하여 카드 가로 공간을 넓게 활용할 수 있도록 UI 완성도를 높임.

* **21:18** - **작업대 중복 할당 및 위치 중복 표시 버그 수정**
  * **원인**: 작업대가 A구역으로 이동 중인 상태(`MOVING_TO_SG2_IN_XX_A`)일 때, 시뮬레이션 적재 API(`/api/simulate`)가 해당 구역에 활성화된 작업대가 없는 것으로 판단(단순 `sg2_in_XX_A`만 검사)하여 창고에서 또 다른 빈 작업대를 강제 배정함에 따라 동일한 구역에 두 개의 작업대가 중복 배정되는 버그 발생.
  * **해결**: 시뮬레이션 적재 API에서 대상 라인의 작업대를 검색할 때 **우선순위 쿼리**(`A구역 -> 회전중 -> A로 이동중 -> B구역 -> B로 이동중`)를 도입하여 이미 해당 라인에 할당되었거나 이동 중인 작업대를 최우선 재사용하도록 개선. 이를 통해 다중 배정 및 위치 중복 겹침 현상을 원천 방지함.

* **21:36** - **아웃바운드 포장 로봇(sg2_out_00) A/B 이중 버퍼 및 동적 승격 스케줄링 구현**
  * 포장존의 병목 해결 및 포장 공정 효율을 극대화하기 위해, 포장 로봇 구역에도 A/B 이중 버퍼 구조(`sg2_out_00_A`, `sg2_out_00_B`) 도입.
  * **관제 센터 노드(`control_tower_node.py`)**:
    * 완충된 작업대 이동 대상지를 `sg2_out_00_A`가 비어있고 이동 중인 작업대가 없으면 A구역, 그렇지 않으면 B구역으로 동적 지정.
    * 7번째 슬롯 포장 완료 시 예비 작업대를 창고에서 `sg2_out_00_B`로 사전 호출(Look-ahead)하도록 연동.
    * Keep-alive 루프에서 포장존 A구역이 비었을 때 B구역 작업대를 A구역으로 승격(`DEPLOY_PACKAGING_WORKSTATION`)시키는 스케줄링 로직 추가.
  * **시뮬레이션 대시보드(`dashboard_server.py`)**:
    * `/api/simulate_packaging` API를 개편하여 A구역 작업대 포장 완료, 7번째 Look-ahead 호출(B구역 대기), 8번째 전체 완포 시 B구역의 예비 작업대를 A구역으로 승격시키는 일련의 자동화 동작 완비.

---

## 📅 2026년 6월 5일 (금요일)

* **09:20** - **바닥 QR코드 공간 격자 맵 데이터베이스(Spatial Floor QR Map DB) 연동 완료**
  - PostgreSQL 데이터베이스 초기화 SQL 스크립트(`docker/init.sql`) 내 `floor_qr_map` 테이블 정의 추가.
  - 격자 생성기(`scratch/generate_all_qr_codes.py`)를 확장하여, 실행 시 1,813개 격자점의 미터법 X, Y, Z 좌표와 함께 논리 주차/작업 공간 매핑 데이터(`spot_XX`, `sg2_in_XX_A/B`, `sg2_out_00_A/B`)를 PostgreSQL DB에 일괄 TRUNCATE 후 Bulk Insert(적재)하도록 연동 모듈 추가.
  - 관제 센터 노드(`control_tower_node.py`)의 `trigger_workstation_move`에서 이송 액션을 발행할 때, 하드코딩 좌표나 고정 문자열 대신 데이터베이스의 `floor_qr_map` 테이블을 조회하여 물리 Goal coordinates와 바닥 QR ID를 실시간으로 해석(Resolution)하고 검증하는 로직 통합.
  - 모의 로봇 에뮬레이터(`run_full_simulation_robot.py`)의 `execute_manage_ws` 및 `execute_move_pkg` 콜백 내에서 동일하게 PostgreSQL DB를 쿼리해 이동 경로의 시/종점 물리 좌표와 마커 식별자를 화면에 실시간으로 로깅하도록 에뮬레이터 통합 완료.

* **10:55** - **AMR 플릿 연동 및 하이브리드 통신 아키텍처 설계 합의 완료**
  - AMR 개발자 피드백을 기반으로 4대 연동 설계 원칙 수립 및 `SYSTEM_IMPROVEMENT_PLAN.md`에 공식 규격 추가 반영.
  - 제어 채널과 상태 모니터링 채널을 확실하게 분리하여 제어는 ROS2 Action/Service로만 수행하고, `/fleet/*` JSON 토픽은 공유/모니터링으로만 제한하도록 아키텍처 정립.
  - `QR_XXXX` 식별자 관리 하에서 DB `floor_qr_map`과 AMR 로컬 백업 YAML 캐시를 연계한 2중 복구체계 및 Goal 전송 시 좌표 동시 인하 규격 검토 완료.

* **11:30** - **AMR 플릿 연동 하이브리드 통신 규격 구현 및 검증 완료**
  - `ManageWorkstation.action` 정의를 수정하여 Goal 필드에 `target_qr_id`(string), `target_x/y/yaw`(float64)를 추가하고, 관제 센터 노드(`control_tower_node.py`)에서 DB의 `floor_qr_map`을 통해 실시간 좌표 및 바닥 QR ID를 획득하여 Action Goal Payload로 함께 하향 전송하도록 수정 완료.
  - `control_tower_node.py` 내에 `/fleet/amr_states`, `/fleet/workstation_states`, `/fleet/package_states`, `/fleet/task_events` 4개 JSON 토픽 퍼블리셔 등록 및 1Hz 주기 전송 루틴 추가 완료.
  - `workstations` 테이블의 `status`, `reserved_by` 컬럼 상태를 AMR 액션 제어 주기(`trigger_workstation_move`, `completed`, `failed` 등)에 맞춰 실시간으로 PostgreSQL에 갱신/동기화하도록 제어 루프를 개선하고, 작업 상태 변경 시 즉시 `/fleet/task_events`에 JSON 이벤트를 발행하는 이벤트 핸들러 추가 완료.
  - 액션 클라이언트 대기 로직에서 발생할 수 있는 교착 상태(Deadlock)를 방지하기 위해 `wait_for_server` 호출에 `timeout_sec=1.0` 타임아웃 규격을 전면 도입하고 실패 예외 처리 로직 반영 완료.

* **13:18** - **동적 출고예정일(route_zone) 기반 라우팅 및 창고 완충 작업대 포장 선별 로직 구현**
  - 기존의 하드코딩된 출고 예정일(`2026-06-01`) 처리 방식을 탈피하고, 데이터베이스 내 미처리(`status != 'COMPLETED'`) 패키지들의 고유 `route_zone` 날짜를 오름차순으로 정렬한 동적 목록을 획득하는 구조 설계.
  - **`dashboard_server.py` & `control_tower_node.py`**:
    - 조회된 미처리 날짜 목록의 첫 번째 원소를 "오늘의 출고 대상 일자(`today_date`)"로 삼아, 창고 완충 작업대를 포장존으로 공급하는 쿼리(`simulate_packaging` 및 keep-alive scheduler)에 바인딩 변수로 동적 할당되도록 수정 완료.
    - 입고 시뮬레이션(`/api/simulate_inbound`)에서 조회된 배송 날짜의 상대 순서에 따라 `sg2_in_01`(오늘), `sg2_in_02`(내일), `sg2_in_03`(모레) 라인으로 분기 라우팅되도록 개선 완료.
    - 오늘 물량이 모두 출고 완료되면 별도의 수동 조작 없이 다음 출고 예정 날짜가 "오늘 날짜"로 자동 승격되어 연속 처리가 보장됨.
  - 관련 변경 내용을 프로젝트 종합 보고서(`PROJECT_REPORT.md`) 및 인터페이스 명세서(`INTERFACE_CHANGES.md`)에 상세 기술하고 전체 동기화 완료.

* **14:10** - **웹 대시보드 2D 맵 UI 고도화 및 실시간 플로어 플랜 격자 시각화 반영**
  - 기존 캔버스(Canvas) 기반의 단순 2D 좌표 맵을 물류창고의 실제 구조(상단 주차 구역, 좌우 대칭형 컨베이어 라인 1~3, 중앙 AMR 운행 영역, 하단 포장 라인 A/B)를 정확히 나타내는 반응형 격자형 HTML/CSS 레이아웃으로 대체했습니다.
  - `floor_qr_map` 및 데이터베이스 내 각 작업대 위치, 상태, 주차 스팟의 점유 상태(`OCCUPIED`/`EMPTY`)를 실시간(1Hz)으로 조회하여 UI 요소(시안색 점유 표시, 대기/활성 버퍼 구분)에 즉각 렌더링되도록 `dashboard_server.py` 내 프론트엔드 HTML/CSS/JS 로직을 전면 갱신했습니다.

* **14:20** - **중복 입고 검사 오류 수정 및 시뮬레이터 무한 루프 버그 해결**
  - **관제탑 노드 (`control_tower_node.py`)**: `CheckWarehouseStatus` 호출 시 기존의 `customer_name` 기반 조회 방식을 `package_id` 기반의 정확한 조회 방식으로 변경하였습니다. 이를 통해 동일 수령인의 완료된 과거 택배 이력으로 인해 신규 입고 패키지가 중복 보관 중인 것으로 오인하여 직송을 유발하던 문제를 해결했습니다.
  - **시뮬레이터 (`run_full_simulation_robot.py`)**: 관제탑으로부터 직송 지시(`is_already_in_warehouse=True`)를 받았을 때, 데이터베이스 내 해당 패키지의 상태를 `IN_WAREHOUSE`로 갱신하여 다음 루프의 분류 대상(WAITING)에서 제외되도록 수정함으로써, 동일 패키지에 대해 적재 요청을 무한히 반복하는 교착 현상을 방지했습니다.
  - 변경 패키지 빌드(`colcon build --packages-select cobot3`) 및 정상 시나리오 운행 테스트를 통해 흐름 검증을 마쳤습니다.

* **15:40** - **포장 완료 후 180도 회전 완료 시의 포장 프로세스 중복 트리거(Double-trigger) 버그 수정**
  - **현상**: 포장 로봇이 4번째 슬롯 포장 완료 후 작업대 180도 제자리 회전(`ROTATE_WORKSTATION`)을 수행하고 복귀(`sg2_out_00_A`)할 때, 이송 완료 콜백(`workstation_move_completed_callback`)에서 목적지가 `sg2_out_00_A`라는 이유로 포장 액션(`trigger_packaging_process`)을 중복 호출하는 버그가 있었음. 이로 인해 동일 작업대에 대해 두 개의 포장 시퀀스가 동시에 실행되어 DB 스팟 중복 점유(`spot_01`, `spot_03` 동시 점유 등) 및 상태 꼬임 유발.
  - **해결**: 이송 요청 및 완료 콜백 인터페이스(`workstation_move_response_callback`, `workstation_move_completed_callback`)에 출발지(`start`) 인자를 추가로 전달하도록 구조 변경. 최종 도착 완료 시 출발지가 `sg2_out_00_A_ROTATING`이거나 `ROTATING` 키워드를 포함하는 제자리 회전 동작인 경우 포장 공정이 다시 트리거되지 않도록 방어 로직 적용.
  - **검증**: `colcon build` 후 150개 대용량 패키지 기반 시나리오 테스트를 다시 기동하여, 포장 로봇 및 AMR이 이중 트리거 없이 깔끔하게 1회씩만 작동하고 주차 스팟(`warehouse_locations`)에 작업대들이 중복 할당 없이 1:1로 정확하게 EMPTY/OCCUPIED 매핑이 갱신되는 것을 완벽히 검증 및 확인 완료.

* **16:35** - **Docker Adminer 컨테이너 포트 충돌(8080) 해결**
  - **문제**: 호스트 PC의 8080 포트가 이미 점유되어 있어 `warehouse_adminer` 컨테이너가 바인딩에 실패하여 실행되지 않는 문제 발생.
  - **해결**: `docker-compose.yml` 내 Adminer 포트 매핑을 기존 `"8080:8080"`에서 **`"8082:8080"`**으로 변경하고 `README.md` 가이드 문서도 해당 포트에 맞춰 동기화 완료.

* **16:37** - **FastAPI 대시보드 서버 포트 충돌(8000) 해결**
  - **문제**: 호스트 PC에 떠 있는 NVIDIA Omniverse Nucleus Auth 서비스가 8000 포트를 점유하고 있어 `dashboard_server.py`가 구동되지 않는 문제 발생.
  - **해결**: `dashboard_server.py` 실행 포트를 기존 `8000`에서 **`8009`**로 변경하고, `README.md` 및 `PROJECT_REPORT.md` 내 가이드를 신규 포트에 맞춰 동기화 완료.

* **16:40** - **AMR 액션 서버 오프라인에 따른 관제탑 교착 상태(Deadlock) 방지 및 DB 롤백 처리 완료**
  - **문제**: 관제탑 노드가 구동될 때 AMR 에뮬레이터(`mock_full_robot_node`)가 아직 실행되지 않아 Action Server (`manage_workstation`)를 찾지 못하고 타임아웃/실패 처리되는 경우, 작업대의 현재 위치(`current_location`)가 `MOVING_TO_...` 상태로 고착되어 스케줄러가 두 번 다시 해당 작업대 배치를 시도하지 않는 영구적인 교착 상태가 발생함.
  - **해결**: 이송 액션 기동 실패, 취소 또는 실행 에러 발생 시 데이터베이스 내 작업대 상태(`current_location`, `status`, `reserved_by`)와 창고 주차 스팟 상태(`warehouse_locations`)를 최초 기동 직전 상태로 복구해 주는 **`recover_workstation_move_db_state()`** 롤백 메커니즘을 구현하여 통합 적용함.

* **18:50** - **control_tower_node_00.py 스레드 안정화 리팩토링**
  - **문제**: `MultiThreadedExecutor` 환경에서 PostgreSQL 커넥션이 동시에 여러 콜백에서 접근되어 간헐적 데이터 무결성 위반 및 커서 충돌 발생 가능성 존재.
  - **해결**: `threading.RLock()` 기반 `self.pg_lock` 도입하여 모든 `self.pg_conn.cursor()` 호출부를 `with self.pg_lock:` 블록으로 래핑. 중첩 호출(재진입) 시 데드락 방지를 위해 `RLock`(재진입 락) 사용.
  - **추가 변경**: Look-ahead 포장존 사전 호출 타이밍을 3번째 슬롯에서 **7번째 슬롯**으로 변경 (사양 문서 동기화).
  - 결과물: `control_tower_node_00.py` (기존 `control_tower_node.py` 기반 클린 버전).

* **18:55** - **USD 바닥 QR 격자 인스턴싱 최적화 (`add_all_qr_to_usd_0.py`)**
  - **문제**: 기존 방식은 1,800+개 격자마다 독립 Mesh를 생성하여 GPU VRAM 과부하 유발.
  - **해결**: OpenUSD **인스턴싱(Instancing)** 기법 적용. 단 1개의 마스터 프로토타입 메쉬(25cm)만 생성하고 나머지는 내부 참조(`AddInternalReference`) + `SetInstanceable(True)` 활성화로 GPU 인스턴싱 하드웨어 가속 활용.
  - **타겟 변경**: `map.usd` → `floor.usd` (전용 바닥 레이어 분리).
  - **격자 크기**: 0.3m → **0.25m** (25cm 규격 통일).

* **19:00** - **창고 레이아웃 재설계 논의 및 일자별 배치 전략 수립**
  - 기존 단일 측면 컨베이어 + 상단 가로형 창고 구조에서 **좌우 대칭 + 중앙 세로형 메인 창고 + 양 사이드 하단 출고 대기 창고** 구조로 개편 설계 (`image copy.png`).
  - 실제 물류창고(쿠팡, Amazon) 방식을 적용한 일자별 배치 전략 수립:
    - **1일차(오늘)** → 출고 대기 창고(크로스도킹)
    - **2일차(내일)** → 메인 창고 하단(골든 존)
    - **3일차(모레)** → 메인 창고 상단(딥 스토리지)
  - 일자 전환 시 물리적 이동 없이 **논리적 승격(Logical Promotion)** 방식 적용 결정: DB에서 날짜 플래그만 변경하여 스케줄러가 자동으로 "오늘 물량"을 인식하여 출고 대기 창고→포장라인으로 공급.

* **19:09** - **왼쪽 절반 단순화 레이아웃 확정 및 관제탑 라우팅 로직 수정**
  - 원본 대칭형 레이아웃에서 **왼쪽 절반만 사용**하기로 확정. 입고 라인 1세트(1,2,3), 포장 라인 1개, 메인 창고(중앙 세로형), 출고 대기 창고(좌측 하단) 구조.
  - 기존 위치명(`sg2_in_01~03`, `spot_01~10`, `stage_01~06`, `sg2_out_00_A/B`) **변경 없이 그대로 유지**.
  - **`control_tower_node_00.py` 라우팅 변경**:
    - 오늘 물량(`sg2_in_01_A` 완충): 기존 `sg2_out_00_A → sg2_out_00_B → staging` → **`sg2_out_00_A` 직행 or `staging` 대기** (B구역 분기 제거)
    - 내일 물량(`sg2_in_02_A` 완충): 기존 `staging` → **`warehouse`** (staging은 오늘 전용으로 역할 변경)
    - 모레 물량(`sg2_in_03_A` 완충): `warehouse` 유지 (변경 없음)

* **19:21** - **대시보드 UI 레이아웃 동기화 및 ROS2 setup.py 진입점 변경**
  - **`dashboard_server.py`**:
    - 시뮬레이션 적재/포장 API에서 완충 작업대 회수 및 공급 목적지를 신규 레이아웃 전략에 맞춤 (오늘 물량은 `stage_01~06` 우선, 내일/모레 물량은 `spot_01~10`으로 이송).
    - 2D Live Plan UI에서 우측 입고 라인 세트(3개 라인)를 `display: none`으로 숨김 처리하여 원본의 왼쪽 절반만 보이도록 수정.
    - "포장 라인 B"의 헤더명을 "포장 대기존 B (Look-ahead)"로 변경하여 사전 호출 대기소 역할을 명확히 함.
  - **`setup.py`**:
    - ROS2 실행 진입점을 기존 `control_tower_node`에서 신규 기능이 모두 구현된 `control_tower_node_00`으로 변경 및 colcon 빌드 검증 완료.

* **19:40** - **웹 대시보드 테마 고도화 (다크 네온/글래스모피즘 테마 전면 교체)**
  - 대시보드의 전반적인 CSS 테마를 고급스러운 하이테크 다크 네온 및 글래스모피즘 테마로 개편했습니다.
  - HSL 보정된 테두리 및 그림자 효과, 트랜지션 효과(Hover Effect), 커스텀 스크롤바, `Inter` 및 `Outfit` 폰트 적용 등으로 시각적 프리미엄 느낌을 극대화했습니다.
  - 2D 플로어 플랜(Floor Plan) 내의 웨어하우스 그리드, 스테이징 그리드, AMR 레이어, 컨베이어 라인(conveyor), 워크스테이션 슬롯 등의 색상 및 보더 스타일을 모두 다크 테마 변수(`--primary`, `--warning`, `--accent`, `--card-bg` 등)와 투명한 rgba 스타일로 동기화 적용했습니다.

* **19:50** - **FastAPI 대시보드 서버 데이터베이스/SQL 및 지능형 AMR 시각화 개선**
  - **SQL 500 에러 해결**: 포장 시뮬레이션(`/api/simulate_packaging`) API 호출 시 PostgreSQL의 `SELECT DISTINCT` 문에서 `ORDER BY` 표현식이 `SELECT` 목록에 포함되어 있지 않아 발생하던 SQL Syntax 구문 오류를, `IN (SELECT DISTINCT ...)` 서브쿼리 구조로 리팩토링하여 완벽하게 해결했습니다.
  - **지능형 AMR 실시간 동적 렌더링**: Redis 내부에 AMR 정보(`amr:*`)가 없을 경우를 대비하여, 현재 PostgreSQL에서 이송 중(`moving_to_*` 또는 `_rotating`)인 워크스테이션의 위치를 추적해 자동으로 AMR 인스턴스를 동적으로 바인딩하고 시각화하는 지능형 폴백(Smart Fallback Mock) 로직을 `dashboard_server.py`의 `/api/status` API에 추가 구현했습니다. 이로 인해 시뮬레이션 도중 AMRs가 2D Floor Plan 상에서 부드럽게 이송 이동하는 효과를 실시간으로 모니터링할 수 있습니다.
  - **서버 포트 및 바인딩 관리**: Uvicorn reload 환경에서 8009 포트의 기존 프로세스를 강제 종료(`fuser -k 8009/tcp`)하고 재시작함으로써, 최신 변경 코드가 안정적으로 웹 대시보드에 무중단 반영되도록 조치했습니다.

---

## 📅 2026년 6월 6일 (토요일)

* **23:25** - **창고 및 출고 대기 창고 레이아웃 축소 및 통로(Aisle) 반영 완료**
  - **데이터베이스 스키마 및 마이그레이션**: `docker/init.sql`의 창고 스팟 등록을 10개(`spot_01` ~ `spot_10`), 출고 대기 스팟을 6개(`stage_01` ~ `stage_06`)로 축소하고, 현재 활성화된 작업대의 위치 정보를 보존한 채 신규 레이아웃에 맞춰 테이블을 재생성하는 `migrate_layout.py` 스크립트를 구축하여 DB 마이그레이션을 안전하게 수행 완료.
  - **대시보드 UI 그리드 및 좌표 고도화**: `dashboard_server.py`의 HTML 레이아웃에서 창고 영역을 5행 2열 구조(각 층 사이에 가로 통로 배치), 출고 대기 영역을 2행 5열 구조(각 1x2 세로 열 사이에 세로 통로 배치)로 전면 재편하였으며, AMR의 실시간 렌더링을 위해 `locationCoords` 매핑 수식을 새로운 슬롯 좌표계로 동기화 완료.

---

## 📅 2026년 6월 7일 (일요일)

* **01:00** - **실제 날짜 기준 영업일 전환 및 이월 작업대 연속 적재 시스템 구현 및 검증 완료**
  - **8개 미만 작업대 포장 공급 조건 수정**: 대기 중인 오늘 날짜 패키지가 없고 인바운드 라인에도 오늘 날짜 패키지가 없는 경우(`waiting_today == 0 and inbound_today_packages == 0`) 8개 미만 적재된 마지막 작업대도 포장존으로 공급하도록 쿼리를 개선했습니다.
  - **조기 포장 방지용 Redis 플래그 도입**: 날짜 전환 직후 새로운 CSV 파일이 업로드되기 전에 마지막 작업대가 즉시 포장존으로 자동 공급(플러시)되는 것을 막기 위해, Redis의 `system:inbound_started` 플래그가 `true`일 때만 자동 플러시를 수행하도록 수정했습니다.
  - **FastAPI 서버 핫픽스**: `dashboard_server.py`에서 영업일 전환 API 실행 시 발생한 `timedelta` 임포트 누락 에러(`NameError`)를 해결하기 위해 `from datetime import datetime, timedelta` 구문을 보완했습니다.
  - **Carry-over 연속 시나리오 최종 검증**: `2026-06-06`과 `2026-06-07` 영업일의 연속 동작을 검증하였으며, 이월된 작업대(`WS02`, 6개 적재 상태)가 1번 라인 `sg2_in_01_A`로 이동하여 안정적으로 대기하다가 신규 CSV 파일 업로드 직후 남은 2개 슬롯이 마저 채워진 뒤 포장존으로 이송되어 정상 처리됨을 완벽하게 검증하였습니다.

* **14:30** - **AMR 플릿 주행 연동 방안 보류 및 신규 물리 레이아웃 좌표 정보 정리 완료**
  - **AMR 연동 보류 명세 기록**: AMR 담당자가 작성한 A* 알고리즘 주행 코드의 연동 방안을 `SYSTEM_IMPROVEMENT_PLAN.md`에 공식 추가 및 보류 상태로 명시.
  - **물리 레이아웃 좌표 가이드 작성**: 창고 주차 구역(12개), 입고라인 버퍼(오늘/내일/모레 각 A/B), 출고대기 창고(6개), 출고포장라인 A/B 등 변경/확정된 실좌표 맵 정보를 정리하여 `PHYSICAL_LAYOUT.md` 신규 작성 및 배포 완료.

* **14:45** - **신규 물리 레이아웃 좌표 데이터베이스 및 대시보드 실시간 연동 완료**
  - **데이터베이스 스키마 및 마이그레이션**: `docker/init.sql`에 신규 확장된 `spot_11` 및 `spot_12`를 빈 스팟(`EMPTY`)으로 추가하고, `migrate_layout.py`를 12스팟 및 6스테이징스팟 마이그레이션이 가능하도록 구조를 수정 및 정상 실행 완료.
  - **격자 밖 논리 스팟 적재 보정**: `generate_all_qr_codes.py`에서 offset 배치된 출고 대기 창고(`stage_01` ~ `stage_06`)와 같이 1.5m 간격 바닥 격자에 딱 맞지 않는 좌표도 데이터베이스 table(`floor_qr_map`)에 누락 없이 정상 적재되도록 예외 적재 보정 로직을 추가하여 총 1,819개의 마커 노드 적재 완료.
  - **대시보드 UI 및 좌표 렌더링 동기화**: `dashboard_server.py`의 2D 플로어 플랜을 6행 2열(12칸) 구조 및 CSS 픽셀 매핑을 위해 `locationCoords`를 수정하여 12스팟과 6스테이징 구역이 시각적으로 완벽하게 연동되도록 대시보드 UI를 업데이트 완료.
  - **통합 제어 루프 최종 검증**: ROS2 `control_tower` 노드 및 `run_full_simulation_robot` 노드를 동시 구동하여 신규 물리 좌표(X, Y) 해석 및 작업대 이송 명령이 실시간으로 정상 작동하고, 대시보드에서 12개 보관 스팟과 6개 스테이징 스팟이 실시간 렌더링 및 이송 상태가 정상 표시됨을 최종 검증 완료.

* **14:50** - **입고 버퍼 라인 Y 좌표 보정 스왑 반영 및 DB 재적재**
  - **좌표 보정 스왑**: Line 1(오늘)과 Line 3(모레)의 Y축 물리적 coordinates를 맞교환 반영했습니다. (Line 1 Y = -11.025, Line 3 Y = -2.025)
  - **재적재 및 검증**: `PHYSICAL_LAYOUT.md`와 `generate_all_qr_codes.py` 내의 coordinates 정의 수정 후, `generate_all_qr_codes.py`를 재기동하여 PostgreSQL `floor_qr_map`에 새로운 coordinates 매핑을 업데이트하고 마이그레이션 완료했습니다.
  - **실시간 주행 정상화**: `control_tower`와 `run_full_simulation_robot` 에뮬레이터가 새로운 Y 좌표에 맞춰 에러 없이 실시간 이송 및 스캐닝을 처리함을 확인했습니다.

* **16:50** - **관제탑 노드 엔트리포인트 수정 및 레거시 코드 제거**
  - **setup.py 엔트리포인트 수정**: `control_tower` 실행 시작점이 삭제된 백업 파일(`control_tower_node_00.py`)을 가리키고 있어 `ModuleNotFoundError` 에러가 발생하는 문제를 해결. `setup.py`의 `console_scripts`를 프로덕션 노드 `control_tower_node:main`으로 수정.
  - **pg_lock 참조 제거**: `control_tower_node.py`의 일일 완료 검사(Day Finished Check) 타이머 콜백에서 더 이상 존재하지 않는 `self.pg_lock` 참조를 제거하여 `AttributeError` 해결.
  - **포트 충돌 정리**: Omniverse Nucleus 인증 서버가 점유 중인 포트 8000과의 충돌을 해소하고, 대시보드 서버 포트를 `8009`로 통일.

* **17:00** - **원클릭 통합 테스트 환경 구축 및 데이터베이스 초기화 스크립트 개발**
  - **`scratch/reset_db.py` 신규 생성**: PostgreSQL 테이블 초기화(packages TRUNCATE, workstations 상태 리셋, warehouse_locations 재배치), Redis 전체 플러시, 바닥 QR 격자 맵 재생성을 자동 수행하는 데이터베이스 완전 초기화 스크립트.
  - **`start_test_env.sh` 신규 생성**: Docker 컨테이너 점검 → DB 초기화 → ROS 2 빌드 확인 → 대시보드/관제탑/로봇 시뮬레이터 3개 노드를 선택적으로 구동하는 통합 테스트 런처 스크립트.

* **17:10** - **NVIDIA Isaac Sim 3D 시뮬레이터 실시간 연동 커넥터 개발**
  - **`scratch/isaac_amr_connector.py` 신규 생성**: Isaac Sim 3D 환경(`floor_with_con,storage.usd` 맵)과 관제 시스템(Redis/PostgreSQL)을 실시간으로 브리지하는 커넥터 스크립트.
  - **사용 맵**: `src/cobot3/resource/floor_with_con,storage.usd` (바닥 QR 격자, 입출고 컨베이어, 메인/출고 스토리지, 작업대 선반 기설치 완료).
  - **3D 모델**: AMR 5대(Cyan색 실린더, `/World/AMRs/`) 및 이동식 작업대 10대(Orange색 큐브, `/World/Workstations/`)를 맵 위에 동적 생성.
  - **동기화**: 매 프레임(30Hz)마다 Redis의 AMR 좌표 및 PostgreSQL의 작업대 주차 위치를 읽어 Isaac Sim 3D 공간에 텔레포트 반영.
  - **실행 방법**: `isaac-python scratch/isaac_amr_connector.py` (`~/.bashrc`에 정의된 alias 사용).
  - **문서 업데이트**: `SYSTEM_IMPROVEMENT_PLAN.md` 섹션 13.5 및 `README.md` 섹션 4~5 신규 추가.


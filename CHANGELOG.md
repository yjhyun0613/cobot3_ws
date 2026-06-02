# 📝 프로젝트 개발 히스토리 (Changelog)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 합니다.

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

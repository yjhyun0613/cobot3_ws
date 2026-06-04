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


# 📝 프로젝트 개발 히스토리 (Changelog)

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

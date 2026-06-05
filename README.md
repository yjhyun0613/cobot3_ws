# 🏗️ 쿠팡 물류창고 관제 시스템 (Control Tower) 실행 가이드

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

이 문서는 다중 로봇 시뮬레이션 환경을 제어하는 **중앙 관제탑 시스템(Control Tower)**을 구동하는 전체 프로세스를 안내합니다.

---

## 📂 프로젝트 문서 지도 (Documentation Map)

프로젝트 루트에 생성된 다양한 마크다운(`.md`) 문서들의 성격에 따라 다음과 같이 5가지 카테고리로 정리하였습니다. 필요한 내용을 찾을 때 참고하시기 바랍니다.

### 1. 📖 시스템 가이드 및 종합 보고서
* **[README.md](file:///home/rokey/cobot3_ws/README.md)**: 전체 시스템의 사전 요구사항, 데이터베이스 및 관제 노드 구동, 시뮬레이터 연동 및 백업 방법 가이드.
* **[PROJECT_REPORT.md](file:///home/rokey/cobot3_ws/PROJECT_REPORT.md)**: NVIDIA Isaac Sim 시뮬레이터 연동 결과 및 핵심 비즈니스 시나리오, 설계 결정 사항을 총망라한 최종 요약 보고서.

### 2. 📐 시스템 설계 및 명세서
* **[DATABASE_SCHEMA.md](file:///home/rokey/cobot3_ws/DATABASE_SCHEMA.md)**: PostgreSQL 및 Redis의 테이블 스키마 정의, ERD 관계도 및 캐싱 매핑 상세 설명서.
* **[INTERFACE_CHANGES.md](file:///home/rokey/cobot3_ws/INTERFACE_CHANGES.md)**: ROS2 Custom Service/Action 인터페이스 및 Fleet 실시간 모니터링을 위한 JSON 토픽 사양서.
* **[SYSTEM_IMPROVEMENT_PLAN.md](file:///home/rokey/cobot3_ws/SYSTEM_IMPROVEMENT_PLAN.md)**: 데이터베이스 정규화, QR코드 도입, 이중 버퍼, 우선순위 큐, Fail-safe 등 개선 계획 및 진행 상황 보고서.

### 3. 🔩 개별 기능 연동 계획서
* **[WAREHOUSE_DB_INTEGRATION_PLAN.md](file:///home/rokey/cobot3_ws/WAREHOUSE_DB_INTEGRATION_PLAN.md)**: 창고 주차 스팟(`spot_01` ~ `spot_10`)의 실시간 자원 관리 및 데이터베이스 연동 시나리오 계획서.
* **[ARUCO_INTEGRATION_GUIDE.md](file:///home/rokey/cobot3_ws/ARUCO_INTEGRATION_GUIDE.md)**: (레거시) ArUco 마커 기반 식별 기능 설계 및 비전 센서 연동 매뉴얼.

### 4. 📈 개발 이력 및 수정 내역
* **[CHANGELOG.md](file:///home/rokey/cobot3_ws/CHANGELOG.md)**: 프로젝트 시작(2026-06-01)부터 현재까지 날짜 및 시간별 상세 개발 이력.
* **[RECENT_UPDATES.md](file:///home/rokey/cobot3_ws/RECENT_UPDATES.md)**: 최근 배포된 일자 전환 워크플로우, 2D 맵 격자 UI, 중복 입고 검사 및 180도 회전 중복 트리거 버그 수정 내역 요약.

### 5. 🤖 AI 에이전트 인수인계
* **[AI_AGENT_GUIDE.md](file:///home/rokey/cobot3_ws/AI_AGENT_GUIDE.md)**: 후속 개발을 담당할 AI 에이전트를 위한 시스템 아키텍처, 핵심 DB 쿼리, 시나리오 분석 및 실행 커맨드 가이드.

---

## 🛠️ 1. 사전 요구사항 (Prerequisites)

구동하기 전에 다음 패키지들이 로컬 PC에 설치되어 있어야 합니다.

### ① Docker & Docker Compose
데이터베이스 서버를 띄우기 위해 필요합니다. (설치된 상태여야 함)

### ② Python 의존성 라이브러리 설치
관제탑 노드가 데이터베이스와 연결하기 위해 파이썬 드라이버가 필요합니다.
```bash
pip install psycopg2-binary redis
```

---

## 🚀 2. 구동 순서

### 1단계: 데이터베이스 및 GUI 모니터링 툴 구동
Docker Compose를 사용하여 PostgreSQL DB, Redis DB 및 두 DB의 웹 GUI 뷰어 툴을 백그라운드로 띄웁니다.

```bash
# 1. docker 폴더로 이동
cd ~/cobot3_ws/docker

# 2. 컨테이너 백그라운드 구동 (관리자 권한 필요)
sudo docker compose up -d
```
* 최초 구동 시 `init.sql` 스크립트가 실행되어 **로봇 정보, 작업대 10대(WS01~WS10), 창고 주차 스팟 10개(spot_01~spot_10), 예시 택배 데이터 8개**가 자동으로 적재됩니다.

---

### 2단계: 웹 GUI를 통한 실시간 데이터 확인
도커가 성공적으로 켜지면 웹 브라우저를 열고 다음 주소에 접속하여 마우스 클릭만으로 실시간 데이터를 보거나 파일로 다운로드할 수 있습니다.

#### ① PostgreSQL 데이터 조회 및 다운로드 (Adminer)
* **주소**: [http://localhost:8082](http://localhost:8082)
* **로그인 정보**:
  * **System**: `PostgreSQL` 선택
  * **Server**: `postgres` 입력
  * **Username**: `rokey` 입력
  * **Password**: `rokey_pass` 입력
  * **Database**: `warehouse_db` 입력
* 테이블 목록에서 `packages`나 `workstations`를 클릭하여 실시간 상태를 표로 볼 수 있고, 결과창 밑의 **Export** 버튼으로 CSV나 SQL 파일 저장이 가능합니다.

#### ② Redis 실시간 AMR 작업 큐 모니터링 (Redis Commander)
* **주소**: [http://localhost:8081](http://localhost:8081)
* 왼쪽 트리 메뉴의 `queue:amr_tasks` 리스트를 클릭하여 현재 AMR에게 대기 중인 작업 스케줄링 현황을 한눈에 시각화해 볼 수 있습니다.

---

### 3단계: ROS2 관제탑 노드 빌드 및 구동
로봇들로부터 통신을 받아 DB를 갱신하고 스케줄링 명령을 하달하는 메인 ROS2 노드를 실행합니다.

```bash
# 1. 워크스페이스 루트로 이동
cd ~/cobot3_ws

# 2. ROS2 패키지 컴파일 (최초 1회 또는 코드 수정 시)
colcon build

# 3. ROS2 환경 변수 소싱
. install/setup.bash

# 4. 관제 센터 노드 실행
ros2 run cobot3 control_tower
```

---

## 🖥️ 3. 실시간 웹 대시보드 및 모의 시뮬레이터 구동 (테스트용)

관제탑 시스템 및 DB 상태를 시각적으로 확인하고 가상의 적재 시나리오를 테스트할 수 있도록 웹 대시보드 및 모의 시나리오 실행 스크립트가 `scratch/` 디렉토리에 내장되어 있습니다.

### ① 실시간 웹 대시보드 (FastAPI 기반)
DB 데이터(PostgreSQL & Redis)를 한눈에 모니터링할 수 있는 멋진 다크 모드 대시보드를 제공합니다.

* **구동 방법**:
  ```bash
  # 1. FastAPI 및 Uvicorn 라이브러리 설치 (미설치 시)
  pip install fastapi uvicorn

  # 2. 대시보드 서버 실행 (워크스페이스 루트에서 실행)
  python3 scratch/dashboard_server.py
  ```
* **접속 주소**: 웹 브라우저를 열고 `http://localhost:8009`에 접속합니다.
* **주요 기능**:
  * 창고 주차 스팟 10개(`spot_01` ~ `spot_10`) 및 작업대 10개(`WS01` ~ `WS10`)의 실시간 상태 시각화
  * Redis AMR 명령 대기열(`queue:amr_tasks`) 실시간 우선순위 목록 표시
  * 택배 위치, 수령인, 상태, 출고 바코드 등을 테이블로 실시간 추적
  * **[⚡ 시뮬레이션 적재 발생]** 버튼으로 DB 및 Redis에 Look-ahead 명령어가 정상 동작하는지 모의 테스트 가능
  * **[🔄 데이터베이스 초기화]** 버튼으로 테이블 상태 공장 초기화 가능

### ② 모의 ROS2 시뮬레이터 테스트 (`run_full_simulation_robot.py`)
실제 ROS2 통신 환경에서 관제 센터 노드가 올바르게 응답하는지 검증하기 위한 가상 노드입니다. AMR 액션 서버(`manage_workstation`), 포장 로봇 액션 서버(`start_packaging`) 등을 모의(Mocking)하여 관제탑과의 핑퐁 제어 루프를 시뮬레이션합니다.

* **구동 방법**:
  ```bash
  # 1. 새로운 터미널에서 ROS2 환경 설정 소싱
  cd ~/cobot3_ws
  . install/setup.bash

  # 2. 시뮬레이터 실행
  python3 scratch/run_full_simulation_robot.py
  ```
* **시나리오 흐름**:
  1. 시뮬레이터 가동 시 대기(`WAITING`) 상태인 택배 상자를 순차적으로 분류합니다.
  2. 분류 로봇(bg2)이 택배 박스를 스캔하여 목적지 날짜를 조회하고 이에 해당하는 대상 로봇(`sg2_in_01` ~ `03`)을 결정합니다.
  3. 로봇은 해당 라인의 A구역(`sg2_in_XX_A`)에 빈 작업대가 배치될 때까지 대기한 후 적재 및 진척도 보고를 진행합니다.
  4. 3번째 슬롯 적재 완료 시점에 관제탑에서 **Look-ahead 예비 작업대 배치 태스크(B구역 호출)**를 정상 발행하는지 감시합니다.
  5. 8번째 슬롯까지 적재 시 완충 작업대가 회수 및 보관/포장 이송되고, B구역의 작업대가 A구역으로 승격되어 연속 공정이 이루어지는지 검증합니다.

---

## 💾 4. DB 상태 파일로 백업 및 복원하는 법

### 데이터베이스 전체 백업 (SQL 파일로 저장)
현재까지 시뮬레이션을 진행하면서 DB에 기록된 모든 적재 상태 및 이력을 파일로 영구 보관하고 싶을 때 사용합니다.
```bash
sudo docker exec -t warehouse_postgres pg_dumpall -U rokey > ~/cobot3_ws/docker/warehouse_backup.sql
```

### 백업 파일로 데이터베이스 복원하기
저장해 둔 백업 파일을 다시 DB 컨테이너로 밀어 넣어 이전 시뮬레이션 상태를 복구할 때 사용합니다.
```bash
cat ~/cobot3_ws/docker/warehouse_backup.sql | sudo docker exec -i warehouse_postgres psql -U rokey -d warehouse_db
```

# 🏗️ 쿠팡 물류창고 관제 시스템 (Control Tower) 실행 가이드

이 문서는 다중 로봇 시뮬레이션 환경을 제어하는 **중앙 관제탑 시스템(Control Tower)**을 구동하는 전체 프로세스를 안내합니다.

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
* 최초 구동 시 `init.sql` 스크립트가 실행되어 **로봇 정보, 작업대(WS01~03), 예시 택배 데이터 8개**가 자동으로 적재됩니다.

---

### 2단계: 웹 GUI를 통한 실시간 데이터 확인
도커가 성공적으로 켜지면 웹 브라우저를 열고 다음 주소에 접속하여 마우스 클릭만으로 실시간 데이터를 보거나 파일로 다운로드할 수 있습니다.

#### ① PostgreSQL 데이터 조회 및 다운로드 (Adminer)
* **주소**: [http://localhost:8080](http://localhost:8080)
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

## 💾 3. DB 상태 파일로 백업 및 복원하는 법

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

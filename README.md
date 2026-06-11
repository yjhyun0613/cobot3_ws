# 🏗️ 쿠팡 물류창고 관제 시스템 (Control Tower) 실행 가이드

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

이 문서는 다중 로봇 시뮬레이션 환경을 제어하는 **중앙 관제탑 시스템(Control Tower)**을 구동하는 전체 프로세스를 안내합니다.

---

## 📂 프로젝트 문서 지도 (Documentation Map)

프로젝트 루트의 문서를 효율적으로 찾아볼 수 있도록 다음과 같이 3대 핵심 문서로 단순화하여 통합하였습니다.

### 1. 📖 [README.md](file:///home/yoon/cobot3_ws/README.md) (사용 매뉴얼 및 데모 시나리오)
* 전체 시스템의 기동 프로세스, 사전 요구사항, 데이터 백업/복원, 그리고 실제 발표 현장에서 활용할 **6월 8일 데모 시연 진행 스크립트** 수록.

### 2. 🔌 [ROBOT_AMR_INTEGRATION_GUIDE.md](file:///home/yoon/cobot3_ws/ROBOT_AMR_INTEGRATION_GUIDE.md) (기술 연동 명세 및 아키텍처 규격서)
* ROS 2 서비스/액션 메시지 정의, Redis 캐시 구조, Cyclone DDS 무선 통신 설정, 데이터베이스 스키마(PostgreSQL ERD) 및 창고 물리 격자 좌표(X, Y) 매핑 총망라.

### 3. 📊 [PROJECT_REPORT.md](file:///home/yoon/cobot3_ws/PROJECT_REPORT.md) (종합 구축 결과 및 개선 보고서)
* 4단계 비즈니스 시나리오, JIT 교체/인터로킹 아키텍처 결정 사항, 데이터베이스 정규화/이중 버퍼/우선순위 큐 등의 시스템 개선 내역 및 마일스톤 이력 요약.

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
* 최초 구동 시 `init.sql` 스크립트가 실행되어 **로봇 정보, 작업대 10대(WS01~WS10), 창고 주차 스팟 10개(spot_01~spot_10), 출고 대기 스팟 4개(stage_01~stage_04), 바닥 QR 격자 맵(`floor_qr_map`) 약 117개 노드(논리 스팟 + AMR 주행 경로)**가 자동으로 적재됩니다.

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
* ① 왼쪽 트리 메뉴의 `queue:amr_tasks` 리스트를 클릭하여 현재 AMR에게 대기 중인 작업 스케줄링 현황을 한눈에 시각화해 볼 수 있습니다.

---

### 3단계: 시나리오 데이터 초기화

시뮬레이션 시작 전 DB 상태를 원하는 시나리오로 설정합니다. 두 가지 방식 중 하나를 선택하세요.

#### 방법 A: 빈 상태에서 시작 (공장 초기화)
작업대 10대를 주차장에 정렬하고, 패키지를 모두 비운 깨끗한 상태로 시작합니다.
```bash
cd ~/cobot3_ws
python3 scratch/reset_db.py
```

#### 방법 B: 6월 8일 이월 재고 시나리오에서 시작 (권장)
전날(6~7일)의 부분 적재 작업대(WS01 완충 8개, WS02 5개, WS03 5개)와 AMR 5대 충전기 배치 등 실제 영업 재개 시점의 상태를 마스킹합니다.
```bash
cd ~/cobot3_ws
python3 docker/init_june_8th_state.py
```

---

### 4단계: 프로그램 구동 (터미널 3~4개 필요)

> [!IMPORTANT]
> **분산 환경 vs 로컬 환경**: 4대 PC 분산 환경(관제탑, AMR, SG2, BG2)에서 WiFi로 연동할 때는 각 터미널에서 `export CYCLONEDDS_URI=file://$HOME/.ros/cyclonedds_wifi.xml`을 지정하고 `ROS_LOCALHOST_ONLY=0`으로 설정합니다.

#### 터미널 1: FastAPI 웹 대시보드 서버
```bash
cd ~/cobot3_ws
python3 scratch/dashboard_server.py
```
* 접속 주소: **http://localhost:8009**

#### 터미널 2: ROS2 관제탑(Control Tower) 노드
```bash
cd ~/cobot3_ws
source install/setup.bash
export ROS_DOMAIN_ID=119
export ROS_LOCALHOST_ONLY=0        # 분산 환경
export CYCLONEDDS_URI=file://$HOME/.ros/cyclonedds_wifi.xml
ros2 run cobot3 control_tower
```

#### 터미널 3: 가상 AMR 및 SG2 로봇 시뮬레이터 (Local 통합 테스트용)
만약 실제 로봇 기기나 AMR PC 없이 본인 PC 내부에서 단독 시나리오를 연동 테스트하려면 가상 시뮬레이터 노드들을 켭니다.
```bash
# 가상 AMR 실행 (1초 단위 실시간 주행 보간 및 Redis/대시보드 위젯 동기화)
ros2 run cobot3 mock_amr

# 가상 SG2 실행 (inbound 로봇 자동적재 및 outbound 포장액션, 180도 회전 락 지원)
ros2 run cobot3 mock_sg2
```

#### 터미널 4 (선택): 분산 시뮬레이션 상자 동기화 노드
Isaac Sim bg2/sg2 2대 분산 시뮬레이션 환경에서 상자 순간이동(소멸/소환)을 제어할 때 사용합니다.
```bash
cd ~/cobot3_ws
source install/setup.bash
export ROS_DOMAIN_ID=119
export ROS_LOCALHOST_ONLY=0
export CYCLONEDDS_URI=file://$HOME/.ros/cyclonedds_wifi.xml
ros2 run cobot3 sim_sync_node
```

> [!TIP]
> **로컬 전용 테스트 시**: 다른 PC들과 통신하지 않고 본인 PC 내부에서만 독립적으로 테스트할 때는 각 터미널에서 `unset CYCLONEDDS_URI`를 실행하고 `ROS_LOCALHOST_ONLY=1`로 설정하십시오.

---

### 5단계: 대시보드에서 CSV 업로드 및 영업 시작

1. 웹 브라우저에서 **`http://localhost:8009`**에 접속합니다.
2. 상단의 **[📥 CSV 입고 명단 업로드]** 버튼을 클릭하여 아래 파일 중 하나를 업로드합니다.
   * `scratch/packages_2026-06-08.csv` (6월 8일 시나리오용)
   * `scratch/packages_2026-06-09.csv`, `scratch/packages_2026-06-10.csv` 등
3. 모든 기기가 연결되고 대기 패키지가 존재하면 **[🟢 영업 시작]** 버튼이 활성화되며, 클릭 시 시뮬레이션이 개시됩니다. (비활성화 상태 시 웹 페이지를 새로고침(F5) 해주십시오.)

---

## 💾 6. DB 상태 파일로 백업 및 복원하는 법

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

---

## 🤖 7. AI 에이전트 개발 정보 및 아키텍처
* 이 가이드와 관련한 자세한 통신 규격 및 구조는 **[ROBOT_AMR_INTEGRATION_GUIDE.md](file:///home/yoon/cobot3_ws/ROBOT_AMR_INTEGRATION_GUIDE.md)**를 참조하십시오.

---

## 🎬 8. 데모 시연 시나리오 및 진행 플레이북 (6월 8일 데모 기준)

### ① 시나리오 개요 (Overview)
물류 창고는 매일 리셋되지 않고 전날의 잔여 물량이 누적되는 연속성을 가집니다. 본 데모는 **과거 2일간의 미처리 잔여 재고 18개**가 야간 자율 정렬(Shift-Left)을 통해 완벽하게 전진 배치되어 있는 6월 8일 아침 상황에서 시작합니다. 

* **당일(6/8) 출고 목표량**: 총 13개 (과거 이월분) + 당일 신규 유입분
* **내일(6/9) 출고 대기량**: 총 5개 (과거 이월분) + 당일 신규 유입분

### ② 초기 작업대(Workstation) 맵 배치 현황
시뮬레이션 가동 직전, 총 10대의 작업대는 자원 효율성 규칙(사용하지 않는 예비대는 메인 창고에 바둑판 정렬)에 따라 다음과 같이 마스킹되어 있습니다.

| 작업대 ID | 현재 위치 (Spot) | 적재 상태 | 대상 출고일 | 상태 설명 (야간 정렬 결과) |
| :--- | :--- | :---: | :---: | :--- |
| **`WS01`** | `stage_01` (스테이징) | **8 / 8 칸** | 오늘 (6/8) | 어제 완충되어 대기 중. **시작 즉시 출고장 이송 대상** |
| **`WS02`** | `sg2_in_01_A` (1번 라인) | **5 / 8 칸** | 오늘 (6/8) | 2번 라인에서 전진 배치됨. **신규 택배 이어서 적재** |
| **`WS03`** | `sg2_in_02_A` (2번 라인) | **5 / 8 칸** | 내일 (6/9) | 3번 라인에서 전진 배치됨. |
| **`WS04`** | `sg2_in_03_A` (3번 라인) | **0 / 8 칸** | 모레 (6/10) | 새로 보충된 빈 작업대. |
| **`WS05`**~**`WS10`** | `spot_01`~`06` (메인 창고) | **0 / 8 칸** | - | 주차장에 오와 열을 맞춰 대기 중인 예비 작업대들 |

### ③ 시연 강조 하이라이트 (Demo Highlights)

#### 1. Fail-Safe UI 및 잠금장치 (Data Integrity & Device Sync)
* 데이터베이스에 6월 8일자 신규 CSV 명단이 업로드되고, **실제 구동 중인 AMR(1대 이상)의 Redis 연결 상태가 감지될 때까지** 대시보드의 **[영업 시작] 버튼이 잠금(Disabled) 상태로 유지**되어 운영자 실수 및 무연동 가동을 원천 차단합니다.

#### 2. 단일 슬롯 JIT (Just-In-Time) 직렬 교체 및 인터로킹
* 공간 최적화를 위해 라인당 단 1개의 Active 구역만 사용합니다.
* `WS02`에 3개의 상자가 추가되어 **8칸이 가득 차는 순간**, 관제탑이 입고 로봇에게 **일시정지(Pause) 신호**를 쏴서 동작을 멈춥니다.
* AMR 3대 한정 큐(Queue) 시스템이 만석 작업대를 인출하고 새 작업대를 안착시키면 **재가동(Resume) 신호**가 떨어져 공정이 이어집니다.

#### 3. 이벤트 기반 무부하 마감(EOD) 스캔
* 매초 DB를 조회하는 Polling 부하를 없앴습니다. 포장 로봇이 패키지를 `COMPLETED`로 만들 때마다 카운터를 차감하며, **오늘 날짜의 잔여물이 0이 되는 순간 단 한 번의 트리거**로 영업 종료(Shift-Left)를 발동시킵니다.

### ④ 발표 진행 스크립트 (Step-by-Step Scenario)

1. **환경 초기화 브리핑**
   * 터미널에서 `python3 init_june_8th_state.py` 실행.
   * **발표 멘트**: *"현재 시스템은 6월 8일 아침 9시로 세팅되었습니다. 맵을 보시면 어제 미처리된 5칸짜리 이월 작업대들이 1번, 2번 라인에 전진 배치되어 있고, 남은 예비대들은 주차장에 완벽하게 정돈되어 있습니다. 초기 상태이므로 실제 AMR이 켜져서 연결되기 전까지는 지도상에 AMR이 표시되지 않습니다."*
2. **대시보드 CSV 업로드 및 AMR 기기 연동 (데이터 및 디바이스 주입)**
   * 대시보드의 회색(잠금) 버튼 확인 후 `packages_2026-06-08.csv` 파일 업로드 및 가상 AMR/SG2 모의 노드 실행.
   * **발표 멘트**: *"시스템은 당일 명단 CSV와 실제 물리/시뮬레이션 AMR 기기의 연결 상태가 모두 충족될 때까지 가동을 강제 차단합니다. 방금 CSV를 업로드하고 AMR이 연동되어 데이터 무결성과 통신 정합성이 확보되자 영업 시작 버튼이 초록색으로 활성화되었습니다."*
3. **[영업 시작] 및 하이라이트 동시 다발 발동**
   * 버튼 클릭과 동시에 시뮬레이터 및 관제탑 가동.
   * **발표 멘트**: *"시작과 동시에 관제탑이 스테이징에 대기 중이던 8칸 완충 작업대(WS01)를 감지하고 AMR을 보내 즉시 출고를 시작합니다. 동시에 1번 라인에서는 어제 넘어온 WS02 작업대에 오늘 택배를 6번 슬롯부터 끊김 없이 누적(Carry-over) 적재하고 있습니다."*
4. **JIT 작업대 교대 (Swapping) 연출**
   * 1번 라인 8칸 만석 도달 시.
   * **발표 멘트**: *"8칸이 가득 차자마자 로봇 팔이 일시 정지(Pause)합니다. 대기 큐에 있던 AMR들이 교대 진입하여 새 작업대를 안착시키고 나면 로봇 팔이 다시 깨어나 적재를 이어갑니다. 이 모든 과정에 충돌이나 데드락은 발생하지 않습니다."*

---

## 📝 9. AI 에이전트 문서 유지보수 규칙

본 프로젝트의 관리 및 개발을 맡는 모든 AI 에이전트는 아래 규칙을 엄격하게 수행해야 합니다.

1. **상시 동기화**: 소스코드, 데이터베이스 스펙, ROS 2 인터페이스 변경이 발생하면 관련 모든 마크다운 문서(`ROBOT_AMR_INTEGRATION_GUIDE.md`, `PROJECT_REPORT.md` 등)를 즉시 동시 수정해야 합니다.
2. **경고 헤더 표준화**: 모든 마크다운 파일 최상단에는 반드시 아래 경고 안내문구가 포함되어 있어야 합니다.
   ```markdown
   > [!IMPORTANT]
   > **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.
   ```

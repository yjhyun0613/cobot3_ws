# 🏗️ 쿠팡 물류창고 관제 시스템 (Control Tower)

NVIDIA Isaac Sim 시뮬레이터 환경에서 다중 로봇(분류, 적재, 이송, 포장)과 하이브리드 DB(PostgreSQL + Redis)를 연동하여 물류 전 공정을 자율 제어하는 **중앙 관제 시스템(Control Tower)** 프로젝트입니다.

---

## 📂 프로젝트 구조

```
cobot3_ws/
├── README.md                    ← 현재 문서 (실행 가이드)
├── main_code_guide.ipynb        ← 핵심 코드 및 알고리즘 종합 가이드 (Jupyter)
├── docs/                        ← 기술 문서 모음
│   ├── PROJECT_OVERVIEW.md      ← 프로젝트 개요 및 아키텍처 요약
│   ├── PROJECT_REPORT.md        ← 종합 구축 결과 보고서
│   ├── ROBOT_AMR_INTEGRATION_GUIDE.md  ← ROS 2 연동 규격서
│   ├── DATABASE_SCHEMA.md       ← DB 스키마 설계서
│   ├── PHYSICAL_LAYOUT.md       ← 창고 물리 좌표 맵
│   └── ...
├── src/
│   ├── cobot3/                  ← ROS 2 메인 패키지
│   │   └── cobot3/
│   │       ├── control_tower_node.py   ← 관제탑 노드
│   │       ├── sim_sync_node.py        ← 분산 시뮬 동기화 노드
│   │       ├── mock_amr_node.py        ← 가상 AMR 시뮬레이터
│   │       └── mock_sg2_node.py        ← 가상 SG2 시뮬레이터
│   └── cobot3_interfaces/       ← 커스텀 서비스/액션/메시지 정의
├── docker/                      ← Docker Compose 및 DB 초기화
├── scratch/                     ← 유틸리티 스크립트 및 CSV 데이터
│   ├── dashboard_server.py      ← FastAPI 웹 대시보드
│   ├── reset_db.py              ← DB 공장 초기화
│   └── packages_*.csv           ← 일별 택배 입고 명단
└── start_test_env.sh            ← 통합 테스트 환경 일괄 실행
```

---

## 🛠️ 사전 요구사항

| 항목 | 설명 |
| :--- | :--- |
| **ROS 2 Humble** | 관제탑 노드 실행을 위한 ROS 2 미들웨어 |
| **Docker & Docker Compose** | PostgreSQL + Redis 컨테이너 구동용 |
| **Python 라이브러리** | `pip install psycopg2-binary redis` |

---

## 🚀 실행 순서

### Step 1. 데이터베이스 컨테이너 구동

```bash
cd ~/cobot3_ws/docker
sudo docker compose up -d
```

> [!NOTE]
> 최초 구동 시 `init.sql`이 자동 실행되어 로봇 정보, 작업대 10대, 창고 스팟, 바닥 QR 격자 맵 등이 자동으로 적재됩니다.

---

### Step 2. DB 시나리오 초기화 (택 1)

#### 방법 A — 빈 상태에서 시작 (공장 초기화)
```bash
cd ~/cobot3_ws
python3 scratch/reset_db.py
```

#### 방법 B — 6월 8일 이월 재고 시나리오에서 시작 (권장)
```bash
cd ~/cobot3_ws
python3 docker/init_june_8th_state.py
```

---

### Step 3. 프로그램 구동

> [!IMPORTANT]
> **분산 환경 설정**: 다수 PC 분산 환경에서는 각 터미널에 아래 환경변수를 먼저 설정합니다.
> ```bash
> export ROS_DOMAIN_ID=119
> export ROS_LOCALHOST_ONLY=0
> export CYCLONEDDS_URI=file://$HOME/.ros/cyclonedds_wifi.xml
> ```
> **로컬 전용 테스트** 시에는 `ROS_LOCALHOST_ONLY=1`로 설정하고 `CYCLONEDDS_URI`는 생략합니다.

#### 터미널 1 — 웹 대시보드 서버
```bash
cd ~/cobot3_ws
python3 scratch/dashboard_server.py
```
→ 접속 주소: **http://localhost:8009**

#### 터미널 2 — 관제탑 (Control Tower) 노드
```bash
cd ~/cobot3_ws
source install/setup.bash
ros2 run cobot3 control_tower
```

#### 터미널 3 — 가상 로봇 시뮬레이터 (테스트용)
실제 로봇 없이 단독 테스트할 때 사용합니다.
```bash
cd ~/cobot3_ws && source install/setup.bash

# 가상 AMR (실시간 주행 보간 + Redis 동기화)
ros2 run cobot3 mock_amr

# 가상 SG2 (입고 적재 + 출고 포장 + 180도 회전 락)
ros2 run cobot3 mock_sg2
```

#### 터미널 4 — 분산 시뮬 동기화 노드 (선택)
Isaac Sim bg2/sg2 분산 환경에서 상자 순간이동을 제어할 때 사용합니다.
```bash
cd ~/cobot3_ws && source install/setup.bash
ros2 run cobot3 sim_sync_node
```

---

### Step 4. 대시보드에서 영업 시작

1. **http://localhost:8009** 접속
2. **[📥 CSV 입고 명단 업로드]** 클릭 → `scratch/packages_2026-06-08.csv` 등 업로드
3. AMR이 연결되고 CSV가 등록되면 **[🟢 영업 시작]** 버튼 활성화 → 클릭하여 시뮬레이션 개시

---

## 🖥️ 모니터링 도구

| 도구 | 주소 | 용도 |
| :--- | :--- | :--- |
| **웹 대시보드** | http://localhost:8009 | 실시간 2D 관제 맵 및 시스템 제어 |
| **Adminer (PostgreSQL)** | http://localhost:8082 | DB 테이블 조회 / CSV Export |
| **Redis Commander** | http://localhost:8081 | AMR 작업 큐 및 캐시 실시간 모니터링 |

> **Adminer 로그인**: System → `PostgreSQL` / Server → `postgres` / User → `rokey` / Password → `rokey_pass` / DB → `warehouse_db`

---

## 💾 DB 백업 및 복원

```bash
# 백업 (현재 DB 상태를 SQL 파일로 저장)
sudo docker exec -t warehouse_postgres pg_dumpall -U rokey > ~/cobot3_ws/docker/warehouse_backup.sql

# 복원 (백업 파일에서 DB 상태 복구)
cat ~/cobot3_ws/docker/warehouse_backup.sql | sudo docker exec -i warehouse_postgres psql -U rokey -d warehouse_db
```

---

## 📁 기술 문서 (docs/)

| 문서 | 설명 |
| :--- | :--- |
| [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) | 시스템 아키텍처, 핵심 알고리즘, 기술 스택 요약 |
| [PROJECT_REPORT.md](docs/PROJECT_REPORT.md) | 종합 구축 결과 및 마일스톤 보고서 |
| [ROBOT_AMR_INTEGRATION_GUIDE.md](docs/ROBOT_AMR_INTEGRATION_GUIDE.md) | ROS 2 서비스/액션 규격, DDS 설정, 물리 좌표 매핑 |
| [DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | PostgreSQL 테이블 설계 및 ERD |
| [PHYSICAL_LAYOUT.md](docs/PHYSICAL_LAYOUT.md) | 창고 물리 격자 좌표 맵 |

# AMR 분산 연동 및 구동 가이드

이 문서의 설정은 내 PC(관제탑, DB, 대시보드 전용)와 상대방 PC(아이작 심 및 AMR 제어 전용)로 이중화하여 작동할 때의 실행 방법을 명시합니다. 
(내 PC에서는 시뮬레이션 및 모의 주행 스크립트를 실행하지 않고, 오직 관제와 통신만 수행합니다.)

---

## 1. 상대방 PC (아이작 심 & AMR 실제 제어)

상대방 PC에서는 물리 시뮬레이션 환경(Isaac Sim)과 로봇 및 작업대의 움직임을 제어하는 프로그램을 실행합니다.

### 필수 실행 1: Isaac Sim 실행
상대방 PC의 터미널에서 아래 명령어로 Isaac Sim 환경을 구동합니다.
```bash
/home/rokey/dev_ws/isaac_sim/isaac-sim.sh \
  --/plugins/carb.tasking.plugin/threadCount=8 \
  --/plugins/omni.tbb.globalcontrol/maxThreadCount=8 \
  --/persistent/physics/numThreads=4 \
  --/rtx/post/dlss/execMode=0
```

### 필수 실행 2: AMR 실제 제어 컨트롤러 실행
Isaac Sim이 켜진 후, **Window -> Script Editor**를 열고 아래 파이썬 코드를 입력해 실행합니다.
```python
exec(open('/home/rokey/isaaclab_ws/isaac_aruco/amr/amr_live_existing_stage_true8_qr_camera_controller_gpu.py', encoding='utf-8').read())
```
* **주요 역할**:
  * `AMR_01` ~ `AMR_05` 제어
  * `RACK_01` ~ `RACK_10` 제어
  * `bridge_queue/commands` 감시 및 pickup / carry / place 동작 수행
  * Redis에 AMR의 실시간 위치 및 상태 정보 publish (`REDIS_HOST = "192.168.100.20"`)

### 필수 실행 3: Bridge node 실행
상대방 PC의 새 터미널에서 DDS 통신 설정을 적용한 후 실행합니다.
```bash
export ROS_DOMAIN_ID=119
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

cd ~/isaaclab_ws/isaac_aruco/amr
./run_bridge_gpu.sh
```
* **주요 역할**:
  * 내 PC(관제탑)로부터 `/manage_workstation` 및 `/move_package` Action Goal 수신
  * `bridge_queue/commands/CMD_*.json` 명령 파일 생성 ➡️ Isaac Sim 컨트롤러가 이를 받아 처리
  * 로봇이 동작을 완료하면 결과(success/fail) 및 피드백을 다시 Action client로 반환

---

## 2. 내 PC (관제탑 & 데이터베이스 전용)

내 PC에서는 모의 주행(Simulation) 및 모킹 로봇 관련 노드를 구동하지 않으며, 오직 데이터베이스 서버와 관제탑, 모니터링 웹 대시보드만 구동합니다.

### 필수 실행 1: Docker 데이터베이스 및 캐시 서버 실행
터미널에서 DB 컨테이너들을 백그라운드로 실행합니다.
```bash
cd ~/cobot3_ws/docker
sudo docker compose up -d
```
* **주요 역할**: PostgreSQL(포트 5432) 및 Redis(포트 6379, 외부 접속 허용 모드) 구동

### 필수 실행 2: ROS 2 관제탑 (Control Tower) 실행
ROS 2 분산망 통신 환경 변수를 선언하고 관제탑을 가동합니다.
```bash
cd ~/cobot3_ws
export ROS_DOMAIN_ID=119
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

source install/setup.bash
ros2 run cobot3 control_tower
```
* **주요 역할**: 대시보드의 입고 개시 명령에 맞춰 전체 작업 주문 스케줄링 및 AMR PC로 Action 명령 전달

### 필수 실행 3: FastAPI 웹 대시보드 가동
웹 브라우저 모니터링 및 시나리오 시작 파일(CSV) 업로드를 위해 대시보드 웹 서버를 켭니다.
```bash
cd ~/cobot3_ws
python3 scratch/dashboard_server.py
```
* **주요 역할**: 2D 관제 모니터링 UI 및 패키지 데이터 로드 기능 제공 (`http://localhost:8009`)

# 🔌 로봇 및 설비 연동 명세 통합 가이드 (Robot & AMR Integration Guide)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

이 문서는 **쿠팡 물류창고 관제 시스템(Control Tower)**과 자율 주행 로봇(AMR), 입고/출고 설비 로봇(분류 로봇 `bg2`, 적재 로봇 `sg2_in`, 포장 로봇 `sg2_out`) 간의 데이터 연동 및 인터페이스 세부 규격을 단일 문서로 정의한 통합 연동 가이드입니다.

---

## 📌 1. 시스템 아키텍처 개요 (하이브리드 통신)
본 관제 시스템은 다중 로봇의 안정적인 제어와 가벼운 모니터링을 실현하기 위해 **제어 명령 채널(Control Plane)**과 **상태 모니터링 채널(Data Plane)**을 분리한 하이브리드 아키텍처를 채택하고 있습니다.

```mermaid
graph TD
    subgraph PC B (관제 및 DB)
        CT[Control Tower Node] <--> DB[(PostgreSQL)]
        CT <--> Redis[(Redis Cache)]
        Dash[FastAPI Dashboard] <-- WebSocket (0.5s) --> Browser[Client Dashboard]
    end
    
    subgraph PC A (AMR 및 시뮬레이터)
        AMR_Act[AMR Action Server] <--> CT
        Isaac[NVIDIA Isaac Sim] <-- TCP Socket (30Hz) --> Bridge[Socket-ROS2 Bridge]
    end

    Bridge <--> Redis
    CT -.-> |/fleet/* Topics (1Hz)| Dash
```

1. **제어 명령 (Control Plane)**: 관제탑 ➡️ 각 로봇 설비
   * **방식**: ROS 2 Action 및 Service
   * **목적**: 특정 작업대 이송, 패키지 분류 조회, 포장 지시 등의 트랜잭션 단위 실행.
2. **실시간 모니터링 (Data Plane)**: AMR/설비 ➡️ 관제탑 & 대시보드
   * **방식**: Redis 인메모리 캐시 및 ROS 2 JSON 토픽 (`/fleet/*`)
   * **목적**: AMR의 초당 고주파수 (x, y) 좌표 및 배터리 잔량, 전체 설비 상태를 가볍고 빠르게 브로드캐스팅.

---

## 🏃 2. ROS 2 제어 인터페이스 (Action)

### ① `ManageWorkstation.action`
* **액션 경로**: `cobot3_interfaces/action/ManageWorkstation`
* **역할**: AMR에게 특정 작업대(`WS01`~`WS10`)를 대상 위치(입고 라인, 보관 스팟, 출고 포장대)로 이동시키거나 제자리 회전(`ROTATE_WORKSTATION`)을 하도록 지시합니다.
* **Goal/Result/Feedback 정의**:
```text
# Goal Definition
string workstation_id       # 제어 대상 작업대 고유 ID (예: "WS01" ~ "WS10")
string start_location       # 출발지 논리 위치 (예: "spot_01", "sg2_in_01_A")
string target_location      # 도착지 논리 위치 (예: "sg2_out_00_A", "spot_02")
string workstation_qr_id    # 작업대 물리 QR코드 식별자 (예: "WORKSTATION_WS01")
string target_qr_id         # 목적지 바닥 격자 QR ID (예: "FLOOR_X_1.5_Y_3.0")
float64 target_x            # 목적지 2D 물리 X 좌표 (meters)
float64 target_y            # 목적지 2D 물리 Y 좌표 (meters)
float64 target_yaw          # 목적지 2D 물리 회전각 (radians)

---
# Result Definition
bool success                # 이송 태스크 완료 여부 (성공: true / 실패: false)

---
# Feedback Definition
float32 distance_remaining  # 목적지까지의 남은 거리 (meters)
string status               # 현재 구동 상태 ("PICKING", "NAVIGATING", "PLACING", "CHARGING")
```
> [!NOTE]
> **주행 구현 참고**: AMR 제어기는 `target_qr_id` 또는 `target_x / target_y / target_yaw` 물리 좌표 중 팀의 내비게이션 알고리즘에 적합한 필드를 선택적으로 파싱하여 이동할 수 있습니다.

### ② `MovePackage.action`
* **액션 경로**: `cobot3_interfaces/action/MovePackage`
* **역할**: AMR에게 창고 직송 등의 단일 패키지 강제 이송을 명령할 때 사용됩니다.
* **Goal/Result/Feedback 정의**:
```text
# Goal Definition
string package_id           # 이송 대상 상자 ID
string customer_name        # 수령인 성함
string destination_zone     # 창고 내 보관 구역 (예: "ZONE_A")
string package_qr_id        # 상자 고유 QR코드 ID (예: "PKG_RAND_001")

---
# Result Definition
bool success                # 최종 이송 완료 여부
string error_msg            # 실패 시 에러 메시지

---
# Feedback Definition
string current_position     # AMR의 현재 위치 좌표 또는 구역명
float32 progress            # 이동 진행률 (0.0 ~ 100.0 %)
```

### ③ `StartPackaging.action`
* **액션 경로**: `cobot3_interfaces/action/StartPackaging`
* **역할**: 출고 포장 로봇(`sg2_out_00`)에게 특정 작업대에 도달한 상자 8칸의 포장 공정을 명령합니다.
* **Goal/Result/Feedback 정의**:
```text
# Goal Definition
string workstation_id       # 포장 작업을 수행할 작업대 ID (예: "WS01")
string today_date           # 오늘 영업일 날짜 YYYYMMDD (예: "20260608")
string workstation_qr_id    # 작업대 고유 QR코드 ID

---
# Result Definition
bool success                # 전체 포장 공정 완료 성공 여부
string[] final_output_ids   # 발행된 고유 출고(송장) ID 리스트

---
# Feedback Definition
int32 completed_slots       # 현재 완료한 누적 슬롯 개수 (1 ~ 8)
string last_packed_slot     # 직전에 포장 완료된 슬롯 번호 (예: "slot_3")
```
#### 💡 고유 출고 ID (`final_output_ids`) 규격 규칙
포장 로봇 제어기는 각 슬롯의 포장이 완료될 때마다 아래 포맷으로 고유한 출고 바코드 문자열을 만들어 Result 배열에 담아야 합니다.
* **포맷**: `[포장로봇ID]_[작업대ID]_SLOT[슬롯번호]_[YYYYMMDD]_[HHMMSS]`
* **예시**: `sg2_out_00_WS01_SLOT3_20260608_121545`

---

## 🔌 3. ROS 2 서비스 (Service) 인터페이스

### ① `GetPackageRoute.srv`
* **서비스 경로**: `cobot3_interfaces/srv/GetPackageRoute`
* **역할**: 컨베이어 분류기(`bg2`)가 진입한 택배 박스의 QR코드를 스캔하여 배송일자별로 어떤 라인으로 분류해야 하는지 목적지를 조회합니다.
* **Request/Response 정의**:
```text
# Request
string package_id           # 상자 바코드 ID (비어있을 수 있음)
string customer_name        # 수령인 성함 (비어있을 수 있음)
string qr_id                # 바코드에서 스캔한 QR코드 원본 문자열 (예: "PKG_RAND_001")

---
# Response
string route_destination    # 분류 목적지 배송일자 문자열 (예: "2026-06-08")
```
#### 💡 분류 라인 매핑 규칙
* **오늘 (Today)** 날짜 물량 ➡️ **1번 라인 (`sg2_in_01`)**으로 푸싱 분류
* **내일 (Tomorrow)** 날짜 물량 ➡️ **2번 라인 (`sg2_in_02`)**으로 푸싱 분류
* **모레 (Day After)** 날짜 물량 ➡️ **3번 라인 (`sg2_in_03`)**으로 푸싱 분류

### ② `CheckWarehouseStatus.srv`
* **서비스 경로**: `cobot3_interfaces/srv/CheckWarehouseStatus`
* **역할**: 적재 로봇(`sg2_in_XX`)이 적재를 수행하기 전, 동일 수령인의 패키지가 이미 입고되어 보관 중인지 `package_id`를 기준으로 중복 검사합니다.
* **Request/Response 정의**:
```text
# Request
string customer_name        # 검사 대상 수령인 성함
string package_id           # 검사 대상 상자 ID
string qr_id                # 검사 대상 상자의 QR코드 ID

---
# Response
bool is_already_in_warehouse # 중복 여부 (true: 이미 보관중 -> 적재 스킵 및 Bypass 처리)
```

### ③ `ReportInboundProgress.srv`
* **서비스 경로**: `cobot3_interfaces/srv/ReportInboundProgress`
* **역할**: 적재 로봇(`sg2_in_XX`)이 작업대에 물품 1개를 적재할 때마다 관제탑으로 실시간 보고하여 DB를 동기화합니다.
* **Request/Response 정의**:
```text
# Request
string workstation_id       # 작업대 고유 ID (예: "WS01")
string robot_id             # 보고하는 로봇 식별자 (예: "sg2_in_01")
int32 filled_slots_count    # 적재된 슬롯 번호 (1 ~ 8)
string package_id           # 적재한 패키지 ID
string workstation_qr_id    # 작업대 QR코드 ID
string package_qr_id        # 적재된 패키지 QR코드 ID

---
# Response
bool success                # DB 반영 성공 여부 (true / false)
```

---

## ⚡ 4. Redis 실시간 상태 캐시 규격 (AMR 상태 모니터링)
AMR의 고주파 주행 정보는 네트워크 대역폭과 DB 부하 절감을 위해 Redis에 캐싱됩니다.

* **키 형식**: `amr:[amr_id]` (대문자 구분 필수, 예: `amr:AMR_01`)
* **데이터 필드 명세**:
| 필드명 (Field) | 데이터 타입 (Type) | 예시 값 (Example) | 설명 (Description) |
| :--- | :--- | :--- | :--- |
| `state` | `String` | `"MOVING"` | 현재 동작 상태 (`IDLE`, `MOVING`, `CHARGING`, `ERROR`) |
| `current_qr_id` | `String` | `"FLOOR_X_6.0_Y_1.5"` | 현재 로봇 하부 센서가 인식 중인 바닥 QR ID |
| `target_qr_id` | `String` | `"FLOOR_X_1.5_Y_3.0"` | 목표 목적지 바닥 QR ID |
| `carrying_workstation_id` | `String` | `"WS01"` | 리프트하고 있는 작업대 ID (없을 시 빈 문자열 `""`) |
| `battery` | `String (Float)` | `"82.5"` | 배터리 잔량 백분율 (0.0 ~ 100.0) |

### 💡 AMR 로봇용 실시간 데이터 업로드 (HSET) 코드 예제

AMR 제어기는 주행 루프(예: 10Hz ~ 30Hz) 내에서 자신의 상태 정보를 관제탑 PC의 Redis 서버로 직접 소켓 전송해야 합니다.

#### ① Python 코드 예제
```python
import redis

# 관제탑 Redis (IP: 192.168.100.20, Port: 6379) 연결
r = redis.Redis(host="192.168.100.20", port=6379, decode_responses=True)

def publish_amr_status(amr_id, x, y, battery, carrying_ws=""):
    # Redis Hash에 실시간 갱신 (소켓 전송)
    r.hset(f"amr:{amr_id}", mapping={
        "current_qr_id": f"FLOOR_X_{x}_Y_{y}",
        "state": "MOVING",
        "battery": str(battery),
        "carrying_workstation_id": carrying_ws
    })
```

#### ② C++ 코드 예제 (`sw/redis-plus-plus` 라이브러리 사용 시)
```cpp
#include <sw/redis++/redis++.h>

using namespace sw::redis;

auto redis = Redis("tcp://192.168.100.20:6379");

void publish_amr_status(const std::string& amr_id, double x, double y, double battery, const std::string& carrying_ws = "") {
    std::unordered_map<std::string, std::string> amr_data = {
        {"current_qr_id", "FLOOR_X_" + std::to_string(x) + "_Y_" + std::to_string(y)},
        {"state", "MOVING"},
        {"battery", std::to_string(battery)},
        {"carrying_workstation_id", carrying_ws}
    };
    redis.hset("amr:" + amr_id, amr_data.begin(), amr_data.end());
}
```

---

## 📊 5. Fleet 상태 모니터링 JSON 토픽 상세
관제탑 노드가 1Hz 주기로 발행하는 실시간 상태 모니터링용 ROS 2 토픽입니다 (메시지 유형: `std_msgs/msg/String` 내 직렬화된 JSON 문자열).

### ① `/fleet/amr_states` (1Hz 주기)
```json
{
  "AMR_01": {
    "state": "IDLE",
    "current_qr_id": "FLOOR_X_6.0_Y_1.5",
    "target_qr_id": "",
    "carrying_workstation_id": null,
    "battery": 82.5,
    "available": true
  }
}
```

### ② `/fleet/workstation_states` (1Hz 주기)
```json
{
  "workstations": [
    {
      "workstation_id": "WS01",
      "workstation_qr_id": "WORKSTATION_WS01",
      "current_location": "spot_01",
      "status": "WAITING",
      "slot_count": 8,
      "filled_slots": [1, 2, 3],
      "reserved_by": null
    }
  ]
}
```

### ③ `/fleet/package_states` (1Hz 주기)
```json
{
  "packages": [
    {
      "package_id": "PKG_RAND_001",
      "customer_name": "홍길동",
      "route_zone": "2026-06-08",
      "status": "WAITING",
      "outbound_id": null,
      "workstation_id": null,
      "slot_number": null,
      "qr_id": "PKG_RAND_001"
    }
  ]
}
```

### ④ `/fleet/task_events` (이벤트 발생 시 즉시)
```json
{
  "schema_version": "1.0",
  "timestamp": 1780626168.994,
  "task_id": "uuid-string",
  "type": "MOVE_WORKSTATION",
  "priority": 80,
  "workstation_id": "WS01",
  "workstation_qr_id": "WORKSTATION_WS01",
  "start_location": "spot_01",
  "target_location": "sg2_in_01_A",
  "status": "ASSIGNED",
  "assigned_amr": "AMR_01"
}
```

---

## 🌐 6. 분산 네트워크 & 실행 가이드 (2대 PC 환경)
시뮬레이터(PC A)와 관제 서버(PC B)를 분산 구동하기 위한 가이드입니다.

* **PC A (시뮬레이터 & AMR 제어 노드)**: IP `192.168.100.10`
* **PC B (관제탑, DB, Redis, 대시보드)**: IP `192.168.100.20`

### ① ROS 2 DDS 환경설정 (양쪽 PC 공통)
```bash
export ROS_DOMAIN_ID=119
export ROS_LOCALHOST_ONLY=0  # 분산 환경 통신 활성화
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp  # Cyclone DDS 미들웨어 강제 지정
```

### ② PC A에서 PC B의 DB/Redis 연결 스트링 설정
PC A의 파이썬 노드 및 커넥터 스크립트 실행 시 호스트 접속처를 PC B의 IP로 명시적으로 변경해 줍니다.
* **Database Host**: `192.168.100.20`
* **Redis Host**: `192.168.100.20`

---

## 📅 7. 영업일 전환 및 이월 적재 (Carry-over) 규칙
1. **라인 역할 고정**:
   * **1번 라인 (`sg2_in_01`)**: **오늘 (Today)** 날짜 물량 적재
   * **2번 라인 (`sg2_in_02`)**: **내일 (Tomorrow)** 날짜 물량 적재
   * **3번 라인 (`sg2_in_03`)**: **모레 (Day After)** 날짜 물량 적재
2. **영업일 전환 API 호출 (`/api/start_next_day`)**:
   * 호출 시 Redis의 `system:today_date`가 실제 하루 뒤 날짜로 변경됩니다.
   * 이에 따라 기존 라인의 적재 미완료 작업대들이 **이월(Carry-over)**로 판정되어 아래와 같이 물리적 위치 이동 태스크가 자동 예약됩니다:
     * 2번 라인 작업대 ➡️ 1번 라인 (`sg2_in_01_A`)으로 이동
     * 3번 라인 작업대 ➡️ 2번 라인 (`sg2_in_02_A`)으로 이동
     * 3번 라인에는 창고의 새 빈 작업대가 자동 보충됩니다.
3. **조기 포장 방지 (`system:inbound_started`)**:
   * 날짜 전환 직후 신규 당일 패키지 CSV가 올라와 적재가 개시되기 전까지는, 1번 라인으로 이월된 작업대가 바로 포장존으로 빠지지 않도록 제어합니다.

---

## 🛠️ 8. Isaac Sim 연동 시 프레임 병목 분석 및 성능 최적화 가이드 (Performance Optimization)
다중 AMR을 Isaac Sim 물리 환경에서 구동할 때 발생할 수 있는 극심한 프레임 저하(2 FPS 이하)를 진단하고 해결하는 엔지니어링 가이드입니다.

### 8.1 3대 핵심 성능 병목 요인
1. **`/tf` 및 `/tf_static` 토픽 폭주**
   * **원인**: 1,813개의 바닥 격자 QR코드 메쉬 등 씬 내부의 모든 정적 프림들의 물리적 위치가 `/tf` 채널을 통해 초당 수천 번 발행되어 DDS 네트워크가 마비됩니다.
   * **해결**: Isaac Sim 내 OmniGraph에서 로봇 본체를 제외한 정적 마크들의 TF Publish 설정을 차단해야 합니다.
2. **GPU-to-CPU 이미지 복사 (Readback) 지연**
   * **원인**: 5대 AMR의 카메라 렌더링 픽셀 데이터를 GPU 메모리에서 CPU 메모리(NumPy)로 매 프레임 옮기는 연산 자체가 그래픽 버스 대역폭을 포화시킵니다.
3. **단일 스레드 CPU 비전 디코딩 부하**
   * **원인**: CPU로 가져온 이미지를 OpenCV 및 `zxingcpp` 라이브러리로 디코딩하는 작업이 멀티스레딩/GPU 가속 없이 단일 CPU 스레드를 점유하여 프레임이 중단됩니다.

### 8.2 해결 방안 및 GPU 가속 아키텍처
* **가장 신속한 조치 (무비전 트랜스폼 매핑)**:
  * 실시간 비전 카메라 스캐닝을 생략하고, AMR 주행 좌표(Odometry)와 DB의 `floor_qr_map`을 트랜스폼 계산으로 매칭하는 **`QR_CAMERA_LOCALIZATION_ENABLED = False`** 옵션을 활성화하여 성능을 30 FPS 이상으로 보장합니다.
* **GPU 텐서 직접 조회 (Zero-copy CUDA)**:
  * Isaac Sim Replicator에서 픽셀 데이터를 뽑을 때, CPU용 NumPy 배열 대신 **GPU VRAM 내 PyTorch CUDA 텐서**를 직접 가져오도록 작성합니다.
    ```python
    # CPU 복사 오버헤드가 없는 GPU 다이렉트 텐서 수집
    gpu_tensor = rep.annotators.get("rgb").get_data(device="cuda")
    ```
* **NVIDIA Isaac ROS AprilTag/QR 가속 노드 도입**:
  * 욜로(YOLO) 모델을 직접 학습시킬 필요 없이, 사전 준비된 **NVIDIA Isaac ROS 가속 노드**를 활용하여 GPU 내부에서 직접 QR/AprilTag 코드를 100+ FPS 속도로 초고속 디코딩합니다.

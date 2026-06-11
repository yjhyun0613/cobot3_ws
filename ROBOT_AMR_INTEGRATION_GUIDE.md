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
        SimSync[sim_sync_node] <--> DB
    end
    
    subgraph PC A (AMR 및 시뮬레이터)
        AMR_Act[AMR Action Server] <--> CT
        IsaacBG2[Isaac Sim A - bg2] --> |TransitPackage.srv| SimSync
        SimSync --> |sg2_spawn_trigger| IsaacSG2[Isaac Sim B - sg2]
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

### ① `GetDailyPackageList.srv`
* **서비스 경로**: `cobot3_interfaces/srv/GetDailyPackageList`
* **역할**: 컨베이어 분류기(`bg2`)가 영업 기동 시점에 오늘 처리해야 할 전체 정적 택배 목록을 한 번에 일괄 조회하여 로컬 캐시로 다운로드합니다.
* **Request/Response 정의**:
```text
# Request
bool request_start          # 영업 기동 요청 플래그

---
# Response
string package_list_json    # 오늘 처리할 전체 패키지 리스트 (JSON 직렬화 포맷)
```
#### 💡 로컬 분류 라인 매핑 규칙 (bg2 자체 판단)
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

### ④ `TransitPackage.srv` _(분산 시뮬레이션 전용)_
* **서비스 경로**: `cobot3_interfaces/srv/TransitPackage`
* **역할**: Isaac Sim **분산 시뮬레이션 환경 전용**. bg2(분류 라인) 시뮬레이터에서 상자가 컨베이어 벨트 끝단 트리거 영역에 도달했을 때, 독립 동기화 노드(`sim_sync_node`)에 sg2(적재/포장 라인) 시뮬레이터로의 상자 순간이동(소멸 → 소환)을 요청합니다.
* **Request/Response 정의**:
```text
# Request
string package_id           # 이동 대상 상자의 고유 ID (예: "PKG_20260610_001")
string target_line          # sg2 측 도착 라인 (예: "sg2_in_01", "sg2_in_02", "sg2_in_03")

---
# Response
bool success                # 이송 동기화 처리 성공 여부
string message              # 처리 결과 메시지 또는 에러 상세
```
> [!NOTE]
> **사용 노드**: `sim_sync_node`(서비스 서버)는 관제탑(`control_tower_node`)과 완전히 독립되어 실행됩니다. 실제 현장 배포 시에는 이 노드를 기동하지 않으면 됩니다.

---

## 🛑 4. ROS 2 토픽 (Topic) 인터페이스 (제어용)

### ① `/{robot_id}/pause_status`
* **메시지 타입**: `std_msgs/msg/Bool`
* **역할**: 단일 슬롯 JIT 환경에서 8칸 만석 시, 혹은 앞/뒤 양면(4칸씩) 적재를 위한 **180도 회전(`ROTATE_WORKSTATION`)** 시 관제탑이 로봇 팔의 작업을 일시 정지(Pause)시키거나, 작업대 교체/회전이 완료되어 다시 재개(Resume)시킬 때 사용하는 제어 토픽입니다.
* **사용 로봇**: 적재 로봇 (`sg2_in_01`, `sg2_in_02`, `sg2_in_03`) 및 포장 로봇 (`sg2_out_00`)
* **메시지 구조**:
```text
# std_msgs/msg/Bool
bool data  # true: 일시 정지 지시 (작업대 만석 또는 4칸 회전 대기), false: 작업 재개 지시 (새 작업대 배치 또는 회전 완료)
```

---

## ⚡ 5. Redis 실시간 상태 캐시 규격 (AMR 상태 모니터링)
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

## 📊 6. Fleet 상태 모니터링 JSON 토픽 상세
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

## 🗄️ 7. 데이터베이스 및 Redis 캐시 구조 정의서 (Database Schema Specifications)

### 7.1 PostgreSQL ERD (Entity Relationship Diagram)

```mermaid
erDiagram
    ROBOTS {
        VARCHAR robot_id PK "로봇 고유 문자열 ID"
        VARCHAR robot_type "로봇 역할군 (CONVEYOR, MANIPULATOR 등)"
        VARCHAR qr_id UNIQUE "로봇 고유 QR코드 ID"
    }
    WORKSTATIONS {
        VARCHAR workstation_id PK "작업대 고유 ID (WS01~10)"
        VARCHAR current_location "작업대 물리적 위치 (sg2_in_01_A, spot_01 등)"
        VARCHAR qr_id UNIQUE "작업대 고유 QR코드 ID"
    }
    WAREHOUSE_LOCATIONS {
        VARCHAR spot_id PK "창고 주차 구역 (spot_01~10)"
        VARCHAR workstation_id FK "보관된 작업대 ID"
        VARCHAR status "점유 상태 (EMPTY / OCCUPIED)"
    }
    PACKAGES {
        VARCHAR package_id PK "택배 고유 바코드 ID (PKG_RAND_XXX)"
        VARCHAR customer_name "택배 수령인 성함"
        VARCHAR route_zone "분류 목적지 날짜 (YYYY-MM-DD)"
        VARCHAR status "진행 상태 (WAITING, IN_WORKSTATION, IN_WAREHOUSE, COMPLETED 등)"
        VARCHAR outbound_id "출고 고유 ID"
        VARCHAR workstation_id FK "적재된 작업대 ID"
        INT slot_number "적재된 작업대의 슬롯 번호 (1~8)"
        VARCHAR qr_id UNIQUE "택배 고유 QR코드 ID"
    }
    FLOOR_QR_MAP {
        VARCHAR qr_id PK "바닥 QR코드 고유 ID (FLOOR_X_xx_Y_yy)"
        DOUBLE x_coord "물리 X 좌표 (m)"
        DOUBLE y_coord "물리 Y 좌표 (m)"
        DOUBLE z_coord "물리 Z 좌표 (m)"
        VARCHAR location_name "매핑 논리 위치명"
        VARCHAR location_type "위치 타입"
        TEXT description "설명"
    }
    
    WORKSTATIONS ||--o{ PACKAGES : "contains"
    WORKSTATIONS ||--o| WAREHOUSE_LOCATIONS : "parked at"
```

### 7.2 PostgreSQL 테이블 상세 정의

#### ① 로봇 정보 테이블 (`robots`)
관제 센터가 제어하는 모든 물류 로봇의 정보와 물리 QR코드 식별자의 매핑 테이블입니다.
* **Primary Key**: `robot_id`

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 (Constraints) | 설명 (Description) | 예시 데이터 |
| :--- | :--- | :--- | :--- | :--- |
| **`robot_id`** | `VARCHAR(50)` | `PRIMARY KEY` | 로봇 고유 문자열 ID | `'bg2'`, `'sg2_in_01'` |
| **`robot_type`** | `VARCHAR(50)` | `NOT NULL` | 로봇의 분류/역할군 | `'CONVEYOR_SORTER'`, `'MANIPULATOR'` |
| **`qr_id`** | `VARCHAR(100)` | `UNIQUE` | 로봇 고유 QR코드 ID | `'ROBOT_bg2'`, `'ROBOT_sg2_in_01'` |

#### ② 작업대 정보 테이블 (`workstations`)
로봇들이 상자를 싣는 2x4 슬롯 기반 작업대의 실시간 물리적 위치와 식별 QR코드 정보를 관리합니다.
* **Primary Key**: `workstation_id`

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 (Constraints) | 설명 (Description) | 예시 데이터 |
| :--- | :--- | :--- | :--- | :--- |
| **`workstation_id`** | `VARCHAR(50)` | `PRIMARY KEY` | 작업대 고유 문자열 ID | `'WS01'`, `'WS10'` |
| **`current_location`** | `VARCHAR(50)` | `NOT NULL` | 작업대의 실시간 위치 | `'sg2_in_01_A'`, `'spot_01'`, `'sg2_out_00_A'`, `'sg2_out_00_B'` |
| **`qr_id`** | `VARCHAR(100)` | `UNIQUE` | 작업대 고유 QR코드 ID | `'WORKSTATION_WS01'`, `'WORKSTATION_WS10'` |
| **`status`** | `VARCHAR(50)` | `DEFAULT 'WAITING'` | 작업대의 제어 상태 | `'WAITING'`, `'PROCESSING'` |
| **`reserved_by`** | `VARCHAR(50)` | - | 현재 작업대를 예약/선점 중인 AMR 식별자 | `'AMR_01'`, `NULL` |

#### ③ 창고 세부 스팟 관리 테이블 (`warehouse_locations`)
창고 내부의 개별 보관 슬롯 구역들의 점유 현황과 주차된 작업대 매핑을 관리합니다.
* **Primary Key**: `spot_id`
* **Foreign Key**: `workstation_id` (작업대 테이블 참조)

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 (Constraints) | 설명 (Description) | 예시 데이터 |
| :--- | :--- | :--- | :--- | :--- |
| **`spot_id`** | `VARCHAR(50)` | `PRIMARY KEY` | 창고 내 고유 주차 구역 ID | `'spot_01'`, `'spot_10'` |
| **`workstation_id`** | `VARCHAR(50)` | `FOREIGN KEY` | 주차된 작업대 고유 ID (비었을 시 `NULL`) | `'WS01'`, `NULL` |
| **`status`** | `VARCHAR(20)` | `DEFAULT 'EMPTY'` | 스팟 점유 상태 (`EMPTY` / `OCCUPIED`) | `'OCCUPIED'`, `'EMPTY'` |

#### ④ 택배 정보 테이블 (`packages`)
입고되는 모든 택배의 상태 및 적재/출고 이력을 관리하는 데이터의 흐름 핵심 테이블입니다.
* **Primary Key**: `package_id`
* **Foreign Key**: `workstation_id` (작업대 테이블 참조)

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 (Constraints) | 설명 (Description) | 예시 데이터 |
| :--- | :--- | :--- | :--- | :--- |
| **`package_id`** | `VARCHAR(50)` | `PRIMARY KEY` | 상자 바코드 또는 고유 ID | `'PKG_RAND_001'` |
| **`customer_name`** | `VARCHAR(100)` | `NOT NULL` | 택배 수령인 | `'김철수'` |
| **`route_zone`** | `VARCHAR(20)` | `NOT NULL` | 분류 배송 예정 날짜 | `'2026-06-01'` |
| **`status`** | `VARCHAR(50)` | `DEFAULT 'WAITING'` | 상태 (`WAITING`/`IN_WORKSTATION`/`IN_WAREHOUSE`/`COMPLETED`) | `'IN_WORKSTATION'` |
| **`outbound_id`** | `VARCHAR(100)` | `NULL 허용` | 포장 후 출고 고유 바코드 | `'sg2_out_00_WS01-1-202606021153'` |
| **`workstation_id`** | `VARCHAR(50)` | `FOREIGN KEY` | 적재된 작업대 ID | `'WS01'`, `NULL` |
| **`slot_number`** | `INT` | `NULL 허용` | 작업대 내 적재 슬롯 번호 (1~8) | `1`, `NULL` |
| **`qr_id`** | `VARCHAR(100)` | `UNIQUE` | 택배 고유 QR코드 ID | `'PKG_RAND_001'` |

#### ⑤ 공간 바닥 QR코드 격자 맵 테이블 (`floor_qr_map`)
AMR의 3D 공간 자율주행 및 위치 좌표 해석(Localization)을 위해 바닥에 매핑된 QR코드 격자 맵 정보를 관리합니다.
* **Primary Key**: `qr_id`

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 (Constraints) | 설명 (Description) | 예시 데이터 |
| :--- | :--- | :--- | :--- | :--- |
| **`qr_id`** | `VARCHAR(100)` | `PRIMARY KEY` | 바닥 QR코드 고유 ID | `'FLOOR_X_1.5_Y_3.0'` |
| **`x_coord`** | `DOUBLE PRECISION`| `NOT NULL` | 물리 X 좌표 (m) | `1.5` |
| **`y_coord`** | `DOUBLE PRECISION`| `NOT NULL` | 물리 Y 좌표 (m) | `3.0` |
| **`z_coord`** | `DOUBLE PRECISION`| `DEFAULT 0.0` | 물리 Z 좌표 (m) | `0.0` |
| **`location_name`** | `VARCHAR(50)`| `NULL 허용` | 매핑되는 논리적 위치명 | `'spot_01'`, `'sg2_in_01_A'` |
| **`location_type`** | `VARCHAR(50)`| `NULL 허용` | 위치 용도 분류 | `'PARKING_SPOT'`, `'PATHWAY'` |
| **`description`** | `TEXT` | `NULL 허용` | 세부 위치 설명 | `'1번 주차장 구역 바닥 격자'` |

### 7.3 Redis 실시간 제어 데이터 및 큐 구조
* **AMR 상태 해시**: `amr:[amr_id]` (예: `amr:AMR_01`)
* **AMR 비동기 명령 큐**: `queue:amr_tasks` (Sorted Set 구조, Score=우선순위 가중치)

---

## 🗺️ 8. 창고 물리 레이아웃 및 좌표 정의서 (Physical Layout Coordinates)

### 8.1 메인 보관 창고 (Main Warehouse Spots) - 총 10개 스팟
| 논리 Spot ID | X 물리 좌표 (m) | Y 물리 좌표 (m) | 설명 |
| :--- | :---: | :---: | :--- |
| **`spot_01`** | `-1.5` | `-9.0` | 메인 창고 1행 1열 |
| **`spot_02`** | `-3.0` | `-9.0` | 메인 창고 1행 2열 |
| **`spot_03`** | `-1.5` | `-6.0` | 메인 창고 2행 1열 |
| **`spot_04`** | `-3.0` | `-6.0` | 메인 창고 2행 2열 |
| **`spot_05`** | `-1.5` | `-3.0` | 메인 창고 3행 1열 |
| **`spot_06`** | `-3.0` | `-3.0` | 메인 창고 3행 2열 |
| **`spot_07`** | `-1.5` | `0.0` | 메인 창고 4행 1열 |
| **`spot_08`** | `-3.0` | `0.0` | 메인 창고 4행 2열 |
| **`spot_09`** | `-1.5` | `3.0` | 메인 창고 5행 1열 |
| **`spot_10`** | `-3.0` | `3.0` | 메인 창고 5행 2열 |

### 8.2 입고 분류 라인 (Inbound Line A/B Spots) - 총 6개 스팟 (3개 라인 x 2버퍼)
* **오늘 (Line 1)**: `sg2_in_01_A` `(7.5, 1.5)` | `sg2_in_01_B` `(6.0, 1.5)`
* **내일 (Line 2)**: `sg2_in_02_A` `(7.5, -3.0)` | `sg2_in_02_B` `(6.0, -3.0)`
* **모레 (Line 3)**: `sg2_in_03_A` `(7.5, -7.5)` | `sg2_in_03_B` `(6.0, -7.5)`

### 8.3 출고 대기 창고 / 스테이징 구역 (Outbound Staging Spots) - 총 4개 스팟
| 논리 Spot ID | X 물리 좌표 (m) | Y 물리 좌표 (m) | 설명 |
| :--- | :---: | :---: | :--- |
| **`stage_01`** | `4.5` | `9.0` | 출고 대기 창고 스팟 1 |
| **`stage_02`** | `4.5` | `7.5` | 출고 대기 창고 스팟 2 |
| **`stage_03`** | `7.5` | `9.0` | 출고 대기 창고 스팟 3 |
| **`stage_04`** | `7.5` | `7.5` | 출고 대기 창고 스팟 4 |

### 8.4 출고 포장 라인 (Outbound Line A/B Spots) - 총 2개 스팟
| 논리 Spot ID | X 물리 좌표 (m) | Y 물리 좌표 (m) | 설명 |
| :--- | :---: | :---: | :--- |
| **`sg2_out_00_A`** | `-4.5` | `9.0` | 출고 포장 A라인 Active 버퍼 |
| **`sg2_out_00_B`** | `-4.5` | `7.5` | 출고 포장 B라인 Standby 버퍼 |

### 8.5 AMR 충전 위치 (AMR Charging Spots) - 총 5개 스팟
| 논리 Spot ID | X 물리 좌표 (m) | Y 물리 좌표 (m) | 설명 |
| :--- | :---: | :---: | :--- |
| **`charging_01`** | `-6.0` | `-9.0` | AMR 충전기 스팟 1 |
| **`charging_02`** | `-6.0` | `-7.5` | AMR 충전기 스팟 2 |
| **`charging_03`** | `-6.0` | `-6.0` | AMR 충전기 스팟 3 |
| **`charging_04`** | `-6.0` | `-4.5` | AMR 충전기 스팟 4 |
| **`charging_05`** | `-6.0` | `-3.0` | AMR 충전기 스팟 5 |

### 8.6 로봇 제한 구역 (AMR 불가 진입 구역 - SG2)
* **SG2_OUT**: `(-6.0, 9.0)`, `(-6.0, 7.5)`
* **SG2_IN_1**: `(6.0, 3.0)`, `(7.5, 3.0)`
* **SG2_IN_2**: `(6.0, -1.5)`, `(7.5, -1.5)`
* **SG2_IN_3**: `(6.0, -6.0)`, `(7.5, -6.0)`

### 8.7 중복 수령인 패키지 직송 픽업 위치 (MovePackage.action)
* **sg2_in_01**: `(6.0, 3.0)`
* **sg2_in_02**: `(6.0, -1.5)`
* **sg2_in_03**: `(6.0, -6.0)`

---

## 🌐 9. 분산 네트워크 & 실행 가이드 (2대 PC 환경)
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

### ③ 환경변수 기반 DB/Redis 접속 설정 (sim_sync_node 포함)
분산 환경에서 `sim_sync_node`를 포함한 모든 노드의 DB/Redis 접속 호스트를 환경변수로 주입할 수 있습니다.
```bash
# PC A에서 실행 시 (DB/Redis는 PC B에 있으므로)
export POSTGRES_HOST=192.168.100.20
export REDIS_HOST=192.168.100.20
```

---

## 🌐 9.5 분산 시뮬레이션 상자 동기화 노드 (sim_sync_node)
Isaac Sim bg2(분류 라인)와 sg2(적재/포장 라인) 2대 분산 시뮬레이션 환경 간의 상자 순간이동(소멸/소환)을 전담하는 독립 마이크로 노드입니다.

### 통신 채널 규격
| 채널 타입 | 이름 | 메시지 타입 | 방향 | 용도 |
| :--- | :--- | :--- | :--- | :--- |
| **Service** | `/sim/transit_package` | `TransitPackage.srv` | bg2 → sync_node | 상자 이송 요청 (권장) |
| **Topic** | `/sim/bg2_exit_event` | `std_msgs/String` (JSON) | bg2 → sync_node | 상자 탈출 감지 (대체 채널) |
| **Topic** | `/sim/sg2_spawn_trigger` | `std_msgs/String` (JSON) | sync_node → sg2 | 상자 소환 명령 |

### 데이터 흐름
1. bg2 시뮬레이터에서 상자가 컨베이어 벨트 끝단 트리거 박스에 접촉
2. bg2 스크립트가 `/sim/transit_package` 서비스 호출 (또는 `/sim/bg2_exit_event` 토픽 발행)
3. `sim_sync_node`가 수신하여 PostgreSQL 상태를 `TRANSIT_TO_SG2`로 갱신
4. `/sim/sg2_spawn_trigger` 토픽으로 sg2 시뮬레이터에 소환 명령 발행
5. sg2 시뮬레이터가 토픽을 구독하여 지정된 입구 좌표에 상자 Prim 동적 생성
6. bg2 시뮬레이터는 서비스 응답(success) 수신 후 해당 상자 Prim 즉시 삭제

---

## 📅 10. 영업일 전환 및 이월 적재 (Carry-over) 규칙
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

## 🛠️ 11. Isaac Sim 연동 시 프레임 병목 분석 및 성능 최적화 가이드 (Performance Optimization)
다중 AMR을 Isaac Sim 물리 환경에서 구동할 때 발생할 수 있는 극심한 프레임 저하(2 FPS 이하)를 진단하고 해결하는 엔지니어링 가이드입니다.

### 11.1 3대 핵심 성능 병목 요인
1. **`/tf` 및 `/tf_static` 토픽 폭주**
   * **원인**: 정적 마크들의 물리적 위치가 `/tf` 채널을 통해 초당 수천 번 발행되어 DDS 네트워크가 마비됩니다.
   * **해결**: OmniGraph에서 정적 마크들의 TF Publish 설정을 차단합니다.
2. **GPU-to-CPU 이미지 복사 (Readback) 지연**
   * **원인**: 5대 AMR의 카메라 렌더링 데이터를 CPU 메모리로 매 프레임 옮기는 연산 자체가 버스 대역폭을 포화시킵니다.
3. **단일 스레드 CPU 비전 디코딩 부하**
   * **원인**: CPU로 가져온 이미지를 OpenCV 및 `zxingcpp` 라이브러리로 디코딩하는 작업이 단일 CPU 스레드를 점유하여 프레임이 중단됩니다.

### 11.2 해결 방안 및 GPU 가속 아키텍처
* **가장 신속한 조치 (무비전 트랜스폼 매핑)**:
  * 실시간 비전 카메라 스캐닝을 생략하고, AMR 주행 좌표(Odometry)와 DB의 `floor_qr_map`을 트랜스폼 계산으로 매칭하는 **`QR_CAMERA_LOCALIZATION_ENABLED = False`** 옵션을 활성화하여 성능을 30 FPS 이상으로 보장합니다.
* **GPU 텐서 직접 조회 (Zero-copy CUDA)**:
  * CPU 복사 오버헤드가 없는 GPU 다이렉트 텐서 수집: `rep.annotators.get("rgb").get_data(device="cuda")`
* **NVIDIA Isaac ROS AprilTag/QR 가속 노드 도입**:
  * NVIDIA Isaac ROS 가속 노드를 활용하여 GPU 내부에서 직접 QR/AprilTag 코드를 100+ FPS 속도로 초고속 디코딩합니다.

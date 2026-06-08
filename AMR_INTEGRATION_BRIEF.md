# 🚚 AMR 담당자 협업용 관제탑 인터페이스 및 DB 명세서
> **문서 대상**: AMR 주행 제어기 및 플릿 매니저 개발 담당자
> **작성 목적**: 관제탑(Control Tower) 노드, 데이터베이스(PostgreSQL/Redis), 웹 대시보드와 AMR 로봇 간의 원활한 실시간 연동을 위한 데이터 스펙 및 API 규격 공유.

---

## 📌 1. 시스템 아키텍처 개요 (하이브리드 통신)
본 관제 시스템은 다중 AMR의 안정적인 제어와 가벼운 모니터링을 실현하기 위해 **제어 채널**과 **데이터 공유 채널**을 분리한 하이브리드 아키텍처를 채택하고 있습니다.

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
    CT -.-> |/fleet/amr_states (1Hz)| Dash
```

1. **제어 명령 (Control Plane)**: 관제탑 ➡️ AMR
   * **방식**: ROS 2 Action (`ManageWorkstation.action`)
   * **목적**: 특정 작업대 이송 명령 전달, 주행 상태 피드백 모니터링, 비상 취소 처리.
2. **실시간 모니터링 (Data Plane)**: AMR ➡️ 관제탑 & 대시보드
   * **방식**: Redis 인메모리 캐시 및 TCP/WebSockets
   * **목적**: AMR의 초당 고주파수 (x, y) 좌표 및 배터리, 적재 상태를 DB 부하 없이 초고속 갱신.

---

## 🏃 2. ROS 2 제어 인터페이스 (Action)
AMR 제어기는 관제탑으로부터 명령을 수신하기 위해 **Action Server**를 오픈해야 합니다.

### ① `ManageWorkstation.action`
* **액션 경로**: `cobot3_interfaces/action/ManageWorkstation`
* **역할**: AMR에게 특정 작업대(`WS01`~`10`)를 대상 위치(입고 라인, 보관 스팟, 출고 포장대)로 이동시키도록 지시합니다.

#### 📄 인터페이스 세부 정의
```text
# Goal Definition
string workstation_id       # 제어 대상 작업대 고유 ID (예: "WS01" ~ "WS10")
string start_location       # 출발지 논리 위치 (예: "spot_01", "sg2_in_01_A")
string target_location      # 도착지 논리 위치 (예: "sg2_out_00_A", "spot_02")
string workstation_qr_id    # 작업대 물리 QR코드 식별자 (예: "WORKSTATION_WS01")
string target_qr_id         # 목적지 바닥 격자 QR ID (예: "FLOOR_X_-10.775_Y_-9.525")
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

---

## ⚡ 3. Redis 실시간 데이터 규격 (인메모리 캐시)
AMR의 실시간 주행 정보는 네트워크 대역폭과 DB 트래픽 절감을 위해 Redis에 직접 캐싱되며, 대시보드는 이 데이터를 구독하여 화면에 렌더링합니다.

### ① AMR 실시간 상태 캐시 (Hash Type)
* **키 형식**: `amr:[amr_id]` (대문자 구분 필수, 예: `amr:AMR_01`)
* **데이터 필드 명세**:

| 필드명 (Field) | 데이터 타입 (Type) | 예시 값 (Example) | 설명 (Description) |
| :--- | :--- | :--- | :--- |
| `state` | `String` | `"MOVING"` | 현재 동작 상태 (`IDLE`, `MOVING`, `CHARGING`, `ERROR`) |
| `current_qr_id` | `String` | `"FLOOR_X_-25.775_Y_-11.025"` | 현재 로봇 하부 센서가 인식 중인 바닥 QR ID |
| `target_qr_id` | `String` | `"FLOOR_X_-10.775_Y_-9.525"` | 목표 목적지 바닥 QR ID |
| `carrying_workstation_id` | `String` | `"WS01"` | 현재 리프트하여 싣고 있는 작업대 ID (없을 시 빈 문자열 `""`) |
| `battery` | `String (Float)` | `"82.5"` | 배터리 잔량 백분율 (0.0 ~ 100.0) |

---

## 🗄️ 4. PostgreSQL 데이터베이스 매핑
관제탑이 기준 정보 조회 및 이력 관리를 위해 사용하는 관계형 테이블 구조 중 AMR과 연관된 부분입니다.

### ① 바닥 QR 맵 테이블 (`floor_qr_map`)
AMR이 이동할 수 있는 1,813개 격자 노드 및 고유 물리 좌표 테이블입니다.
* **키 형식**: `FLOOR_X_[X좌표]_Y_[Y좌표]`

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 | 설명 (Description) |
| :--- | :--- | :--- | :--- |
| `qr_id` | `VARCHAR(100)` | `PRIMARY KEY` | 바닥 QR 고유 문자열 식별자 |
| `x_coord` | `DOUBLE` | `NOT NULL` | 물리 공간 X 기준 좌표 (m) |
| `y_coord` | `DOUBLE` | `NOT NULL` | 물리 공간 Y 기준 좌표 (m) |
| `location_name` | `VARCHAR(50)` | `NULL` | 특정 논리 구역명 (예: `spot_01`, `sg2_in_01_A` 등) |
| `location_type` | `VARCHAR(50)` | `NULL` | 용도 분류 (`PARKING_SPOT`, `LOADING_SPOT`, `PATHWAY` 등) |

### ② 작업대 상태 테이블 (`workstations`)
* **역할**: 각 작업대(`WS01`~`WS10`)의 선점 상태 및 위치 동기화.
* **AMR 연동 필드**: `reserved_by` (AMR이 작업을 위해 해당 작업대를 선점할 경우, 타 로봇의 중복 접근을 막기 위해 `'AMR_01'` 등의 문자열로 선점 처리함. 작업 완료 시 `NULL` 리셋)

---

## 🌐 5. 분산 네트워크 & 실행 가이드 (2대 PC 환경)
시뮬레이터(PC A)와 관제 서버(PC B)는 **Thunderbolt C-to-C direct connection (40Gbps)** 또는 기가비트 LAN 망을 통해 연동됩니다.

* **PC A (시뮬레이터 & AMR 제어 노드)**: IP `192.168.100.10`
* **PC B (관제탑, DB, Redis, 대시보드)**: IP `192.168.100.20`

### ① ROS 2 DDS 환경설정 (양쪽 PC 공통)
```bash
export ROS_DOMAIN_ID=119
export ROS_LOCALHOST_ONLY=0  # 분산 환경 통신 활성화
```

### ② PC A (AMR 제어 노드) DB/Redis 연결 스트링
PC A에서 동작하는 AMR 노드들은 PC B에 기동된 PostgreSQL과 Redis 컨테이너로 소켓 통신을 연결해야 합니다.
* **DB 호스트 지정**: `192.168.100.20`
* **Redis 호스트 지정**: `192.168.100.20`

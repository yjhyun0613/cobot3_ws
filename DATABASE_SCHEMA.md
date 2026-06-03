# 🗄️ 쿠팡 물류창고 데이터베이스 구조 정의서 (DB Schema Guide)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 합니다.

이 문서는 ArUco 마커 ID가 통합된 **관계형 DB(PostgreSQL) 및 Redis 캐시 시스템**의 전체 구조와 데이터 테이블을 한눈에 파악하기 위해 작성되었습니다.

---

## 📊 1. 데이터베이스 ERD (Entity Relationship Diagram)

```mermaid
erDiagram
    ROBOTS {
        VARCHAR robot_id PK "로봇 고유 문자열 ID"
        VARCHAR robot_type "로봇 역할군 (CONVEYOR, MANIPULATOR 등)"
        INT aruco_id UNIQUE "물리 ArUco 마커 ID (1~5)"
    }
    WORKSTATIONS {
        VARCHAR workstation_id PK "작업대 고유 ID (WS01~10)"
        VARCHAR current_location "작업대 물리적 위치 (sg2_in_01, spot_01 등)"
        INT aruco_id UNIQUE "물리 ArUco 마커 ID (11~20)"
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
        INT slot_number "적재된 작업대의 슬롯 번호 (1~4)"
        INT aruco_id UNIQUE "물리 ArUco 마커 ID (100+)"
    }
    
    WORKSTATIONS ||--o{ PACKAGES : "contains"
    WORKSTATIONS ||--o| WAREHOUSE_LOCATIONS : "parked at"
```

---

## 🗄️ 2. PostgreSQL 테이블 상세 정의

### ① 로봇 정보 테이블 (`robots`)
관제 센터가 제어하는 모든 물류 로봇의 정보와 물리 ArUco 마커 번호의 매핑 테이블입니다.

* **Primary Key**: `robot_id`

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 (Constraints) | 설명 (Description) | 예시 데이터 |
| :--- | :--- | :--- | :--- | :--- |
| **`robot_id`** | `VARCHAR(50)` | `PRIMARY KEY` | 로봇 고유 문자열 ID | `'bg2'`, `'sg2_in_01'` |
| **`robot_type`** | `VARCHAR(50)` | `NOT NULL` | 로봇의 분류/역할군 | `'CONVEYOR_SORTER'`, `'MANIPULATOR'` |
| **`aruco_id`** | `INT` | `UNIQUE` | 물리 마커 번호 (1~5) | `1`, `2` |

---

### ② 작업대 정보 테이블 (`workstations`)
로봇들이 상자를 싣는 2x2 슬롯 기반 작업대의 실시간 물리적 위치와 식별 마커 정보를 관리합니다.

* **Primary Key**: `workstation_id`

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 (Constraints) | 설명 (Description) | 예시 데이터 |
| :--- | :--- | :--- | :--- | :--- |
| **`workstation_id`** | `VARCHAR(50)` | `PRIMARY KEY` | 작업대 고유 문자열 ID | `'WS01'`, `'WS10'` |
| **`current_location`** | `VARCHAR(50)` | `NOT NULL` | 작업대의 실시간 위치 | `'sg2_in_01'`, `'spot_01'`, `'sg2_out_00'` |
| **`aruco_id`** | `INT` | `UNIQUE` | 물리 마커 번호 (11~20) | `11`, `20` |

---

### ③ 창고 세부 스팟 관리 테이블 (`warehouse_locations`)
창고 내부의 개별 보관 슬롯 구역들의 점유 현황과 주차된 작업대 매핑을 관리합니다.

* **Primary Key**: `spot_id`
* **Foreign Key**: `workstation_id` (작업대 테이블 참조)

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 (Constraints) | 설명 (Description) | 예시 데이터 |
| :--- | :--- | :--- | :--- | :--- |
| **`spot_id`** | `VARCHAR(50)` | `PRIMARY KEY` | 창고 내 고유 주차 구역 ID | `'spot_01'`, `'spot_10'` |
| **`workstation_id`** | `VARCHAR(50)` | `FOREIGN KEY` | 주차된 작업대 고유 ID (비었을 시 `NULL`) | `'WS01'`, `NULL` |
| **`status`** | `VARCHAR(20)` | `DEFAULT 'EMPTY'` | 스팟 점유 상태 (`EMPTY` / `OCCUPIED`) | `'OCCUPIED'`, `'EMPTY'` |

---

### ④ 택배 정보 테이블 (`packages`)
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
| **`slot_number`** | `INT` | `NULL 허용` | 작업대 내 적재 슬롯 번호 (1~4) | `1`, `NULL` |
| **`aruco_id`** | `INT` | `UNIQUE` | 물리 마커 번호 (101 이상) | `101` |

---

## ⚡ 3. Redis 실시간 제어 데이터 구조

자율 주행 로봇(AMR) 제어 및 명령 큐에 사용되는 실시간 고속 인메모리 데이터의 구성 방식입니다.

### ① AMR 로봇 상태 캐시 (Hash Type)
* **키 형식**: `amr:[amr_id]:status` (예: `amr:amr_01:status`)
* **관리 데이터**:
  ```json
  {
      "x": 12.34,
      "y": 5.67,
      "z": 0.0,
      "state": "IDLE" // IDLE, MOVING, ERROR
  }
  ```

### ② AMR 비동기 제어 명령 대기열 (Queue / List Type)
* **키 형식**: `queue:amr_tasks`
* **관리 데이터**: 관제 센터 스케줄러가 AMR에 순차적으로 이송 명령을 보낼 때 저장되는 JSON 배열 데이터입니다.
  ```json
  {
      "task_type": "PRE_FETCH_WORKSTATION", // 태스크 종류
      "workstation_id": "WS01",
      "from": "sg2_in_01",
      "to": "sg2_out_00",
      "workstation_aruco_id": 11
  }
  ```

---

## 💡 4. 데이터 적재 흐름 및 상태 변화 예시 (Scenario Example)

수령인이 **'김철수'**인 택배 상자(`PKG_RAND_001`, ArUco: `101`)가 작업대 `WS01`(ArUco: `11`)의 첫 번째 슬롯에 적재될 때의 데이터 변화 예시입니다.

### ① 적재 전 상태 (초기 상태)
* **`workstations` 테이블 (`workstation_id = 'WS01'`)**
  * `current_location`: `'spot_01'`
* **`packages` 테이블 (`package_id = 'PKG_RAND_001'`)**
  * `status`: `'WAITING'`
  * `workstation_id`: `NULL`
  * `slot_number`: `NULL`

### ② 적재 완료 후 상태 (`ReportInboundProgress` 호출 후)
* **`workstations` 테이블 (`workstation_id = 'WS01'`)**
  * `current_location`: `'sg2_in_01'`
* **`packages` 테이블 (`package_id = 'PKG_RAND_001'`)**
  * `status`: `'IN_WORKSTATION'`
  * `workstation_id`: `'WS01'`
  * `slot_number`: `1` (1번 슬롯 매핑)

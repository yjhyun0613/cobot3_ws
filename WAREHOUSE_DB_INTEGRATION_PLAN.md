# 📦 창고 세부 주차 스팟(Spot) 관리 DB 구축 및 연동 계획서

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

이 문서는 창고(Warehouse) 내부의 작업대 보관 위치를 개별 스팟 단위(`spot_01` ~ `spot_10`)로 관리하기 위해 **신규 DB 테이블 스키마 설계 및 파이썬 코드 연동 방안**을 정리한 계획서입니다.

---

## 📊 1. 수정된 데이터베이스 ERD 구조

창고 스팟 관리 테이블(`warehouse_locations`)이 추가되어 작업대 테이블(`workstations`)과 1:1 관계를 형성합니다.

```mermaid
erDiagram
    WORKSTATIONS {
        VARCHAR workstation_id PK "작업대 ID (WS01~10)"
        VARCHAR current_location "작업대 실시간 위치"
        INT aruco_id UNIQUE "ArUco ID (11~20)"
    }
    WAREHOUSE_LOCATIONS {
        VARCHAR spot_id PK "창고 주차 구역 (spot_01~10)"
        VARCHAR workstation_id FK "보관된 작업대 ID (NULL 허용)"
        VARCHAR status "스팟 점유 상태 (EMPTY, OCCUPIED)"
    }
    
    WORKSTATIONS ||--o| WAREHOUSE_LOCATIONS : "parked at"
```

---

## 🗄️ 2. 신규 테이블 정의: `warehouse_locations`

* **용도**: 창고 내부의 구체적인 작업대 주차 공간(Slot/Spot) 현황 모니터링 및 실시간 빈자리 검색
* **Primary Key**: `spot_id`
* **Foreign Key**: `workstation_id` (작업대 테이블 참조)

| 열 이름 (Column) | 데이터 타입 (Type) | 제약 조건 (Constraints) | 설명 (Description) | 예시 데이터 |
| :--- | :--- | :--- | :--- | :--- |
| **`spot_id`** | `VARCHAR(50)` | `PRIMARY KEY` | 창고 내 고유 주차 구역 ID | `'spot_01'`, `'spot_02'`, `'spot_10'` |
| **`workstation_id`** | `VARCHAR(50)` | `FOREIGN KEY` (참조: `workstations`) | 주차된 작업대 ID (비어있으면 `NULL`) | `'WS01'`, `NULL` |
| **`status`** | `VARCHAR(20)` | `DEFAULT 'EMPTY'` | 스팟 점유 상태 (`EMPTY` / `OCCUPIED`) | `'OCCUPIED'`, `'EMPTY'` |

---

## 🔄 3. 데이터 적재 시나리오 예시

작업대 `WS01`이 인바운드 분류존(`sg2_in_01`)에서 창고로 이송되어 주차되고, 다시 포장존으로 출고될 때의 데이터 변화 단계입니다.

### [1단계] 초기 상태 (창고가 텅 비어 있음)
* **`warehouse_locations` 테이블**:
  | spot_id | workstation_id | status |
  | :--- | :--- | :--- |
  | `spot_01` | `NULL` | `'EMPTY'` |
  | `spot_02` | `NULL` | `'EMPTY'` |
* **`workstations` 테이블**:
  | workstation_id | current_location |
  | :--- | :--- |
  | `WS01` | `'sg2_in_01'` |

---

### [2단계] 창고 입고 실행 (AMR 이송 지시 시점)
1. 관제탑이 비어있는 가장 빠른 스팟을 찾습니다.
   ```sql
   SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;
   -- 결과: 'spot_01' 획득
   ```
2. 획득한 `spot_01` 구역을 `WS01` 작업대가 선점하도록 업데이트합니다.
   ```sql
   UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = 'WS01' WHERE spot_id = 'spot_01';
   ```
3. 작업대의 실시간 위치를 `spot_01`로 변경합니다.
   ```sql
   UPDATE workstations SET current_location = 'spot_01' WHERE workstation_id = 'WS01';
   ```
* **결과 데이터 형태 (`warehouse_locations`)**:
  | spot_id | workstation_id | status |
  | :--- | :--- | :--- |
  | **`spot_01`** | **`'WS01'`** | **`'OCCUPIED'`** |
  | `spot_02` | `NULL` | `'EMPTY'` |

---

### [3단계] 창고 출고 실행 (포장 완료 후 회수 혹은 다음 포장 시작 시점)
1. 관제탑이 `WS01` 작업대가 창고 어느 스팟에 보관 중인지 확인합니다.
   ```sql
   SELECT spot_id FROM warehouse_locations WHERE workstation_id = 'WS01';
   -- 결과: 'spot_01' 확인 (AMR에게 출발지로 지시)
   ```
2. 주차되어 있던 공간을 다시 비워주고 작업대 위치를 포장존(`sg2_out_00`)으로 변경합니다.
   ```sql
   UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = 'spot_01';
   UPDATE workstations SET current_location = 'sg2_out_00' WHERE workstation_id = 'WS01';
   ```
* **결과 데이터 형태 (`warehouse_locations`)**:
  | spot_id | workstation_id | status |
  | :--- | :--- | :--- |
  | **`spot_01`** | **`NULL`** | **`'EMPTY'`** |
  | `spot_02` | `NULL` | `'EMPTY'` |

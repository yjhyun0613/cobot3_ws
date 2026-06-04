# 🔌 ROS2 커스텀 인터페이스 변경 내역 정의서 (Interface Changes)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

이 문서는 ArUco 마커 ID 도입에 따라 수정된 **`cobot3_interfaces`** 패키지 내 서비스(Service) 및 액션(Action) 정의 파일들의 변경 사항을 정리한 문서입니다.

---

## 📌 1. 인터페이스 변경 요약

기존의 문자열 식별자(예: `package_id`, `workstation_id`)만 사용하던 구조에서 카메라 센서로 읽은 정수형 마커 번호인 **ArUco ID**(`aruco_id`, `package_aruco_id`, `workstation_aruco_id`)를 추가 연동할 수 있도록 데이터 구조를 확장했습니다. 

* **호환성 유지**: 기존 문자열 ID 필드는 그대로 유지하여 레거시(Legacy) 코드와 완벽한 하위 호환성을 제공합니다.
* **마커 우선 처리**: 관제탑 노드는 ArUco ID 값이 `0`보다 클 경우 해당 마커 정보로 DB에서 데이터를 우선적으로 조회 및 매핑합니다.

---

## 🛠️ 2. ROS2 서비스(Service) 변경 상세

### ① `GetPackageRoute.srv`
컨베이어 분류기(`bg2`)가 입고 상자를 스캔한 뒤 목적지 날짜를 조회할 때 사용됩니다.

* **변경 내역 (Request)**:
  * `int32 aruco_id` 추가 (상자 마커 번호)

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 변경 사항 (Change) | 역할 (Role) |
| :--- | :--- | :--- | :--- | :--- |
| **Request** | `package_id` | `string` | 유지 | 택배 상자 바코드 ID (기본값: 공백 허용) |
| | `customer_name` | `string` | 유지 | 수령인 성함 (기본값: 공백 허용) |
| | **`aruco_id`** | **`int32`** | **신규 추가** | **상자에 부착된 ArUco 마커 번호 (예: 101)** |
| **Response**| `route_destination` | `string` | 유지 | 분류 목적지 배송예정 날짜 (예: `2026-06-01`) |

---

### ② `CheckWarehouseStatus.srv`
적재 매니퓰레이터(`sg2_in_XX`)가 적재를 수행하기 전 동일 수령인의 물품이 창고에 보관 중인지 중복 검사합니다.

* **변경 내역 (Request)**:
  * `int32 aruco_id` 추가 (상자 마커 번호)

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 변경 사항 (Change) | 역할 (Role) |
| :--- | :--- | :--- | :--- | :--- |
| **Request** | `customer_name` | `string` | 유지 | 검사 대상 수령인 성함 (기본값: 공백 허용) |
| | `package_id` | `string` | 유지 | 검사 대상 상자 ID (기본값: 공백 허용) |
| | **`aruco_id`** | **`int32`** | **신규 추가** | **검사 대상 상자의 ArUco 마커 번호 (예: 101)** |
| **Response**| `is_already_in_warehouse` | `bool` | 유지 | 기존 동일 물품 존재 여부 (`true` / `false`) |

---

### ③ `ReportInboundProgress.srv`
적재 매니퓰레이터(`sg2_in_XX`)가 2x4 작업대에 상자를 안전하게 얹어놓을 때마다 관제 센터로 진척도를 실시간 보고합니다.

* **변경 내역 (Request)**:
  * `int32 workstation_aruco_id` 추가 (작업대 마커 번호)
  * `int32 package_aruco_id` 추가 (상자 마커 번호)

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 변경 사항 (Change) | 역할 (Role) |
| :--- | :--- | :--- | :--- | :--- |
| **Request** | `workstation_id` | `string` | 유지 | 작업대 고유 ID (기본값: 공백 허용) |
| | `robot_id` | `string` | 유지 | 적재를 보고하는 로봇 식별자 (예: `'sg2_in_01'`) |
| | `filled_slots_count` | `int32` | 유지 | 적재된 슬롯 위치 번호 (`1` ~ `8`) |
| | `package_id` | `string` | 유지 | 적재한 패키지 ID (기본값: 공백 허용) |
| | **`workstation_aruco_id`** | **`int32`** | **신규 추가** | **적재 중인 작업대의 ArUco 마커 번호 (예: 11)** |
| | **`package_aruco_id`** | **`int32`** | **신규 추가** | **적재된 상자의 ArUco 마커 번호 (예: 101)** |
| **Response**| `success` | `bool` | 유지 | 처리 결과 및 DB 반영 완료 여부 (`true` / `false`) |

---

## 🏃 3. ROS2 액션(Action) 변경 상세

### ① `MovePackage.action`
AMR(자율 이송 로봇)에게 창고 직송 등의 단일 패키지 강제 이송을 명령할 때 사용됩니다.

* **변경 내역 (Goal)**:
  * `int32 package_aruco_id` 추가 (상자 마커 번호)

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 변경 사항 (Change) | 역할 (Role) |
| :--- | :--- | :--- | :--- | :--- |
| **Goal** | `package_id` | `string` | 유지 | 이송 대상 상자 ID |
| | `customer_name` | `string` | 유지 | 수령인 성함 |
| | `destination_zone` | `string` | 유지 | 창고 내 보관 구역 (예: `'ZONE_A'`) |
| | **`package_aruco_id`** | **`int32`** | **신규 추가** | **상자 고유 ArUco 마커 ID (예: 101)** |
| **Result** | `success` | `bool` | 유지 | 최종 이송 완료 여부 |
| **Feedback**| `estimated_time_remaining` | `float32` | 유지 | 도착 예상 남은 시간 |

---

### ② `ManageWorkstation.action`
AMR에게 작업대를 다른 공정존이나 보관용 창고로 이송하도록 지시합니다. (예: 완충 시 포장존 이송, 포장 완료 시 빈 작업대 회수 등)

* **변경 내역 (Goal)**:
  * `int32 workstation_aruco_id` 추가 (작업대 마커 번호)

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 변경 사항 (Change) | 역할 (Role) |
| :--- | :--- | :--- | :--- | :--- |
| **Goal** | `workstation_id` | `string` | 유지 | 제어 대상 작업대 ID |
| | `start_location` | `string` | 유지 | 출발 물리 위치 (예: `'sg2_in_01'`) |
| | `target_location` | `string` | 유지 | 도착 물리 위치 (예: `'sg2_out_00'`) |
| | **`workstation_aruco_id`** | **`int32`** | **신규 추가** | **작업대 고유 ArUco 마커 ID (예: 11)** |
| **Result** | `success` | `bool` | 유지 | 이송 완료 성공 여부 |
| **Feedback**| `current_pose` | `string` | 유지 | 이동 중인 AMR의 실시간 3D 위치 상태 |

---

### ③ `StartPackaging.action`
포장 로봇(`sg2_out_00`)에게 특정 작업대에 도달한 상자 8칸의 포장 공정을 명령합니다.

* **변경 내역 (Goal)**:
  * `int32 workstation_aruco_id` 추가 (작업대 마커 번호)

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 변경 사항 (Change) | 역할 (Role) |
| :--- | :--- | :--- | :--- | :--- |
| **Goal** | `workstation_id` | `string` | 유지 | 포장 대상 작업대 ID |
| | `today_date` | `string` | 유지 | 오늘 날짜 YYYYMMDD |
| | **`workstation_aruco_id`** | **`int32`** | **신규 추가** | **작업대 고유 ArUco 마커 ID (예: 11)** |
| **Result** | `success` | `bool` | 유지 | 포장 공정 완료 여부 |
| | `final_output_ids` | `string[]` | 유지 | 생성된 고유 출고 ID 리스트 (포장 로봇 ID prefix 포함) |
| **Feedback**| `completed_slots` | `int32` | 유지 | 현재 포장 완료된 슬롯 누적 갯수 (1~8) |
| | `last_packed_slot` | `int32` | 유지 | 직전에 포장 완료된 슬롯 번호 |

# 🔌 ROS2 커스텀 인터페이스 정의서 (Interface Specification)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

이 문서는 **`cobot3_interfaces`** 패키지 내 서비스(Service) 및 액션(Action) 정의 파일들의 최신 명세를 정리한 문서입니다. QR코드 시스템 도입(2026-06-04)으로 기존 ArUco `int32` ID 필드가 QR `string` ID 필드로 전면 교체되었습니다.

---

## 📌 1. 인터페이스 변경 이력 요약

### v1.0 → v2.0 (ArUco → QR 전환, 2026-06-04)
기존의 정수형 ArUco 마커 번호(`int32 aruco_id`)를 사용하던 구조에서 **문자열 QR코드 ID**(`string qr_id`)로 전면 전환하였습니다.

* **타입 변경**: `int32` → `string` (QR코드는 가변 길이 문자열을 인코딩하므로)
* **필드 이름 변경**: `aruco_id` → `qr_id`, `workstation_aruco_id` → `workstation_qr_id`, `package_aruco_id` → `package_qr_id`
* **호환성**: ArUco 기반 레거시 코드는 `qr_id` 필드에 빈 문자열(`""`)을 전송하고, 기존 `package_id` / `workstation_id` 문자열 필드를 사용하면 됩니다.
* **마커 우선 처리**: 관제탑 노드는 `qr_id` 값이 비어있지 않을 경우(`!= ""`) 해당 QR 정보로 DB에서 데이터를 우선적으로 조회 및 매핑합니다.

---

## 🛠️ 2. ROS2 서비스(Service) 정의 상세

### ① `GetPackageRoute.srv`
컨베이어 분류기(`bg2`)가 입고 상자를 스캔한 뒤 목적지 날짜를 조회할 때 사용됩니다.

**파일 경로**: `src/cobot3_interfaces/srv/GetPackageRoute.srv`

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 역할 (Role) |
| :--- | :--- | :--- | :--- |
| **Request** | `package_id` | `string` | 택배 상자 바코드 ID (기본값: 공백 허용) |
| | `customer_name` | `string` | 수령인 성함 (기본값: 공백 허용) |
| | `qr_id` | `string` | 상자에 부착된 QR코드 ID (예: `"PKG_RAND_001"`) |
| **Response** | `route_destination` | `string` | 분류 목적지 배송예정 날짜 (예: `"2026-06-01"`) |

---

### ② `CheckWarehouseStatus.srv`
적재 매니퓰레이터(`sg2_in_XX`)가 적재를 수행하기 전 동일 수령인의 물품이 창고에 보관 중인지 중복 검사합니다.

**파일 경로**: `src/cobot3_interfaces/srv/CheckWarehouseStatus.srv`

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 역할 (Role) |
| :--- | :--- | :--- | :--- |
| **Request** | `customer_name` | `string` | 검사 대상 수령인 성함 (기본값: 공백 허용) |
| | `package_id` | `string` | 검사 대상 상자 ID (기본값: 공백 허용) |
| | `qr_id` | `string` | 검사 대상 상자의 QR코드 ID (예: `"PKG_RAND_001"`) |
| **Response** | `is_already_in_warehouse` | `bool` | 기존 동일 물품 존재 여부 (`true` / `false`) |

---

### ③ `ReportInboundProgress.srv`
적재 매니퓰레이터(`sg2_in_XX`)가 2x4 작업대에 상자를 안전하게 얹어놓을 때마다 관제 센터로 진척도를 실시간 보고합니다.

**파일 경로**: `src/cobot3_interfaces/srv/ReportInboundProgress.srv`

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 역할 (Role) |
| :--- | :--- | :--- | :--- |
| **Request** | `workstation_id` | `string` | 작업대 고유 ID (기본값: 공백 허용) |
| | `robot_id` | `string` | 적재를 보고하는 로봇 식별자 (예: `"sg2_in_01"`) |
| | `filled_slots_count` | `int32` | 적재된 슬롯 위치 번호 (`1` ~ `8`) |
| | `package_id` | `string` | 적재한 패키지 ID (기본값: 공백 허용) |
| | `workstation_qr_id` | `string` | 적재 중인 작업대의 QR코드 ID (예: `"WORKSTATION_WS01"`) |
| | `package_qr_id` | `string` | 적재된 상자의 QR코드 ID (예: `"PKG_RAND_001"`) |
| **Response** | `success` | `bool` | 처리 결과 및 DB 반영 완료 여부 (`true` / `false`) |

---

## 🏃 3. ROS2 액션(Action) 정의 상세

### ① `MovePackage.action`
AMR(자율 이송 로봇)에게 창고 직송 등의 단일 패키지 강제 이송을 명령할 때 사용됩니다.

**파일 경로**: `src/cobot3_interfaces/action/MovePackage.action`

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 역할 (Role) |
| :--- | :--- | :--- | :--- |
| **Goal** | `package_id` | `string` | 이송 대상 상자 ID |
| | `customer_name` | `string` | 수령인 성함 |
| | `destination_zone` | `string` | 창고 내 보관 구역 (예: `"ZONE_A"`) |
| | `package_qr_id` | `string` | 상자 고유 QR코드 ID (예: `"PKG_RAND_001"`) |
| **Result** | `success` | `bool` | 최종 이송 완료 여부 |
| | `error_msg` | `string` | 실패 시 에러 메시지 |
| **Feedback** | `current_position` | `string` | AMR의 현재 위치 좌표 또는 구역명 |
| | `progress` | `float32` | 이동 진행률 (0.0 ~ 100.0 %) |

---

### ② `ManageWorkstation.action`
AMR에게 작업대를 다른 공정존이나 보관용 창고로 이송하도록 지시합니다. (예: 완충 시 포장존 이송, 포장 완료 시 빈 작업대 회수 등)

**파일 경로**: `src/cobot3_interfaces/action/ManageWorkstation.action`

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 역할 (Role) |
| :--- | :--- | :--- | :--- |
| **Goal** | `workstation_id` | `string` | 제어 대상 작업대 ID |
| | `start_location` | `string` | 출발 물리 위치 (예: `"sg2_in_01"`) |
| | `target_location` | `string` | 도착 물리 위치 (예: `"sg2_out_00"`) |
| | `workstation_qr_id` | `string` | 작업대 고유 QR코드 ID (예: `"WORKSTATION_WS01"`) |
| **Result** | `success` | `bool` | 이송 완료 성공 여부 |
| **Feedback** | `distance_remaining` | `float32` | 목적지까지 남은 거리 (m) |
| | `status` | `string` | 현재 상태 (`"PICKING"`, `"NAVIGATING"`, `"PLACING"`) |

---

### ③ `StartPackaging.action`
포장 로봇(`sg2_out_00`)에게 특정 작업대에 도달한 상자 8칸의 포장 공정을 명령합니다.

**파일 경로**: `src/cobot3_interfaces/action/StartPackaging.action`

| 구분 | 필드명 (Field) | 데이터 타입 (Type) | 역할 (Role) |
| :--- | :--- | :--- | :--- |
| **Goal** | `workstation_id` | `string` | 포장 대상 작업대 ID |
| | `today_date` | `string` | 출고 ID 생성용 오늘 날짜 (YYYYMMDD) |
| | `workstation_qr_id` | `string` | 작업대 고유 QR코드 ID (예: `"WORKSTATION_WS01"`) |
| **Result** | `success` | `bool` | 포장 공정 완료 여부 |
| | `final_output_ids` | `string[]` | 생성된 고유 출고 ID 리스트 (포장 로봇 ID prefix 포함) |
| **Feedback** | `completed_slots` | `int32` | 현재 포장 완료된 슬롯 누적 갯수 (1~8) |
| | `last_packed_slot` | `string` | 직전에 포장 완료된 슬롯 번호 (예: `"slot_3"`) |

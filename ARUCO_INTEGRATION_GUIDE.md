# 🏷️ ArUco & QR코드 통합 연동 가이드 및 코드 매뉴얼 (Cheat Sheet)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

이 문서는 쿠팡 물류창고 관제 시스템(Control Tower)에 적용된 **ArUco 마커 및 QR코드 식별자 매핑 테이블**과 각 단계별 **DB 쿼리**, **ROS2 파이썬 예제 코드**를 모아둔 통합 매뉴얼입니다. 개발 시 참고하여 필요한 데이터를 입력해 주세요.

---

## 📌 1. QR코드 및 식별자 매핑 테이블

물리적으로 인식할 QR코드 ID와 데이터베이스의 ID 매핑 현황입니다. 중복되지 않도록 고유 형식을 유지해야 합니다.

### ① 로봇 (Robots)
| 로봇 문자열 ID (`robot_id`) | 로봇 종류 (`robot_type`) | QR코드 ID (`qr_id`) |
| :--- | :--- | :--- |
| **`bg2`** | 컨베이어 분류기 (CONVEYOR_SORTER) | **`ROBOT_bg2`** |
| **`sg2_in_01`** | 적재 로봇 (MANIPULATOR) | **`ROBOT_sg2_in_01`** |
| **`sg2_in_02`** | 적재 로봇 (MANIPULATOR) | **`ROBOT_sg2_in_02`** |
| **`sg2_in_03`** | 적재 로봇 (MANIPULATOR) | **`ROBOT_sg2_in_03`** |
| **`sg2_out_00`** | 포장 로봇 (MANIPULATOR) | **`ROBOT_sg2_out_00`** |

### ② 작업대 (Workstations)
| 작업대 문자열 ID (`workstation_id`) | 초기 위치 (`current_location`) | QR코드 ID (`qr_id`) |
| :--- | :--- | :--- |
| **`WS01`** | `spot_01` (창고 주차 스팟 1) | **`WORKSTATION_WS01`** |
| **`WS02`** | `spot_02` (창고 주차 스팟 2) | **`WORKSTATION_WS02`** |
| **`WS03`** | `spot_03` (창고 주차 스팟 3) | **`WORKSTATION_WS03`** |
| **`WS04`** | `spot_04` (창고 주차 스팟 4) | **`WORKSTATION_WS04`** |
| **`WS05`** | `spot_05` (창고 주차 스팟 5) | **`WORKSTATION_WS05`** |
| **`WS06`** | `spot_06` (창고 주차 스팟 6) | **`WORKSTATION_WS06`** |
| **`WS07`** | `spot_07` (창고 주차 스팟 7) | **`WORKSTATION_WS07`** |
| **`WS08`** | `spot_08` (창고 주차 스팟 8) | **`WORKSTATION_WS08`** |
| **`WS09`** | `spot_09` (창고 주차 스팟 9) | **`WORKSTATION_WS09`** |
| **`WS10`** | `spot_10` (창고 주차 스팟 10) | **`WORKSTATION_WS10`** |

### ③ 기본 등록 택배 (Packages) - 일부 예시
| 택배 ID (`package_id`) | 수령인 (`customer_name`) | 배송 목적지 (`route_zone`) | QR코드 ID (`qr_id`) |
| :--- | :--- | :--- | :--- |
| `PKG_RAND_001` | 김태희 | `2026-06-01` | **`PKG_RAND_001`** |
| `PKG_RAND_002` | 김철수 | `2026-06-03` | **`PKG_RAND_002`** |
| `PKG_RAND_003` | 이경규 | `2026-06-01` | **`PKG_RAND_003`** |
| `PKG_RAND_004` | 유재석 | `2026-06-01` | **`PKG_RAND_004`** |
| `PKG_RAND_005` | 공유 | `2026-06-01` | **`PKG_RAND_005`** |

### ④ 작업대 슬롯별 QR코드 식별자 (Slots)
* **포맷**: `WORKSTATION_WSxx_SLOT_y`
* **예시**:
  * `WORKSTATION_WS01_SLOT_1` ~ `WORKSTATION_WS01_SLOT_4`
  * ...
  * `WORKSTATION_WS10_SLOT_1` ~ `WORKSTATION_WS10_SLOT_8`

### ⑤ 바닥 자율주행 격자용 QR코드 식별자 (Floor Grid)
* **포맷**: `FLOOR_X_{x}_Y_{y}` (실제 월드 좌표 미터 단위 소수점 3자리 매핑)
* **범위**: 
  * $X$ 좌표: `-34.775` ~ `37.225` (1.5m 간격, 49개 열)
  * $Y$ 좌표: `-29.025` ~ `24.975` (1.5m 간격, 37개 행)
  * 총 개수: **1,813개**
* **예시**:
  * `FLOOR_X_-34.775_Y_-29.025` (좌하단 경계점)
  * `FLOOR_X_37.225_Y_24.975` (우상단 경계점)

---


## 🗄️ 2. 데이터베이스(DB) 입력 양식 (SQL)

새로운 객체(로봇, 작업대, 상자)를 DB에 등록하고 QR코드 식별자를 연동할 때 사용하는 템플릿입니다.

```sql
-- 1. 신규 로봇 등록 시 (QR ID: ROBOT_bg3)
INSERT INTO robots (robot_id, robot_type, qr_id) 
VALUES ('bg3', 'CONVEYOR_SORTER', 'ROBOT_bg3');

-- 2. 신규 작업대 등록 시 (QR ID: WORKSTATION_WS11)
INSERT INTO workstations (workstation_id, current_location, qr_id) 
VALUES ('WS11', 'spot_01', 'WORKSTATION_WS11');

-- 3. 신규 택배 등록 시 (QR ID: PKG_RAND_100)
INSERT INTO packages (package_id, customer_name, route_zone, status, qr_id) 
VALUES ('PKG_RAND_100', '이순신', '2026-06-01', 'WAITING', 'PKG_RAND_100');
```

---


## 💻 3. ROS2 로봇 노드 통신 코드 예시 (Python)

로봇이 카메라 센서로부터 QR코드를 디코딩한 후 관제탑 노드로 서비스 및 액션 요청을 보낼 때 사용하는 코드 예제입니다.

### ① 택배 분류 목적지 요청 (`GetPackageRoute`)
컨베이어 분류 로봇(`bg2`)이 박스의 QR코드를 찍은 후 목적지를 받아옵니다.
```python
from cobot3_interfaces.srv import GetPackageRoute

# 서비스 클라이언트 생성 및 요청 작성
client = node.create_client(GetPackageRoute, 'get_package_route')
request = GetPackageRoute.Request()

# 스캔한 QR코드 문자열과 기타 정보를 입력
request.qr_id = "PKG_RAND_001"   # 필수: 박스의 QR코드 ID (카메라 디코딩 결과)
request.package_id = ""          # 옵션 (QR ID가 있으면 자동 매핑)
request.customer_name = ""       # 옵션

# 비동기 호출
future = client.call_async(request)
```

### ② 창고 보관 여부 검사 요청 (`CheckWarehouseStatus`)
적재 로봇(`sg2_in_XX`)이 적재 작업 직전에 동일 수령인의 물품이 창고에 있는지 조회합니다.
```python
from cobot3_interfaces.srv import CheckWarehouseStatus

client = node.create_client(CheckWarehouseStatus, 'check_warehouse_status')
request = CheckWarehouseStatus.Request()

# 적재 전 상자의 QR코드 ID를 입력
request.qr_id = "PKG_RAND_001"   # 필수: 검사 대상 상자의 QR코드 ID
request.package_id = ""          # 옵션
request.customer_name = ""       # 옵션

future = client.call_async(request)
```

### ③ 적재 완료 및 진척도 보고 (`ReportInboundProgress`)
적재 로봇(`sg2_in_XX`)이 2x4 작업대에 상자를 안전하게 적재했을 때 이를 보고합니다.
```python
from cobot3_interfaces.srv import ReportInboundProgress

client = node.create_client(ReportInboundProgress, 'report_inbound_progress')
request = ReportInboundProgress.Request()

# 작업대 및 박스의 QR코드 ID를 각각 입력
request.workstation_qr_id = "WORKSTATION_WS01"  # 필수: 작업대의 QR코드 ID
request.package_qr_id = "PKG_RAND_001"          # 필수: 적재한 박스의 QR코드 ID
request.filled_slots_count = 1                   # 필수: 현재 채워진 칸의 개수 (1~8)
request.robot_id = "sg2_in_01"                   # 필수: 보고하는 로봇의 문자열 ID
request.workstation_id = ""                      # 옵션 (QR ID가 있으면 자동 매핑)
request.package_id = ""                          # 옵션

future = client.call_async(request)
```

### ④ OpenCV & zxing-cpp 기반 QR코드 디코딩 예시
카메라 노드에서 수신한 비디오 프레임으로부터 QR코드를 디코딩하여 문자열 정보를 추출합니다.
```python
import cv2
import zxingcpp

def detect_and_decode_qr(frame):
    # zxingcpp를 사용하여 프레임 내의 모든 QR코드/바코드를 스캔합니다.
    results = zxingcpp.read_barcodes(frame)
    for barcode in results:
        # 해독된 문자열 결과 반환 (예: "PKG_RAND_001", "FLOOR_X_12.500_Y_-15.000")
        if barcode.text:
            print(f"[Vision] Detected QR Code: {barcode.text}")
            return barcode.text
    return None
```



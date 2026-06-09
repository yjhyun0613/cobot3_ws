# 🚀 쿠팡 물류창고 관제 시스템 개선 및 고도화 계획서 (System Improvement Plan)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 하며, 변경사항이 발생하면 관련 마크다운 문서를 지속적으로 자동 갱신해야 합니다.

본 문서는 현재 구축된 쿠팡 물류창고 관제 시스템(Control Tower)의 한계점과 문제점을 분석하고, 이를 극복하기 위한 데이터베이스 구조 정규화, QR코드 시스템 도입, 이중 버퍼(Double Buffer) 물리 레이아웃 설계, Redis 작업 우선순위 지정, 관제 단일장애점(SPOF) 대응, 외부 엑셀/CSV 데이터 연동을 통한 동적 택배 명단 로드, 그리고 바닥 QR코드 공간 격자 데이터베이스 연동 설계 방안을 구체적으로 정리한 계획서입니다.

---

## 📌 1. 데이터베이스 구조 정규화 (DB Schema Optimization) - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 3일 구현 완료. `workstations` 테이블의 중복 슬롯 정보가 `packages` 테이블의 외래키 정보로 통합 정규화되었습니다.

### 1.1 현재 문제점
* `workstations` 테이블에 1~8번 슬롯의 수령인 및 상태 컬럼(`slot_X_customer`, `slot_X_status`)을 컬럼 형태로 직접 정의함.
* `packages` 테이블 역시 `workstation_id`와 `slot_number`를 가지고 있어 **데이터 중복 및 불일치 위험**이 존재함.
* 8칸 외에 슬롯 개수가 변경(예: 3x3 layout)될 경우 DB 스키마 및 쿼리 전체를 수정해야 하므로 확장성이 떨어짐.

### 1.2 개선 방향
* `workstations` 테이블의 슬롯별 상세 정보 컬럼들을 삭제하고, **작업대 고유 식별자(`workstation_id`) 및 실시간 물리 위치(`current_location`) 정보만 유지**함.
* 특정 작업대 슬롯의 점유 여부는 `packages` 테이블의 외래키 매핑 정보를 기반으로 `JOIN` 쿼리 또는 조건 조회를 수행하여 판단함.

```sql
-- 예시: WS01 작업대의 슬롯별 점유 현황 조회 쿼리
SELECT slot_number, package_id, customer_name 
FROM packages 
WHERE workstation_id = 'WS01' 
ORDER BY slot_number;
```

---

## 🏷️ 2. QR코드 시스템 도입 및 인식 설계 - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 4일 구현 완료. 
> - 패키지 및 설비용 QR코드 자동 생성 패키지(`scratch/qr_handler.py`)와 종단간 테스트(`scratch/run_qr_simulation_test.py`) 완료.
> - `warehouse.yaml` 기반 월드 좌표계 파싱 및 1,813개 바닥 격자/80개 작업대 슬롯 QR코드 일괄 생성 완료 (`scratch/generate_all_qr_codes.py`).
> - Isaac Sim `map.usd` 내 1,813개 바닥 QR코드 메쉬/재질 자동 배치 완료 (`scratch/add_all_qr_to_usd.py`).
> - 바닥 글레어 현상 방지용 환경광(DomeLight) 보강 및 조명 최적화 완료 (`scratch/adjust_usd_lighting.py`).

일회용 택배 박스에 영구 마커인 ArUco ID를 직접 인쇄하여 매칭하는 방식의 비현실성을 극복하고, 자율주행 AMR의 격자 주행(Grid-based Navigation)을 지원하기 위해 바코드/QR코드 매핑 방식을 전면 도입합니다.

### 2.1 QR코드 생성 및 적용
* **택배 박스 및 로봇/설비**: 파이썬 `qrcode` 라이브러리를 활용해 고유 ID 정보를 담은 PNG 코드를 동적 생성하고, 가상 3D 모델의 텍스처로 바인딩합니다.
* **바닥 격자 마커 (Floor Grid)**: 
  * 맵 설정(`warehouse.yaml`) 및 사용자 지정 창고 영역 경계 제한(X: [-38.0, 38.0], Y: [-36.08472, 25.0])을 적용하여 1.5m 간격으로 1,813개의 격자점 좌표를 산출.
  * 각 격자의 실제 미터법 좌표 값(예: `FLOOR_X_-34.775_Y_-29.025`)을 인코딩한 QR코드를 일괄 생성.
* **작업대 슬롯 마커 (Slots)**: 10개 작업대의 슬롯별 식별자(예: `WORKSTATION_WS01_SLOT_1` ~ `WORKSTATION_WS10_SLOT_8`, 총 80개) 생성 완료.

### 2.2 USD 3D 맵 매핑 및 시각화
* Isaac Sim의 `SimulationApp` 및 Pixar USD (`pxr`) API를 이용해 `src/cobot3/resource/map.usd` 맵 상에 1,813개의 30cm 크기의 격자 메쉬(Plane)와 개별 QR 텍스처를 바인딩한 재질(Material)을 자동 배치하여 맵을 갱신하였습니다.

### 2.3 비전 인식용 조명 최적화
* **문제점**: 강한 스포트라이트 성격의 직사광선이 바닥에 맺혀 빛 반사(Specular Glare)로 인해 QR코드 시인성이 떨어지고 인식이 실패함.
* **해결 방안**:
  * 기존 `/Environment/defaultLight` (DistantLight) 세기를 3000.0에서 **600.0**으로 약화시켜 눈부심 제거.
  * 부드러운 산란광을 비추는 `/Environment/domeLight` (DomeLight, 세기 **1200.0**)을 추가하여 공장 전체의 그림자를 지우고 일정한 조도를 보장.

### 2.4 비전 기반 QR코드 디코딩
* 로봇/카메라 노드에서 카메라 토픽을 구독하여 OpenCV 및 `zxing-cpp` 라이브러리로 이미지를 처리합니다.
* 해독된 문자열로 PostgreSQL DB를 조회하여 목적지와 수령인 등 제어에 필요한 데이터를 획득합니다.

```python
import cv2
import zxingcpp

def decode_qr_from_frame(frame):
    results = zxingcpp.read_barcodes(frame)
    for barcode in results:
        if barcode.text:
            return barcode.text # 예: "PKG_RAND_001" or "FLOOR_X_1.5_Y_-3.0"
    return None
```

---


## ⚙️ 3. 이중 버퍼 (Double Buffer) 물리 레이아웃 및 Keep-Alive Dispatcher - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 4일 구현 완료.
> - 각 인바운드 라인에 활성(Active) 적재 구역인 A구역(`_A`)과 예비 대기(Standby) 구역인 B구역(`_B`) 이중 버퍼 레이아웃 도입.
> - 아웃바운드 포장 로봇 구역(`sg2_out_00`)에도 활성 포장 구역인 A구역(`sg2_out_00_A`)과 예비 대기 구역인 B구역(`sg2_out_00_B`) 이중 버퍼 적용 완료.
> - 1Hz 주기의 `dispatch_workstations_keepalive()` 백그라운드 스케줄러를 통한 자동 작업대 보충 및 B구역 대기 작업대 승격(Promotion) 로직 적용.
> - 인바운드(3번째 슬롯 적재 완료 시), 아웃바운드(7번째 슬롯 포장 완료 시) Look-ahead 메커니즘 연동 완료.

AMR 이송 속도가 로봇의 적재 및 포장 속도보다 느려 발생하는 병목 및 대기 현상을 해결하기 위해 작업대 대기 구역을 이중화하고 동적으로 관리합니다.

```
[인바운드 적재 라인]                     [아웃바운드 포장 라인]
[적재 로봇 (sg2_in_XX)]                 [포장 로봇 (sg2_out_00)]
         │                                       │
 ┌───────┴───────┐                       ┌───────┴───────┐
 ▼               ▼                       ▼               ▼
[A 구역: _A]     [B 구역: _B]            [A 구역: _A]     [B 구역: _B]
(활성 적재 구역) (예비 대기 구역)        (활성 포장 구역) (예비 대기 구역)
```

* **인바운드 동작 루프**:
  1. 관제탑 스케줄러가 비어 있는 각 인바운드 라인의 **A 구역 (`sg2_in_XX_A`)**에 창고 내 빈 작업대를 자동으로 즉시 공급합니다.
  2. 적재 로봇은 A 구역에 배치된 작업대에 상자를 적재합니다.
  3. 작업대 슬롯에 **3번째 상자**가 채워지는 즉시, 관제탑은 Look-ahead 트리거를 발동하여 창고 내 다른 빈 작업대를 해당 라인의 **B 구역 (`sg2_in_XX_B`)**으로 호출(`PRE_FETCH_EMPTY_WORKSTATION`)합니다.
  4. 8번째 슬롯까지 적재가 완료(완충)되면, 관제탑은 완충 작업대를 포장존 또는 창고로 회수하고, 동시에 B 구역에 대기 중이던 예비 작업대를 A 구역으로 승격시킵니다.
  5. 승격된 새 작업대에 적재를 진행하는 동안, 비어 있게 된 B 구역에는 Look-ahead 스케줄링에 의해 새로운 빈 작업대가 미리 배치되어 로봇의 유휴 시간(Idle Time)이 최소화됩니다.

* **아웃바운드 동작 루프**:
  1. 관제탑 스케줄러가 활성 포장 구역인 **A 구역 (`sg2_out_00_A`)**에 완충된 작업대를 창고에서 즉시 공급(혹은 분류 완료 즉시 공급)합니다.
  2. 포장 로봇은 A 구역에 배치된 작업대에서 상자를 포장합니다.
  3. 작업대 슬롯의 **7번째 상자**가 포장되는 즉시, 관제탑은 Look-ahead 트리거를 발동하여 창고 내 다른 완충 작업대를 포장 **B 구역 (`sg2_out_00_B`)**으로 호출(`PRE_FETCH_PACKAGING_WORKSTATION`)합니다.
  4. 8번째 슬롯까지 포장이 완료되면, 관제탑은 빈 작업대를 창고로 회수(`RETRIEVE_EMPTY_WORKSTATION`)하고, 동시에 B 구역에 대기 중이던 작업대를 A 구역으로 승격(`DEPLOY_PACKAGING_WORKSTATION`)시킵니다.

---

## 📊 4. Redis Sorted Set 기반 우선순위(Priority) 큐 및 180도 회전 도입 - [완료]

단순 선입선출(FIFO) 큐 구조의 한계를 개선하여 물류 정체를 유발하는 긴급 연산에 우선순위를 부여하고, 2x4 배열 적재를 위해 180도 회전 기능을 도입했습니다.

### 4.1 작업 우선순위 등급 정의
1. **P1 (우선순위 점수: 100)**: 
   * 적재 완료된 작업대 배출 (`RETRIEVE_FULL_WORKSTATION`)
   * 창고 직송 처리 (`DIRECT_WAREHOUSE`)
   * **작업대 180도 제자리 회전 (`ROTATE_WORKSTATION`)**: 앞열 4칸 적재 완료 후 뒷열 4칸 적재를 위해 회전
2. **P1.5 (우선순위 점수: 90)**: 활성 적재 구역 빈 작업대 공급 (`DEPLOY_EMPTY_WORKSTATION`)
3. **P2 (우선순위 점수: 80)**: 포장 대기용 완충 작업대 공급 (`DEPLOY_PACKAGING_WORKSTATION`, `FETCH_FOR_PACKAGING`)
4. **P2.5 (우선순위 점수: 70)**: 포장 대기용 완충 작업대 사전 이송 (`PRE_FETCH_PACKAGING_WORKSTATION`)
5. **P3 (우선순위 점수: 50)**: 이중 버퍼 대기 구역 내 빈 작업대 보충 (`PRE_FETCH_EMPTY_WORKSTATION` - Look-ahead)
6. **P4 (우선순위 점수: 20)**: 완전히 비어 있는 작업대 회수 및 재배치 (`RETRIEVE_EMPTY_WORKSTATION`)

### 4.2 Redis ZSET 명령어 및 중복 방지 설계
* **중복 방지**: Redis Sorted Set은 고유 멤버만 보관하므로, 동일 내용의 태스크 누락을 예방하기 위해 각 태스크 딕셔너리에 `uuid`를 고유하게 부여하여 직렬화합니다.
* **태스크 등록**: `ZADD queue:amr_tasks [Score] [Task_JSON]`
* **태스크 팝(Pop)**: 관제탑 스케줄러에서 가장 높은 점수(가장 시급한 작업)를 원자적으로 가져옵니다.
  ```python
  # Redis Python Client 기반 최고 점수 팝
  redis_client.zpopmax('queue:amr_tasks')
  ```
* **180도 회전 연동**: 4번째 슬롯 적재 시 작업대 위치를 `_A_ROTATING`으로 변경하여 로봇 적재를 일시 정지(Sync)시키고, 회전 액션 완료 시 `_A`로 복귀시켜 5번째 슬롯 적재를 이어서 진행합니다.

---

## 🛡️ 5. 관제 단일장애점 (SPOF) 대응 및 Fail-safe 설계 - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 4일 구현 완료.
> - 서비스 호출 시 1초 타임아웃 및 3회 자동 재시도 헬퍼 함수 (`call_service_with_fail_safe`) 도입.
> - 접속 끊김 시 로컬 오프라인 룰베이스(Fallback Callback)를 활성화하여 패키지 해시 분배 및 예외 안전 순환 회차로 처리 구현.

관제 센터 서버 다운 시 전체 라인이 정지하는 문제를 완화하기 위해 로컬 제어와 예외 처리 루틴을 적용합니다.

* **타임아웃(Timeout) 및 재시도(Retry)**:
  * 로봇이 관제탑에 서비스 응답을 보낸 후 1초간 무응답 시 타임아웃 처리 후 자동 재시도(최대 3회) 및 응답 지연(2초)에 따른 블로킹 해제 메커니즘을 통합했습니다.
* **로컬 순환 회차로(Recirculation Loop) 활용**:
  * DB 다운 시 중복 여부를 확인할 수 없으므로, 패키지들을 라인 끝의 예외 수거 박스나 순환용 회차 트랙(Fallback)으로 유도하여 물리적 걸림을 차단합니다.
* **오프라인 룰베이스(Offline Rule-base) 구동**:
  * 서버 연동 불가 상태가 감지되면 패키지 ID의 아스키 해시값을 기반으로 3개 적재 로봇 라인에 균등 분배하는 로컬 백업 제어 로직을 활성화하여 벨트 적체를 예방합니다.

---

## 🔒 6. ROS2 멀티스레딩 데드락(Deadlock) 방지 설계 - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 4일 구현 완료.
> - 서비스/액션 콜백 내의 중첩된 블로킹 대기 루틴을 완전 논블로킹(Non-blocking) 폴링 구조로 전환.

### 6.1 문제 배경
* 관제탑 노드가 `MultiThreadedExecutor`로 병렬 처리를 수행하더라도, 특정 스레드 콜백 내부에서 다른 서비스의 미래 객체(Future)를 `spin_until_future_complete`와 같은 동기 방식으로 대기할 경우 실행기의 스레드 풀이 소진되어 서로를 기다리는 **교착 상태(Deadlock)**가 빈번히 발생했습니다.

### 6.2 개선 및 구현 방안
* 스레드를 블로킹하지 않고 제어권을 즉시 양보할 수 있도록 다음과 같이 논블로킹 폴링 구조로 구현하였습니다.
  ```python
  # 비동기 호출 후 논블로킹 방식으로 상태 체크 및 스레드 양보
  future = self.cli_report_progress.call_async(req)
  while not future.done():
      time.sleep(0.01) # 실행기 루프가 돌 수 있도록 양보
  response = future.result()
  ```
* 이로써 복잡한 비동기식 핑퐁 통신 흐름 하에서도 무한 대기 현상 없이 안전하게 트랜잭션을 처리할 수 있게 되었습니다.

---

## 🗃️ 7. 창고 주차 스팟(Spot) 상태 자원 정합성 보장 - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 4일 구현 완료.
> - `'warehouse'` 출발지의 추상적 표기를 데이터베이스 실시간 주차 스팟 ID로 역추적 분석하는 동적 리졸버 탑재.

### 7.1 문제 배경
* 관제탑이 창고에 주차되어 있던 작업대를 출고하는 이송 액션(`ManageWorkstation.action`)을 AMR에게 전달할 때, 출발지가 단순히 `'warehouse'`로 기록되면 실제 해당 작업대가 물리적으로 점유하고 있던 개별 주차 스팟(`spot_01` ~ `spot_12`)을 식별할 수 없었습니다.
* 이로 인해 이송이 시작되었음에도 해당 스팟이 계속 `OCCUPIED`로 남아 있어, 다른 작업대가 진입할 수 없는 **자원 점유 누수**가 발생하였습니다.

### 7.2 개선 및 구현 방안
* 작업대 이송 명령이 개시되는 즉시, 데이터베이스의 `workstations` 테이블에서 해당 작업대의 실시간 `current_location`을 조회합니다.
* 조회된 위치가 `spot_`으로 시작하는 경우, 관제탑은 이를 실제 물리 스팟 ID로 해석(Resolve)하여 데이터베이스 `warehouse_locations` 테이블의 상태를 즉시 `EMPTY`로 반환하고 `workstation_id` 매핑을 해제하도록 보장하였습니다.
* 이 조치로 실시간 작업대 공급/회수 주기 동안 창고 점유 정보가 항상 100% 실시간 정합성을 유지하게 되었습니다.

---

## 📂 8. 외부 파일 연동을 통한 동적 택배 명단 로드 시스템 도입 - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 4일 구현 완료.
> - 웹 대시보드 서버(`/api/upload_packages`) 및 프론트엔드 HTML/JS CSV 리더 탑재.
> - 시뮬레이터 비전 모듈(`run_full_simulation_robot.py`)의 `generate_qr_code` 연동 고도화.

### 8.1 문제 배경
* 현재 물류 시스템은 데이터베이스 초기화 스크립트(`init.sql`) 내부에 모의 패키지 데이터(`INSERT INTO packages`)가 SQL 형태로 하드코딩되어 있습니다.
* 이로 인해 실제 물류 현장이나 현업에서 신규 택배 명단이 업데이트되거나 입고 일정이 변경될 때마다 개발자가 매번 SQL 소스 코드를 수정하고 데이터베이스 컨테이너를 재배치/재초기화해야 하므로 실무 운용성이 저하됩니다.
* 또한 현업 관리자가 엑셀(`.xlsx`)이나 CSV 등 일반 오피스 형식으로 택배 일일 입고 일정을 기록하고 있을 경우, 시스템 연동을 위해 수동으로 데이터를 가공해야 하는 리소스 낭비가 발생합니다.

### 8.2 개선 및 구현 방안
* **대시보드 CSV 업로드 기능**:
  * 웹 대시보드 UI 상단에 **[📥 CSV 입고 명단 업로드]** 버튼 및 숨김 처리된 파일 선택 필드를 추가했습니다.
  * 추가 라이브러리(`python-multipart`) 설치 없이도 작동하도록, 브라우저가 `FileReader` API를 통해 로컬 파일을 텍스트 형식으로 인코딩한 후 `fetch` POST raw text request body로 전송하는 안전한 무의존성(Zero-dependency) 구조를 구현했습니다.
* **FastAPI 백엔드 파싱 및 Upsert 적용**:
  * `/api/upload_packages` API 엔드포인트에서 전송된 텍스트 스트림을 파이썬 내장 `csv` 및 `io` 모듈을 이용하여 가볍고 안전하게 파싱합니다.
  * 업로드된 파일의 필수 열(`package_id`, `customer_name`, `route_zone`)의 정합성 유효성을 검사합니다.
  * 만약 CSV 명단에 개 개별 택배별 `qr_id`가 지정되어 있지 않을 경우, 시스템이 자동으로 `package_id`를 QR 코드 텍스트로 보존합니다.
  * 중복된 패키지가 업로드될 경우 `ON CONFLICT (package_id) DO UPDATE` 구문을 통해 기존 수령인 정보나 배송 예정일을 자동으로 동적 Upsert 처리합니다.
* **실시간 비전(Vision) 스캔 연동**:
  * 모의 로봇 시뮬레이터(`run_full_simulation_robot.py`)가 입고 대상 상자를 가져올 때, DB에서 조회한 실제 QR코드 매핑 데이터(`pkg_qr`)를 사용하여 QR 이미지를 동적으로 렌더링하고 비전 카메라 스캐닝 루프를 수행하도록 연결을 고도화했습니다. (예: `qr_file = generate_qr_code(pkg_qr or pkg_id)`).
* **실제 날짜 기준 영업일 전환 및 이월 연속 적재 규격 (Carry-over)**:
  * 입고 라인을 고정(라인1=오늘, 라인2=내일, 라인3=모레)으로 운영하고, 오늘 날짜 패키지가 완료되면 `/api/start_next_day` API를 호출하여 날짜를 전환하고 라인을 물리적으로 상향 이동(2->1, 3->2)시킵니다.
  * 이전 날 부분 적재된 작업대(예: 6개 적재 상태)가 1번 라인으로 이동했을 때, 당일 신규 패키지 CSV 파일이 로드되기 전까지는 포장존으로 자동 플러시되지 않도록 Redis `system:inbound_started` 플래그를 도입하여 연동 상태를 제어합니다. CSV 파일이 업로드된 후에만 이월 적재를 재개하여 슬롯 7, 8을 연속 채우고 포장존으로 이송합니다.

---

## 🗺️ 9. 바닥 QR코드 공간 격자 맵 데이터베이스(Spatial Floor QR Map DB) 연동 설계 - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 5일 구현 완료 (2026년 6월 7일 신규 물리 좌표 및 Offset 1,819개 노드 적재 추가, 2026년 6월 9일 init.sql 시드 데이터 추가).
> - PostgreSQL 데이터베이스 초기화 스크립트(`docker/init.sql`)에 `floor_qr_map` 테이블 정의 및 **시드 데이터(INSERT) 약 117개 노드** 추가 완료. Docker 최초 기동 시 자동 적재.
> - 격자 생성기(`scratch/generate_all_qr_codes.py`) 실행 시 1,819개의 물리 격자 좌표 및 논리 스팟(`spot_XX`, `sg2_in_XX_A/B`, `sg2_out_00_A/B`) 정보를 PostgreSQL DB로 자동 적재 연동 완료.
> - 관제탑(`control_tower_node.py`) 및 모의 로봇 에뮬레이터(`run_full_simulation_robot.py`) 기동 시 하드코딩된 목적지 명칭 대신 `floor_qr_map` 데이터베이스를 실시간으로 쿼리하여 물리 coordinates와 바닥 QR 마커 식별자를 해석(Resolution)하는 구조 구현 및 검증 완료.

### 9.1 배경 및 필요성
* 바닥에 배치된 격자형 QR코드(예: 1,819개의 바닥 QR)는 AMR이 이동 및 로컬라이제이션(Localization)을 수행하는 물리적 기준 역할을 합니다.
* 창고 내 보관 위치(`spot_01` ~ `spot_12`), 인바운드 대기/작업 위치(`sg2_in_01_A`, `sg2_in_01_B`), 아웃바운드 포장 위치(`sg2_out_00_A`, `sg2_out_00_B`) 등의 논리적 위치가 AMR의 물리적 목적지 좌표와 매핑되어야 합니다.
* 이러한 매핑과 좌표 정보를 소스코드 내부에 하드코딩할 경우, 레이아웃 변경 시 소스코드를 전면 재수정해야 하는 심각한 유지보수 문제가 발생합니다. 따라서 이를 관계형 데이터베이스(PostgreSQL)의 전용 공간 매핑 테이블에서 관리하여 **단일 진실 공급원(Single Source of Truth)**을 구축해야 합니다.

### 9.2 데이터베이스 테이블 설계 (`floor_qr_map`)
PostgreSQL에 다음과 같은 공간 격자 맵 정보 관리 테이블을 정의합니다.
* **Primary Key**: `qr_id`
* **설계 필드**:
  * `qr_id` (`VARCHAR(100)`): 바닥 QR코드 고유 ID (예: `'FLOOR_X_15.0_Y_-12.5'`)
  * `x_coord` (`DOUBLE PRECISION`): 물리 X 좌표 (m)
  * `y_coord` (`DOUBLE PRECISION`): 물리 Y 좌표 (m)
  * `z_coord` (`DOUBLE PRECISION`): 물리 Z 좌표 (m, 기본값 0.0)
  * `location_name` (`VARCHAR(50)`): 매핑되는 물리/논리 스팟 이름 (예: `'spot_01'`, `'sg2_in_01_A'`, `'sg2_out_00_A'`)
  * `location_type` (`VARCHAR(50)`): 위치 용도 구분 (예: `'PARKING_SPOT'`, `'LOADING_SPOT'`, `'PATHWAY'`)
  * `description` (`TEXT`): 상세 용도 설명

### 9.3 동작 및 연동 메커니즘
1. **위치 해석(Resolution)**:
   * 관제탑이 AMR에게 `"WS01 작업대를 sg2_in_01_A로 이송하라"`는 액션 명령을 내릴 때, 하드코딩된 좌표 대신 `SELECT x_coord, y_coord FROM floor_qr_map WHERE location_name = 'sg2_in_01_A'`를 쿼리하여 대상 좌표와 대응되는 바닥 QR ID를 동적으로 확보해 Goal 정보로 전송합니다.
2. **레이아웃 재설정(Dynamic Layout Reconfiguration)**:
   * 예를 들어, 포장 로봇 앞의 작업대 대기 장소가 물리적으로 `y=3.5`에서 `y=4.5`로 이동하는 경우, 소스코드 빌드 및 컨테이너 재작동 없이 데이터베이스의 특정 행을 갱신하는 쿼리 하나로 모든 AMR과 관제탑의 목적지 좌표 연동이 동적으로 변경됩니다.
     ```sql
     UPDATE floor_qr_map SET location_name = 'sg2_in_01_A' WHERE qr_id = 'FLOOR_X_2.5_Y_4.5';
     ```
3. **AMR 자율주행 격자 생성**:
   * 대시보드 및 관제 노드는 기동 시 `floor_qr_map`을 쿼리하여 가용 좌표 지도를 구성하고, AMR의 현재 좌표와 매핑된 바닥 QR를 조회하여 최단 경로(A* 알고리즘 등)를 동적으로 계산합니다.

---

## 🤝 10. AMR 플릿 연동 및 하이브리드 통신 아키텍처 규격 - [구현 완료]

> [!NOTE]
> **설계 및 구현 완료**: 2026년 6월 5일 설계 검토 및 합의 완료 후 관제탑 노드(`control_tower_node.py`) 및 인터페이스 정의 수정, 토픽 발행 검증까지 최종 완료되었습니다.

### 10.1 핵심 설계 원칙 (4대 수정안)
1. **수정안 1 (통신 제한)**: JSON 토픽은 제어 명령용이 아니라 모니터링과 대시보드 표시용으로 제한한다.
2. **수정안 2 (제어 채널)**: AMR 이동, 작업대 픽업/드롭, 작업 취소는 반드시 ROS2 Action으로 처리한다.
3. **수정안 3 (좌표 전송)**: QR ID는 `QR_XXXX` 형식을 사용하되, 관제탑은 DB의 `floor_qr_map`에서 좌표를 조회하고, AMR에는 `target_qr_id`와 `target_pose`를 함께 전달한다.
4. **수정안 4 (DB 정규화)**: DB는 정규화 구조를 원본으로 유지하고, `filled_slots` 같은 배열 데이터는 관제탑이 송신 시점에 실시간으로 생성한다.

### 10.2 아키텍처 비교 요약 (동작 한계 정의)
* **제어 명령 (Control Plane)**: `ROS2 Action/Service`를 사용하여 성공/실패 결과 반환, 피드더백, 중도 취소(Action Cancel)를 처리함으로써 무선 네트워크 불안정 시에도 데드락이나 명령 유실이 발생하지 않도록 조치합니다.
* **상태 모니터링 (Data/State Plane)**: `/fleet/amr_states`, `/fleet/workstation_states`, `/fleet/package_states`, `/fleet/task_events` 토픽에 JSON을 직렬화하여 송신함으로써 빌드 변경 최소화 및 대시보드 연동성을 확보합니다.
* **비상 백업 (Fail-safe)**: DB 장애 대응을 위해 AMR 로컬 장비 내에 `floor_qr_map.yaml` 파일을 비상 백업 맵으로 상시 유지하여, 관제탑과의 연결 유실 시에도 마커 스캔을 통해 로컬 복구 주행이 가능하도록 백업 체계를 구축합니다.

### 10.3 상세 구현 규격 및 JSON 메시지 구조
* **`ManageWorkstation.action` Goal 확장**:
  ```protobuf
  string target_qr_id        # 목적지 바닥 QR ID (예: "QR_0030")
  float64 target_x           # 목적지 X 좌표 (m)
  float64 target_y           # 목적지 Y 좌표 (m)
  float64 target_yaw         # 목적지 Yaw 각도 (rad)
  ```

* **상태 모니터링 JSON 토픽 사양**:
  1. `/fleet/amr_states` (`std_msgs/msg/String` JSON):
     ```json
     {
       "AMR_01": {
         "state": "IDLE",
         "current_qr_id": "QR_0030",
         "target_qr_id": "",
         "carrying_workstation_id": null,
         "battery": 82.5,
         "available": true
       }
     }
     ```
  2. `/fleet/workstation_states` (`std_msgs/msg/String` JSON):
     ```json
     {
       "workstations": [
         {
           "workstation_id": "WS01",
           "workstation_qr_id": "WORKSTATION_WS01",
           "current_location": "QR_0030",
           "status": "WAITING",
           "slot_count": 8,
           "filled_slots": [1, 2, 3, 4],
           "reserved_by": null
         }
       ]
     }
     ```
  3. `/fleet/package_states` (`std_msgs/msg/String` JSON):
     ```json
     {
       "packages": [
         {
           "package_id": "PKG_RAND_001",
           "customer_name": "김태희",
           "route_zone": "2026-06-01",
           "status": "WAITING",
           "outbound_id": null,
           "workstation_id": null,
           "slot_number": null,
           "qr_id": "PKG_RAND_001"
         }
       ]
     }
     ```
  4. `/fleet/task_events` (`std_msgs/msg/String` JSON):
     ```json
     {
       "schema_version": "1.0",
       "timestamp": 1780626168.9948,
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

## 🚀 11. 향후 개선 및 확장 제안 (Future Improvements & Extensions) - [진행 중]

시스템의 안정성, 성능 및 확장성을 한 단계 더 끌어올리기 위해 도입을 고려해볼 수 있는 추가 개선 항목들입니다.

### 11.1 DB 커넥션 풀 (Connection Pool) 도입 - [완료]
* **적용 완료**: 2026년 6월 8일 구현 완료.
* **현재 구성**: `control_tower_node.py` 내에 `psycopg2.pool.ThreadedConnectionPool`을 도입하여 각 스레드가 필요할 때 풀에서 독립적인 커넥션을 획득하여 SQL 쿼리를 수행하게 함으로써 병목 해소 및 DB 동시 처리 능력 개선.
* **해결 방안**: `@contextmanager` 데코레이터를 이용한 `get_db_connection()` 컨텍스트 매니저를 구현하여 쿼리 연산 완료 후 자동으로 커넥션이 풀에 반환되도록 조치함.

### 11.2 실시간 양방향 모니터링을 위한 WebSockets 전환 - [완료]
* **적용 완료**: 2026년 6월 8일 구현 완료.
* **구현 요약**:
  - **백엔드**: FastAPI에서 `ConnectionManager` 클래스 및 `/ws` WebSocket 라우트를 정의하고, 백그라운드 async 태스크 `status_broadcast_loop`를 기동하여 활성 세션에 0.5초 주기로 DB/Redis 상태 snapshot을 Broadcast하도록 구현하였습니다. 동기 DB/Redis IO 병목 방지를 위해 `loop.run_in_executor`를 활용하였습니다.
  - **프론트엔드**: 브라우저의 HTTP 1Hz Polling 루프를 삭제하고, `connectWebSocket()`을 통해 동적으로 `window.location.host`에 연결해 실시간 상태 패킷을 즉시 UI 렌더러(`updateUI`)에 피딩하도록 연동하였습니다. 3초 주기 자동 재연결(Reconnect) 기능을 탑재해 네트워크 일시 유실 상황에 견고하게 대응합니다.
  - **검증**: C-to-C 분산 환경 하에서 모니터링 브라우저가 기동 시 실시간 웹소켓 핸드셰이크를 성공하고 `⚡ 실시간 WebSocket 관제 연결 완료` 토스트 알림을 정상 출력하는 것을 뷰 검증 완료했습니다.

### 11.3 배터리 잔량 기반 AMR 스케줄링 고도화 (Battery-aware Dispatching)
* **현재 구성**: `/fleet/amr_states` 토픽으로 배터리 정보를 발행하고 있으나, Redis 큐에서 작업을 분배할 때 배터리 상태는 반영되지 않음.
* **개선 방향**: 
  * AMR 배터리가 일정 수준 이하(예: 20%)로 내려가면 스케줄러가 해당 AMR을 가용 목록에서 임시 제외.
  * 최우선 순위로 충전소(`GO_TO_CHARGING`) 이송 태스크를 예약 및 할당하여 충전 구역으로 이동시키고, 충전 완료(예: 80% 이상) 시에만 작업 대기 상태로 복귀시키는 자동 스케줄링 구현.

### 11.4 물리적 창고 포화(Full) 및 교착 상태(Deadlock) 제어 (Throttling)
* **현재 구성**: 창고 스팟(10개) 및 대기 구역(4개)이 포화된 경우에 대한 인바운드 분류 속도 제어 로직이 없음.
* **개선 방향**: 
  * 스팟 점유 상태를 상시 카운트하여 여유 공간이 임계치 이하(예: 1~2개)인 경우, 컨베이어 입고 분류 로봇(`bg2`)의 작동 속도를 낮추거나 일시 정지(Hold)시키는 **쓰로틀링(Throttling) 메커니즘** 구현.
  * 과거 미처리 패키지를 오늘 날짜로 롤오버(Roll-over) 또는 강제 완료(Force-completed)하여 일자 전환 시의 데드락을 사전 차단.

### 11.5 다중 AMR 경로/공간 점유 트래픽 제어 (Traffic Management)
* **현재 구성**: 로컬 AMR 주행 시뮬레이터나 개별 회피에 경로 결정을 위임함. 좁은 통로(Aisle)나 교차로에서 다중 AMR이 마주치는 경우 정체 또는 교착이 발생할 수 있음.
* **개선 방향**:
  * 격자 맵(`floor_qr_map`) 상의 주요 병목 구간 및 교차로 마커를 **세마포어(Semaphore)** 또는 **공간 예약제(Space Reservation)** 방식으로 관리.
  * 특정 구역에 AMR이 진입하기 전 관제탑에 해당 Node 점유 권한을 획득하게 함으로써 다중 로봇 간 교차 주행 및 병목을 중앙 제어.

### 11.6 bg2 분류 로봇의 로컬 캐시 조회 및 배치 동기화 도입 (bg2 Local Caching Optimization) - [완료]
> [!NOTE]
> **적용 완료**: 2026년 6월 9일 구현 완료.
> - `mock_sg2_devices.py` 및 `run_full_simulation_robot.py` 내의 입고 시뮬레이션 루프(`inbound_sim_loop`)에 로컬 캐시 동기화 로직 적용.
> - 영업 개시(`day_status == 'RUNNING'`) 감지 시 PostgreSQL 데이터베이스로부터 당일 패키지 목록을 일괄 캐싱(`load_package_cache()`).
> - 스캔 시 관제탑 ROS 2 서비스 질의를 생략하고 로컬 메모리 캐시에서 즉시 목적지 판별.
> - 캐시 미스 또는 조회 오류 발생 시 안전 회차 라인(4번 라인 / Bypass)으로 분류하여 패키지 상태를 즉시 `IN_WAREHOUSE`로 업데이트.

### 11.7 대시보드 기기 연동 및 택배 명단 등록 기반 영업 개시 인터록 (Safety Start Interlock) - [완료]
> [!NOTE]
> **적용 완료**: 2026년 6월 9일 구현 완료.
> - 대시보드 서버(`dashboard_server.py`)의 `reset_db()` 및 `start_next_day()` API 기본 상태를 `'WAITING_FOR_START'`로 변경.
> - `get_status()` API가 Redis에 등록된 기기 하트비트(`device:<name>:heartbeat`)와 AMR 인스턴스를 수집해 `device_status`로 전달하도록 갱신.
> - 대시보드 UI 상단에 **[영업 시작]** 버튼 추가 및 각 실시간 기기 연결 상태(bg2, sg2들, AMR)를 보여주는 배지 스트립 배치.
> - 모든 필수 하드웨어 기기가 정상 연결(Online)되고 오늘자 물량 CSV 업로드(WAITING 패키지 존재) 시에만 [영업 시작] 버튼이 활성화(ready)되어 영업일 가동을 승인하는 인터록 안전 장치 구현 완료.

---

## 🚚 12. AMR 플릿 주행 알고리즘 연동 설계 및 검증 (AMR Fleet Path Planner Integration) - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 7일 구현 완료.
> - 시간 확장 A* 알고리즘(`TimeAStarPlanner`), 예약 테이블(`ReservationTable`) 및 틱 타이머 루틴(0.45s 틱)을 `scratch/run_full_simulation_robot.py`에 물리 시뮬레이터 동작으로서 완벽히 리팩토링 및 이식 완료했습니다.
> - 관제탑의 `ManageWorkstation` 액션 서버 이송 태스크와 연동하여 무충돌 주행 테스트를 최종 완료했습니다.

---

## 🔌 13. 2대 노트북 분산 환경 및 썬더볼트 C-to-C 다이렉트 고속 네트워킹 가이드 (Distributed Multi-Machine Setup) - [검증 및 완료]

> [!NOTE]
> **검증 및 적용 완료**: 2026년 6월 7일 완료.
> - 두 고성능 노트북 간 40Gbps C-to-C 케이블 직결 후 `Intel Ethernet` 가상 네트워크 인터페이스 활성화 및 수동 고정 IP(`192.168.100.10` / `20`) 설정을 성공적으로 마쳤습니다.
> - 양방향 `ping` 테스트 결과 0.5ms 미만의 실시간 통신 지연 속도를 확보하여 분산 가동을 위한 준비를 완수했습니다.

하드웨어 오버헤드가 큰 3D 물리 시뮬레이터(Isaac Sim)와 실시간 스케줄러/데이터베이스 서버를 분리하여 하드웨어 성능을 최대로 활용하기 위한 분산 네트워킹 가이드입니다.

### 13.1 하드웨어 물리 배정 및 케이블 스펙
* **노트북 A (시뮬레이션 머신)**: NVIDIA Isaac Sim, 로봇 주행(A*) 제어 노드 구동.
* **노트북 B (관제 및 DB 머신)**: 관제탑 노드(Control Tower), PostgreSQL, Redis, FastAPI 대시보드 서버 구동.
* **연결 케이블**: **Thunderbolt 4 / USB4 40Gbps (240W EPR 지원) C to C 케이블**을 양측 노트북의 썬더볼트(번개 마크 ⚡) 포트에 직결합니다. 
  *(이 규격은 일반 랜선보다 약 10배 이상 빠르고 10Gbps~20Gbps의 대역폭과 0ms에 가까운 지연 시간을 보장합니다.)*

### 13.2 네트워크 환경 설정 (고정 IP 구성)
공유기(DHCP) 없이 1대1로 연결되므로 유선 가상 어댑터에 수동으로 고정 IP를 지정해야 합니다.

1. **물리 장치 승인 (우분투)**:
   * 각 노트북의 **설정 ➡️ 썬더볼트(Thunderbolt)** 메뉴에서 연결된 상대 노트북 장치를 **Authorize(승인)** 또는 **Trust(신뢰)** 등록합니다.
2. **노트북 A (시뮬레이터) 가상 IP 세팅**:
   * IPv4 설정: **Manual (수동)**
   * IP Address: `192.168.100.10`
   * Subnet Mask: `255.255.255.0`
3. **노트북 B (관제 및 DB) 가상 IP 세팅**:
   * IPv4 설정: **Manual (수동)**
   * IP Address: `192.168.100.20`
   * Subnet Mask: `255.255.255.0`
4. **연결 및 방화벽 확인**:
   * 노트북 A에서 `ping 192.168.100.20` 실행 시 지연 시간 0.5ms 미만으로 응답이 와야 합니다.
   * 통신 차단 발생 시 양쪽 노트북에서 방화벽 해제: `sudo ufw disable`

### 13.3 ROS 2 멀티머신 환경변수 동기화
DDS 프로토콜이 유선 연결 네트워크망을 타게 만들기 위해 두 컴퓨터의 `~/.bashrc`에 아래 환경변수를 등록합니다.
```bash
# 양쪽 노트북 동일한 ID 지정 (예: 30)
export ROS_DOMAIN_ID=30
# 외부 멀티머신 통신 허용 (반드시 0으로 지정)
export ROS_LOCALHOST_ONLY=0
# 기본 DDS 대신 성능이 우수한 Cyclone DDS로 통신 미들웨어 변경
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

### 13.4 원격 데이터베이스 연결 구성 (노트북 B ➡️ A 개방)
노트북 B에서 실행되는 DB 컨테이너/인스턴스가 외부 접속을 허용하도록 설정합니다.
* **PostgreSQL (`/etc/postgresql/.../main/postgresql.conf` 및 `pg_hba.conf`)**:
  * `listen_addresses = '*'` 설정
  * `pg_hba.conf` 파일 하단에 `host warehouse_db rokey 192.168.100.0/24 md5` 추가
* **Redis (`/etc/redis/redis.conf`)**:
  * `bind 0.0.0.0` 및 `protected-mode no` 설정
* **노트북 A의 로봇 에뮬레이터 코드 수정**:
  * DB 및 Redis 접속 IP 주소를 `localhost`에서 노트북 B의 썬더볼트 IP인 `192.168.100.20`으로 수정하여 접속합니다.

### 13.5 NVIDIA Isaac Sim 3D 시뮬레이터 연동 및 실시간 3D 뷰 가이드
실제 NVIDIA Isaac Sim 3D 물리 환경 상에서 5대의 AMR 로봇 및 10대의 작업대(Rack)의 물리적 움직임을 실시간으로 렌더링하고 시각화할 수 있는 통합 커넥터 시스템이 구축되었습니다.

* **통합 연동 스크립트**: [scratch/isaac_amr_connector.py](file:///home/rokey/cobot3_ws/scratch/isaac_amr_connector.py) (AMR + 작업대 동시 동기화, PostgreSQL & Redis 사용)
* **AMR 전용 연동 스크립트**: [scratch/isaac_only_amr_connector.py](file:///home/rokey/cobot3_ws/scratch/isaac_only_amr_connector.py) (AMR 단독 동기화, Redis만 사용)
* **사용 맵 파일**: `src/cobot3/resource/floor_with_con,storage.usd`
  * 바닥 QR 격자(1,813개), 입고 컨베이어(`IN_conveyor`), 출고 컨베이어(`OUT_conveyor`), 메인 스토리지(`MAIN_storage`), 출고 스토리지(`OUT_storage`), 작업대 선반(`custom_rack`) 등이 **이미 사전 세팅**되어 있는 완성된 3D 창고 맵입니다.
* **작동 메커니즘**:
  1. `isaacsim.SimulationApp`을 3D GUI 모드로 가동하여 위 맵 스테이지를 로드합니다.
  2. (통합형만 해당) PostgreSQL `floor_qr_map` 테이블에서 위치 좌표 정보를 로드하여 물리적 좌표 체계를 동적으로 구성합니다.
  3. 기존 맵 위에 5대의 AMR 모델(Cyan색 실린더, `/World/AMRs/`)을 동적으로 추가 생성합니다. (통합형의 경우 10대의 이동식 작업대 모델인 Orange색 큐브도 생성)
  4. 매 프레임(30Hz)마다 Redis에서 각 AMR의 실시간 `(x, y)` 좌표를 읽어 3D 공간에서 텔레포트 이동시킵니다. (AMR 전용 연동의 경우 QR ID 문자열 파싱 방식을 채택하여 DB 쿼리 오버헤드가 전혀 없으며, 통합형의 경우 추가로 PostgreSQL에서 작업대 위치도 함께 동기화)
  5. 10초마다 동기화 상태 요약을 콘솔에 출력합니다.

* **실행 방법** (`isaac-python` alias 사용):
  * **통합 연동 실행 (AMR + 작업대)**:
    ```bash
    isaac-python scratch/isaac_amr_connector.py
    ```
  * **AMR 전용 연동 실행 (가벼운 Redis 단독 구독)**:
    ```bash
    isaac-python scratch/isaac_only_amr_connector.py
    ```

---

## 🖥️ 14. Isaac Sim 네이티브 ROS2 / 소켓 하이브리드 연동 및 2대 분산 가동 가이드 - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 8일 설계 완료. 
> - 기존 Python API를 활용한 강제 3D 텔레포트 방식의 한계를 보완하고, Isaac Sim 내에 이미 준비된 3D 월드 및 로봇 물리 모델을 안전하게 제어하기 위해 ROS2 Action 및 TCP 소켓 하이브리드 브릿지 통신 모델을 수립하였습니다.
> - 고성능 시뮬레이션 환경 유지를 위해 2대의 PC로 분산 처리하여 가동할 수 있는 네트워크 인프라 가이드를 함께 완성하였습니다.

### 14.1 시스템 구성 및 아키텍처 개요
Isaac Sim의 풍부한 물리 모델을 완전히 사용하면서 제어 오버헤드를 줄이기 위해 **제어 채널(DDS Action)**과 **토픽 피드백 채널(TCP Socket)**을 하이브리드 형태로 구성합니다.

```
[PC B (관제 및 DB)]                                  [PC A (시뮬레이터)]
┌────────────────────────┐                          ┌────────────────────────┐
│  • Control Tower Node  │ ◄─── (ROS2 Action) ────► │  • AMR Control Node    │
│  • PostgreSQL & Redis  │                          │  • Socket-ROS2 Bridge  │
│  • FastAPI Dashboard   │                          └───────────┬────────────┘
└────────────────────────┘                                      │ (TCP Socket)
                                                                ▼
                                                    ┌────────────────────────┐
                                                    │  • Isaac Sim Physics   │
                                                    │  • Robot 3D Model      │
                                                    └────────────────────────┘
```

* **제어 평면 (Control Plane - ROS2 Action)**:
  * 관제탑 노드(PC B)와 AMR 제어 노드(PC A)는 네이티브 ROS2 환경을 공유합니다.
  * 관제탑이 `ManageWorkstation` 또는 `MovePackage` 액션 골(Goal)을 던지면, PC A의 AMR 제어 노드가 이를 수신해 경로를 생성하고 주행을 수행합니다.
* **상태/피드백 평면 (Data Plane - TCP Socket)**:
  * 실시간 위치(`/odom`, `/tf`) 및 속도 명령(`/cmd_vel`) 같은 주기가 짧은 토픽들은 ROS Bridge의 DDS 오버헤드를 방지하기 위해 가벼운 **TCP 소켓 서버/클라이언트(JSON 포맷)**로 중계합니다.
  * PC A에 떠 있는 `socket_ros2_bridge` 노드가 이 TCP 패킷을 ROS2 표준 토픽으로 번역해 AMR 제어 노드에 전달합니다.

### 14.2 분산 환경(2대 PC) 구성 가이드
시뮬레이터와 관제탑을 네트워크로 엮어 2대의 PC에서 안정적으로 구동하는 세부 지침입니다.

#### ① 물리 네트워크 및 ROS2 DDS 설정
* **네트워크**: 두 PC를 동일 기가비트 공유기에 연결하거나 Thunderbolt C-to-C 케이블로 직접 연결합니다.
  * PC A (시뮬레이터) IP: `192.168.100.10`
  * PC B (관제/DB) IP: `192.168.100.20`
* **DDS 멀티머신 설정** (양쪽 PC 모두 `~/.bashrc`에 적용):
  ```bash
  export ROS_DOMAIN_ID=119
  export ROS_LOCALHOST_ONLY=0  # 외부 기기와의 통신을 위해 반드시 0으로 설정
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp  # Cyclone DDS 활성화
  ```

#### ② PC A의 연결 코드 수정 (DB 호스트 변경)
PC A의 AMR 제어 노드가 PC B의 데이터베이스와 Redis에 접근할 수 있도록 연결 설정의 호스트를 PC B의 IP 주소로 수정합니다.
* **PostgreSQL 연결**: `host="192.168.100.20"` (PC B의 IP)
* **Redis 연결**: `host="192.168.100.20"`, `port=6379`

#### ③ PC B의 DB 외부 접근 개방
* **PostgreSQL (`postgresql.conf`, `pg_hba.conf`)**: `listen_addresses = '*'`로 설정하고 PC A IP 대역의 md5 접속을 허용합니다.
* **Redis (`redis.conf`)**: `bind 0.0.0.0`으로 호스트 포트를 외부로 개방합니다.

### 14.3 구동 및 실행 프로세스
순서에 맞춰 각 터미널에서 서비스를 차례대로 구동합니다.

#### 1단계: PC B (관제 및 DB 머신) 구동
1. **DB 가동**:
   ```bash
   cd ~/cobot3_ws/docker && sudo docker compose up -d
   ```
2. **FastAPI 대시보드 실행**:
   ```bash
   python3 scratch/dashboard_server.py
   ```
3. **관제탑 노드(Control Tower) 실행**:
   ```bash
   source install/setup.bash && ros2 run cobot3 control_tower
   ```

#### 2단계: PC A (시뮬레이터 머신) 구동
1. **Isaac Sim 구동**: 로봇 모델이 탑재된 USD 스테이지를 로드하고 내부 소켓 스크립트를 활성화한 뒤 Play 버튼을 클릭합니다.
2. **소켓-ROS2 브릿지 노드 실행**:
   ```bash
   source install/setup.bash && ros2 run cobot3 socket_ros2_bridge
   ```
3. **AMR 제어 노드 실행**:
   ```bash
   source install/setup.bash && ros2 run cobot3 amr_controller_node
   ```

---

## 🛠️ 15. 분산 네트워킹 및 실 운영 관제 안전 고도화 (Distributed Operation & Safety Control) - [진행 중]

시뮬레이터와 관제탑을 PC 2대로 분산하여 기동하는 실운영 환경에서, 네트워크 안정성과 물리적 설비 간 정합성을 완벽하게 보장하기 위해 즉각 적용할 수 있는 설계 및 개선 방안들입니다.

### 15.1 DB 및 Redis 접속 주소의 동적 파라미터화 (Configuration Dynamic Parametrization) - [완료]
> [!NOTE]
> **적용 완료**: 2026년 6월 9일 구현 완료.
> - `control_tower_node.py`의 PostgreSQL 및 Redis 접속 정보를 `os.environ.get()` 기반 환경변수 주입으로 변경.
> - 지원 환경변수: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `REDIS_HOST`, `REDIS_PORT`
> - 기본값은 `localhost`로 유지하여 기존 로컬 실행 환경과의 호환성을 보장합니다.

* **내용**: 기존에 `'localhost'`로 하드코딩되어 있던 PostgreSQL 및 Redis 접속 호스트 정보를 환경변수(`os.environ.get`) 기반 외부 주입식으로 변경하였습니다.
* **구현 방법**:
  * 환경변수를 통한 주입으로, Docker Compose 및 분산 운용 시 소스코드 수정과 재빌드 없이 기동할 수 있도록 유지보수성을 극대화합니다.
  * 향후 필요 시 ROS 2 파라미터(`declare_parameter` 및 `get_parameter`) 방식으로 Launch 파일에서도 주입 가능하도록 확장 검토.

### 15.2 노이즈성 QR코드 오인식 예외 처리 및 유효성 검증 필터 (QR Decoding Sanity Check)
* **내용**: 비전 카메라의 난반사나 오인식으로 잘못 해독된 노이즈 문자열이 DB에 유령 패키지로 신규 등록되는 문제를 방지합니다.
* **개선 방향**:
  * `GetPackageRoute` 서비스 콜백에 정규 표현식 검증 필터를 도입하여, 지정된 규격 패턴(예: `PKG_RAND_` 또는 `PKG_QR_`)을 만족하는 정상 QR 데이터만 DB 등록 프로세스를 거치도록 보안 코딩을 적용합니다.

### 15.3 Cyclone DDS 다중 네트워크 인터페이스 카드(NIC) 전용 바인딩 (DDS Interface Lock-in)
* **내용**: 두 대의 PC를 썬더볼트 고속 C-to-C 통신망과 일반 WiFi 공유기망에 동시에 연결해 구동할 때 통신이 꼬이는 현상을 예방합니다.
* **개선 방향**:
  * Cyclone DDS 전용 설정 파일(`cyclonedds.xml`)을 구성하여, DDS 브로드캐스트 패킷이 WiFi 인터페이스 대신 오직 썬더볼트의 가상 이더넷 카드 주소 대역(`192.168.100.X`)만 전용 점유하도록 NIC 바인딩을 강제합니다.

### 15.4 일자 영업 완료(Day Transition) 단계 시 컨베이어 벨트 안전 인터록(Interlock) 연동
* **내용**: 당일 물량이 전체 포장 완료되어 시스템이 `PENDING_TRANSITION` 상태로 전환될 때, 물리 설비를 안전하게 연동 보호합니다.
* **개선 방향**:
  * 대기 모드 진입 즉시 관제탑 노드가 입고 로봇(`bg2`) 및 컨베이어 모터 제어 노드에 즉각 정지 명령(Service/Topic)을 전달하여, 잔여 공급 상자들의 낙하 및 물리적 충돌 위험을 방지하는 안전 인터록을 소프트웨어적으로 연동합니다.

---

## 16. 20m × 20m 신규 맵 개편, 장애물 우회(A*) 및 분산 연동 안정화

### 16.1 격자 생성 및 데이터베이스 연동 규격 개편
* **배경**: 맵 중심이 `(3.0, 0.0)`, 가로(X) `13.5m`, 세로(Y) `20.0m` 크기의 개편된 월드 물리 좌표계 도입에 따라 격자 맵 및 회피 라우팅을 구축했습니다.
* **좌표 대역**: X는 `[-3.0, 9.0]` (9개), Y는 `[-9.0, 9.0]` (13개) (총 117개 활성 격자점)
* **논리 스팟 매핑 세부 규격**:
  * **주차 구역 (spot_01 ~ spot_10)**: X는 `1.5` / `0.0`, Y는 `-9.0` ~ `3.0` 구간에 1.5m 간격으로 10개 배치.
  * **출고 대기 창고 (stage_01 ~ stage_04)**: X는 `4.5` / `7.5`, Y는 `9.0` / `7.5` 에 4개 배치 (st05, st06 제거 완료).
  * **포장 작업대 (sg2_out_00_A/B)**: `(0.0, 9.0)` 및 `(0.0, 7.5)`에 배치.
  * **입고라인 (오늘 / 내일 / 모레)**:
    * 오늘(Line 1): `(7.5, 1.5)` (Active), `(6.0, 1.5)` (Standby)
    * 내일(Line 2): `(7.5, -3.0)` (Active), `(6.0, -3.0)` (Standby)
    * 모레(Line 3): `(7.5, -7.5)` (Active), `(6.0, -7.5)` (Standby)
    * (A/B구역 2칸을 하나의 직사각형 작업대로 합치고 중심에 이름을 기재하도록 시인성 개선)
  * **AMR 충전기 (charging_01 ~ charging_05)**: X는 `-3.0` 고정, Y는 `-9.0` ~ `-3.0` 구간에 1.5m 간격 배치.
* **정적 장애물 (STATIC_OBSTACLE) 구역 설정**:
  * **SG2 로봇 구역**: SG2_OUT `(-1.5, 7.5)`, `(-3.0, 7.5)`, `(-1.5, 9.0)`, `(-3.0, 9.0)` 및 입고라인 로봇 구역 `(6.0/7.5, 3.0)`, `(6.0/7.5, -1.5)`, `(6.0/7.5, -6.0)` 차단.
  * **컨베이어벨트 구역**: X = `9.0` 라인 전체 (Y: `-9.0` ~ `9.0`) 차단.
* **자동화 스크립트 구축 및 A* 회피**:
  * `scratch/update_20x20_grid_assets.py` 스크립트를 사용하여 117개 유효 활성 노드 및 장애물을 DB(`floor_qr_map`)에 TRUNCATE 및 Bulk Insert로 자동 적재했습니다.
  * `run_full_simulation_robot.py` (AMR A* 경로 플래너)가 `floor_qr_map`에서 `location_type = 'STATIC_OBSTACLE'` 인 좌표를 동적 쿼리하여 경로 탐색 시 원천 차단하고 정밀 우회하도록 플래닝 모듈을 보강 완료했습니다.

### 16.2 분산 환경 실연동 안정화
* **Action Client wait_for_server 타임아웃 상향**:
  * 관제탑 노드(`control_tower_node.py`)에서 AMR PC와의 실제 ROS2 무선 연동 시 발생하는 디스커버리 지연을 극복하기 위해 `wait_for_server` 타임아웃을 기존 `1.0초`에서 `5.0초`로 연장했습니다.
* **start_test_env.sh 구동 유연성 확보**:
  * 로컬 및 분산 연동 여부를 환경변수 `ROS_LOCALHOST_ONLY` (0: 외부 통신 허용, 1: 로컬) 주입을 통해 다이내믹하게 결정할 수 있도록 환경 구축 스크립트를 개선했습니다.

### 16.3 분산 연동 디버깅 및 실시간 관제 장애 해결 - [완료]
* **관제탑 노드 자원 종료 교착 해결**:
  * 관제탑 노드가 `SIGINT`(Ctrl+C) 종료 시점에 백그라운드 스케줄러 타이머들이 비동기로 PostgreSQL DB 세션을 잡고 있어 커넥션 풀 강제 종료 시 `cannot use Destroyable` 에러가 나던 현상을 해결했습니다.
  * 종료 시퀀스를 **타이머 취소 ➡️ Executor 스레드 대기 종료(Join) ➡️ Node 소멸 및 DB 커넥션 풀 폐쇄** 순서로 전면 동기화하였습니다.
* **경량 Mock 기기/로봇 에뮬레이터 개발 (`scratch/mock_sg2_devices.py`)**:
  * 3D 물리 공간이나 A* 시뮬레이터 없이도 입고/이송/포장/회전 액션 및 서비스에 100% 모의 핑퐁 응답을 하며 DB와 Redis 데이터를 실시간 업데이트하는 독립 테스트 스크립트를 생성하여 개발 생산성을 개선했습니다.
* **Redis 외부 개방 및 2D 맵 AMR 마커 유실 해결**:
  * Docker 기반 Redis 컨테이너의 보안 제한(`protected-mode`)을 해제하기 위해 [docker-compose.yml](file:///home/rokey/cobot3_ws/docker/docker-compose.yml#L28)의 redis 서비스 구동 command에 `--protected-mode no` 인자를 추가하여 외부 AMR PC의 상태 데이터 push가 가능하도록 조치했습니다.
  * AMR PC가 송신하는 소수점 아래 세 자리 좌표 문자열(예: `FLOOR_X_-3.000_Y_-9.000`)과 대시보드 2D 맵의 격자 매핑용 키(예: `FLOOR_X_-3.0_Y_-9.0`) 불일치로 마커가 렌더링되지 않던 버그를 [dashboard_server.py](file:///home/rokey/cobot3_ws/scratch/dashboard_server.py#L74)에 `normalize_qr_id` 문자열 규격화 함수를 추가 적용하여 해결했습니다.


---

## 🔍 17. 코드 리뷰 및 Isaac Sim 연동 성능 병목 진단 (2026-06-09)

코드 리뷰, 문서 교차 검증, 성능 분석, Isaac Sim 연동 디버깅을 통해 발견된 이슈와 조치 결과를 기록합니다.

### 17.1 코드 버그 수정 (4건 완료, 1건 미수정)

> [!NOTE]
> **적용 완료**: 2026년 6월 9일 커밋 `ad942a4`
> - `init.sql`에 `floor_qr_map` 시드 데이터 약 117개 노드 INSERT 추가 (논리 스팟 27개 + 주행 경로 격자 약 90개)
> - `control_tower_node.py`에 `threading.Lock(trigger_lock)` 도입하여 `pre_fetch_triggered`/`rotation_triggered` 세트 Race Condition 해결
> - Redis 배터리 `float()` 파싱에 개별 AMR 단위 `try-except` 가드 적용
> - PostgreSQL/Redis 접속 호스트를 `os.environ.get()` 기반 환경변수 7개로 동적 파라미터화 (`POSTGRES_HOST`, `REDIS_HOST` 등)

* **`floor_qr_map` 시드 데이터 누락 [Critical → 해결]**: `init.sql`에 `CREATE TABLE`만 있고 `INSERT`가 없어 `trigger_workstation_move` 함수가 좌표를 전부 `(0.0, 0.0, 0.0)`으로 전송하던 문제. Docker 최초 기동 시 자동 적재되도록 수정.
* **멀티스레드 Race Condition [Medium → 해결]**: `MultiThreadedExecutor` 환경에서 `pre_fetch_triggered`/`rotation_triggered` 세트에 Lock 없이 접근하던 문제. `threading.Lock` 도입 및 `set.remove()` → `set.discard()` 변경으로 `KeyError` 방지.
* **Redis `float()` 변환 예외 [Medium → 해결]**: `float(val.get("battery", 100.0))`에 빈 문자열 입력 시 한 AMR 오류로 전체 AMR 상태 로딩이 실패하던 문제. 개별 AMR 단위 안전 파싱으로 개선.
* **`localhost` 하드코딩 [Conditional → 해결]**: PostgreSQL/Redis 접속 정보를 환경변수 주입 방식으로 변경. 기본값 `localhost` 유지로 기존 로컬 환경 호환성 보장.
* **`AMR_01` 하드코딩 [Conditional → 미수정]**: 8곳에서 `assigned_amr='AMR_01'` 또는 `reserved_by = 'AMR_01'`이 하드코딩됨. Fleet Management 알고리즘(가용 AMR 선택, 큐 기반 할당) 설계가 필요하여 단순 패치로 해결 불가. 향후 11장 Fleet 최적화와 연계하여 구현 예정.

### 17.2 마크다운 문서 동기화 (5건 완료, 1건 미수정)

* **`PHYSICAL_LAYOUT.md`**: `floor_qr_map`이 "정확히 적재되어 있다"는 허위 기술을 init.sql 시드 데이터 추가 후 사실에 맞게 갱신.
* **`README.md`**: init.sql 적재 범위에 `floor_qr_map` 약 117개 노드 설명 추가, Docker 환경변수 사용법(`POSTGRES_HOST`, `REDIS_HOST`) 추가.
* **`SYSTEM_IMPROVEMENT_PLAN.md` 9장**: init.sql 자동 적재 범위를 "시드 데이터(INSERT) 약 117개 노드 추가 완료. Docker 최초 기동 시 자동 적재"로 명확화.
* **`SYSTEM_IMPROVEMENT_PLAN.md` 11.4**: 출고 대기 스팟 개수 "6개" → "4개"로 수정 (코드 기준 `stage_01` ~ `stage_04`).
* **Look-ahead 트리거 시점 [미수정]**: 문서에는 "7번째 슬롯"이라 했지만 코드는 3번째 슬롯에서 발동. 코드를 7번째로 변경할지, 문서를 3번째로 변경할지 **정책 결정 필요**.

### 17.3 성능 병목 진단 결과

외부에서 지적된 4가지 성능 이슈를 코드 대조 검증한 결과:

| 지적 항목 | 실제 확인 결과 | 심각도 |
| :--- | :--- | :--- |
| **1초 DB Polling** | `publish_fleet_states_callback()`이 매초 PostgreSQL SELECT 2회 + Redis 조회 실행. 현재 규모(10 WS, 150 PKG)에서는 문제없으나 패키지 1000개+ 시 주의 | 🟡 중간 |
| **WebSocket 0.5초 브로드캐스팅** | **이미 1.5초로 완화 완료** (`dashboard_server.py:172`). `grid_cells` 캐싱도 적용됨 | 🟢 완화됨 |
| **Python GIL 병목** | `psycopg2`/`redis-py` C 확장이 I/O 대기 중 GIL 자동 해제. 5대 AMR 규모에서 무시 가능 | 🟢 미미 |
| **Docker Bridge NAT** | ROS2 노드는 Docker 밖에서 실행, Docker 안에는 PostgreSQL/Redis만 존재. DDS 트래픽은 Bridge 미경유 | 🟢 해당없음 |

### 17.4 `/fleet/*` 토픽 불필요 발행 문제 - [진행 중]

* **현상**: 관제탑이 4개 토픽(`/fleet/amr_states`, `/fleet/workstation_states`, `/fleet/package_states`, `/fleet/task_events`)을 1Hz로 발행하지만, **현재 구독자가 단 하나도 없음**.
  * 대시보드(`dashboard_server.py`)는 ROS2 토픽이 아닌 **PostgreSQL/Redis를 직접 조회**하여 데이터를 가져옴.
  * AMR 제어 코드(`fleet_manager_bridge_node.py`)는 `/fleet/*` 토픽을 구독하지 않고 **Action Server** 방식으로만 동작.
* **낭비 리소스**: 아무도 받지 않는 토픽을 위해 매초 PostgreSQL SELECT 2회 + `json.dumps()` 3회 + DDS 멀티캐스트 4패킷 발생.
* **개선 방향**:
  * **조건부 발행**: `self.amr_states_pub.get_subscription_count() > 0`일 때만 DB 조회 및 발행하여 평소에는 자원 절약, `ros2 topic echo` 디버깅 시에만 자동 활성화.
  * **패키지 상태 요약화**: `/fleet/package_states`에 전체 패키지 목록 대신 요약 통계(`{"total": 150, "waiting": 30, "completed": 120}`)만 발행하여 DDS 페이로드 축소.

### 17.5 Isaac Sim 연동 시 프레임 드롭 원인 분석 및 Dispatch Throttle 설계 - [진행 중]

> [!IMPORTANT]
> **핵심 원인**: 관제탑 스케줄러가 AMR 5대 운용 한도를 고려하지 않고 여러 작업대 이송을 연쇄 발행하는 구조.
> 문제는 "동일 WS 중복 발행"이 아니라 **"서로 다른 WS 작업이 매초 여러 개 연쇄 발행"**되는 것.

#### 문제 진단

* **동일 WS 중복 발행**: `trigger_workstation_move()` 내부에서 `MOVING_TO_*`, `PROCESSING`, `reserved_by` 상태로 차단되므로 **완전 중복은 발생하기 어려움** ✅
* **실제 문제**: 초기 상태에서 인바운드 라인 A/B, 포장존, staging, warehouse 조건이 동시에 만족하면, `check_completed_workstations()`와 `dispatch_workstations_keepalive()`가 서로 다른 작업대들에 대해 **빠르게 5~6개 이송 명령을 연쇄 발행** ⚠️
* **Bridge 구조**: `fleet_manager_bridge_node.py`는 `/manage_workstation` Action Goal이 들어올 때마다 **제한 없이** `bridge_queue/commands/CMD_xxx.json`을 즉시 생성 (backpressure 없음)
* **결과**: `bridge_queue/commands`에 CMD가 짧은 시간에 누적 → Isaac controller의 polling/planner/status/file I/O 부하 증가 → 물리 시뮬레이션 프레임 드롭

#### 문제 코드 책임 범위

| 우선순위 | 코드 | 파일 | 문제 |
| :--- | :--- | :--- | :--- |
| **1순위** | Control Tower 스케줄러 | `control_tower_node.py` | `check_completed_workstations()`, `dispatch_workstations_keepalive()`, `trigger_workstation_move()` 호출 전역 제어(dispatch gate) 부재 |
| **2순위** | Fleet Manager Bridge | `fleet_manager_bridge_node.py` | 들어온 ManageWorkstation Goal을 제한 없이 CMD 파일로 생성, in-flight command 상한/backpressure 없음 |
| **낮음** | Isaac Sim AMR Controller | `amr_controller.py` | 수동 CMD 1개에서는 정상. 다수 CMD 누적 시 처리량 부담을 받는 쪽이지, 원인 발생 지점은 아님 |
| **해당없음** | DDS 트래픽 | — | 관제탑이 `/tf`, `/camera`, `/pointcloud` 등 고대역폭 토픽을 발행하지 않음. `/fleet/*` 1Hz JSON 토픽도 주 원인 아님 |

#### 운영 목표 정책

```
MAX_ACTIVE_WORKSTATION_MOVES = 5  (AMR 최대 5대 동시 운용)
```

* 동일 WS 중복 방지: **유지**
* 서로 다른 WS 연쇄 발행: **허용하되 최대 5개까지만**
* `bridge_queue` CMD 폭주: **방지** (active/in-flight CMD ≤ 5)
* AMR 5대 병렬성: **유지**

#### Dispatch Gate 설계 (1순위: Control Tower)

`trigger_workstation_move()` 호출 전 아래 조건을 반드시 확인:
1. 현재 active workstation move 개수 < `MAX_ACTIVE_WORKSTATION_MOVES`
2. 사용 가능한 AMR 개수 > 0
3. 해당 workstation이 이미 `MOVING`/`PROCESSING`/`reserved` 상태가 아님
4. `target_location`이 이미 다른 작업에 의해 예약되지 않음
5. 동일 AMR에 이미 active task가 없음
6. 이번 scheduler tick에서 새로 dispatch한 개수까지 포함해 5개를 넘지 않음

```python
# 제안 구현 구조 (의사 코드)
MAX_ACTIVE_WORKSTATION_MOVES = 5

def can_dispatch_new_move(self):
    active_count = self.get_active_workstation_move_count()  # DB에서 MOVING_TO_* / PROCESSING 상태 카운트
    available_amr = self.get_available_amr_count()            # Redis에서 available AMR 카운트
    if active_count >= MAX_ACTIVE_WORKSTATION_MOVES:
        return False
    if available_amr <= 0:
        return False
    return True

# 한 scheduler tick 안에서 local counter도 사용
dispatched_this_tick = 0
for candidate in candidates:
    if active_count + dispatched_this_tick >= MAX_ACTIVE_WORKSTATION_MOVES:
        break
    if self.trigger_workstation_move(...):
        dispatched_this_tick += 1
```

#### Bridge Backpressure 설계 (2순위: Fleet Manager Bridge)

* `fleet_manager_bridge_node.py`에서 `commands` + `status` 기준 in-flight CMD가 5개 이상이면 새 Goal을 WAITING/REJECT/BUSY 처리
* 주 수정 지점은 Control Tower이므로 Bridge는 2차 방어선으로 구현

### 17.6 Isaac Sim 물리 제어 충돌 및 USD 리소스 병목 정밀 분석 - [진행 중]

> [!IMPORTANT]
> **핵심 원인**: Isaac Sim 가상 환경에서 랙이 유발되거나 작업대 이송 시 충돌/튀는 현상의 주원인은, 고정 배경 설비 구조물인 `custom_rack`을 강제로 들어올리려고 시도하면서 물리 연산(PhysX) 및 Stage 계층 구조가 꼬였기 때문입니다. 또한 DB 상태가 실제 물리적 이동이 끝나기 전에 목적지로 선행 변경되는 구조도 위치 불일치를 초래합니다.

#### 1. 핵심 문제점 7가지 세부 분석

1. **custom_rack의 본래 용도 혼선**: 
   * **원인**: 맵에 이미 존재하는 `custom_rack`들은 이동식 작업대가 아닌 고정형 스토리지 배경용 프림(Prim)으로 설계되었습니다.
   * **영향**: 고정 랙을 AMR이 억지로 움직이려고 PhysX 물리 연산을 처리하면 시뮬레이터 렉의 1순위 원인이 됩니다. 본래 설계는 `/World/Workstations/WS01~WS10`에 정의된 10대의 독립적인 이동식 작업대를 생성해 움직이는 것이 정상입니다.

2. **Stage 계층 구조의 종속성 (Parent Offset 및 Collision)**:
   * **원인**: `custom_rack`은 독립적인 최상위 Transform 프림이 아니라, `/World/IN_conveyor/IN_storage/custom_rack`, `/World/MAIN_storage/MAIN_storage/custom_rack` 등 하위 구조물(Child)로 귀속되어 있습니다.
   * **영향**: 부모-자식 관계의 로컬 오프셋과 고정 설비 간의 Collision이 얽히고설키며, AMR이 리프트(Lift)하는 순간 PhysX가 비이상적인 관성/오버라이드 처리를 강제하여 튐 현상 또는 극심한 지연이 유발됩니다.

3. **이송 전 DB 위치 선행 변경으로 인한 동기화 파탄**:
   * **원인**: 대시보드 및 관제 시스템의 일부 API가 AMR의 실제 물리 이송이 끝나기 전에 `workstations.current_location`을 목적지(Target)로 미리 변경합니다.
   * **영향**: Isaac Sim 연동 커넥터 스크립트가 DB를 보고 3D 씬을 갱신하려 할 때, 작업대가 순간이동(Teleport)하여 실제 AMR 리프트와 root 위치의 불일치가 일어나고 물리 콜라이더가 꼬이면서 렉이나 튐이 발생합니다.

4. **isaac_amr_connector.py와 실제 AMR 컨트롤러의 제어권 충돌**:
   * **원인**: DB의 `workstations.current_location`을 지속적으로 읽어서 작업대 위치를 강제 동기화하는 스크립트(`isaac_amr_connector.py`)와, 실제 주행/리프트를 물리 제어하는 AMR 컨트롤러가 3D 씬 내 동일한 작업대 프림에 동시에 쓰기(Write) 명령을 내립니다.
   * **영향**: 두 시스템이 하나의 프림에 대해 제어권을 경쟁하며 충돌합니다. 물리 제어를 사용할 때는 커넥터 측에서 작업대 강제 이동 기능을 해제하고, 로봇(AMR) 위치만 렌더링하는 전용 스크립트(`isaac_only_amr_connector.py` 등)로 대체해야 합니다.

5. **custom_rack USD의 물리 컴포넌트(Physics/Payload) 무거운 구조**:
   * **원인**: `customrack.usd`, `workstation_2x8.usd` 에셋 내부에는 `PhysicsRigidBodyAPI`, `PhysicsCollisionAPI`, `RigidBody` 등 다양한 물리 속성과 페이로드(Payload)가 적용되어 있을 수 있습니다.
   * **영향**: 랙을 통째로 레퍼런스(Reference)하고 자식 단위로 리프트할 때 PhysX Stage 갱신에 큰 연산 오버헤드를 줍니다. 이동식 작업대는 최상위 root에만 kinematic/rigid body를 할당하고 자식 메쉬는 visual 전용으로 단순화하는 것이 이상적입니다.

6. **QR 코드 메쉬 및 텍스처 과다 배치**:
   * **원인**: 바닥 격자 맵을 구성하기 위해 1,813개(또는 169개)의 개별 QR plane mesh를 생성하고 재질(Material)/텍스처(Texture)를 일일이 바인딩했습니다.
   * **영향**: Isaac Sim의 뷰포트 드로우콜(Draw Call)과 비디오 메모리를 점유하여 시뮬레이터 자체의 기본 FPS를 낮추는 잠재적 부하 요인입니다. 단, 랙을 들 때만 발생하는 순간적인 프레임 드롭의 1순위 원인은 아닙니다.

#### 2. 최종 문제점 정리 및 우선순위

| 우선순위 | 문제점 | 원인 분석 | 해결 방안 |
| :--- | :--- | :--- | :--- |
| **1순위** | `custom_rack` 강제 이송 시 물리 렉 | 고정 스토리지 배경용 Prim을 작업대로 잘못 사용 | `/World/Workstations/WS01~WS10` 전용 이동식 작업대 프림으로 대체 |
| **2순위** | 하위 계층 구조물(Child) 이송 | 부모 구조에 얽힌 local offset 및 collision 꼬임 | 부모-자식 종속성이 없는 독립적인 root 레벨의 이송체 구성 |
| **3순위** | DB 위치 선행 확정 | 실제 이동 완료 전 current_location 변경하여 순간이동 유발 | `MOVING_TO_*` (PROCESSING) 상태를 도입하고 이동 완료 시점(`COMPLETED`)에만 최종 위치 갱신 |
| **4순위** | 커넥터와 AMR 제어권 충돌 | `isaac_amr_connector.py`와 AMR controller가 동일 프림 위치 중복 제어 | 물리 구동 시에는 커넥터의 랙 동기화 기능을 끄고 로봇 위치 렌더링으로 전환 |
| **5순위** | Asset Physics 무거움 | Physics/Collision/Payload 복잡도 연산 부하 | Visual 전용 단순 메쉬 및 최상위 root kinematic 단일 설정 |
| **6순위** | QR 메쉬/텍스처 과다 | 1,813개 QR 생성으로 드로우콜 폭증 | 격자 그리드 간격을 넓히거나, 필요한 구역만 동적 생성하여 기본 FPS 확보 |


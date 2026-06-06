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
* 관제탑이 창고에 주차되어 있던 작업대를 출고하는 이송 액션(`ManageWorkstation.action`)을 AMR에게 전달할 때, 출발지가 단순히 `'warehouse'`로 기록되면 실제 해당 작업대가 물리적으로 점유하고 있던 개별 주차 스팟(`spot_01` ~ `spot_10`)을 식별할 수 없었습니다.
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
> **적용 완료**: 2026년 6월 5일 구현 완료.
> - PostgreSQL 데이터베이스 초기화 스크립트(`docker/init.sql`)에 `floor_qr_map` 테이블 정의 추가.
> - 격자 생성기(`scratch/generate_all_qr_codes.py`) 실행 시 1,813개의 물리 격자 좌표 및 논리 스팟(`spot_XX`, `sg2_in_XX_A/B`, `sg2_out_00_A/B`) 정보를 PostgreSQL DB로 자동 적재 연동 완료.
> - 관제탑(`control_tower_node.py`) 및 모의 로봇 에뮬레이터(`run_full_simulation_robot.py`) 기동 시 하드코딩된 목적지 명칭 대신 `floor_qr_map` 데이터베이스를 실시간으로 쿼리하여 물리 coordinates와 바닥 QR 마커 식별자를 해석(Resolution)하는 구조 구현 및 검증 완료.

### 9.1 배경 및 필요성
* 바닥에 배치된 격자형 QR코드(예: 1,813개의 바닥 QR)는 AMR이 이동 및 로컬라이제이션(Localization)을 수행하는 물리적 기준 역할을 합니다.
* 창고 내 보관 위치(`spot_01` ~ `spot_10`), 인바운드 대기/작업 위치(`sg2_in_01_A`, `sg2_in_01_B`), 아웃바운드 포장 위치(`sg2_out_00_A`, `sg2_out_00_B`) 등의 논리적 위치가 AMR의 물리적 목적지 좌표와 매핑되어야 합니다.
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



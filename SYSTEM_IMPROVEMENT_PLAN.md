# 🚀 쿠팡 물류창고 관제 시스템 개선 및 고도화 계획서 (System Improvement Plan)

> [!IMPORTANT]
> **AI 에이전트 가이드**: 이 문서를 읽는 AI 에이전트는 본 프로젝트에 관해서 분석, 기록 및 작성을 수행해야 합니다.

본 문서는 현재 구축된 쿠팡 물류창고 관제 시스템(Control Tower)의 한계점과 문제점을 분석하고, 이를 극복하기 위한 데이터베이스 구조 정규화, QR코드 시스템 도입, 이중 버퍼(Double Buffer) 물리 레이아웃 설계, Redis 작업 우선순위 지정, 그리고 관제 단일장애점(SPOF) 대응 방안을 구체적으로 정리한 계획서입니다.

---

## 📌 1. 데이터베이스 구조 정규화 (DB Schema Optimization) - [완료]

> [!NOTE]
> **적용 완료**: 2026년 6월 3일 구현 완료. `workstations` 테이블의 중복 슬롯 정보가 `packages` 테이블의 외래키 정보로 통합 정규화되었습니다.

### 1.1 현재 문제점
* `workstations` 테이블에 1~4번 슬롯의 수령인 및 상태 컬럼(`slot_X_customer`, `slot_X_status`)을 컬럼 형태로 직접 정의함.
* `packages` 테이블 역시 `workstation_id`와 `slot_number`를 가지고 있어 **데이터 중복 및 불일치 위험**이 존재함.
* 4칸 외에 슬롯 개수가 변경(예: 3x3 layout)될 경우 DB 스키마 및 쿼리 전체를 수정해야 하므로 확장성이 떨어짐.

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

## 🏷️ 2. QR코드 시스템 도입 및 인식 설계

일회용 택배 박스에 영구 마커인 ArUco ID를 직접 인쇄하여 매칭하는 방식의 비현실성을 극복하기 위해 바코드/QR코드 매핑 방식을 도입합니다.

### 2.1 QR코드 생성 및 적용
* 파이썬의 `qrcode` 라이브러리를 활용해 택배 고유 ID(`package_id`, 예: `PKG_RAND_001`) 정보를 담은 PNG 이미지 코드를 동적 생성합니다.
* **Isaac Sim 시뮬레이션**: 생성된 이미지를 가상 택배 박스 3D 모델의 재질(Material/Texture)로 바인딩하여 렌더링합니다.

### 2.2 비전 기반 QR코드 디코딩
* 로봇/카메라 노드에서 카메라 토픽을 구독하여 OpenCV 또는 `pyzbar` 라이브러리로 이미지를 처리합니다.
* 해독된 문자열(`PKG_RAND_001`)로 PostgreSQL DB를 조회하여 목적지와 수령인 등 제어에 필요한 데이터를 획득합니다.

```python
import cv2
from pyzbar.pyzbar import decode

def decode_qr_from_frame(frame):
    decoded_objects = decode(frame)
    for obj in decoded_objects:
        package_id = obj.data.decode('utf-8')
        return package_id # 예: "PKG_RAND_001"
    return None
```

---

## ⚙️ 3. 이중 버퍼 (Double Buffer) 물리 레이아웃 설계

AMR 이송 속도가 로봇의 적재 속도보다 느려 발생하는 병목 및 적재 로봇 대기 현상을 해결하기 위해 작업대 임시 적재 구역을 이중화합니다.

```
[적재 로봇 (sg2_in_XX)]
         │
 ┌───────┴───────┐
 ▼               ▼
[A 구역: 적재중]  [B 구역: 예비 대기]
(현재 가득 채움)  (AMR이 미리 배달한 빈 작업대)
```

* **동작 루프**:
  1. 적재 로봇이 **A 구역**의 작업대에 상자를 적재합니다.
  2. A 구역의 마지막(4번째) 슬롯이 적재 완료되면, 로봇은 멈춤 없이 즉시 **B 구역**의 예비 작업대에 적재를 개시합니다.
  3. 로봇이 B 구역에 적재하는 동안, 관제탑은 AMR에게 명령하여 A 구역의 완충 작업대를 창고로 이송하고 해당 자리에 새로운 빈 작업대를 채워 넣습니다.
  4. 로봇은 B 구역이 가득 차면 다시 A 구역으로 대상을 전환하며 이를 반복합니다.

---

## 📊 4. Redis Sorted Set 기반 우선순위(Priority) 큐 도입

단순 선입선출(FIFO) 큐 구조의 한계를 개선하여 물류 정체를 유발하는 긴급 연산에 우선순위를 부여합니다.

### 4.1 작업 우선순위 등급 정의
1. **P1 (우선순위 점수: 100)**: 적재 완료된 작업대 배출 (`sg2_in_XX` -> `warehouse` / `sg2_out_00`)
2. **P2 (우선순위 점수: 80)**: 포장 대기용 완충 작업대 공급 (`warehouse` -> `sg2_out_00`)
3. **P3 (우선순위 점수: 50)**: 이중 버퍼 대기 구역 내 빈 작업대 보충 (`warehouse` -> Standby Spot)
4. **P4 (우선순위 점수: 20)**: 완전히 비어 있는 작업대 회수 및 재배치 (`sg2_out_00` -> Recovery Spot)

### 4.2 Redis ZSET 명령어 적용
* **태스크 등록**: `ZADD queue:amr_priority_tasks [Score] [Task_JSON]`
* **태스크 팝(Pop)**: 스케줄러 노드에서 가장 높은 점수(우선순위가 가장 높은 작업)부터 가져와 분배합니다.
  ```bash
  # 가장 우선순위가 높은 태스크 하나를 가져오고 삭제 (Redis 5.0 이상 지원)
  ZPOPMIN queue:amr_priority_tasks
  # (점수가 낮은 것부터 정렬되므로 우선순위 점수를 음수나 내림차순 정렬하여 팝하는 로직 설계 필요)
  ```

---

## 🛡️ 5. 관제 단일장애점 (SPOF) 대응 및 Fail-safe 설계

관제 센터 서버 다운 시 전체 라인이 정지하는 문제를 완화하기 위해 로컬 제어와 예외 처리 루틴을 적용합니다.

* **타임아웃(Timeout) 및 재시도(Retry)**:
  * 로봇이 관제탑에 서비스 응답을 보낸 후 1초간 무응답 시 타임아웃 처리 후 자동 재시도합니다.
* **로컬 순환 회차로(Recirculation Loop) 활용**:
  * DB 다운 시 컨베이어 벨트를 멈추지 않고, 패키지들을 라인 끝의 예외 수거 박스나 순환용 회차 트랙으로 흘려보내 물리적 걸림을 차단합니다.
* **오프라인 룰베이스(Offline Rule-base) 구동**:
  * 서버 연동 불가 상태가 감지되면 로컬 카메라 노드에 주입되어 있는 기본 규칙(예: ArUco 100번대는 무조건 1번 컨베이어로 분기)에 따라 독자적으로 1차 처리를 수행하도록 대체 제어 로직을 활성화합니다.

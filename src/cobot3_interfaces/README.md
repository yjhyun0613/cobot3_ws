# 📦 `cobot3_interfaces` Package

본 패키지는 쿠팡 물류창고 관제 시스템(Control Tower)과 여러 로봇(AMR, 분류 로봇, 적재 로봇, 포장 로봇) 간의 비동기 제어 명령 및 상태 동기화를 위한 **ROS 2 커스텀 인터페이스(Action, Service)** 명세서를 보관합니다.

최근 JIT(Just-In-Time) 단일 슬롯 환경 전환에 맞추어 기존 B구역 관련 의존성이 제거되었으며, 동적 일시 정지(Pause/Resume)를 위한 표준 메시지 연동 규격이 추가로 정리되어 있습니다.

## 📂 디렉토리 구조 및 인터페이스 규격

### 1. Action 인터페이스 (`/action`)
AMR이나 로봇 팔처럼 수 초에서 수 분이 걸리는 긴 호흡의 트랜잭션을 지시하고 피드백을 받을 때 사용합니다.

*   **`ManageWorkstation.action`**
    *   **역할**: AMR에게 특정 작업대를 목적지(입고 존, 포장 존, 스테이징 등)로 이동시키거나, 작업대의 앞/뒤 방향을 뒤집는 제자리 180도 회전(`ROTATE_WORKSTATION`)을 지시합니다.
    *   **Goal**: `workstation_id`, `target_location`, `target_qr_id` 등
*   **`MovePackage.action`**
    *   **역할**: AMR이 창고 내 보관 구역으로 단일 상자를 직접 이송할 때 사용됩니다.
    *   **Goal**: `package_id`, `destination_zone`
*   **`StartPackaging.action`**
    *   **역할**: 포장 로봇(`sg2_out_00`)에게 작업대의 8칸 패키지 포장 및 출고 바코드 생성을 지시합니다. 단일 슬롯 환경에 맞춰 즉각적인 완료 처리를 수행합니다.
    *   **Goal**: `workstation_id`, `today_date`

### 2. Service 인터페이스 (`/srv`)
데이터베이스 조회, 목적지 분류 판별 등 관제탑(Control Tower)에 즉각적인 데이터 확인을 요청할 때 사용합니다.

*   **`GetPackageRoute.srv`**
    *   **역할**: 컨베이어 분류 로봇(`bg2`)이 바코드를 읽고 오늘/내일/모레 중 어느 출고 라인으로 물건을 보낼지 노선(Route)을 요청합니다.
*   **`CheckWarehouseStatus.srv`**
    *   **역할**: 동일 수령인의 물품이 메인 창고에 존재하는지 파악하여 중복 적재를 방지합니다.
*   **`ReportInboundProgress.srv`**
    *   **역할**: 입고 적재 로봇(`sg2_in_XX`)이 슬롯을 채울 때마다 관제탑 DB에 진행 상황을 갱신합니다. 이 서비스 호출을 기반으로 관제탑은 **8칸 완충 여부를 판단하여 JIT 일시 정지 토픽을 발행**합니다.

## 🛑 3. JIT 교대 제어용 표준 토픽 (Topic)
단일 슬롯(A Only) 환경에서는 작업대가 교체되는 동안 로봇 팔이 동작을 멈춰야 합니다. 이를 위해 커스텀 인터페이스가 아닌 표준 `std_msgs` 토픽을 활용하여 즉각적인 인터로킹을 수행합니다.

*   **토픽 명**: `/{robot_id}/pause_status` (예: `/sg2_in_01/pause_status`, `/sg2_out_00/pause_status`)
*   **메시지 타입**: `std_msgs/msg/Bool`
*   **동작 로직**:
    *   `true` 발행: 8칸이 모두 적재된 순간, 혹은 양면 작업(4칸) 완료 후 180도 회전(ROTATE_WORKSTATION)이 시작될 때 로봇 팔 작동 일시 정지 (관제탑이 발행)
    *   `false` 발행: 텅 빈 새 작업대가 A구역에 배치 완료된 순간, 혹은 180도 회전이 완료되어 작업이 가능한 순간 로봇 팔 작동 재개 (관제탑이 발행)

---

> 상세한 통합 연동 설계 및 시스템 하이브리드 아키텍처는 프로젝트 루트 디렉토리의 `ROBOT_AMR_INTEGRATION_GUIDE.md`를 참고해 주십시오.

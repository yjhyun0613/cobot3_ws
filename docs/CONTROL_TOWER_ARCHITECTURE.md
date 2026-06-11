# 📡 관제탑 노드 토폴로지 및 파이프라인 시스템 아키텍처

본 문서는 물류창고 관제 시스템(Control Tower)을 구성하는 핵심 ROS 2 노드들의 데이터 흐름, 시스템 아키텍처, 그리고 제어 파이프라인을 시각화(Mermaid) 및 기술적으로 정리한 아키텍처 명세서입니다.

---

## 📌 1. 시스템 노드 & 데이터 토폴로지 (Node & Data Topology)

관제 시스템은 제어 평면(ROS 2 Humble / DDS)과 데이터 평면(PostgreSQL / Redis)이 분리된 하이브리드 아키텍처를 채택하고 있습니다. 각 노드 간의 통신 채널과 데이터 접근 모델은 다음과 같이 정의됩니다.

```mermaid
graph LR
    %% Nodes
    CT[control_tower_node<br>중앙 스케줄러]
    Sync[sim_sync_node<br>시뮬레이션 동기화]
    Dash[dashboard_server<br>FastAPI 백엔드]
    Conn[isaac_amr_connector<br>Isaac Sim 브릿지]
    AMR[mock_full_robot_node<br>AMR 에뮬레이터]
    Out[mock_sg2_out_node<br>포장기 에뮬레이터]
    
    %% Databases
    Postgres[(PostgreSQL 15<br>WMS DB)]
    Redis[(Redis 7.0<br>Cache & ZSET Queue)]

    %% Interfaces/Topics
    CT <-->|psycopg2 pool| Postgres
    CT <-->|ZSET Push/Pop| Redis
    Dash <-->|Real-time Query| Postgres
    Dash <-->|Cache Fetch| Redis
    
    %% ROS 2 Communications
    CT -->|ManageWorkstation Action| AMR
    AMR -->|ReportInboundProgress Service| CT
    CT -.->|"/{robot_id}/pause_status Topic"| Out
    
    %% Simulation Sync Channels
    Sync -->|TransitPackage Service| Postgres
    Sync -.->|/sim/sg2_spawn_trigger Topic| Conn
    CT -.->|/sim/sg2_workstation_trigger Message| Conn
    Conn <-->|Redis HGET amr:locations| Redis
    Conn -->|Teleport/PhysX| IsaacSim[NVIDIA Isaac Sim]
    
    %% Styling
    classDef nodeStyle fill:#e6f2ff,stroke:#0066cc,stroke-width:2px;
    classDef dbStyle fill:#ffe6e6,stroke:#cc0000,stroke-width:2px;
    classDef simStyle fill:#e6ffe6,stroke:#009900,stroke-width:2px;
    
    class CT,Sync,Dash,Conn,AMR,Out nodeStyle;
    class Postgres,Redis dbStyle;
    class IsaacSim simStyle;
```

---

## 🔄 2. 입출고 물류 파이프라인 플로차트 (Logistic Pipeline Flowcharts)

### ① 입고분류 및 적재 파이프라인 (Inbound Pipeline)
상자가 입고 컨베이어 벨트에 진입한 순간부터 AMR이 적재 완료된 작업대를 보관 구역으로 이송하기까지의 전체 제어 흐름입니다.

```mermaid
flowchart TD
    subgraph Stage1 [1단계: 입고 및 라우팅 분류]
        direction LR
        Start([상자 진입]) --> Scan[카메라 스캔] --> DB{수령인 조회} --> Route{배송일자 분기}
        Route -->|오늘| Line1[입고라인 1]
        Route -->|내일/모레| Line23[입고라인 2/3]
    end
    
    subgraph Stage2 [2단계: 적재 및 JIT 180도 회전]
        direction LR
        Pile[로봇 적재] --> Report[ReportProgress] --> Count{3/4슬롯 도달?} -->|Yes| JIT_Rot[JIT 180도 회전]
    end
    
    subgraph Stage3 [3단계: 완충 및 작업대 교체 이송]
        direction LR
        Full{8슬롯 완충?} -->|Yes| JIT_Swap[JIT 작업대 교체] --> End([창고 이송 및 주차])
    end

    Stage1 --> Stage2
    Stage2 --> Stage3
```

### ② 출고 및 포장 파이프라인 (Outbound Pipeline)
오늘 배송해야 하는 패키지들을 선별하고, 포장 로봇이 포장을 수행한 뒤 영업일을 마감하는 과정입니다.

```mermaid
flowchart TD
    subgraph Stage1 [1단계: 출고 준비 및 이송]
        direction LR
        Start([출고 스케줄러]) --> CheckA{A구역 비어있음?} -->|Yes| FetchA[완충작업대 A구역 이송]
    end
    
    subgraph Stage2 [2단계: 포장 및 Look-ahead 사전이송]
        direction LR
        Pack[포장 개시] --> PackLoop[포장 및 DB 갱신] --> Look{7슬롯 완포?} -->|Yes| FetchB[Look-ahead: B구역 호출]
    end
    
    subgraph Stage3 [3단계: 교체 및 영업 마감]
        direction LR
        Full{8슬롯 완포?} -->|Yes| Swap[작업대 교체] --> EOD{잔여물 = 0?} -->|Yes| EOD_Proc[EOD 마감 및 이월 승격]
    end

    Stage1 --> Stage2
    Stage2 --> Stage3
```

---

## ⚡ 3. JIT 일시정지 및 인터로킹 시퀀스 (JIT Interlocking Sequence)

로봇 팔(Manipulator)의 적재/포장 물리 좌표 영역과 AMR의 주입/탈출 공간이 겹치는 물리 충돌 병목을 원천 방지하기 위해 설계된 시퀀스 다이어그램입니다.

```mermaid
sequenceDiagram
    autonumber
    participant Robot as 적재/포장 로봇 노드
    participant CT as 관제탑 (control_tower)
    participant Redis as Redis Sorted Set (ZSET)
    participant AMR as AMR 에뮬레이터
    participant Conn as Isaac Sim 커넥터

    Note over Robot, CT: 4번째 상자 적재 완료 또는 8번째 상자 적재 완료
    Robot->>CT: ReportInboundProgress.srv (또는 Action Feedback)
    CT->>Robot: /{robot_id}/pause_status (std_msgs/Bool = True) 발행
    Note over Robot: 로봇 팔 기동 물리 정지 (안전 대기)
    
    CT->>Redis: ZSET 우선순위 큐에 태스크 삽입 (UUID 포함)
    Redis->>CT: Task Scheduler가 최상단 Task Pop (우선순위 가중치 100)
    CT->>AMR: ManageWorkstation.action Goal 송신 (ROTATE 또는 DEPLOY)
    
    AMR->>Conn: 1.5m 바닥 격자 맵 기반 최단 경로 주행 및 도킹 회전
    Conn->>AMR: Action Succeeded 반환
    
    AMR->>CT: Action Result (Success) 보고
    CT->>Robot: /{robot_id}/pause_status (std_msgs/Bool = False) 발행
    Note over Robot: 로봇 팔 기동 해제 및 다음 슬롯 연속 작업 진행
```

---

## 🛡️ 4. AMR 스케줄러 & 트랜잭션 롤백 흐름 (Scheduler & Rollback Flow)

AMR 배정 시 동시 기동 제약 조건을 준수하고, 통신 지연이나 로봇 오프라인 상황에서 데이터베이스 교착 상태를 복구하는 예외 처리 아키텍처입니다.

```mermaid
flowchart TD
    subgraph Stage1 [1단계: 태스크 스캔 및 리소스 검증]
        direction LR
        Start([스케줄러 루프]) --> Fetch[ZSET 태스크 조회] --> Limit{AMR 가동제한<br>active < 5?} -->|Yes| Lock{작업대/스팟 락?}
    end
    
    subgraph Stage2 [2단계: 최적 AMR 배정 및 명령 발송]
        direction LR
        Lock -->|No| Reserve[DB 예약 처리] --> Distance[최단거리 AMR 매핑] --> Dispatch[Action Goal 전송]
    end
    
    subgraph Stage3 [3단계: 예외 처리 및 트랜잭션 롤백]
        direction LR
        Wait{연결 성공?} -->|Fail / Timeout| Rollback[DB 롤백 및 예약 해제]
        Wait -->|Success| Exec[주행 모니터링] --> Result{성공?}
        Result -->|실패| Rollback
        Result -->|성공| Commit[DB 최종 업데이트]
    end

    Stage1 --> Stage2
    Stage2 --> Stage3
```

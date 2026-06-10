#!/usr/bin/env python3
"""
🚚 AMR 단독 시뮬레이션 명령 시퀀스 관리자 (Command Sequence Manager)
====================================================================
- AMR 5대 (AMR_01 ~ AMR_05): Isaac Sim에서 실제 이동
- SG2 3대 (SG2_01 ~ SG2_03): 보이지 않음, 타이머 이벤트로만 처리
- 작업대: 2면 × 4칸 = 8칸, SG2가 한 면 채우는 데 6초
- 한 면 완료 → AMR 회전 / 양면 완료 → AMR 운반

mock 함수 내부를 Isaac Sim API 또는 ROS2 Action으로 교체하면 실제 시뮬레이션 연동 가능.
"""
import time
import threading
import heapq
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict

# ============================================================
# 상수 정의
# ============================================================
SG2_WORK_DURATION = 6.0       # SG2가 한 면(4칸) 채우는 시간 (초)
AMR_MOVE_DURATION = 3.0       # AMR 이동 소요 시간 (mock)
AMR_DOCK_DURATION = 1.5       # AMR 도킹 소요 시간
AMR_ROTATE_DURATION = 2.0     # 작업대 180도 회전 소요 시간
AMR_PICK_DURATION = 1.0       # 작업대 픽업 소요 시간
AMR_DROP_DURATION = 1.0       # 작업대 드롭 소요 시간
AMR_RETURN_DURATION = 2.5     # AMR 복귀 소요 시간

DESTINATIONS = ['STAGE_01', 'STAGE_02', 'MAIN_WAREHOUSE']

# 목적지별 물리 좌표 (운반 후 AMR 위치 갱신에 사용)
DESTINATION_POSITIONS = {
    'STAGE_01': (6.0, 8.25),
    'STAGE_02': (4.5, 8.25),
    'MAIN_WAREHOUSE': (0.75, -3.0),
}

# ============================================================
# 상태 Enum 정의
# ============================================================
class WorkstationState(Enum):
    EMPTY = "EMPTY"
    SIDE_A_WORKING = "SIDE_A_WORKING"
    HALF_FULL = "HALF_FULL"
    ROTATE_REQUESTED = "ROTATE_REQUESTED"
    ROTATING = "ROTATING"
    SIDE_B_WORKING = "SIDE_B_WORKING"
    FULL = "FULL"
    TRANSPORT_REQUESTED = "TRANSPORT_REQUESTED"
    TRANSPORTING = "TRANSPORTING"
    DELIVERED = "DELIVERED"

class AMRState(Enum):
    IDLE = "IDLE"
    RESERVED = "RESERVED"       # dispatch에서 선점 완료, 아직 스레드 미시작
    MOVING_TO_WORKSTATION = "MOVING_TO_WORKSTATION"
    DOCKING = "DOCKING"
    ROTATING_WORKSTATION = "ROTATING_WORKSTATION"
    PICKING_WORKSTATION = "PICKING_WORKSTATION"
    MOVING_TO_DESTINATION = "MOVING_TO_DESTINATION"
    DROPPING_WORKSTATION = "DROPPING_WORKSTATION"
    RETURNING = "RETURNING"
    STANDBY = "STANDBY"

class TaskType(Enum):
    ROTATE = "ROTATE"           # 우선순위 높음
    TRANSPORT = "TRANSPORT"     # 우선순위 낮음

# ============================================================
# 데이터 클래스
# ============================================================
@dataclass
class Workstation:
    ws_id: str
    state: WorkstationState = WorkstationState.EMPTY
    assigned_sg2: Optional[str] = None
    assigned_amr: Optional[str] = None
    slots_filled: int = 0       # 0~8
    position: tuple = (0.0, 0.0)  # (x, y) 물리 좌표

@dataclass(order=True)
class Task:
    priority: int               # 낮을수록 우선 (ROTATE=1, TRANSPORT=2)
    created_at: float = field(compare=False)
    task_id: str = field(compare=False, default_factory=lambda: str(uuid.uuid4())[:8])
    task_type: TaskType = field(compare=False, default=TaskType.ROTATE)
    workstation_id: str = field(compare=False, default="")

@dataclass
class AMR:
    amr_id: str
    state: AMRState = AMRState.IDLE
    current_task: Optional[Task] = None
    position: tuple = (0.0, 0.0)      # (x, y) 현재 물리 좌표 (이동 시 갱신됨)
    home_position: tuple = (0.0, 0.0) # 대기/충전 위치 (복귀 목적지)

# ============================================================
# Mock 함수 (Isaac Sim API 또는 ROS2로 교체 가능)
# ============================================================
class AMRMotionController:
    """AMR 물리 이동 제어 인터페이스. mock 구현을 실제 Isaac Sim/ROS2로 교체."""

    def move_amr_to(self, amr_id: str, target_pose: tuple) -> bool:
        """AMR을 목표 위치로 이동. 반환: 성공 여부"""
        time.sleep(AMR_MOVE_DURATION)
        return True

    def dock_to_workstation(self, amr_id: str, workstation_id: str) -> bool:
        """AMR을 작업대에 도킹/정렬"""
        time.sleep(AMR_DOCK_DURATION)
        return True

    def rotate_workstation_180(self, amr_id: str, workstation_id: str) -> bool:
        """작업대를 180도 회전"""
        time.sleep(AMR_ROTATE_DURATION)
        return True

    def pick_workstation(self, amr_id: str, workstation_id: str) -> bool:
        """작업대를 들어올리기/연결"""
        time.sleep(AMR_PICK_DURATION)
        return True

    def move_to_destination(self, amr_id: str, destination_id: str) -> bool:
        """AMR을 목적지로 이동 (작업대 운반 중)"""
        time.sleep(AMR_MOVE_DURATION)
        return True

    def drop_workstation(self, amr_id: str, workstation_id: str) -> bool:
        """작업대를 목적지에 내려놓기"""
        time.sleep(AMR_DROP_DURATION)
        return True

    def return_to_standby(self, amr_id: str, standby_pose: tuple) -> bool:
        """AMR을 대기/충전 위치로 복귀"""
        time.sleep(AMR_RETURN_DURATION)
        return True

# ============================================================
# 핵심: 명령 시퀀스 관리자 (TaskManager)
# ============================================================
class TaskManager:
    """작업대 상태 전이, AMR 배정, 우선순위 큐 기반 태스크 스케줄링을 총괄"""

    def __init__(self):
        self.sim_start_time = time.time()
        self.motion = AMRMotionController()
        self.lock = threading.Lock()

        # AMR 초기화 (5대, 충전 대기 위치)
        amr_positions = [(-3.0, -9.0), (-3.0, -7.5), (-3.0, -6.0), (-3.0, -4.5), (-3.0, -3.0)]
        self.amrs: Dict[str, AMR] = {
            f"AMR_{i+1:02d}": AMR(
                amr_id=f"AMR_{i+1:02d}",
                position=amr_positions[i],
                home_position=amr_positions[i]
            )
            for i in range(5)
        }

        # SG2 → 작업대 매핑 (SG2 3대, 각각 담당 작업대 1대씩)
        ws_positions = [(7.5, 1.5), (7.5, -3.0), (7.5, -7.5)]
        self.workstations: Dict[str, Workstation] = {}
        self.sg2_assignments: Dict[str, str] = {}  # sg2_id -> ws_id
        for i in range(3):
            ws_id = f"WS_{i+1:02d}"
            sg2_id = f"SG2_{i+1:02d}"
            self.workstations[ws_id] = Workstation(ws_id, assigned_sg2=sg2_id, position=ws_positions[i])
            self.sg2_assignments[sg2_id] = ws_id

        # 우선순위 큐 (heapq)
        self.task_queue: List[Task] = []
        self.running = True

        # 목적지 순환 카운터
        self._dest_idx = 0

    # ---- 로그 헬퍼 ----
    def log(self, msg: str):
        elapsed = time.time() - self.sim_start_time
        print(f"[{elapsed:7.1f}s] {msg}")

    # ---- 목적지 순환 선택 ----
    def _next_destination(self) -> str:
        dest = DESTINATIONS[self._dest_idx % len(DESTINATIONS)]
        self._dest_idx += 1
        return dest

    # ---- IDLE AMR 선택 (거리 기반, 호출부에서 lock 보유 상태에서 호출) ----
    def _select_nearest_idle_amr_unlocked(self, target_pos: tuple) -> Optional[AMR]:
        """lock이 이미 잡힌 상태에서 호출. 가장 가까운 IDLE AMR 반환."""
        idle_amrs = [a for a in self.amrs.values() if a.state == AMRState.IDLE]
        if not idle_amrs:
            return None
        idle_amrs.sort(key=lambda a: (a.position[0]-target_pos[0])**2 + (a.position[1]-target_pos[1])**2)
        return idle_amrs[0]

    # ---- 태스크 생성 및 큐 투입 ----
    def enqueue_task(self, task_type: TaskType, ws_id: str):
        priority = 1 if task_type == TaskType.ROTATE else 2
        task = Task(priority=priority, created_at=time.time(), task_type=task_type, workstation_id=ws_id)
        with self.lock:
            heapq.heappush(self.task_queue, task)
        self.log(f"📋 태스크 큐 등록: {task_type.value} for {ws_id} (priority={priority})")

    # ---- 태스크 디스패처 (메인 루프) ----
    def dispatch_loop(self):
        """큐에서 태스크를 꺼내어 가용 AMR에 배정하는 무한 루프.
        AMR 선택 + RESERVED 마킹을 단일 lock 블록에서 원자적으로 처리하여 중복 배정 방지."""
        while self.running:
            dispatch_info = None  # (task, amr, ws)

            with self.lock:
                if self.task_queue:
                    candidate = self.task_queue[0]
                    ws = self.workstations[candidate.workstation_id]
                    if ws.assigned_amr is None:
                        amr = self._select_nearest_idle_amr_unlocked(ws.position)
                        if amr:
                            task = heapq.heappop(self.task_queue)
                            # 🔒 원자적 선점: 스레드 시작 전에 AMR/WS 상태를 즉시 마킹
                            amr.state = AMRState.RESERVED
                            amr.current_task = task
                            ws.assigned_amr = amr.amr_id
                            dispatch_info = (task, amr, ws)

            if dispatch_info:
                task, amr, ws = dispatch_info
                if task.task_type == TaskType.ROTATE:
                    t = threading.Thread(target=self._execute_rotate, args=(amr, ws, task), daemon=True)
                else:
                    t = threading.Thread(target=self._execute_transport, args=(amr, ws, task), daemon=True)
                t.start()

            time.sleep(0.5)

    # ---- 회전 작업 실행 시퀀스 ----
    def _execute_rotate(self, amr: AMR, ws: Workstation, task: Task):
        # dispatch_loop에서 이미 RESERVED + assigned_amr 설정 완료
        with self.lock:
            amr.state = AMRState.MOVING_TO_WORKSTATION
            ws.state = WorkstationState.ROTATING
        self.log(f"🤖 {amr.amr_id} → {ws.ws_id} 회전 작업 배정 (MOVING, 현위치: {amr.position})")

        # 1. 작업대로 이동
        self.motion.move_amr_to(amr.amr_id, ws.position)
        with self.lock:
            amr.state = AMRState.DOCKING
            amr.position = ws.position  # 📍 위치 갱신: 작업대 도착
        self.log(f"🔗 {amr.amr_id} → {ws.ws_id} 도킹 중")

        # 2. 도킹
        self.motion.dock_to_workstation(amr.amr_id, ws.ws_id)
        with self.lock: amr.state = AMRState.ROTATING_WORKSTATION
        self.log(f"🔄 {amr.amr_id} → {ws.ws_id} 180도 회전 중")

        # 3. 회전
        self.motion.rotate_workstation_180(amr.amr_id, ws.ws_id)
        self.log(f"✅ {amr.amr_id} → {ws.ws_id} 회전 완료")

        # 4. 회전 완료 → SG2가 B면 작업 시작
        with self.lock:
            ws.state = WorkstationState.SIDE_B_WORKING
            ws.assigned_amr = None
            amr.state = AMRState.RETURNING
            amr.current_task = None
        self.log(f"🏭 {ws.assigned_sg2} → {ws.ws_id} B면 작업 시작 (6초)")

        # 5. AMR 복귀
        home = amr.home_position
        self.motion.return_to_standby(amr.amr_id, home)
        with self.lock:
            amr.state = AMRState.IDLE
            amr.position = home  # 📍 위치 갱신: 충전소 복귀
        self.log(f"🅿️ {amr.amr_id} IDLE 복귀 (위치: {home})")

        # 6. SG2 B면 타이머 시작
        threading.Timer(SG2_WORK_DURATION, self._on_sg2_side_b_complete, args=[ws.ws_id]).start()

    # ---- 운반 작업 실행 시퀀스 ----
    def _execute_transport(self, amr: AMR, ws: Workstation, task: Task):
        dest = self._next_destination()
        dest_pos = DESTINATION_POSITIONS.get(dest, (0.0, 0.0))
        # dispatch_loop에서 이미 RESERVED + assigned_amr 설정 완료
        with self.lock:
            amr.state = AMRState.MOVING_TO_WORKSTATION
            ws.state = WorkstationState.TRANSPORTING
        self.log(f"🤖 {amr.amr_id} → {ws.ws_id} 운반 배정 (목적지: {dest}, 현위치: {amr.position})")

        # 1. 작업대로 이동
        self.motion.move_amr_to(amr.amr_id, ws.position)
        with self.lock:
            amr.state = AMRState.DOCKING
            amr.position = ws.position  # 📍 위치 갱신: 작업대 도착
        self.log(f"🔗 {amr.amr_id} → {ws.ws_id} 도킹 중")

        # 2. 도킹
        self.motion.dock_to_workstation(amr.amr_id, ws.ws_id)
        with self.lock: amr.state = AMRState.PICKING_WORKSTATION
        self.log(f"⬆️ {amr.amr_id} → {ws.ws_id} 픽업 중")

        # 3. 픽업
        self.motion.pick_workstation(amr.amr_id, ws.ws_id)
        with self.lock: amr.state = AMRState.MOVING_TO_DESTINATION
        self.log(f"🚚 {amr.amr_id} → {dest} 운반 중 ({ws.ws_id})")

        # 4. 목적지 이동
        self.motion.move_to_destination(amr.amr_id, dest)
        with self.lock:
            amr.state = AMRState.DROPPING_WORKSTATION
            amr.position = dest_pos  # 📍 위치 갱신: 목적지 도착
        self.log(f"⬇️ {amr.amr_id} → {dest} 작업대 내려놓는 중")

        # 5. 드롭
        self.motion.drop_workstation(amr.amr_id, ws.ws_id)

        # 6. 완료
        with self.lock:
            ws.state = WorkstationState.DELIVERED
            ws.slots_filled = 0
            ws.assigned_amr = None
            amr.state = AMRState.RETURNING
            amr.current_task = None
        self.log(f"📦 {amr.amr_id} → {ws.ws_id} 배달 완료 at {dest}")

        # 7. AMR 복귀
        home = amr.home_position
        self.motion.return_to_standby(amr.amr_id, home)
        with self.lock:
            amr.state = AMRState.IDLE
            amr.position = home  # 📍 위치 갱신: 충전소 복귀
        self.log(f"🅿️ {amr.amr_id} IDLE 복귀 (위치: {home})")

        # 8. 작업대 초기화 → 새 사이클 시작
        threading.Timer(1.0, self._restart_workstation_cycle, args=[ws.ws_id]).start()

    # ---- SG2 이벤트 콜백 ----
    def _on_sg2_side_a_complete(self, ws_id: str):
        """SG2가 A면 4칸 작업 완료 시 호출"""
        ws = self.workstations[ws_id]
        with self.lock:
            ws.slots_filled = 4
            ws.state = WorkstationState.HALF_FULL
        self.log(f"🏭 {ws.assigned_sg2} → {ws_id} A면 완료 (HALF_FULL, 4/8칸)")

        # 회전 요청 태스크 생성
        with self.lock:
            ws.state = WorkstationState.ROTATE_REQUESTED
        self.enqueue_task(TaskType.ROTATE, ws_id)

    def _on_sg2_side_b_complete(self, ws_id: str):
        """SG2가 B면 4칸 작업 완료 시 호출"""
        ws = self.workstations[ws_id]
        with self.lock:
            ws.slots_filled = 8
            ws.state = WorkstationState.FULL
        self.log(f"🏭 {ws.assigned_sg2} → {ws_id} B면 완료 (FULL, 8/8칸)")

        # 운반 요청 태스크 생성
        with self.lock:
            ws.state = WorkstationState.TRANSPORT_REQUESTED
        self.enqueue_task(TaskType.TRANSPORT, ws_id)

    def _restart_workstation_cycle(self, ws_id: str):
        """작업대 배달 완료 후 새 사이클 시작"""
        ws = self.workstations[ws_id]
        with self.lock:
            ws.state = WorkstationState.SIDE_A_WORKING
            ws.slots_filled = 0
        self.log(f"♻️ {ws_id} 새 작업대 세팅 완료 → {ws.assigned_sg2} A면 작업 시작 (6초)")
        threading.Timer(SG2_WORK_DURATION, self._on_sg2_side_a_complete, args=[ws_id]).start()

    # ---- 상태 모니터 (주기적 출력) ----
    def status_monitor(self):
        while self.running:
            time.sleep(10.0)
            print("\n" + "=" * 70)
            self.log("📊 === 시스템 상태 스냅샷 ===")
            for a in self.amrs.values():
                task_info = f" (task: {a.current_task.task_type.value} → {a.current_task.workstation_id})" if a.current_task else ""
                print(f"    {a.amr_id}: {a.state.value} pos={a.position}{task_info}")
            for w in self.workstations.values():
                print(f"    {w.ws_id}: {w.state.value} ({w.slots_filled}/8칸) | SG2={w.assigned_sg2} | AMR={w.assigned_amr or '-'}")
            with self.lock:
                print(f"    대기 큐: {len(self.task_queue)}건")
            print("=" * 70 + "\n")

    # ---- 시뮬레이션 시작 ----
    def start(self):
        self.log("🚀 AMR 명령 시퀀스 시뮬레이션 시작")
        self.log(f"   AMR 5대: {', '.join(self.amrs.keys())}")
        self.log(f"   SG2 3대: {', '.join(self.sg2_assignments.keys())} (타이머 이벤트)")
        self.log(f"   작업대 {len(self.workstations)}대: {', '.join(self.workstations.keys())}")
        print()

        # 1. 디스패처 스레드 시작
        threading.Thread(target=self.dispatch_loop, daemon=True).start()

        # 2. 상태 모니터 스레드 시작
        threading.Thread(target=self.status_monitor, daemon=True).start()

        # 3. 모든 SG2가 A면 작업 시작 (타이머 이벤트 등록)
        for sg2_id, ws_id in self.sg2_assignments.items():
            ws = self.workstations[ws_id]
            ws.state = WorkstationState.SIDE_A_WORKING
            self.log(f"🏭 {sg2_id} → {ws_id} A면 작업 시작 (6초 타이머)")
            threading.Timer(SG2_WORK_DURATION, self._on_sg2_side_a_complete, args=[ws_id]).start()

    def stop(self):
        self.running = False
        self.log("🛑 시뮬레이션 종료")


# ============================================================
# 메인 실행부
# ============================================================
if __name__ == '__main__':
    manager = TaskManager()
    manager.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        manager.stop()
        print("\n시뮬레이션을 종료합니다.")

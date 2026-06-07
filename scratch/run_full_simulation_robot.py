#!/usr/bin/env python3
import sys
import time
import os
import threading
import psycopg2
import redis
from datetime import datetime, timedelta
from heapq import heappush, heappop
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.executors import MultiThreadedExecutor

from cobot3_interfaces.srv import GetPackageRoute, CheckWarehouseStatus, ReportInboundProgress
from cobot3_interfaces.action import ManageWorkstation, MovePackage, StartPackaging

# 모듈 경로 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scratch.qr_handler import generate_qr_code, decode_qr_code

# ==========================================
# 🗺️ 그리드 및 2D 맵 변환 유틸리티
# ==========================================
GRID_W = 49
GRID_H = 37
GRID_SPACING = 1.5
X_ORIGIN = -34.775
Y_ORIGIN = -29.025

GridCell = Tuple[int, int]
TimedCell = Tuple[int, int, int]
EdgeKey = Tuple[int, int, int, int, int]

def world_to_cell(wx: float, wy: float) -> GridCell:
    cx = int(round((wx - X_ORIGIN) / GRID_SPACING))
    cy = int(round((wy - Y_ORIGIN) / GRID_SPACING))
    return (cx, cy)

def cell_to_world(cell: GridCell) -> Tuple[float, float]:
    wx = X_ORIGIN + cell[0] * GRID_SPACING
    wy = Y_ORIGIN + cell[1] * GRID_SPACING
    return (round(wx, 3), round(wy, 3))


# ==========================================
# 🛠️ Time-Expanded A* 자료구조 및 알고리즘
# ==========================================
@dataclass
class RobotPlanRequest:
    robot_id: str
    start: GridCell
    goal: GridCell
    heading: GridCell = (1, 0)
    carrying_rack: bool = False
    priority: int = 0
    waiting_steps: int = 0
    allowed_goal_occupied: bool = False


@dataclass
class RobotPlanResult:
    robot_id: str
    path: List[GridCell]
    timed_path: List[TimedCell]
    success: bool
    reason: str = ""


@dataclass
class TimeAStarConfig:
    grid_width: int = GRID_W
    grid_height: int = GRID_H
    grid_spacing_m: float = GRID_SPACING
    amr_size_m: float = 0.7
    rack_size_m: float = 1.3
    max_time_horizon: int = 90
    reservation_horizon: int = 45
    lookahead_steps: int = 8
    move_cost: float = 1.0
    wait_cost: float = 1.2
    turn_cost: float = 0.25
    rack_turn_cost: float = 1.2
    congestion_cost: float = 0.35
    local_detour_cost: float = 0.65
    goal_hold_steps: int = 6
    allow_local_8_detour: bool = True


class ReservationTable:
    def __init__(self):
        self.reserved_cell: Dict[TimedCell, str] = {}
        self.reserved_edge: Dict[EdgeKey, str] = {}
        self.soft_reserved_cell: Dict[TimedCell, str] = {}

    def clear(self):
        self.reserved_cell.clear()
        self.reserved_edge.clear()
        self.soft_reserved_cell.clear()

    def is_cell_reserved(self, cell: GridCell, t: int, robot_id: str) -> bool:
        owner = self.reserved_cell.get((cell[0], cell[1], t))
        return owner is not None and owner != robot_id

    def is_soft_reserved(self, cell: GridCell, t: int, robot_id: str) -> bool:
        owner = self.soft_reserved_cell.get((cell[0], cell[1], t))
        return owner is not None and owner != robot_id

    def is_edge_conflict(self, from_cell: GridCell, to_cell: GridCell, t: int, robot_id: str) -> bool:
        owner = self.reserved_edge.get((to_cell[0], to_cell[1], from_cell[0], from_cell[1], t))
        return owner is not None and owner != robot_id

    def is_diagonal_cross_conflict(self, from_cell: GridCell, to_cell: GridCell, t: int, robot_id: str) -> bool:
        dx = to_cell[0] - from_cell[0]
        dy = to_cell[1] - from_cell[1]

        if abs(dx) != 1 or abs(dy) != 1:
            return False

        side_a = (from_cell[0] + dx, from_cell[1])
        side_b = (from_cell[0], from_cell[1] + dy)

        keys = [
            (side_a[0], side_a[1], side_b[0], side_b[1], t),
            (side_b[0], side_b[1], side_a[0], side_a[1], t),
        ]

        for key in keys:
            owner = self.reserved_edge.get(key)
            if owner is not None and owner != robot_id:
                return True
        return False

    def reserve_cell(self, cell: GridCell, t: int, robot_id: str):
        self.reserved_cell[(cell[0], cell[1], t)] = robot_id

    def reserve_soft_cell(self, cell: GridCell, t: int, robot_id: str):
        self.soft_reserved_cell[(cell[0], cell[1], t)] = robot_id

    def reserve_edge(self, from_cell: GridCell, to_cell: GridCell, t: int, robot_id: str):
        self.reserved_edge[(from_cell[0], from_cell[1], to_cell[0], to_cell[1], t)] = robot_id

    def reserve_path(self, robot_id: str, timed_path: List[TimedCell], carrying_rack: bool, heading_path: List[GridCell], config: TimeAStarConfig):
        if not timed_path:
            return

        horizon_path = timed_path[:config.reservation_horizon]
        for i, node in enumerate(horizon_path):
            x, y, t = node
            current = (x, y)
            self.reserve_cell(current, t, robot_id)

            if carrying_rack:
                heading = heading_path[i] if i < len(heading_path) else (0, 0)
                for soft_cell in self._rack_soft_cells(current, heading, config):
                    if self._in_bounds(soft_cell, config):
                        self.reserve_soft_cell(soft_cell, t, robot_id)

            if i > 0:
                px, py, pt = horizon_path[i - 1]
                previous = (px, py)
                self.reserve_edge(previous, current, pt, robot_id)

        gx, gy, gt = timed_path[-1]
        goal = (gx, gy)
        for dt in range(config.goal_hold_steps):
            self.reserve_cell(goal, gt + dt, robot_id)

    def _rack_soft_cells(self, cell: GridCell, heading: GridCell, config: TimeAStarConfig) -> List[GridCell]:
        x, y = cell
        hx, hy = heading
        cells = []
        if hx != 0 or hy != 0:
            cells.append((x + hx, y + hy))

        if hx != 0 and hy != 0:
            cells.append((x + hx, y))
            cells.append((x, y + hy))
            cells.append((x - hx, y))
            cells.append((x, y - hy))
        elif hx != 0:
            cells.append((x, y + 1))
            cells.append((x, y - 1))
        elif hy != 0:
            cells.append((x + 1, y))
            cells.append((x - 1, y))
        return cells

    def _in_bounds(self, cell: GridCell, config: TimeAStarConfig) -> bool:
        x, y = cell
        return 0 <= x < config.grid_width and 0 <= y < config.grid_height


class TimeAStarPlanner:
    def __init__(self, config: TimeAStarConfig):
        self.config = config
        self.cardinal_moves = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        self.diagonal_moves = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        self.wait_move = (0, 0)
        self.motion_moves = self.cardinal_moves + self.diagonal_moves
        self.detour_moves_8 = self.cardinal_moves + self.diagonal_moves

    def plan(self, request: RobotPlanRequest, reservation: ReservationTable, static_obstacles: Set[GridCell], start_time: int = 0) -> RobotPlanResult:
        if request.start == request.goal:
            timed_path = [(request.start[0], request.start[1], start_time)]
            return RobotPlanResult(request.robot_id, [request.start], timed_path, True, "already_at_goal")

        if not self._is_valid_cell(request.start, request.goal, request.allowed_goal_occupied, static_obstacles):
            return RobotPlanResult(request.robot_id, [], [], False, "invalid_start")

        open_heap = []
        came_from = {}
        g_score = {}

        sx, sy = request.start
        hx, hy = request.heading
        start_node = (sx, sy, start_time, hx, hy)
        g_score[start_node] = 0.0
        heappush(open_heap, (self._heuristic(request.start, request.goal), 0.0, start_node))

        best_node = None
        best_h = float("inf")

        while open_heap:
            _, current_g, current = heappop(open_heap)
            x, y, t, chx, chy = current
            current_cell = (x, y)

            h = self._heuristic(current_cell, request.goal)
            if h < best_h:
                best_h = h
                best_node = current

            if current_cell == request.goal:
                path, timed_path, _ = self._reconstruct(came_from, current)
                return RobotPlanResult(request.robot_id, path, timed_path, True, "success")

            if t - start_time >= self.config.max_time_horizon:
                continue

            for move in self._get_neighbors():
                dx, dy = move
                nx, ny = x + dx, y + dy
                nt = t + 1
                next_cell = (nx, ny)

                if not self._is_valid_cell(next_cell, request.goal, request.allowed_goal_occupied, static_obstacles):
                    continue

                if not self._is_transition_safe(
                    robot_id=request.robot_id,
                    from_cell=current_cell,
                    to_cell=next_cell,
                    t=t,
                    next_t=nt,
                    carrying_rack=request.carrying_rack,
                    reservation=reservation,
                    move=move,
                    goal=request.goal,
                    allowed_goal_occupied=request.allowed_goal_occupied,
                    static_obstacles=static_obstacles,
                ):
                    continue

                nhx, nhy = self._new_heading((chx, chy), move)
                next_node = (nx, ny, nt, nhx, nhy)
                step_cost = self._step_cost((chx, chy), move, next_cell, nt, request.carrying_rack, reservation, request.robot_id)
                tentative_g = current_g + step_cost

                if tentative_g < g_score.get(next_node, float("inf")):
                    came_from[next_node] = current
                    g_score[next_node] = tentative_g
                    f = tentative_g + self._heuristic(next_cell, request.goal)
                    heappush(open_heap, (f, tentative_g, next_node))

        if best_node is not None and self.config.allow_local_8_detour:
            fallback = self._local_detour_fallback(request, reservation, static_obstacles, start_time)
            if fallback.success:
                return fallback

        return RobotPlanResult(request.robot_id, [], [], False, "no_path")

    def _get_neighbors(self):
        moves = list(self.motion_moves)
        moves.append(self.wait_move)
        return moves

    def _is_valid_cell(self, cell, goal, allowed_goal_occupied, static_obstacles):
        x, y = cell
        if x < 0 or x >= self.config.grid_width:
            return False
        if y < 0 or y >= self.config.grid_height:
            return False
        if cell in static_obstacles:
            if allowed_goal_occupied and cell == goal:
                return True
            return False
        return True

    def _is_transition_safe(self, robot_id, from_cell, to_cell, t, next_t, carrying_rack, reservation, move, goal, allowed_goal_occupied, static_obstacles):
        if reservation.is_cell_reserved(to_cell, next_t, robot_id):
            return False
        if reservation.is_edge_conflict(from_cell, to_cell, t, robot_id):
            return False
        if reservation.is_diagonal_cross_conflict(from_cell, to_cell, t, robot_id):
            return False

        dx = to_cell[0] - from_cell[0]
        dy = to_cell[1] - from_cell[1]

        if abs(dx) == 1 and abs(dy) == 1:
            side_cells = [(from_cell[0] + dx, from_cell[1]), (from_cell[0], from_cell[1] + dy)]
            for side_cell in side_cells:
                if not self._is_valid_cell(side_cell, goal, allowed_goal_occupied, static_obstacles):
                    return False
                if reservation.is_cell_reserved(side_cell, next_t, robot_id):
                    return False

        if carrying_rack:
            for cell in self._rack_occupied_cells(to_cell, move):
                if not self._is_valid_cell(cell, goal, allowed_goal_occupied, static_obstacles):
                    return False
                if reservation.is_cell_reserved(cell, next_t, robot_id):
                    return False

        return True

    def _rack_occupied_cells(self, center_cell, move):
        x, y = center_cell
        dx, dy = move
        cells = [(x, y)]
        if dx != 0 or dy != 0:
            cells.append((x + dx, y + dy))
        if abs(dx) == 1 and abs(dy) == 1:
            cells.append((x + dx, y))
            cells.append((x, y + dy))
        return cells

    def _step_cost(self, current_heading, move, next_cell, next_t, carrying_rack, reservation, robot_id):
        if move == (0, 0):
            cost = self.config.wait_cost
        elif abs(move[0]) == 1 and abs(move[1]) == 1:
            cost = 1.41421356237
            cost += 1.0 if carrying_rack else 0.15
        else:
            cost = self.config.move_cost

        if move != (0, 0) and current_heading != (0, 0) and move != current_heading:
            cost += self.config.rack_turn_cost if carrying_rack else self.config.turn_cost

        if reservation.is_soft_reserved(next_cell, next_t, robot_id):
            cost += self.config.congestion_cost

        return cost

    def _new_heading(self, old_heading, move):
        if move == (0, 0):
            return old_heading
        return move

    def _heuristic(self, cell, goal):
        dx = abs(cell[0] - goal[0])
        dy = abs(cell[1] - goal[1])
        return max(dx, dy) + (1.41421356237 - 1.0) * min(dx, dy)

    def _reconstruct(self, came_from, current):
        nodes = [current]
        while current in came_from:
            current = came_from[current]
            nodes.append(current)
        nodes.reverse()
        path = [(n[0], n[1]) for n in nodes]
        timed_path = [(n[0], n[1], n[2]) for n in nodes]
        heading_path = [(n[3], n[4]) for n in nodes]
        return path, timed_path, heading_path

    def _local_detour_fallback(self, request, reservation, static_obstacles, start_time):
        sx, sy = request.start
        candidates = []
        for dx, dy in self.detour_moves_8:
            nx, ny = sx + dx, sy + dy
            candidate = (nx, ny)
            nt = start_time + 1
            if not self._is_valid_cell(candidate, request.goal, request.allowed_goal_occupied, static_obstacles):
                continue
            if reservation.is_cell_reserved(candidate, nt, request.robot_id):
                continue
            if reservation.is_edge_conflict(request.start, candidate, start_time, request.robot_id):
                continue

            dist_to_goal = self._heuristic(candidate, request.goal)
            soft_penalty = self.config.congestion_cost if reservation.is_soft_reserved(candidate, nt, request.robot_id) else 0.0
            score = dist_to_goal + self.config.local_detour_cost + soft_penalty
            candidates.append((score, candidate))

        if not candidates:
            return RobotPlanResult(request.robot_id, [], [], False, "local_detour_failed")

        candidates.sort(key=lambda x: x[0])
        detour_cell = candidates[0][1]
        path = [request.start, detour_cell]
        timed_path = [(request.start[0], request.start[1], start_time), (detour_cell[0], detour_cell[1], start_time + 1)]
        return RobotPlanResult(request.robot_id, path, timed_path, True, "local_detour")


# ==========================================
# 🤖 통합 로봇 에뮬레이터 노드 클래스
# ==========================================
class MockFullRobotNode(Node):
    def __init__(self):
        super().__init__('mock_full_robot_node')
        self.get_logger().info('=== [A* Multi-AMR Controller] 통합 로봇 에뮬레이터 구동 시작 ===')

        # DB 및 Redis 연결
        self.pg_conn = None
        self.redis_client = None
        self.connect_db()

        # A* Planner 및 예약 테이블 초기화
        self.config = TimeAStarConfig()
        self.planner = TimeAStarPlanner(self.config)
        self.reservation = ReservationTable()

        # 5대 AMR 상태 관리 맵 초기화 (충전소 좌표를 시작점으로 배치)
        initial_charging_spots = [
            (16, 35),  # AMR_01 (charging_01)
            (15, 35),  # AMR_02 (charging_02)
            (14, 35),  # AMR_03 (charging_03)
            (13, 35),  # AMR_04 (charging_04)
            (12, 35)   # AMR_05 (charging_05)
        ]
        self.amrs = {}
        for idx, cell in enumerate(initial_charging_spots, 1):
            amr_id = f"AMR_{idx:02d}"
            self.amrs[amr_id] = {
                "id": amr_id,
                "state": "IDLE",  # IDLE, NAVIGATING, LIFTING, DELIVERING, DROPPING, ROTATING
                "current_cell": cell,
                "heading": (1, 0),
                "carrying_workstation_id": None,
                "target_cell": None,
                "path": [],
                "timed_path": [],
                "current_step": 0,
                "task_type": None,  # MANAGE_WS, MOVE_PACKAGE
                "workstation_id": None,
                "workstation_qr_id": None,
                "phase": None,  # TRAVEL_TO_START, LIFT, TRAVEL_TO_GOAL, DROP, ROTATE
                "start_cell": None,
                "destination_cell": None,
                "final_destination": None,
                "wait_steps": 0,
                "stuck_ticks": 0,
                "completed": False,
                "success": False,
                "goal_handle": None,
                "lock": threading.Lock()
            }
        
        # Redis 초기 값 기입
        if self.redis_client:
            for amr_id, amr in self.amrs.items():
                wx, wy = cell_to_world(amr["current_cell"])
                qr_id = f"FLOOR_X_{wx}_Y_{wy}"
                try:
                    self.redis_client.hset(f"amr:{amr_id}", mapping={
                        "state": "IDLE",
                        "current_qr_id": qr_id,
                        "target_qr_id": "",
                        "carrying_workstation_id": "",
                        "battery": "100.0",
                        "available": "true"
                    })
                except Exception as e:
                    self.get_logger().error(f"Failed to set initial AMR state in Redis: {e}")

        # 1. AMR Action Servers
        self._manage_ws_server = ActionServer(
            self,
            ManageWorkstation,
            'manage_workstation',
            execute_callback=self.execute_manage_ws
        )
        self.get_logger().info('Action Server [manage_workstation] 대기 중...')

        self._move_pkg_server = ActionServer(
            self,
            MovePackage,
            'move_package',
            execute_callback=self.execute_move_pkg
        )
        self.get_logger().info('Action Server [move_package] 대기 중...')

        # 2. Packaging Robot Action Server
        self._start_pkg_server = ActionServer(
            self,
            StartPackaging,
            'start_packaging',
            execute_callback=self.execute_start_pkg
        )
        self.get_logger().info('Action Server [start_packaging] 대기 중...')

        # 3. Service Clients (관제탑 호출용)
        self.get_route_client = self.create_client(GetPackageRoute, 'get_package_route')
        self.check_warehouse_client = self.create_client(CheckWarehouseStatus, 'check_warehouse_status')
        self.report_inbound_client = self.create_client(ReportInboundProgress, 'report_inbound_progress')

        # 4. 시뮬레이션 주기적 틱 타이머 기동 (0.45초 주기로 AMR 1격자 이동 업데이트)
        self.timer = self.create_timer(0.45, self.tick_loop)

    def connect_db(self):
        try:
            self.pg_conn = psycopg2.connect(
                host='localhost',
                port=5432,
                user='rokey',
                password='rokey_pass',
                database='warehouse_db'
            )
            self.pg_conn.autocommit = True
            self.get_logger().info('PostgreSQL 연동 완료 (상태 변경 감지용)')
        except Exception as e:
            self.get_logger().error(f'PostgreSQL 연결 실패: {e}')
            
        try:
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True
            )
            self.get_logger().info('Redis 연동 완료')
        except Exception as e:
            self.get_logger().error(f'Redis 연결 실패: {e}')
            self.redis_client = None

    # ==========================================
    # 📍 위치 이름 ➡️ 그리드 셀 변환 헬퍼
    # ==========================================
    def resolve_location_to_cell(self, loc_name: str) -> Optional[GridCell]:
        if not self.pg_conn:
            return None
        # ROTATING/ROTATE 상태 꼬리표 제거
        clean_loc = loc_name.replace('_ROTATING', '').replace('ROTATING', '').replace('_ROTATE', '')
        try:
            with self.pg_conn.cursor() as cursor:
                cursor.execute(
                    "SELECT x_coord, y_coord FROM floor_qr_map WHERE location_name = %s;",
                    (clean_loc,)
                )
                row = cursor.fetchone()
                if row:
                    return world_to_cell(row[0], row[1])
        except Exception as e:
            self.get_logger().error(f"Failed to resolve location coordinates for '{loc_name}': {e}")
        return None

    # ==========================================
    # 🧱 정적 장애물 정보 추출 (미운전 중인 워크스테이션들)
    # ==========================================
    def get_static_obstacles(self) -> Set[GridCell]:
        obstacles = set()
        if not self.pg_conn:
            return obstacles

        # 현재 이동중(AMR이 들고 있는) 워크스테이션 ID 제외 필터링용
        carrying_ws_ids = set()
        for amr in self.amrs.values():
            with amr["lock"]:
                if amr["carrying_workstation_id"]:
                    carrying_ws_ids.add(amr["carrying_workstation_id"])

        try:
            with self.pg_conn.cursor() as cursor:
                cursor.execute("SELECT workstation_id, current_location FROM workstations;")
                rows = cursor.fetchall()
                for ws_id, loc in rows:
                    if ws_id in carrying_ws_ids:
                        continue
                    if not loc:
                        continue
                    # 위치 좌표 획득
                    clean_loc = loc.replace('_ROTATING', '').replace('ROTATING', '').replace('_ROTATE', '')
                    cursor.execute("SELECT x_coord, y_coord FROM floor_qr_map WHERE location_name = %s;", (clean_loc,))
                    row = cursor.fetchone()
                    if row:
                        obstacles.add(world_to_cell(row[0], row[1]))
        except Exception as e:
            self.get_logger().error(f"Error fetching static obstacles from DB: {e}")
        return obstacles

    # ==========================================
    # ⏱️ 0.45초 시뮬레이션 틱 루프 (A* 주행 업데이트)
    # ==========================================
    def tick_loop(self):
        static_obstacles = self.get_static_obstacles()

        # 1. 예약 테이블 리빌드
        self.reservation.clear()
        
        # 각 AMR들의 현재 위치 점유 및 계획된 경로 예약 등록
        for amr_id, amr in self.amrs.items():
            with amr["lock"]:
                if amr["state"] == "IDLE":
                    # IDLE 로봇은 자기 자리 t=0~4 동안 임시 예약하여 방해 방지
                    for t in range(5):
                        self.reservation.reserve_cell(amr["current_cell"], t, amr_id)
                elif amr["state"] in ["NAVIGATING", "DELIVERING"]:
                    # 남은 경로 예약
                    remaining = amr["timed_path"][amr["current_step"]:]
                    for idx, timed_cell in enumerate(remaining):
                        cell = (timed_cell[0], timed_cell[1])
                        self.reservation.reserve_cell(cell, idx, amr_id)
                        if idx > 0:
                            prev_cell = (remaining[idx - 1][0], remaining[idx - 1][1])
                            self.reservation.reserve_edge(prev_cell, cell, idx - 1, amr_id)
                        
                        # 워크스테이션을 들고 가는 경우 주변 공간도 소프트 예약 설정
                        if amr["carrying_workstation_id"]:
                            heading = amr["heading"] if idx == 0 else (cell[0] - prev_cell[0], cell[1] - prev_cell[1])
                            for soft_cell in self.reservation._rack_soft_cells(cell, heading, self.config):
                                if self.reservation._in_bounds(soft_cell, self.config):
                                    self.reservation.reserve_soft_cell(soft_cell, idx, amr_id)

        # 2. 우선순위에 따른 A* 경로 계획 (들고 움직이는 로봇 우선, 그 다음 대기 단계가 긴 로봇)
        sorted_amr_ids = sorted(
            self.amrs.keys(),
            key=lambda aid: (
                -int(self.amrs[aid]["carrying_workstation_id"] is not None),
                -self.amrs[aid]["wait_steps"]
            )
        )

        for amr_id in sorted_amr_ids:
            amr = self.amrs[amr_id]
            with amr["lock"]:
                if amr["state"] in ["NAVIGATING", "DELIVERING"]:
                    need_replan = False
                    
                    # 경로가 유효하지 않거나 막혀있는지 확인
                    if not amr["path"] or amr["current_step"] >= len(amr["path"]) - 1:
                        pass
                    else:
                        next_step_idx = amr["current_step"] + 1
                        next_cell = amr["path"][next_step_idx]
                        
                        # 예약 충돌 확인
                        if self.reservation.is_cell_reserved(next_cell, 1, amr_id) or \
                           self.reservation.is_edge_conflict(amr["current_cell"], next_cell, 0, amr_id) or \
                           self.reservation.is_diagonal_cross_conflict(amr["current_cell"], next_cell, 0, amr_id):
                            need_replan = True
                            amr["stuck_ticks"] += 1
                        else:
                            amr["stuck_ticks"] = 0

                    # 3틱 연속 대기 시 우회 경로 재계획 (stuck-replan)
                    if need_replan and amr["stuck_ticks"] >= 3:
                        carrying = amr["carrying_workstation_id"] is not None
                        req = RobotPlanRequest(
                            robot_id=amr_id,
                            start=amr["current_cell"],
                            goal=amr["destination_cell"],
                            heading=amr["heading"],
                            carrying_rack=carrying,
                            priority=1 if carrying else 0,
                            waiting_steps=amr["wait_steps"]
                        )
                        res = self.planner.plan(req, self.reservation, static_obstacles, start_time=0)
                        if res.success:
                            amr["path"] = res.path
                            amr["timed_path"] = res.timed_path
                            amr["current_step"] = 0
                            amr["stuck_ticks"] = 0
                            # 새 예약 테이블 반영
                            for idx, timed_cell in enumerate(res.timed_path):
                                cell = (timed_cell[0], timed_cell[1])
                                self.reservation.reserve_cell(cell, idx, amr_id)
                                if idx > 0:
                                    prev_cell = (res.timed_path[idx - 1][0], res.timed_path[idx - 1][1])
                                    self.reservation.reserve_edge(prev_cell, cell, idx - 1, amr_id)
                        else:
                            amr["wait_steps"] += 1

        # 3. 로봇 주행 진행 (Step-forward)
        for amr_id, amr in self.amrs.items():
            with amr["lock"]:
                if amr["state"] == "IDLE":
                    continue

                # 적재/하역/회전 대기 타임 처리
                if amr["phase"] in ["LIFT", "DROP", "ROTATE"]:
                    amr["wait_steps"] -= 1
                    if amr["wait_steps"] <= 0:
                        if amr["phase"] == "LIFT":
                            amr["carrying_workstation_id"] = amr["workstation_id"]
                            amr["phase"] = "TRAVEL_TO_GOAL"
                            amr["destination_cell"] = amr["final_destination"]
                            amr["state"] = "DELIVERING"
                            # 목적지로 출발 전 경로 계획
                            req = RobotPlanRequest(
                                robot_id=amr_id,
                                start=amr["current_cell"],
                                goal=amr["destination_cell"],
                                heading=amr["heading"],
                                carrying_rack=True,
                                priority=1,
                                waiting_steps=0
                            )
                            res = self.planner.plan(req, self.reservation, static_obstacles, start_time=0)
                            if res.success:
                                amr["path"] = res.path
                                amr["timed_path"] = res.timed_path
                                amr["current_step"] = 0
                            else:
                                amr["path"] = []
                                amr["timed_path"] = []
                                amr["current_step"] = 0
                                amr["stuck_ticks"] = 3
                        elif amr["phase"] == "DROP":
                            amr["carrying_workstation_id"] = None
                            amr["completed"] = True
                            amr["success"] = True
                            amr["state"] = "IDLE"
                            amr["phase"] = None
                        elif amr["phase"] == "ROTATE":
                            amr["completed"] = True
                            amr["success"] = True
                            amr["state"] = "IDLE"
                            amr["phase"] = None
                    continue

                # 주행 이동 처리
                if amr["phase"] in ["TRAVEL_TO_START", "TRAVEL_TO_GOAL"]:
                    if not amr["path"]:
                        carrying = amr["carrying_workstation_id"] is not None
                        req = RobotPlanRequest(
                            robot_id=amr_id,
                            start=amr["current_cell"],
                            goal=amr["destination_cell"],
                            heading=amr["heading"],
                            carrying_rack=carrying,
                            priority=1 if carrying else 0,
                            waiting_steps=0
                        )
                        res = self.planner.plan(req, self.reservation, static_obstacles, start_time=0)
                        if res.success:
                            amr["path"] = res.path
                            amr["timed_path"] = res.timed_path
                            amr["current_step"] = 0
                        else:
                            continue

                    if amr["stuck_ticks"] == 0:
                        amr["current_step"] += 1
                        if amr["current_step"] < len(amr["path"]):
                            prev_cell = amr["current_cell"]
                            amr["current_cell"] = amr["path"][amr["current_step"]]
                            amr["heading"] = (amr["current_cell"][0] - prev_cell[0], amr["current_cell"][1] - prev_cell[1])

                        if amr["current_step"] >= len(amr["path"]) - 1:
                            if amr["phase"] == "TRAVEL_TO_START":
                                if amr["task_type"] == "MOVE_PACKAGE":
                                    amr["phase"] = "DROP"
                                    amr["wait_steps"] = 2  # 2 ticks drop
                                    amr["state"] = "DROPPING"
                                else:
                                    amr["phase"] = "LIFT"
                                    amr["wait_steps"] = 2  # 2 ticks lift
                                    amr["state"] = "LIFTING"
                            elif amr["phase"] == "TRAVEL_TO_GOAL":
                                amr["phase"] = "DROP"
                                amr["wait_steps"] = 2  # 2 ticks drop
                                amr["state"] = "DROPPING"

        # 4. Redis 상태 업데이트
        if self.redis_client:
            for amr_id, amr in self.amrs.items():
                with amr["lock"]:
                    wx, wy = cell_to_world(amr["current_cell"])
                    qr_id = f"FLOOR_X_{wx}_Y_{wy}"
                    
                    target_qr = ""
                    if amr["destination_cell"]:
                        tx, ty = cell_to_world(amr["destination_cell"])
                        target_qr = f"FLOOR_X_{tx}_Y_{ty}"

                    try:
                        self.redis_client.hset(f"amr:{amr_id}", mapping={
                            "state": amr["state"],
                            "current_qr_id": qr_id,
                            "target_qr_id": target_qr,
                            "carrying_workstation_id": amr["carrying_workstation_id"] or "",
                            "battery": "95.0",
                            "available": "true" if amr["state"] == "IDLE" else "false"
                        })
                    except Exception as e:
                        self.get_logger().error(f"Failed to update AMR {amr_id} state in Redis: {e}")

    # ==========================================
    # 🚀 Action Server: ManageWorkstation (이송/회전)
    # ==========================================
    def execute_manage_ws(self, goal_handle):
        goal = goal_handle.request
        target = goal.target_location
        is_rotation = target.endswith('_ROTATE') or 'ROTATING' in target or 'ROTATING' in goal.start_location

        self.get_logger().info(f'🤖 [AMR Fleet Server] 작업대 이송 명령 수신: {goal.workstation_id} ({goal.start_location} ➡️ {target})')

        start_cell = self.resolve_location_to_cell(goal.start_location)
        target_cell = self.resolve_location_to_cell(target)

        if not start_cell or not target_cell:
            self.get_logger().error(f'❌ 위치 분석 실패: {goal.start_location} 또는 {target}의 좌표가 없습니다.')
            goal_handle.abort()
            result = ManageWorkstation.Result()
            result.success = False
            return result

        # 유휴 AMR 배정
        assigned_amr_id = None
        while rclpy.ok() and assigned_amr_id is None:
            for amr_id, amr in self.amrs.items():
                with amr["lock"]:
                    if amr["state"] == "IDLE":
                        assigned_amr_id = amr_id
                        
                        # Task 정보 주입
                        amr["task_type"] = "MANAGE_WS"
                        amr["workstation_id"] = goal.workstation_id
                        amr["workstation_qr_id"] = goal.workstation_qr_id
                        amr["start_cell"] = start_cell
                        amr["destination_cell"] = start_cell  # 최초 목표는 작업대 위치
                        amr["final_destination"] = target_cell
                        
                        if is_rotation:
                            amr["phase"] = "ROTATE"
                            amr["wait_steps"] = 4  # 회전 소요 시간(4틱)
                            amr["state"] = "ROTATING"
                        else:
                            amr["phase"] = "TRAVEL_TO_START"
                            amr["state"] = "NAVIGATING"
                            
                        amr["path"] = []
                        amr["timed_path"] = []
                        amr["current_step"] = 0
                        amr["stuck_ticks"] = 0
                        amr["wait_steps"] = 0
                        amr["completed"] = False
                        amr["success"] = False
                        amr["goal_handle"] = goal_handle
                        break
            if assigned_amr_id is None:
                time.sleep(0.1)

        self.get_logger().info(f'🤖 {assigned_amr_id} 로봇이 작업 배정되었습니다.')

        # 완료 대기 루프
        amr = self.amrs[assigned_amr_id]
        feedback_msg = ManageWorkstation.Feedback()
        while rclpy.ok():
            with amr["lock"]:
                if amr["completed"]:
                    success = amr["success"]
                    break
                
                # 피드백 송신
                if amr["path"]:
                    rem = len(amr["path"]) - amr["current_step"]
                    feedback_msg.distance_remaining = float(rem)
                else:
                    feedback_msg.distance_remaining = 99.0
                feedback_msg.status = amr["state"]
                goal_handle.publish_feedback(feedback_msg)
            time.sleep(0.2)

        if success:
            goal_handle.succeed()
            result = ManageWorkstation.Result()
            result.success = True
            self.get_logger().info(f'🤖 {assigned_amr_id} 이송 완료 보고!')
            return result
        else:
            goal_handle.abort()
            result = ManageWorkstation.Result()
            result.success = False
            self.get_logger().error(f'🤖 {assigned_amr_id} 이송 실패 또는 중단!')
            return result

    # ==========================================
    # 🚀 Action Server: MovePackage (단일 직송)
    # ==========================================
    def execute_move_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'🤖 [AMR Fleet Server] 단일 패키지 직송 명령 수신: {goal.package_id} ➡️ {goal.destination_zone}')

        target_cell = self.resolve_location_to_cell(goal.destination_zone)
        if not target_cell:
            self.get_logger().error(f'❌ 위치 분석 실패: {goal.destination_zone} 좌표가 없습니다.')
            goal_handle.abort()
            result = MovePackage.Result()
            result.success = False
            return result

        # 유휴 AMR 배정
        assigned_amr_id = None
        while rclpy.ok() and assigned_amr_id is None:
            for amr_id, amr in self.amrs.items():
                with amr["lock"]:
                    if amr["state"] == "IDLE":
                        assigned_amr_id = amr_id
                        
                        amr["task_type"] = "MOVE_PACKAGE"
                        amr["workstation_id"] = None
                        amr["workstation_qr_id"] = None
                        amr["start_cell"] = amr["current_cell"]
                        amr["destination_cell"] = target_cell
                        amr["final_destination"] = target_cell
                        amr["phase"] = "TRAVEL_TO_GOAL"
                        amr["state"] = "DELIVERING"
                        amr["path"] = []
                        amr["timed_path"] = []
                        amr["current_step"] = 0
                        amr["stuck_ticks"] = 0
                        amr["wait_steps"] = 0
                        amr["completed"] = False
                        amr["success"] = False
                        amr["goal_handle"] = goal_handle
                        break
            if assigned_amr_id is None:
                time.sleep(0.1)

        self.get_logger().info(f'🤖 {assigned_amr_id} 로봇이 패키지 직송 작업에 배정되었습니다.')

        amr = self.amrs[assigned_amr_id]
        feedback_msg = MovePackage.Feedback()
        while rclpy.ok():
            with amr["lock"]:
                if amr["completed"]:
                    success = amr["success"]
                    break
                
                feedback_msg.current_position = f"Cell {amr['current_cell']}"
                if amr["path"]:
                    feedback_msg.progress = float(amr["current_step"]) / float(len(amr["path"])) * 100.0
                else:
                    feedback_msg.progress = 0.0
                goal_handle.publish_feedback(feedback_msg)
            time.sleep(0.2)

        if success:
            goal_handle.succeed()
            result = MovePackage.Result()
            result.success = True
            self.get_logger().info(f'🤖 {assigned_amr_id} 패키지 직송 완료 보고!')
            return result
        else:
            goal_handle.abort()
            result = MovePackage.Result()
            result.success = False
            return result

    # ==========================================
    # 📦 Action Server: StartPackaging (포장 로봇 제어)
    # ==========================================
    def execute_start_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'📦 [포장로봇] 작업대 {goal.workstation_id} 포장 지시 수신!')

        feedback_msg = StartPackaging.Feedback()
        for slot in range(1, 9):
            # 4번째 포장이 끝났을 때 AMR이 회전 완료해서 A구역에 들어왔는지 감지 대기
            if slot == 5:
                self.get_logger().info(f'📦 [포장로봇] 4개 슬롯 포장 완료. 작업대 회전을 대기합니다...')
                time.sleep(1.0)
                if self.pg_conn:
                    rotated = False
                    for _ in range(60):  # 최대 30초 대기
                        try:
                            with self.pg_conn.cursor() as cursor:
                                cursor.execute(
                                    "SELECT current_location FROM workstations WHERE workstation_id = %s;",
                                    (goal.workstation_id,)
                                )
                                row = cursor.fetchone()
                                if row and row[0] == 'sg2_out_00_A':
                                    rotated = True
                                    self.get_logger().info(f'📦 [포장로봇] 작업대 {goal.workstation_id} 180도 회전 완료 확인! 작업을 재개합니다.')
                                    break
                        except Exception as e:
                            self.get_logger().error(f'회전 상태 감지 중 오류: {e}')
                        time.sleep(0.5)
                    if not rotated:
                        self.get_logger().warn(f'📦 [포장로봇] 회전 감지 타임아웃! 포장 작업을 그대로 강제 재개합니다.')

            time.sleep(0.4)  # 슬롯당 포장 시간
            feedback_msg.completed_slots = slot
            feedback_msg.last_packed_slot = f"slot_{slot}"
            goal_handle.publish_feedback(feedback_msg)
            self.get_logger().info(f'📦 [포장로봇] {goal.workstation_id} 슬롯 {slot} 포장 완료...')

        goal_handle.succeed()
        result = StartPackaging.Result()
        result.success = True
        result.final_output_ids = [
            f"sg2_out_00_{goal.workstation_id}-{slot}-{goal.today_date}" for slot in range(1, 9)
        ]
        self.get_logger().info(f'📦 [포장로봇] 작업대 {goal.workstation_id} 모든 슬롯 포장 완료 및 출고ID 발행 완료!')
        return result

    # ==========================================
    # 📡 Fail-safe 관제탑 호출 헬퍼
    # ==========================================
    def call_service_with_fail_safe(self, client, request, service_name, fallback_callback):
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            if client.wait_for_service(timeout_sec=1.0):
                self.get_logger().info(f'[{service_name}] 관제 서버 연결 성공 (시도 {attempt}/{max_retries})')
                future = client.call_async(request)
                
                start_time = time.time()
                while rclpy.ok() and not future.done():
                    time.sleep(0.05)
                    if time.time() - start_time > 2.0:
                        self.get_logger().warn(f'[{service_name}] 응답 대기 시간 초과(Timeout)')
                        break
                
                if future.done():
                    res = future.result()
                    if res is not None:
                        return res, False
                self.get_logger().warn(f'[{service_name}] 호출 실패, 재시도 진행... ({attempt}/{max_retries})')
            else:
                self.get_logger().warn(f'[{service_name}] 관제 서버 접속 지연/무응답 (시도 {attempt}/{max_retries})')
            time.sleep(0.5)

        self.get_logger().error(f'❌ [{service_name}] 관제 서버 접속 실패! 로컬 오프라인 룰베이스(Fail-safe)를 기동합니다.')
        fallback_res = fallback_callback(request)
        return fallback_res, True

    def fallback_route(self, request):
        val = sum(ord(c) for c in request.package_id)
        dates = ['2026-06-01', '2026-06-02', '2026-06-03']
        res = GetPackageRoute.Response()
        res.route_destination = dates[val % len(dates)]
        return res

    def fallback_check_warehouse(self, request):
        res = CheckWarehouseStatus.Response()
        res.is_already_in_warehouse = True
        return res

    def fallback_report_inbound(self, request):
        res = ReportInboundProgress.Response()
        res.success = True
        return res


# ==========================================
# 🚚 인바운드 물품 공급 시뮬레이션 루프
# ==========================================
def inbound_sim_loop(node):
    time.sleep(5.0)  # 관제탑 노드 기동 대기
    node.get_logger().info('=== [Scenario Setup] 이중 버퍼 감지 루프 시작 ===')
    node.get_logger().info('=== [Scenario Loop] 자율 물류 적재/포장 루프 가동 ===')

    while rclpy.ok():
        if not node.pg_conn:
            time.sleep(2.0)
            continue

        try:
            with node.pg_conn.cursor() as cursor:
                # 1. WAITING 상태인 패키지 하나 가져오기
                cursor.execute("SELECT package_id, customer_name, qr_id FROM packages WHERE status = 'WAITING' LIMIT 1;")
                pkg_row = cursor.fetchone()
                
                if not pkg_row:
                    node.get_logger().info('[Scenario] 대기 중인 입고 패키지가 없습니다. 신규 입고를 대기합니다...')
                    time.sleep(3.0)
                    continue
                
                pkg_id, cust_name, pkg_qr = pkg_row
                
                # Step A: QR코드 생성 및 카메라 비전 인식 흉내
                qr_file = generate_qr_code(pkg_qr or pkg_id)
                decoded_qr = decode_qr_code(qr_file)
                node.get_logger().info(f'[Scenario] 🚀 패키지 {pkg_id} 입고 처리 시작 (QR: {decoded_qr})')

                # Step B: GetPackageRoute 서비스 호출하여 목적지(날짜) 획득
                req_route = GetPackageRoute.Request()
                req_route.package_id = pkg_id
                req_route.customer_name = cust_name
                req_route.qr_id = decoded_qr
                
                route_res, is_offline = node.call_service_with_fail_safe(
                    node.get_route_client, req_route, 'get_package_route', node.fallback_route
                )
                dest_date = route_res.route_destination
                node.get_logger().info(f'[Scenario]   - 분류 목적지 획득: {dest_date} (오프라인 모드: {is_offline})')

                # Redis 기준 오늘, 내일, 모레 날짜 계산
                today_date = node.redis_client.get('system:today_date') if node.redis_client else '2026-06-06'
                if not today_date:
                    today_date = '2026-06-06'
                try:
                    t_dt = datetime.strptime(today_date, '%Y-%m-%d')
                except ValueError:
                    t_dt = datetime.strptime(today_date, '%Y%m%d')
                tomorrow_date = (t_dt + timedelta(days=1)).strftime('%Y-%m-%d')
                day_after_date = (t_dt + timedelta(days=2)).strftime('%Y-%m-%d')

                # 목적지 날짜에 따른 적재 로봇 결정
                if dest_date == today_date:
                    target_robot = 'sg2_in_01'
                elif dest_date == tomorrow_date:
                    target_robot = 'sg2_in_02'
                elif dest_date == day_after_date:
                    target_robot = 'sg2_in_03'
                else:
                    target_robot = 'sg2_in_01'
                
                # 2. 해당 로봇의 A 구역에 작업대가 배치되어 있는지 확인
                cursor.execute(
                    "SELECT workstation_id, qr_id FROM workstations WHERE current_location = %s LIMIT 1;",
                    (f"{target_robot}_A",)
                )
                ws_row = cursor.fetchone()
                
                if not ws_row:
                    node.get_logger().info(f'[Scenario]   - {target_robot}_A 구역에 작업대가 없습니다. 관제탑의 배치를 대기합니다...')
                    time.sleep(2.0)
                    continue
                
                ws_id, ws_qr = ws_row
                
                # 3. 해당 작업대의 다음 빈 슬롯 확인
                cursor.execute("""
                    SELECT slot_number FROM packages 
                    WHERE workstation_id = %s AND status = 'IN_WORKSTATION';
                """, (ws_id,))
                filled_slots = {r[0] for r in cursor.fetchall()}
                
                next_slot = None
                for s in range(1, 9):
                    if s not in filled_slots:
                        next_slot = s
                        break
                
                if next_slot is None:
                    node.get_logger().info(f'[Scenario]   - 작업대 {ws_id}가 이미 가득 찼습니다. 교체 대기 중...')
                    time.sleep(2.0)
                    continue

                # Step C: CheckWarehouseStatus 서비스 호출
                req_chk = CheckWarehouseStatus.Request()
                req_chk.package_id = pkg_id
                req_chk.customer_name = cust_name
                req_chk.qr_id = decoded_qr
                
                chk_res, is_offline_chk = node.call_service_with_fail_safe(
                    node.check_warehouse_client, req_chk, 'check_warehouse_status', node.fallback_check_warehouse
                )
                
                if chk_res.is_already_in_warehouse:
                    if is_offline_chk:
                        node.get_logger().warn(f'[Scenario] ⚠️ [Fail-safe] 관제탑 오프라인 상태! 패키지 {pkg_id}를 안전 순환 회차로로 이송 조치합니다.')
                    else:
                        node.get_logger().warn(f'[Scenario]   - 패키지 {pkg_id}({cust_name})는 이미 작업대/창고에 있습니다. AMR 직송 명령 대기.')
                    
                    try:
                        with node.pg_conn.cursor() as cursor:
                            cursor.execute(
                                "UPDATE packages SET status = 'IN_WAREHOUSE' WHERE package_id = %s AND status = 'WAITING';",
                                (pkg_id,)
                            )
                            node.get_logger().info(f'[Scenario]   - 패키지 {pkg_id} 상태를 IN_WAREHOUSE로 갱신 (직송 처리 대기 중)')
                    except Exception as db_err:
                        node.get_logger().error(f'[Scenario] DB 상태 갱신 실패: {db_err}')
                    
                    time.sleep(2.0)
                    continue

                # Step D: ReportInboundProgress 서비스 호출 (적재 완료 보고)
                req_in = ReportInboundProgress.Request()
                req_in.workstation_id = ws_id
                req_in.robot_id = target_robot
                req_in.filled_slots_count = next_slot
                req_in.package_id = pkg_id
                req_in.workstation_qr_id = ws_qr
                req_in.package_qr_id = decoded_qr
                
                in_res, is_offline_in = node.call_service_with_fail_safe(
                    node.report_inbound_client, req_in, 'report_inbound_progress', node.fallback_report_inbound
                )
                if is_offline_in:
                    node.get_logger().info(f'[Scenario] ⚠️ [Fail-safe] 슬롯 적재 보고 오프라인 임시 처리 완료: WS {ws_id} - Slot {next_slot}')
                else:
                    node.get_logger().info(f'[Scenario]   - 슬롯 적재 보고 완료: WS {ws_id} - Slot {next_slot} (라인: {target_robot}_A)')
                
                time.sleep(1.5)

        except Exception as e:
            node.get_logger().error(f'[Scenario Loop Error] {e}')
            time.sleep(2.0)


# ==========================================
# 🏁 메인 실행 함수
# ==========================================
def main(args=None):
    rclpy.init(args=args)
    node = MockFullRobotNode()
    
    # 적재 시나리오 루프를 백그라운드 스레드로 실행
    t = threading.Thread(target=inbound_sim_loop, args=(node,))
    t.daemon = True
    t.start()

    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('시뮬레이션 노드 종료 중...')
    finally:
        if node.pg_conn:
            node.pg_conn.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

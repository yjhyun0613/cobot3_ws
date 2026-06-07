from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": False})

from pxr import UsdGeom, UsdShade, UsdLux, Sdf, Gf
import omni.timeline
import omni.usd
import time
import random
import math
from dataclasses import dataclass
from heapq import heappush, heappop
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set


GRID_W = 40
GRID_H = 25
GRID_SPACING = 1.5

AMR_COUNT = 50
RACK_COUNT = 20

AMR_SIZE_M = 0.7
RACK_SIZE_M = 1.3

CELL_STEP_TIME = 0.45
LIFT_TIME = 0.20
PLACE_TIME = 0.20
LIFT_HEIGHT = 0.10

MAX_TIME_HORIZON = 90
RESERVATION_HORIZON = 45
LOOKAHEAD_STEPS = 8
GOAL_HOLD_STEPS = 6

USE_AMR_ASSET = False
USE_RACK_ASSET = False

AMR_ASSET_PATH = "/home/rokey/Downloads/customamr.usd"
RACK_ASSET_PATH = "/home/rokey/isaaclab_ws/isaac_aruco/usd/customrack.usd"

WORLD = "/World"
QR_ROOT = "/World/QR_Grid"
AMR_ROOT = "/World/AMRs"
RACK_ROOT = "/World/Racks"
GOAL_ROOT = "/World/GoalMarkers"

FRAME_SLEEP = 1.0 / 60.0
RANDOM_SEED = 42

MAX_ACTIVE_RACK_TASKS = 20
RACK_COMMAND_MIN_TICK = 5
RACK_COMMAND_MAX_TICK = 20
RACK_COMMAND_INTERVAL_MIN = 3
RACK_COMMAND_INTERVAL_MAX = 12
STUCK_REPLAN_TICKS = 6
COLLISION_LOG_COOLDOWN_TICKS = 1
FORCE_MOVE_ON_WAIT = True
ALLOW_EMERGENCY_8_DIR_DETOUR = True
SECOND_LOOKAHEAD_ENABLED = True
SECOND_LOOKAHEAD_COST_WEIGHT = 0.75
SECOND_LOOKAHEAD_STRICT = False

TRUE_8_WAY_GLOBAL = True
SUPPRESS_GOAL_LOGS = True
SUPPRESS_START_LOGS = True
DIAGONAL_MOVE_COST = 1.41421356237
DIAGONAL_TURN_EXTRA_COST = 0.15
RACK_DIAGONAL_EXTRA_COST = 1.0

LOG_FORCED_MOVE = False
LOG_TICK_SUMMARY = True
LOG_TICK_SUMMARY_INTERVAL = 30
LOG_RACK_COMMANDS = False
LOG_PICKUP_DONE = False
LOG_RACK_DONE = False
LOG_NO_SAFE_MOVE = False

GridCell = Tuple[int, int]
TimedCell = Tuple[int, int, int]
EdgeKey = Tuple[int, int, int, int, int]


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
    amr_size_m: float = AMR_SIZE_M
    rack_size_m: float = RACK_SIZE_M
    max_time_horizon: int = MAX_TIME_HORIZON
    reservation_horizon: int = RESERVATION_HORIZON
    lookahead_steps: int = LOOKAHEAD_STEPS
    move_cost: float = 1.0
    wait_cost: float = 1.2
    turn_cost: float = 0.25
    rack_turn_cost: float = 1.2
    congestion_cost: float = 0.35
    local_detour_cost: float = 0.65
    goal_hold_steps: int = GOAL_HOLD_STEPS
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

    def seed_current_positions(self, requests: List[RobotPlanRequest], start_time: int):
        for req in requests:
            self.reserve_cell(req.start, start_time, req.robot_id)
            self.reserve_cell(req.start, start_time + 1, req.robot_id)

    def reserve_path(self, robot_id: str, timed_path: List[TimedCell], carrying_rack: bool, heading_path: List[GridCell], config: TimeAStarConfig):
        if not timed_path:
            return

        horizon_path = timed_path[: config.reservation_horizon]

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
        self.motion_moves = self.cardinal_moves + self.diagonal_moves if TRUE_8_WAY_GLOBAL else list(self.cardinal_moves)
        self.detour_moves_8 = self.cardinal_moves + self.diagonal_moves

    def plan(self, request: RobotPlanRequest, reservation: ReservationTable, static_obstacles: Set[GridCell], start_time: int = 0) -> RobotPlanResult:
        if request.start == request.goal:
            timed_path = [(request.start[0], request.start[1], start_time)]
            return RobotPlanResult(request.robot_id, [request.start], timed_path, True, "already_at_goal")

        if not self._is_valid_cell(request.start, request.goal, request.allowed_goal_occupied, static_obstacles):
            return RobotPlanResult(request.robot_id, [], [], False, "invalid_start")

        open_heap = []
        came_from: Dict[Tuple[int, int, int, int, int], Tuple[int, int, int, int, int]] = {}
        g_score: Dict[Tuple[int, int, int, int, int], float] = {}

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

    def _get_neighbors(self) -> List[GridCell]:
        moves = list(self.motion_moves)
        moves.append(self.wait_move)
        return moves

    def _is_valid_cell(self, cell: GridCell, goal: GridCell, allowed_goal_occupied: bool, static_obstacles: Set[GridCell]) -> bool:
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

    def _is_transition_safe(
        self,
        robot_id: str,
        from_cell: GridCell,
        to_cell: GridCell,
        t: int,
        next_t: int,
        carrying_rack: bool,
        reservation: ReservationTable,
        move: GridCell,
        goal: GridCell,
        allowed_goal_occupied: bool,
        static_obstacles: Set[GridCell],
    ) -> bool:
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

    def _rack_occupied_cells(self, center_cell: GridCell, move: GridCell) -> List[GridCell]:
        x, y = center_cell
        dx, dy = move
        cells = [(x, y)]

        if dx != 0 or dy != 0:
            cells.append((x + dx, y + dy))

        if abs(dx) == 1 and abs(dy) == 1:
            cells.append((x + dx, y))
            cells.append((x, y + dy))

        return cells

    def _step_cost(self, current_heading: GridCell, move: GridCell, next_cell: GridCell, next_t: int, carrying_rack: bool, reservation: ReservationTable, robot_id: str) -> float:
        if move == (0, 0):
            cost = self.config.wait_cost
        elif abs(move[0]) == 1 and abs(move[1]) == 1:
            cost = DIAGONAL_MOVE_COST
            cost += RACK_DIAGONAL_EXTRA_COST if carrying_rack else DIAGONAL_TURN_EXTRA_COST
        else:
            cost = self.config.move_cost

        if move != (0, 0) and current_heading != (0, 0) and move != current_heading:
            cost += self.config.rack_turn_cost if carrying_rack else self.config.turn_cost

        if reservation.is_soft_reserved(next_cell, next_t, robot_id):
            cost += self.config.congestion_cost

        return cost

    def _new_heading(self, old_heading: GridCell, move: GridCell) -> GridCell:
        if move == (0, 0):
            return old_heading
        return move

    def _heuristic(self, cell: GridCell, goal: GridCell) -> float:
        dx = abs(cell[0] - goal[0])
        dy = abs(cell[1] - goal[1])

        if TRUE_8_WAY_GLOBAL:
            return max(dx, dy) + (DIAGONAL_MOVE_COST - 1.0) * min(dx, dy)

        return dx + dy

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

    def _local_detour_fallback(self, request: RobotPlanRequest, reservation: ReservationTable, static_obstacles: Set[GridCell], start_time: int) -> RobotPlanResult:
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


class FleetTimePlanner:
    def __init__(self, config: TimeAStarConfig):
        self.config = config
        self.reservation = ReservationTable()
        self.planner = TimeAStarPlanner(config)

    def plan_all(self, requests: List[RobotPlanRequest], static_obstacles_by_robot: Dict[str, Set[GridCell]], start_time: int = 0) -> Dict[str, RobotPlanResult]:
        self.reservation.clear()
        self.reservation.seed_current_positions(requests, start_time)

        ordered_requests = sorted(
            requests,
            key=lambda r: (
                -int(r.carrying_rack),
                -r.waiting_steps,
                -r.priority,
                abs(r.start[0] - r.goal[0]) + abs(r.start[1] - r.goal[1]),
                r.robot_id,
            ),
        )

        results: Dict[str, RobotPlanResult] = {}
        for request in ordered_requests:
            static_obstacles = static_obstacles_by_robot.get(request.robot_id, set())
            result = self.planner.plan(request, self.reservation, static_obstacles, start_time)
            results[request.robot_id] = result
            if result.success:
                heading_path = self._heading_path_from_cells(result.path, request.heading)
                self.reservation.reserve_path(request.robot_id, result.timed_path, request.carrying_rack, heading_path, self.config)
        return results

    def _heading_path_from_cells(self, path: List[GridCell], initial_heading: GridCell) -> List[GridCell]:
        if not path:
            return []
        headings = [initial_heading]
        for i in range(1, len(path)):
            px, py = path[i - 1]
            cx, cy = path[i]
            dx = cx - px
            dy = cy - py
            if dx == 0 and dy == 0:
                headings.append(headings[-1])
            else:
                headings.append((dx, dy))
        return headings


@dataclass
class RackState:
    name: str
    prim_path: str
    cell: GridCell
    carried_by: Optional[str] = None
    assigned_to: Optional[str] = None
    goal_cell: Optional[GridCell] = None
    completed_moves: int = 0


@dataclass
class AMRState:
    name: str
    prim_path: str
    cell: GridCell
    world_pos: Tuple[float, float]
    heading: GridCell = (1, 0)
    state: str = "IDLE"
    target_cell: Optional[GridCell] = None
    assigned_rack: Optional[str] = None
    carrying_rack: bool = False
    next_cell: Optional[GridCell] = None
    lookahead2_cell: Optional[GridCell] = None
    move_from: Optional[GridCell] = None
    move_to: Optional[GridCell] = None
    previous_cell: Optional[GridCell] = None
    wait_steps: int = 0
    priority: int = 0
    lift_progress: float = 0.0
    current_goal_cell: Optional[GridCell] = None
    completed_normal_goals: int = 0
    completed_rack_tasks: int = 0


def cell_to_world(cell: GridCell) -> Tuple[float, float]:
    x = (cell[0] - (GRID_W - 1) * 0.5) * GRID_SPACING
    y = (cell[1] - (GRID_H - 1) * 0.5) * GRID_SPACING
    return x, y


def world_z_for_amr():
    return 0.08


def world_z_for_rack():
    return 0.0


def ensure_xform(stage, path):
    prim = stage.GetPrimAtPath(path)
    if prim.IsValid():
        return prim
    return UsdGeom.Xform.Define(stage, path).GetPrim()


def set_xform(prim, translate, scale=(1.0, 1.0, 1.0), rotate=(0.0, 0.0, 0.0)):
    xformable = UsdGeom.Xformable(prim)
    xformable.ClearXformOpOrder()
    api = UsdGeom.XformCommonAPI(prim)
    api.SetTranslate(Gf.Vec3d(float(translate[0]), float(translate[1]), float(translate[2])))
    api.SetRotate(Gf.Vec3f(float(rotate[0]), float(rotate[1]), float(rotate[2])), UsdGeom.XformCommonAPI.RotationOrderXYZ)
    api.SetScale(Gf.Vec3f(float(scale[0]), float(scale[1]), float(scale[2])))


def make_material(stage, path, color, roughness=0.95, metallic=0.0):
    old = stage.GetPrimAtPath(path)
    if old.IsValid():
        return UsdShade.Material(old)
    mat = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path + "/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(metallic))
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def bind_material(prim, mat):
    UsdShade.MaterialBindingAPI(prim).Bind(mat)


def make_cube(stage, path, pos, scale, mat):
    cube = UsdGeom.Cube.Define(stage, path)
    prim = cube.GetPrim()
    cube.GetSizeAttr().Set(1.0)
    set_xform(prim, pos, scale)
    bind_material(prim, mat)
    return prim


def create_stage():
    ctx = omni.usd.get_context()
    ctx.new_stage()
    stage = ctx.get_stage()

    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    stage.SetDefaultPrim(ensure_xform(stage, WORLD))
    ensure_xform(stage, "/World/Looks")
    ensure_xform(stage, QR_ROOT)
    ensure_xform(stage, AMR_ROOT)
    ensure_xform(stage, RACK_ROOT)
    ensure_xform(stage, GOAL_ROOT)

    floor_mat = make_material(stage, "/World/Looks/FloorMat", (0.34, 0.34, 0.34), 0.98)
    qr_mat_a = make_material(stage, "/World/Looks/QRMatA", (0.92, 0.92, 0.88), 0.98)
    qr_mat_b = make_material(stage, "/World/Looks/QRMatB", (0.12, 0.12, 0.12), 0.98)
    amr_mat = make_material(stage, "/World/Looks/AMRMat", (0.05, 0.16, 0.32), 0.95)
    amr_busy_mat = make_material(stage, "/World/Looks/AMRBusyMat", (0.05, 0.34, 0.45), 0.95)
    rack_mat = make_material(stage, "/World/Looks/RackMat", (0.10, 0.45, 0.75), 0.95)
    goal_mat = make_material(stage, "/World/Looks/GoalMat", (0.95, 0.65, 0.05), 0.9)
    rack_goal_mat = make_material(stage, "/World/Looks/RackGoalMat", (0.95, 0.18, 0.05), 0.9)

    floor_w = GRID_W * GRID_SPACING + 3.0
    floor_h = GRID_H * GRID_SPACING + 3.0
    make_cube(stage, "/World/Floor", (0.0, 0.0, -0.025), (floor_w * 0.5, floor_h * 0.5, 0.025), floor_mat)

    dome = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
    dome.CreateIntensityAttr(500.0)
    distant = UsdLux.DistantLight.Define(stage, "/World/DistantLight")
    distant.CreateIntensityAttr(800.0)
    set_xform(distant.GetPrim(), (0, 0, 10), (1, 1, 1), (-45, 0, 35))

    for y in range(GRID_H):
        for x in range(GRID_W):
            wx, wy = cell_to_world((x, y))
            marker_path = f"{QR_ROOT}/QR_{y:02d}_{x:02d}"
            mat = qr_mat_a if (x + y) % 2 == 0 else qr_mat_b
            make_cube(stage, marker_path, (wx, wy, 0.002), (0.18, 0.18, 0.002), mat)

    return stage, {
        "amr": amr_mat,
        "amr_busy": amr_busy_mat,
        "rack": rack_mat,
        "goal": goal_mat,
        "rack_goal": rack_goal_mat,
    }


def create_amr(stage, mats, idx, cell):
    name = f"AMR_{idx:02d}"
    path = f"{AMR_ROOT}/{name}"
    wx, wy = cell_to_world(cell)

    if USE_AMR_ASSET and Path(AMR_ASSET_PATH).exists():
        prim = ensure_xform(stage, path)
        prim.GetReferences().AddReference(AMR_ASSET_PATH)
        set_xform(prim, (wx, wy, world_z_for_amr()), (1.0, 1.0, 1.0))
    else:
        prim = ensure_xform(stage, path)
        make_cube(stage, f"{path}/Body", (0.0, 0.0, 0.0), (AMR_SIZE_M * 0.5, AMR_SIZE_M * 0.5, 0.08), mats["amr"])
        make_cube(stage, f"{path}/Top", (0.0, 0.0, 0.09), (0.22, 0.22, 0.025), mats["amr_busy"])
        set_xform(prim, (wx, wy, world_z_for_amr()), (1.0, 1.0, 1.0))

    return AMRState(name=name, prim_path=path, cell=cell, world_pos=(wx, wy))


def create_rack(stage, mats, idx, cell):
    name = f"RACK_{idx:02d}"
    path = f"{RACK_ROOT}/{name}"
    wx, wy = cell_to_world(cell)

    if USE_RACK_ASSET and Path(RACK_ASSET_PATH).exists():
        prim = ensure_xform(stage, path)
        prim.GetReferences().AddReference(RACK_ASSET_PATH)
        set_xform(prim, (wx, wy, world_z_for_rack()), (1.0, 1.0, 1.0))
    else:
        prim = ensure_xform(stage, path)
        make_cube(stage, f"{path}/BaseShelf", (0.0, 0.0, 0.30), (RACK_SIZE_M * 0.5, RACK_SIZE_M * 0.5, 0.035), mats["rack"])
        make_cube(stage, f"{path}/TopShelf", (0.0, 0.0, 0.90), (RACK_SIZE_M * 0.5, RACK_SIZE_M * 0.5, 0.035), mats["rack"])
        leg_offset = RACK_SIZE_M * 0.42
        for leg_name, lx, ly in [
            ("Leg_FL", -leg_offset, leg_offset),
            ("Leg_FR", leg_offset, leg_offset),
            ("Leg_RL", -leg_offset, -leg_offset),
            ("Leg_RR", leg_offset, -leg_offset),
        ]:
            make_cube(stage, f"{path}/{leg_name}", (lx, ly, 0.45), (0.035, 0.035, 0.45), mats["rack"])
        set_xform(prim, (wx, wy, world_z_for_rack()), (1.0, 1.0, 1.0))

    return RackState(name=name, prim_path=path, cell=cell)


class FleetDemo:
    def __init__(self):
        random.seed(RANDOM_SEED)
        self.stage, self.mats = create_stage()
        self.config = TimeAStarConfig()
        self.planner = FleetTimePlanner(self.config)
        self.amrs: Dict[str, AMRState] = {}
        self.racks: Dict[str, RackState] = {}
        self.goal_cells_in_use: Set[GridCell] = set()
        self.tick = 0
        self.next_rack_command_tick = random.randint(RACK_COMMAND_MIN_TICK, RACK_COMMAND_MAX_TICK)
        self.motion_progress = 1.0
        self.collision_log_last_tick: Dict[str, int] = {}
        self.collision_total_count = 0
        self.collision_type_count = {
            "CELL": 0,
            "EDGE_SWAP": 0,
            "DIAGONAL_CROSS": 0,
            "FOOTPRINT": 0,
            "SWEPT_FOOTPRINT": 0,
        }
        self.no_safe_move_count = 0

        self.spawn_all()
        self.assign_initial_normal_goals()
        self.detect_and_log_collisions(reason="initial_spawn")

        print("\nFleet demo loaded")
        print(f"  QR grid:          {GRID_W * GRID_H} ({GRID_W} x {GRID_H})")
        print(f"  spacing:          {GRID_SPACING} m")
        print(f"  AMRs:             {AMR_COUNT}")
        print(f"  racks:            {RACK_COUNT}")
        print(f"  max rack tasks:   {MAX_ACTIVE_RACK_TASKS}")
        print("  planner:          true 8-way Time-Expanded A* + Reservation Table")
        print("\nBehavior")
        print("  - All 50 AMRs always receive random goals and keep moving.")
        print("  - Rack commands are assigned to random available AMRs, not fixed workers.")
        print("  - After placing a rack, the AMR immediately receives a new random normal goal.")
        print("  - Rack tasks are injected forever while the demo is running.")
        print("  - Cell/edge/footprint collisions are logged in the terminal.")
        print("  - NO-IDLE mode: every non-lift/place AMR is forced to move every tick if any safe neighboring cell exists.")
        print("  - SECOND-LOOKAHEAD mode: each AMR evaluates the next cell and the next-next cell before committing movement.")
        print("\nControls")
        print("  Play  : start / resume")
        print("  Pause : pause")
        print("  Stop  : close and re-run script")

    def spawn_all(self):
        all_cells = [(x, y) for y in range(GRID_H) for x in range(GRID_W)]
        random.shuffle(all_cells)
        used = set()

        rack_cells = []
        for cell in all_cells:
            if len(rack_cells) >= RACK_COUNT:
                break
            if self._is_good_spawn_cell(cell, used):
                rack_cells.append(cell)
                used.add(cell)

        amr_cells = []
        for cell in all_cells:
            if len(amr_cells) >= AMR_COUNT:
                break
            if self._is_good_spawn_cell(cell, used):
                amr_cells.append(cell)
                used.add(cell)

        for i, cell in enumerate(rack_cells, start=1):
            rack = create_rack(self.stage, self.mats, i, cell)
            self.racks[rack.name] = rack

        for i, cell in enumerate(amr_cells, start=1):
            amr = create_amr(self.stage, self.mats, i, cell)
            self.amrs[amr.name] = amr

    def _is_good_spawn_cell(self, cell, used):
        x, y = cell
        if x < 1 or x >= GRID_W - 1 or y < 1 or y >= GRID_H - 1:
            return False
        if cell in used:
            return False
        return True

    def assign_initial_normal_goals(self):
        for amr in self.amrs.values():
            self.assign_new_normal_goal(amr, reason="initial")

    def active_rack_task_count(self) -> int:
        return sum(1 for r in self.racks.values() if r.assigned_to is not None or r.carried_by is not None)

    def release_goal_cell(self, cell: Optional[GridCell]):
        if cell is not None and cell in self.goal_cells_in_use:
            self.goal_cells_in_use.remove(cell)

    def reserve_goal_cell(self, cell: GridCell):
        self.goal_cells_in_use.add(cell)

    def occupied_cells_now(self, exclude_amr: Optional[str] = None) -> Set[GridCell]:
        occupied = set()
        for amr in self.amrs.values():
            if exclude_amr is not None and amr.name == exclude_amr:
                continue
            occupied.add(amr.cell)
        for rack in self.racks.values():
            if rack.carried_by is None:
                occupied.add(rack.cell)
        return occupied

    def random_free_goal(self, exclude: Optional[Set[GridCell]] = None, exclude_amr: Optional[str] = None) -> Optional[GridCell]:
        if exclude is None:
            exclude = set()

        blocked = set(exclude)
        blocked |= self.occupied_cells_now(exclude_amr=exclude_amr)
        blocked |= self.goal_cells_in_use

        candidates = []
        for y in range(1, GRID_H - 1):
            for x in range(1, GRID_W - 1):
                cell = (x, y)
                if cell not in blocked:
                    candidates.append(cell)

        if candidates:
            return random.choice(candidates)

        # Fallback: goal reservation이 너무 빡빡하게 잡혔을 때도 AMR이 멈추지 않도록
        # rack/다른 AMR 현재 위치만 피해서 임시 goal을 준다.
        hard_blocked = set(exclude)
        hard_blocked |= self.occupied_cells_now(exclude_amr=exclude_amr)

        fallback_candidates = []
        for y in range(1, GRID_H - 1):
            for x in range(1, GRID_W - 1):
                cell = (x, y)
                if cell not in hard_blocked:
                    fallback_candidates.append(cell)

        if fallback_candidates:
            return random.choice(fallback_candidates)

        return None

    def assign_new_normal_goal(self, amr: AMRState, reason: str = "normal") -> bool:
        self.release_goal_cell(amr.current_goal_cell)
        self.remove_amr_goal_marker(amr.name)

        goal = self.random_free_goal(exclude_amr=amr.name)
        if goal is None:
            amr.state = "IDLE"
            amr.target_cell = None
            amr.current_goal_cell = None
            if not SUPPRESS_GOAL_LOGS:
                print(f"NORMAL GOAL FAILED | {amr.name} reason=no_free_goal")
            return False

        self.reserve_goal_cell(goal)
        amr.current_goal_cell = goal
        amr.state = "TO_RANDOM_GOAL"
        amr.target_cell = goal
        amr.assigned_rack = None
        amr.carrying_rack = False
        amr.priority = 0
        amr.wait_steps = 0
        amr.next_cell = None
        amr.move_from = None
        amr.move_to = None
        amr.lift_progress = 0.0
        self.create_or_update_amr_goal_marker(amr.name, goal)
        if not SUPPRESS_GOAL_LOGS:
            print(f"NORMAL GOAL | tick={self.tick} {amr.name} -> {goal} reason={reason}")
        return True

    def try_issue_rack_command(self):
        if self.tick < self.next_rack_command_tick:
            return

        self.next_rack_command_tick = self.tick + random.randint(RACK_COMMAND_INTERVAL_MIN, RACK_COMMAND_INTERVAL_MAX)

        if self.active_rack_task_count() >= MAX_ACTIVE_RACK_TASKS:
            return

        available_amrs = [
            a for a in self.amrs.values()
            if a.state == "TO_RANDOM_GOAL"
            and not a.carrying_rack
            and a.assigned_rack is None
            and a.move_from is None
        ]
        available_racks = [r for r in self.racks.values() if r.assigned_to is None and r.carried_by is None]

        if not available_amrs or not available_racks:
            return

        amr = random.choice(available_amrs)
        near_racks = sorted(available_racks, key=lambda r: abs(r.cell[0] - amr.cell[0]) + abs(r.cell[1] - amr.cell[1]))
        rack = random.choice(near_racks[: min(8, len(near_racks))])
        self.assign_rack_command(amr, rack)

    def assign_rack_command(self, amr: AMRState, rack: RackState) -> bool:
        if rack.assigned_to is not None or rack.carried_by is not None:
            return False

        self.release_goal_cell(amr.current_goal_cell)
        self.remove_amr_goal_marker(amr.name)
        amr.current_goal_cell = None

        exclude = {r.cell for r in self.racks.values() if r.name != rack.name and r.carried_by is None}
        goal = self.random_free_goal(exclude=exclude, exclude_amr=amr.name)
        if goal is None:
            self.assign_new_normal_goal(amr, reason="rack_command_failed_no_goal")
            return False

        self.reserve_goal_cell(goal)
        amr.current_goal_cell = goal
        amr.state = "TO_RACK"
        amr.target_cell = rack.cell
        amr.assigned_rack = rack.name
        amr.carrying_rack = False
        amr.priority = 3
        amr.wait_steps = 0
        amr.next_cell = None
        amr.move_from = None
        amr.move_to = None
        amr.lift_progress = 0.0

        rack.assigned_to = amr.name
        rack.goal_cell = goal
        self.create_or_update_rack_goal_marker(rack.name, goal)

        if not SUPPRESS_GOAL_LOGS:
            if LOG_RACK_COMMANDS:
                print(f"RACK COMMAND | tick={self.tick} {amr.name} -> {rack.name} pickup={rack.cell} drop={goal}")
        else:
            if LOG_RACK_COMMANDS:
                print(f"RACK COMMAND | tick={self.tick} {amr.name} -> {rack.name}")
        return True

    def create_or_update_amr_goal_marker(self, amr_name: str, cell: GridCell):
        path = f"{GOAL_ROOT}/Goal_{amr_name}"
        wx, wy = cell_to_world(cell)
        prim = self.stage.GetPrimAtPath(path)
        if not prim.IsValid():
            make_cube(self.stage, path, (wx, wy, 0.025), (0.18, 0.18, 0.025), self.mats["goal"])
        else:
            set_xform(prim, (wx, wy, 0.025), (0.18, 0.18, 0.025))

    def remove_amr_goal_marker(self, amr_name: str):
        path = f"{GOAL_ROOT}/Goal_{amr_name}"
        if self.stage.GetPrimAtPath(path).IsValid():
            self.stage.RemovePrim(path)

    def create_or_update_rack_goal_marker(self, rack_name: str, cell: GridCell):
        path = f"{GOAL_ROOT}/RackGoal_{rack_name}"
        wx, wy = cell_to_world(cell)
        prim = self.stage.GetPrimAtPath(path)
        if not prim.IsValid():
            make_cube(self.stage, path, (wx, wy, 0.06), (0.30, 0.30, 0.035), self.mats["rack_goal"])
        else:
            set_xform(prim, (wx, wy, 0.06), (0.30, 0.30, 0.035))

    def remove_rack_goal_marker(self, rack_name: str):
        path = f"{GOAL_ROOT}/RackGoal_{rack_name}"
        if self.stage.GetPrimAtPath(path).IsValid():
            self.stage.RemovePrim(path)

    def static_obstacles_for(self, amr: AMRState) -> Set[GridCell]:
        obstacles = set()
        for rack in self.racks.values():
            if rack.carried_by is not None:
                continue
            if amr.state == "TO_RACK" and amr.assigned_rack == rack.name:
                continue
            obstacles.add(rack.cell)
        return obstacles

    def _in_bounds_cell(self, cell: GridCell) -> bool:
        x, y = cell
        return 0 <= x < GRID_W and 0 <= y < GRID_H

    def _movement_candidate_dirs(self, amr: AMRState) -> List[GridCell]:
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        random.shuffle(dirs)
        return dirs

    def _cell_static_blocked_for_amr(self, amr: AMRState, cell: GridCell) -> bool:
        if not self._in_bounds_cell(cell):
            return True

        if cell in self.static_obstacles_for(amr):
            if amr.state == "TO_RACK" and amr.target_cell == cell:
                return False
            return True

        return False

    def _is_cell_occupied_by_other_amr(self, cell: GridCell, amr_name: str) -> bool:
        for other in self.amrs.values():
            if other.name == amr_name:
                continue
            if other.cell == cell:
                return True
        return False

    def _runtime_half_extent(self, amr: AMRState) -> float:
        return (RACK_SIZE_M if amr.carrying_rack else AMR_SIZE_M) * 0.5

    def _point_segment_distance_2d(self, p, a, b) -> float:
        px, py = p
        ax, ay = a
        bx, by = b
        vx = bx - ax
        vy = by - ay
        wx = px - ax
        wy = py - ay
        denom = vx * vx + vy * vy
        if denom <= 1e-12:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
        qx = ax + t * vx
        qy = ay + t * vy
        return math.hypot(px - qx, py - qy)

    def _segments_intersect_2d(self, a, b, c, d) -> bool:
        def orient(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

        def on_segment(p, q, r):
            return (min(p[0], r[0]) - 1e-9 <= q[0] <= max(p[0], r[0]) + 1e-9 and
                    min(p[1], r[1]) - 1e-9 <= q[1] <= max(p[1], r[1]) + 1e-9)

        o1 = orient(a, b, c)
        o2 = orient(a, b, d)
        o3 = orient(c, d, a)
        o4 = orient(c, d, b)

        if o1 * o2 < 0 and o3 * o4 < 0:
            return True
        if abs(o1) < 1e-9 and on_segment(a, c, b):
            return True
        if abs(o2) < 1e-9 and on_segment(a, d, b):
            return True
        if abs(o3) < 1e-9 and on_segment(c, a, d):
            return True
        if abs(o4) < 1e-9 and on_segment(c, b, d):
            return True
        return False

    def _segment_distance_world(self, a0_cell: GridCell, a1_cell: GridCell, b0_cell: GridCell, b1_cell: GridCell) -> float:
        a0 = cell_to_world(a0_cell)
        a1 = cell_to_world(a1_cell)
        b0 = cell_to_world(b0_cell)
        b1 = cell_to_world(b1_cell)

        if self._segments_intersect_2d(a0, a1, b0, b1):
            return 0.0

        return min(
            self._point_segment_distance_2d(a0, b0, b1),
            self._point_segment_distance_2d(a1, b0, b1),
            self._point_segment_distance_2d(b0, a0, a1),
            self._point_segment_distance_2d(b1, a0, a1),
        )

    def _is_swept_segment_safe_against_planned_edges(
        self,
        amr: AMRState,
        from_cell: GridCell,
        to_cell: GridCell,
        planned_edges: Dict[Tuple[GridCell, GridCell], str],
    ) -> bool:
        if to_cell == from_cell:
            return True

        for (other_from, other_to), other_name in planned_edges.items():
            if other_name == amr.name:
                continue

            other = self.amrs.get(other_name)
            if other is None:
                continue

            if other_from == other_to:
                continue

            distance = self._segment_distance_world(from_cell, to_cell, other_from, other_to)
            threshold = self._runtime_half_extent(amr) + self._runtime_half_extent(other)
            if distance < threshold - 1e-6:
                return False

        return True

    def _is_move_segment_safe_for_tick(
        self,
        amr: AMRState,
        from_cell: GridCell,
        to_cell: GridCell,
        planned_destinations: Dict[GridCell, str],
        planned_edges: Dict[Tuple[GridCell, GridCell], str],
        allow_same_cell: bool = False,
    ) -> bool:
        if to_cell == from_cell:
            return allow_same_cell

        if self._cell_static_blocked_for_amr(amr, to_cell):
            return False

        if to_cell in planned_destinations and planned_destinations[to_cell] != amr.name:
            return False

        if self._is_cell_occupied_by_other_amr(to_cell, amr.name):
            return False

        reverse_edge = (to_cell, from_cell)
        if reverse_edge in planned_edges and planned_edges[reverse_edge] != amr.name:
            return False

        if not self._is_swept_segment_safe_against_planned_edges(amr, from_cell, to_cell, planned_edges):
            return False

        dx = to_cell[0] - from_cell[0]
        dy = to_cell[1] - from_cell[1]

        if abs(dx) == 1 and abs(dy) == 1:
            side_a = (from_cell[0] + dx, from_cell[1])
            side_b = (from_cell[0], from_cell[1] + dy)

            for side_cell in (side_a, side_b):
                if self._cell_static_blocked_for_amr(amr, side_cell):
                    return False
                if side_cell in planned_destinations and planned_destinations[side_cell] != amr.name:
                    return False
                if self._is_cell_occupied_by_other_amr(side_cell, amr.name):
                    return False

            cross_edge_1 = (side_a, side_b)
            cross_edge_2 = (side_b, side_a)
            if cross_edge_1 in planned_edges and planned_edges[cross_edge_1] != amr.name:
                return False
            if cross_edge_2 in planned_edges and planned_edges[cross_edge_2] != amr.name:
                return False

        if amr.carrying_rack:
            for fp_cell in self._rack_runtime_footprint_cells(to_cell, (dx, dy)):
                if fp_cell == to_cell:
                    continue
                if self._cell_static_blocked_for_amr(amr, fp_cell):
                    return False
                if fp_cell in planned_destinations and planned_destinations[fp_cell] != amr.name:
                    return False
                if self._is_cell_occupied_by_other_amr(fp_cell, amr.name):
                    return False

        return True

    def _rack_runtime_footprint_cells(self, center_cell: GridCell, move: GridCell) -> List[GridCell]:
        x, y = center_cell
        dx, dy = move
        cells = [(x, y)]

        if dx != 0 or dy != 0:
            cells.append((x + dx, y + dy))

        if abs(dx) == 1 and abs(dy) == 1:
            cells.append((x + dx, y))
            cells.append((x, y + dy))

        return cells

    def _is_next_cell_safe_for_tick(
        self,
        amr: AMRState,
        next_cell: GridCell,
        planned_destinations: Dict[GridCell, str],
        planned_edges: Dict[Tuple[GridCell, GridCell], str],
    ) -> bool:
        return self._is_move_segment_safe_for_tick(
            amr=amr,
            from_cell=amr.cell,
            to_cell=next_cell,
            planned_destinations=planned_destinations,
            planned_edges=planned_edges,
            allow_same_cell=False,
        )

    def _lookahead_candidate_dirs(self, amr: AMRState) -> List[GridCell]:
        return [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]

    def _is_second_cell_safe_for_tick(
        self,
        amr: AMRState,
        first_cell: GridCell,
        second_cell: GridCell,
        planned_destinations: Dict[GridCell, str],
        planned_edges: Dict[Tuple[GridCell, GridCell], str],
    ) -> bool:
        if second_cell == first_cell:
            return True

        if second_cell == amr.cell:
            return False

        return self._is_move_segment_safe_for_tick(
            amr=amr,
            from_cell=first_cell,
            to_cell=second_cell,
            planned_destinations=planned_destinations,
            planned_edges=planned_edges,
            allow_same_cell=False,
        )

    def _best_second_step_score(
        self,
        amr: AMRState,
        first_cell: GridCell,
        planned_destinations: Dict[GridCell, str],
        planned_edges: Dict[Tuple[GridCell, GridCell], str],
    ) -> Tuple[float, int]:
        goal = amr.target_cell if amr.target_cell is not None else first_cell

        if first_cell == goal:
            return 0.0, 1

        best_score = float("inf")
        safe_count = 0

        for dx, dy in self._lookahead_candidate_dirs(amr):
            second_cell = (first_cell[0] + dx, first_cell[1] + dy)

            if not self._is_second_cell_safe_for_tick(amr, first_cell, second_cell, planned_destinations, planned_edges):
                continue

            safe_count += 1
            dist = abs(second_cell[0] - goal[0]) + abs(second_cell[1] - goal[1])
            turn_penalty = 0.0 if (dx, dy) == amr.heading else (1.0 if amr.carrying_rack else 0.25)
            score = dist + turn_penalty
            best_score = min(best_score, score)

        return best_score, safe_count

    def _choose_forced_move(
        self,
        amr: AMRState,
        planned_destinations: Dict[GridCell, str],
        planned_edges: Dict[Tuple[GridCell, GridCell], str],
    ) -> Optional[GridCell]:
        if amr.target_cell is None:
            if not self.assign_new_normal_goal(amr, reason="force_goal_missing"):
                return None

        candidates = []
        fallback_candidates = []

        for dx, dy in self._movement_candidate_dirs(amr):
            candidate = (amr.cell[0] + dx, amr.cell[1] + dy)

            if not self._is_next_cell_safe_for_tick(amr, candidate, planned_destinations, planned_edges):
                continue

            goal = amr.target_cell if amr.target_cell is not None else candidate
            dist = abs(candidate[0] - goal[0]) + abs(candidate[1] - goal[1])
            turn_penalty = 0.0 if (dx, dy) == amr.heading else (1.0 if amr.carrying_rack else 0.25)
            edge_noise = random.random() * 0.05
            base_score = dist + turn_penalty + edge_noise

            if SECOND_LOOKAHEAD_ENABLED:
                second_score, second_count = self._best_second_step_score(amr, candidate, planned_destinations, planned_edges)

                if second_count <= 0 and candidate != goal:
                    fallback_candidates.append((base_score + 10.0, candidate))
                    continue

                base_score += SECOND_LOOKAHEAD_COST_WEIGHT * second_score

            candidates.append((base_score, candidate))

        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[0][1]

        if fallback_candidates and not SECOND_LOOKAHEAD_STRICT:
            fallback_candidates.sort(key=lambda item: item[0])
            return fallback_candidates[0][1]

        return None

    def _apply_tick_move(
        self,
        amr: AMRState,
        next_cell: Optional[GridCell],
        planned_destinations: Dict[GridCell, str],
        planned_edges: Dict[Tuple[GridCell, GridCell], str],
        reason: str,
        lookahead2_cell: Optional[GridCell] = None,
    ) -> bool:
        if next_cell is None or next_cell == amr.cell:
            next_cell = self._choose_forced_move(amr, planned_destinations, planned_edges)
            lookahead2_cell = None
            reason = f"forced_{reason}"

        if next_cell is None:
            amr.next_cell = amr.cell
            amr.lookahead2_cell = None
            amr.move_from = amr.cell
            amr.move_to = amr.cell
            amr.wait_steps += 1
            self.log_no_safe_move(
                f"no_move:{amr.name}:{self.tick}",
                f"NO SAFE MOVE | tick={self.tick} {amr.name} state={amr.state} cell={amr.cell} target={amr.target_cell} reason={reason}",
            )
            return False

        if not self._is_next_cell_safe_for_tick(amr, next_cell, planned_destinations, planned_edges):
            forced = self._choose_forced_move(amr, planned_destinations, planned_edges)
            if forced is None:
                amr.next_cell = amr.cell
                amr.lookahead2_cell = None
                amr.move_from = amr.cell
                amr.move_to = amr.cell
                amr.wait_steps += 1
                self.log_no_safe_move(
                    f"no_move:{amr.name}:{self.tick}",
                    f"NO SAFE MOVE | tick={self.tick} {amr.name} state={amr.state} cell={amr.cell} target={amr.target_cell} reason=unsafe_{reason}",
                )
                return False
            next_cell = forced
            lookahead2_cell = None
            reason = f"forced_unsafe_{reason}"

        if SECOND_LOOKAHEAD_ENABLED:
            second_ok = True

            if lookahead2_cell is not None and next_cell != amr.target_cell:
                second_ok = self._is_second_cell_safe_for_tick(
                    amr,
                    next_cell,
                    lookahead2_cell,
                    planned_destinations,
                    planned_edges,
                )
            else:
                _, second_count = self._best_second_step_score(amr, next_cell, planned_destinations, planned_edges)
                second_ok = second_count > 0 or next_cell == amr.target_cell

            if not second_ok:
                forced = self._choose_forced_move(amr, planned_destinations, planned_edges)
                if forced is None:
                    amr.next_cell = amr.cell
                    amr.lookahead2_cell = None
                    amr.move_from = amr.cell
                    amr.move_to = amr.cell
                    amr.wait_steps += 1
                    self.log_no_safe_move(
                        f"no_second_step:{amr.name}:{self.tick}",
                        f"NO SECOND LOOKAHEAD MOVE | tick={self.tick} {amr.name} state={amr.state} cell={amr.cell} next={next_cell} second={lookahead2_cell} target={amr.target_cell} reason={reason}",
                    )
                    return False

                next_cell = forced
                lookahead2_cell = None
                reason = f"forced_second_lookahead_{reason}"

        amr.next_cell = next_cell
        amr.lookahead2_cell = lookahead2_cell
        amr.move_from = amr.cell
        amr.move_to = next_cell
        amr.wait_steps = 0
        planned_destinations[next_cell] = amr.name
        planned_edges[(amr.cell, next_cell)] = amr.name

        if LOG_FORCED_MOVE and reason.startswith("forced") and self.tick % 8 == 0:
            print(f"FORCED MOVE | tick={self.tick} {amr.name} {amr.cell}->{next_cell} lookahead2={lookahead2_cell} state={amr.state} reason={reason}")

        return True

    def start_motion_tick(self):
        self.try_issue_rack_command()

        requests = []
        static_by_robot = {}

        for amr in self.amrs.values():
            amr.previous_cell = amr.cell

            if amr.state == "IDLE":
                self.assign_new_normal_goal(amr, reason="no_idle_tick_recovery")

            if amr.state not in ["TO_RANDOM_GOAL", "TO_RACK", "TO_RACK_GOAL"]:
                amr.next_cell = amr.cell
                amr.move_from = amr.cell
                amr.move_to = amr.cell
                continue

            if amr.target_cell is None:
                self.assign_new_normal_goal(amr, reason="target_missing_recovery")

            if amr.target_cell is None:
                amr.next_cell = amr.cell
                amr.move_from = amr.cell
                amr.move_to = amr.cell
                continue

            request = RobotPlanRequest(
                robot_id=amr.name,
                start=amr.cell,
                goal=amr.target_cell,
                heading=amr.heading,
                carrying_rack=amr.carrying_rack,
                priority=amr.priority,
                waiting_steps=amr.wait_steps,
                allowed_goal_occupied=(amr.state == "TO_RACK"),
            )
            requests.append(request)
            static_by_robot[amr.name] = self.static_obstacles_for(amr)

        results = self.planner.plan_all(requests, static_by_robot, start_time=self.tick)

        moving_count = 0
        waiting_count = 0
        failed_count = 0
        planned_destinations: Dict[GridCell, str] = {}
        planned_edges: Dict[Tuple[GridCell, GridCell], str] = {}

        ordered_amrs = sorted(
            self.amrs.values(),
            key=lambda a: (-int(a.carrying_rack), -a.priority, -a.wait_steps, a.name),
        )

        for amr in ordered_amrs:
            if amr.state not in ["TO_RANDOM_GOAL", "TO_RACK", "TO_RACK_GOAL"]:
                # LIFTING/PLACING은 작업 중이라 이동하지 않는다. 시간이 짧게 설정되어 있어 다음 tick에 다시 이동 상태가 된다.
                continue

            result = results.get(amr.name)
            proposed_next = None
            proposed_lookahead2 = None
            reason = "no_result"

            if result is not None and result.success and len(result.path) >= 2:
                proposed_next = result.path[1]
                if len(result.path) >= 3:
                    proposed_lookahead2 = result.path[2]
                reason = result.reason
            elif result is not None and result.success:
                proposed_next = None
                proposed_lookahead2 = None
                reason = "astar_wait"
            elif result is not None:
                proposed_next = None
                reason = result.reason
                failed_count += 1
                self.handle_stuck_if_needed(amr, result.reason)

            moved = self._apply_tick_move(
                amr=amr,
                next_cell=proposed_next,
                planned_destinations=planned_destinations,
                planned_edges=planned_edges,
                reason=reason,
                lookahead2_cell=proposed_lookahead2,
            )

            if moved:
                moving_count += 1
            else:
                waiting_count += 1

        # 혹시라도 이동 명령이 비어 있는 AMR은 즉시 복구한다.
        for amr in self.amrs.values():
            if amr.state == "IDLE":
                self.assign_new_normal_goal(amr, reason="post_plan_idle_recovery")
            if amr.state in ["TO_RANDOM_GOAL", "TO_RACK", "TO_RACK_GOAL"] and (amr.move_to is None or amr.move_from is None):
                recovered = self._apply_tick_move(
                    amr=amr,
                    next_cell=None,
                    planned_destinations=planned_destinations,
                    planned_edges=planned_edges,
                    reason="post_plan_missing_motion",
                )
                if recovered:
                    moving_count += 1
                else:
                    waiting_count += 1

        if LOG_TICK_SUMMARY and self.tick % LOG_TICK_SUMMARY_INTERVAL == 0:
            carrying = sum(1 for a in self.amrs.values() if a.carrying_rack)
            active_rack = self.active_rack_task_count()
            active_motion_states = sum(1 for a in self.amrs.values() if a.state in ["TO_RANDOM_GOAL", "TO_RACK", "TO_RACK_GOAL"])
            task_states = sum(1 for a in self.amrs.values() if a.state in ["LIFTING", "PLACING"])
            print(f"TICK {self.tick} | moving={moving_count} wait={waiting_count} fail={failed_count} task_static={task_states} active_motion={active_motion_states} carrying={carrying} rack_active={active_rack} collisions={self.collision_total_count} no_safe={self.no_safe_move_count} detail={self.collision_type_count}")

        self.motion_progress = 0.0

    def handle_stuck_if_needed(self, amr: AMRState, reason: str):
        if amr.wait_steps < STUCK_REPLAN_TICKS:
            return

        if amr.state == "TO_RANDOM_GOAL":
            print(f"STUCK REASSIGN | tick={self.tick} {amr.name} state={amr.state} reason={reason}")
            self.assign_new_normal_goal(amr, reason="stuck_reassign")
            return

        if amr.state == "TO_RACK":
            rack = self.racks.get(amr.assigned_rack)
            if rack is not None:
                rack.assigned_to = None
                rack.goal_cell = None
                self.remove_rack_goal_marker(rack.name)
            print(f"RACK COMMAND CANCELLED | tick={self.tick} {amr.name} reason=stuck_to_rack")
            self.assign_new_normal_goal(amr, reason="stuck_to_rack_cancelled")
            return

        if amr.state == "TO_RACK_GOAL" and amr.carrying_rack:
            rack = self.racks.get(amr.assigned_rack)
            if rack is not None:
                self.release_goal_cell(rack.goal_cell)
                self.remove_rack_goal_marker(rack.name)
                new_goal = self.random_free_goal(exclude_amr=amr.name)
                if new_goal is not None:
                    self.reserve_goal_cell(new_goal)
                    rack.goal_cell = new_goal
                    amr.current_goal_cell = new_goal
                    amr.target_cell = new_goal
                    self.create_or_update_rack_goal_marker(rack.name, new_goal)
                    amr.wait_steps = 0
                    if not SUPPRESS_GOAL_LOGS:
                        print(f"RACK DROP GOAL REASSIGNED | tick={self.tick} {amr.name} {rack.name} -> {new_goal}")

    def update(self, dt):
        self.update_lift_and_place(dt)

        if self.motion_progress >= 1.0:
            self.start_motion_tick()

        self.motion_progress = min(1.0, self.motion_progress + dt / CELL_STEP_TIME)
        self.animate_motion(self.motion_progress)

        if self.motion_progress >= 1.0:
            self.finish_motion_tick()

    def animate_motion(self, alpha: float):
        for amr in self.amrs.values():
            if amr.move_from is None or amr.move_to is None:
                wx, wy = cell_to_world(amr.cell)
            else:
                from_world = cell_to_world(amr.move_from)
                to_world = cell_to_world(amr.move_to)
                wx = from_world[0] * (1.0 - alpha) + to_world[0] * alpha
                wy = from_world[1] * (1.0 - alpha) + to_world[1] * alpha

            self.set_amr_world(amr, wx, wy)

            if amr.carrying_rack and amr.assigned_rack in self.racks:
                rack = self.racks[amr.assigned_rack]
                self.set_rack_world(rack, wx, wy, LIFT_HEIGHT)

    def finish_motion_tick(self):
        transitions = {}

        for amr in self.amrs.values():
            old_cell = amr.cell
            new_cell = amr.move_to if amr.move_to is not None else amr.cell
            transitions[amr.name] = (old_cell, new_cell)

        for amr in self.amrs.values():
            old_cell, new_cell = transitions[amr.name]
            amr.previous_cell = old_cell
            amr.cell = new_cell

            dx = new_cell[0] - old_cell[0]
            dy = new_cell[1] - old_cell[1]
            if dx != 0 or dy != 0:
                amr.heading = (dx, dy)

            amr.move_from = None
            amr.move_to = None
            amr.next_cell = None
            amr.lookahead2_cell = None
            amr.lookahead2_cell = None

        self.tick += 1
        self.handle_arrivals()
        self.detect_and_log_collisions(reason="after_tick")
        self.motion_progress = 1.0

    def handle_arrivals(self):
        for amr in self.amrs.values():
            if amr.target_cell is None:
                continue
            if amr.cell != amr.target_cell:
                continue

            if amr.state == "TO_RANDOM_GOAL":
                amr.completed_normal_goals += 1
                if not SUPPRESS_GOAL_LOGS:
                    print(f"NORMAL GOAL DONE | tick={self.tick} {amr.name} at={amr.cell} count={amr.completed_normal_goals}")
                self.assign_new_normal_goal(amr, reason="normal_goal_done")

            elif amr.state == "TO_RACK":
                amr.state = "LIFTING"
                amr.lift_progress = 0.0
                amr.target_cell = None
                if not SUPPRESS_START_LOGS:
                    print(f"PICKUP START | tick={self.tick} {amr.name} -> {amr.assigned_rack}")

            elif amr.state == "TO_RACK_GOAL":
                amr.state = "PLACING"
                amr.lift_progress = 0.0
                amr.target_cell = None
                if not SUPPRESS_START_LOGS:
                    print(f"PLACE START | tick={self.tick} {amr.name} -> {amr.assigned_rack}")

    def update_lift_and_place(self, dt):
        for amr in self.amrs.values():
            if amr.state == "IDLE":
                self.assign_new_normal_goal(amr, reason="idle_recovery")
                continue

            if amr.state == "LIFTING":
                self.update_lifting(amr, dt)
            elif amr.state == "PLACING":
                self.update_placing(amr, dt)

    def update_lifting(self, amr: AMRState, dt):
        rack = self.racks.get(amr.assigned_rack)
        if rack is None:
            self.assign_new_normal_goal(amr, reason="missing_rack_lift")
            return

        amr.lift_progress += dt / LIFT_TIME
        alpha = min(amr.lift_progress, 1.0)
        wx, wy = cell_to_world(amr.cell)
        self.set_rack_world(rack, wx, wy, LIFT_HEIGHT * alpha)

        if alpha >= 1.0:
            rack.carried_by = amr.name
            rack.cell = amr.cell
            amr.carrying_rack = True
            amr.state = "TO_RACK_GOAL"
            amr.target_cell = rack.goal_cell
            amr.priority = 5
            amr.wait_steps = 0
            amr.move_from = None
            amr.move_to = None
            if LOG_PICKUP_DONE:
                print(f"PICKUP DONE | tick={self.tick} {amr.name} carrying={rack.name} goal={rack.goal_cell}")

    def update_placing(self, amr: AMRState, dt):
        rack = self.racks.get(amr.assigned_rack)
        if rack is None:
            self.assign_new_normal_goal(amr, reason="missing_rack_place")
            return

        amr.lift_progress += dt / PLACE_TIME
        alpha = min(amr.lift_progress, 1.0)
        wx, wy = cell_to_world(amr.cell)
        self.set_rack_world(rack, wx, wy, LIFT_HEIGHT * (1.0 - alpha))

        if alpha >= 1.0:
            self.release_goal_cell(rack.goal_cell)
            self.remove_rack_goal_marker(rack.name)

            rack.cell = amr.cell
            rack.carried_by = None
            rack.assigned_to = None
            rack.goal_cell = None
            rack.completed_moves += 1

            finished_rack = amr.assigned_rack
            amr.completed_rack_tasks += 1
            amr.carrying_rack = False
            amr.assigned_rack = None
            amr.target_cell = None
            amr.current_goal_cell = None
            amr.state = "IDLE"
            amr.priority = 0
            amr.wait_steps = 0
            amr.move_from = None
            amr.move_to = None

            if LOG_RACK_DONE:
                print(f"RACK TASK DONE | tick={self.tick} {amr.name} placed={finished_rack} at={rack.cell} amr_count={amr.completed_rack_tasks} rack_count={rack.completed_moves}")
            self.assign_new_normal_goal(amr, reason="rack_task_done")

    def detect_and_log_collisions(self, reason: str):
        cell_owners: Dict[GridCell, List[str]] = {}
        for amr in self.amrs.values():
            cell_owners.setdefault(amr.cell, []).append(amr.name)

        for cell, names in cell_owners.items():
            if len(names) > 1:
                key = f"cell:{cell}:{','.join(sorted(names))}"
                self.log_collision("CELL", key, f"CELL COLLISION | tick={self.tick} cell={cell} robots={names} reason={reason}")

        amr_list = list(self.amrs.values())
        for i in range(len(amr_list)):
            a = amr_list[i]
            for j in range(i + 1, len(amr_list)):
                b = amr_list[j]

                if a.previous_cell is not None and b.previous_cell is not None:
                    if a.previous_cell == b.cell and b.previous_cell == a.cell and a.cell != b.cell:
                        key = f"edge:{a.name}:{b.name}:{a.previous_cell}->{a.cell}:{b.previous_cell}->{b.cell}"
                        self.log_collision("EDGE_SWAP", key, f"EDGE SWAP COLLISION | tick={self.tick} {a.name}:{a.previous_cell}->{a.cell} {b.name}:{b.previous_cell}->{b.cell}")

                    if self._segments_cross_cells(a.previous_cell, a.cell, b.previous_cell, b.cell):
                        key = f"diag_cross:{a.name}:{b.name}:{self.tick}"
                        self.log_collision("DIAGONAL_CROSS", key, f"DIAGONAL CROSS COLLISION | tick={self.tick} {a.name}:{a.previous_cell}->{a.cell} {b.name}:{b.previous_cell}->{b.cell}")

                    swept_distance = self._segment_distance_world(a.previous_cell, a.cell, b.previous_cell, b.cell)
                    swept_threshold = self._runtime_half_extent(a) + self._runtime_half_extent(b)
                    if swept_distance < swept_threshold - 1e-6:
                        key = f"swept:{a.name}:{b.name}:{self.tick}"
                        self.log_collision("SWEPT_FOOTPRINT", key, f"SWEPT FOOTPRINT COLLISION | tick={self.tick} {a.name}:{a.previous_cell}->{a.cell} {b.name}:{b.previous_cell}->{b.cell} distance={swept_distance:.2f} threshold={swept_threshold:.2f}")

                ax, ay = cell_to_world(a.cell)
                bx, by = cell_to_world(b.cell)
                d = math.hypot(ax - bx, ay - by)
                a_half = RACK_SIZE_M * 0.5 if a.carrying_rack else AMR_SIZE_M * 0.5
                b_half = RACK_SIZE_M * 0.5 if b.carrying_rack else AMR_SIZE_M * 0.5
                threshold = a_half + b_half
                if d < threshold - 1e-6:
                    key = f"footprint:{a.name}:{b.name}:{self.tick}"
                    self.log_collision("FOOTPRINT", key, f"FOOTPRINT COLLISION | tick={self.tick} {a.name}@{a.cell} {b.name}@{b.cell} distance={d:.2f} threshold={threshold:.2f}")

    def _segments_cross_cells(self, a0: GridCell, a1: GridCell, b0: GridCell, b1: GridCell) -> bool:
        if a0 == a1 or b0 == b1:
            return False
        if a0 in (b0, b1) or a1 in (b0, b1):
            return False

        adx = a1[0] - a0[0]
        ady = a1[1] - a0[1]
        bdx = b1[0] - b0[0]
        bdy = b1[1] - b0[1]

        if abs(adx) != 1 or abs(ady) != 1 or abs(bdx) != 1 or abs(bdy) != 1:
            return False

        # 같은 1x1 cell square 안에서 서로 반대 대각선을 동시에 통과하는 경우
        return {a0, a1} == {(b0[0], b1[1]), (b1[0], b0[1])}

    def log_no_safe_move(self, key: str, message: str):
        last_tick = self.collision_log_last_tick.get(key, -999999)
        if self.tick - last_tick >= COLLISION_LOG_COOLDOWN_TICKS:
            self.collision_log_last_tick[key] = self.tick
            self.no_safe_move_count += 1
            if LOG_NO_SAFE_MOVE:
                print(f"NO SAFE MOVE | total={self.no_safe_move_count} | {message}")

    def log_collision(self, collision_type: str, key: str, message: str):
        last_tick = self.collision_log_last_tick.get(key, -999999)
        if self.tick - last_tick >= COLLISION_LOG_COOLDOWN_TICKS:
            self.collision_log_last_tick[key] = self.tick
            self.collision_total_count += 1
            if collision_type in self.collision_type_count:
                self.collision_type_count[collision_type] += 1
            print(f"COLLISION DETECTED | type={collision_type} total={self.collision_total_count} | {message}")

    def set_amr_world(self, amr: AMRState, wx, wy):
        prim = self.stage.GetPrimAtPath(amr.prim_path)
        if not prim.IsValid():
            return
        yaw = math.degrees(math.atan2(amr.heading[1], amr.heading[0])) if amr.heading != (0, 0) else 0.0
        set_xform(prim, (wx, wy, world_z_for_amr()), (1.0, 1.0, 1.0), (0.0, 0.0, yaw))
        amr.world_pos = (wx, wy)

    def set_rack_world(self, rack: RackState, wx, wy, lift_z):
        prim = self.stage.GetPrimAtPath(rack.prim_path)
        if not prim.IsValid():
            return
        set_xform(prim, (wx, wy, world_z_for_rack() + lift_z), (1.0, 1.0, 1.0))


def main():
    demo = FleetDemo()
    timeline = omni.timeline.get_timeline_interface()
    print("\nPress Play in Isaac Sim viewport to start simulation.")
    print("Close the window or Ctrl+C in terminal to exit.")

    last_time = time.time()

    while simulation_app.is_running():
        now = time.time()
        dt = max(0.0, min(now - last_time, 0.05))
        last_time = now

        if timeline.is_playing():
            demo.update(dt)

        simulation_app.update()
        time.sleep(FRAME_SLEEP)

    simulation_app.close()


if __name__ == "__main__":
    main()

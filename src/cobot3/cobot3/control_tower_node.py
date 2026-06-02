import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.action import ActionClient

# 커스텀 ROS2 인터페이스 임포트
from cobot3_interfaces.srv import GetPackageRoute, CheckWarehouseStatus, ReportInboundProgress
from cobot3_interfaces.action import MovePackage, ManageWorkstation, StartPackaging

import json
import time
from datetime import datetime

# 데이터베이스 연동 라이브러리 임포트 시도
try:
    import psycopg2
    import redis
    DB_LIBS_AVAILABLE = True
except ImportError:
    DB_LIBS_AVAILABLE = False


class ControlTowerNode(Node):
    def __init__(self):
        super().__init__('control_tower_node')
        self.get_logger().info('=== 쿠팡 물류창고 관제 센터(Control Tower) 노드 구동 시작 ===')

        # 1. 데이터베이스 연결 정보 설정
        self.pg_conn = None
        self.redis_client = None
        self.init_databases()

        # 2. ROS2 서비스 서버 등록 (로봇들로부터의 요청 수신)
        self.route_service = self.create_service(
            GetPackageRoute,
            'get_package_route',
            self.get_package_route_callback
        )
        self.warehouse_status_service = self.create_service(
            CheckWarehouseStatus,
            'check_warehouse_status',
            self.check_warehouse_status_callback
        )
        self.inbound_progress_service = self.create_service(
            ReportInboundProgress,
            'report_inbound_progress',
            self.report_inbound_progress_callback
        )

        # 3. ROS2 액션 클라이언트 등록 (AMR 및 포장 로봇에게 명령 하달)
        self.move_package_action_client = ActionClient(self, MovePackage, 'move_package')
        self.manage_workstation_action_client = ActionClient(self, ManageWorkstation, 'manage_workstation')
        self.start_packaging_action_client = ActionClient(self, StartPackaging, 'start_packaging')

        # 4. 주기적 상태 체크 및 스케줄러 타이머 구동 (1초마다 실행)
        self.scheduler_timer = self.create_timer(1.0, self.task_scheduler_loop)
        
        self.get_logger().info('ROS2 서비스 서버 및 액션 클라이언트 준비 완료.')

    def init_databases(self):
        """데이터베이스 연결 초기화"""
        if not DB_LIBS_AVAILABLE:
            self.get_logger().error(
                'psycopg2 또는 redis 모듈이 설치되지 않았습니다. '
                '가상 시뮬레이션(Mock 모드)으로 동작합니다.'
            )
            return

        try:
            # PostgreSQL 연결
            self.pg_conn = psycopg2.connect(
                host='localhost',
                port=5432,
                user='rokey',
                password='rokey_pass',
                database='warehouse_db'
            )
            self.pg_conn.autocommit = True
            self.get_logger().info('PostgreSQL 데이터베이스 연결 완료.')

            # Redis 연결
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True
            )
            self.get_logger().info('Redis 인메모리 데이터베이스 연결 완료.')

        except Exception as e:
            self.get_logger().error(f'데이터베이스 연결 중 오류 발생: {str(e)}')
            self.get_logger().warn('데이터베이스 연결 실패로 가상 시뮬레이션(Mock 모드)으로 동작합니다.')
            self.pg_conn = None
            self.redis_client = None

    # ==========================================
    # ROS2 서비스 콜백 함수 정의 (인바운드 라인)
    # ==========================================

    def get_package_route_callback(self, request, response):
        """bg2 로봇이 바코드를 찍어 목적지 날짜를 조회할 때 호출"""
        package_id = request.package_id
        customer_name = request.customer_name
        aruco_id = request.aruco_id
        self.get_logger().info(f'[GetPackageRoute] 입고 택배 바코드/ArUco 스캔 - ID: {package_id}, 수령인: {customer_name}, ArUco ID: {aruco_id}')

        route_date = None
        if self.pg_conn:
            try:
                with self.pg_conn.cursor() as cursor:
                    # 1. ArUco ID가 주어지면 ArUco ID로 먼저 조회
                    if aruco_id > 0:
                        cursor.execute(
                            "SELECT route_zone, package_id, customer_name FROM packages WHERE aruco_id = %s;",
                            (aruco_id,)
                        )
                        row = cursor.fetchone()
                        if row:
                            route_date = row[0]
                            package_id = row[1]
                            customer_name = row[2]
                            self.get_logger().info(f'[GetPackageRoute] ArUco ID {aruco_id}로 조회 성공 - 패키지 ID: {package_id}')

                    # 2. ArUco ID로 조회에 실패했거나 제공되지 않은 경우 기존 package_id로 조회
                    if not route_date and package_id:
                        cursor.execute(
                            "SELECT route_zone, customer_name, aruco_id FROM packages WHERE package_id = %s;",
                            (package_id,)
                        )
                        row = cursor.fetchone()
                        if row:
                            route_date = row[0]
                            customer_name = row[1]
                            if row[2] is not None:
                                aruco_id = row[2]
                            self.get_logger().info(f'[GetPackageRoute] Package ID {package_id}로 조회 성공 - ArUco ID: {aruco_id}')

                    # 3. 데이터베이스에 없는 새로운 패키지인 경우 자동 등록
                    if not route_date:
                        route_date = datetime.now().strftime('%Y-%m-%d')
                        if not package_id:
                            package_id = f"PKG_ARUCO_{aruco_id}"
                        if not customer_name:
                            customer_name = f"Customer_{aruco_id}"

                        if aruco_id > 0:
                            cursor.execute(
                                "INSERT INTO packages (package_id, customer_name, route_zone, status, aruco_id) "
                                "VALUES (%s, %s, %s, 'WAITING', %s);",
                                (package_id, customer_name, route_date, aruco_id)
                            )
                        else:
                            cursor.execute(
                                "INSERT INTO packages (package_id, customer_name, route_zone, status) "
                                "VALUES (%s, %s, %s, 'WAITING');",
                                (package_id, customer_name, route_date)
                            )
                        self.get_logger().info(f'[GetPackageRoute] 신규 패키지 등록 완료 - ID: {package_id}, ArUco: {aruco_id}')
            except Exception as e:
                self.get_logger().error(f'GetPackageRoute DB 조회 중 오류: {str(e)}')

        # DB 미연결 또는 예외 시 Mock 값 대응 (2026-06-01 기준)
        if not route_date:
            route_date = '2026-06-01'

        response.route_destination = route_date
        self.get_logger().info(f'[GetPackageRoute] 목적지 분류 결과 전송 -> {route_date}')
        return response

    def check_warehouse_status_callback(self, request, response):
        """sg2_in_XX 로봇이 적재 전 해당 수령인의 물품이 창고에 있는지 조회"""
        customer_name = request.customer_name
        package_id = request.package_id
        aruco_id = request.aruco_id
        self.get_logger().info(f'[CheckWarehouseStatus] 적재 검사 - 수령인: {customer_name}, 택배ID: {package_id}, ArUco: {aruco_id}')

        if self.pg_conn:
            try:
                with self.pg_conn.cursor() as cursor:
                    # 1. ArUco ID가 들어왔고 다른 정보가 부족하면 DB에서 정보를 채운다
                    if aruco_id > 0 and (not customer_name or not package_id):
                        cursor.execute(
                            "SELECT customer_name, package_id FROM packages WHERE aruco_id = %s;",
                            (aruco_id,)
                        )
                        row = cursor.fetchone()
                        if row:
                            customer_name = row[0]
                            package_id = row[1]
                            self.get_logger().info(f'[CheckWarehouseStatus] ArUco {aruco_id} 매핑 완료 -> ID: {package_id}, 수령인: {customer_name}')

                    # 2. 만약 package_id만 들어오고 customer_name이 없으면 DB에서 조회
                    if package_id and not customer_name:
                        cursor.execute(
                            "SELECT customer_name, aruco_id FROM packages WHERE package_id = %s;",
                            (package_id,)
                        )
                        row = cursor.fetchone()
                        if row:
                            customer_name = row[0]
                            if row[1] is not None:
                                aruco_id = row[1]
            except Exception as e:
                self.get_logger().error(f'CheckWarehouseStatus 매핑 및 DB 조회 중 오류: {str(e)}')

        is_already_in_warehouse = False
        if self.pg_conn:
            try:
                with self.pg_conn.cursor() as cursor:
                    # 창고(IN_WAREHOUSE)에 동일한 수령인의 물건이 있는지 확인
                    cursor.execute(
                        "SELECT COUNT(*) FROM packages WHERE customer_name = %s AND status = 'IN_WAREHOUSE';",
                        (customer_name,)
                    )
                    count = cursor.fetchone()[0]
                    if count > 0:
                        is_already_in_warehouse = True
            except Exception as e:
                self.get_logger().error(f'CheckWarehouseStatus DB 조회 중 오류: {str(e)}')

        response.is_already_in_warehouse = is_already_in_warehouse
        
        if is_already_in_warehouse:
            self.get_logger().info(f'[CheckWarehouseStatus] {customer_name}님의 기존 물품이 창고에 감지되었습니다. 창고 직송을 결정합니다.')
            # [AMR 직송 태스크 추가] 관제탑이 즉시 Redis 큐에 AMR 직송 명령을 적재 (ArUco ID 포함)
            self.push_amr_task({
                'task_type': 'DIRECT_WAREHOUSE',
                'package_id': package_id,
                'customer_name': customer_name,
                'destination_zone': 'ZONE_A', # 기본 보관 구역 A
                'package_aruco_id': aruco_id
            })
        else:
            self.get_logger().info(f'[CheckWarehouseStatus] 기존 물품이 창고에 없습니다. 작업대 적재 진행.')

        return response

    def report_inbound_progress_callback(self, request, response):
        """sg2_in_XX 로봇이 작업대 칸 적재 완료 시 진척도를 보고"""
        workstation_id = request.workstation_id
        robot_id = request.robot_id
        filled_slots_count = request.filled_slots_count
        package_id = request.package_id
        workstation_aruco_id = request.workstation_aruco_id
        package_aruco_id = request.package_aruco_id

        self.get_logger().info(
            f'[ReportInboundProgress] {robot_id} 보고 - 작업대: {workstation_id} (ArUco: {workstation_aruco_id}), '
            f'적재 수량: {filled_slots_count}/4, 택배 ID: {package_id} (ArUco: {package_aruco_id})'
        )

        # DB에 작업대 및 패키지 정보 업데이트
        if self.pg_conn:
            try:
                with self.pg_conn.cursor() as cursor:
                    # 1. ArUco ID가 제공된 경우, ID 조회하여 매핑
                    if workstation_aruco_id > 0:
                        cursor.execute(
                            "SELECT workstation_id FROM workstations WHERE aruco_id = %s;",
                            (workstation_aruco_id,)
                        )
                        row = cursor.fetchone()
                        if row:
                            workstation_id = row[0]
                            self.get_logger().info(f'[ReportInboundProgress] workstation_aruco_id {workstation_aruco_id} ➡️ workstation_id {workstation_id}')

                    if package_aruco_id > 0:
                        cursor.execute(
                            "SELECT package_id FROM packages WHERE aruco_id = %s;",
                            (package_aruco_id,)
                        )
                        row = cursor.fetchone()
                        if row:
                            package_id = row[0]
                            self.get_logger().info(f'[ReportInboundProgress] package_aruco_id {package_aruco_id} ➡️ package_id {package_id}')

                    # 2. 패키지 소유 수령인 조회
                    cursor.execute(
                        "SELECT customer_name FROM packages WHERE package_id = %s;",
                        (package_id,)
                    )
                    row = cursor.fetchone()
                    customer_name = row[0] if row else 'UNKNOWN'

                    slot_column_status = f"slot_{filled_slots_count}_status"
                    slot_column_customer = f"slot_{filled_slots_count}_customer"

                    # 3. 작업대 슬롯 상태 및 수령인 업데이트
                    cursor.execute(
                        f"UPDATE workstations SET {slot_column_status} = 'FULL', {slot_column_customer} = %s "
                        f"WHERE workstation_id = %s;",
                        (customer_name, workstation_id)
                    )

                    # 4. 개별 패키지 위치 정보 매핑 및 상태 갱신
                    cursor.execute(
                        "UPDATE packages SET workstation_id = %s, slot_number = %s, status = 'IN_WORKSTATION' "
                        "WHERE package_id = %s;",
                        (workstation_id, filled_slots_count, package_id)
                    )
            except Exception as e:
                self.get_logger().error(f'ReportInboundProgress DB 업데이트 중 오류: {str(e)}')

        # [Look-ahead 최적화] 3번째 칸 적재 완료 시 다음 빈 작업대 대기 명령 적재
        if filled_slots_count == 3:
            self.get_logger().info(f'[Look-ahead] {workstation_id}의 3번째 슬롯 적재 감지! 다음 빈 작업대 사전 배치 태스크 추가.')
            self.push_amr_task({
                'task_type': 'PRE_FETCH_EMPTY_WORKSTATION',
                'target_robot': robot_id,
                'description': f'{robot_id} 앞 다음 작업대 대기',
                'workstation_aruco_id': 0
            })

        response.success = True
        return response

    # ==========================================
    # Redis 작업 큐 핸들링 함수
    # ==========================================

    def push_amr_task(self, task_dict):
        """AMR 작업 명령을 Redis 대기 큐에 집어넣음"""
        if self.redis_client:
            try:
                self.redis_client.lpush('queue:amr_tasks', json.dumps(task_dict))
                self.get_logger().info(f'[Redis Queue] AMR 태스크 추가 -> {task_dict["task_type"]}')
            except Exception as e:
                self.get_logger().error(f'Redis Push 실패: {str(e)}')
        else:
            self.get_logger().warn(f'[Mock Queue] AMR 태스크 추가 (DB 미연결) -> {task_dict}')

    # ==========================================
    # 주기적 스케줄링 및 액션 제어 루프
    # ==========================================

    def task_scheduler_loop(self):
        """주기적으로 시스템 상태 및 Redis 큐를 체크하여 AMR/로봇 액션 구동"""
        if not self.redis_client:
            return

        try:
            # 1. Redis 큐에서 처리할 AMR 태스크가 있는지 조회 (가장 마지막에 들어온 것부터 RPOP)
            task_data = self.redis_client.rpop('queue:amr_tasks')
            if task_data:
                task = json.loads(task_data)
                self.get_logger().info(f'[Scheduler] Redis 큐에서 태스크 감지 -> {task["task_type"]}')
                self.execute_amr_task(task)

            # 2. 작업대 4칸이 모두 찼을 때의 이송 스케줄링 체크
            self.check_completed_workstations()

        except Exception as e:
            self.get_logger().error(f'스케줄러 루프 실행 중 에러 발생: {str(e)}')

    def execute_amr_task(self, task):
        """큐에서 꺼낸 태스크 종류에 맞춰 ROS2 액션 명령 하달"""
        task_type = task.get('task_type')

        if task_type == 'DIRECT_WAREHOUSE':
            # 단일 패키지 창고 직송 액션 전송
            goal_msg = MovePackage.Goal()
            goal_msg.package_id = task.get('package_id', '')
            goal_msg.customer_name = task.get('customer_name', '')
            goal_msg.destination_zone = task.get('destination_zone', '')
            goal_msg.package_aruco_id = task.get('package_aruco_id', 0)

            self.get_logger().info(f'AMR에게 단일 택배({goal_msg.package_id}, ArUco: {goal_msg.package_aruco_id}) 창고 직송 액션 전송 중...')
            self.move_package_action_client.wait_for_server()
            self.move_package_action_client.send_goal_async(goal_msg)

        elif task_type == 'PRE_FETCH_EMPTY_WORKSTATION':
            # 다음 빈 작업대를 특정 적재 로봇 앞으로 이동시키는 액션
            target_robot = task['target_robot']
            workstation_id = 'WS_TEMP_EMPTY'
            start_location = 'buffer'
            workstation_aruco_id = 0

            # DB에서 창고에 보관된 빈 작업대 중 하나를 조회
            if self.pg_conn:
                try:
                    with self.pg_conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT workstation_id, current_location, aruco_id FROM workstations "
                            "WHERE current_location LIKE 'spot_%%' "
                            "AND slot_1_status = 'EMPTY' AND slot_2_status = 'EMPTY' "
                            "AND slot_3_status = 'EMPTY' AND slot_4_status = 'EMPTY' "
                            "LIMIT 1;"
                        )
                        row = cursor.fetchone()
                        if row:
                            workstation_id = row[0]
                            start_location = row[1]
                            workstation_aruco_id = row[2] if row[2] is not None else 0
                            self.get_logger().info(f'[Scheduler] 창고 빈 작업대 선점 성공: {workstation_id}(ArUco: {workstation_aruco_id})')
                except Exception as e:
                    self.get_logger().error(f'창고 빈 작업대 조회 중 에러: {str(e)}')

            if workstation_id != 'WS_TEMP_EMPTY':
                self.trigger_workstation_move(workstation_id, start_location, target_robot, workstation_aruco_id)
            else:
                self.get_logger().warn("경고: 대기 중인 빈 작업대가 없어 이송을 대기합니다.")

        elif task_type == 'PRE_FETCH_WORKSTATION':
            # 포장 라인을 위해 창고의 작업대를 포장 로봇 앞으로 가져오는 액션
            workstation_id = task['workstation_id']
            self.trigger_workstation_move(workstation_id, task['from'], task['to'], task.get('workstation_aruco_id', 0))

    def check_completed_workstations(self):
        """4개 칸이 모두 채워진 완성된 작업대를 파악해 이동 명령(AMR) 스케줄링"""
        if not self.pg_conn:
            return

        try:
            with self.pg_conn.cursor() as cursor:
                # 4칸 모두 FULL인 작업대 조회 (aruco_id 추가 선택)
                cursor.execute(
                    "SELECT workstation_id, current_location, aruco_id FROM workstations "
                    "WHERE slot_1_status = 'FULL' AND slot_2_status = 'FULL' "
                    "AND slot_3_status = 'FULL' AND slot_4_status = 'FULL';"
                )
                rows = cursor.fetchall()
                for row in rows:
                    ws_id, curr_loc, ws_aruco_id = row[0], row[1], row[2]
                    if ws_aruco_id is None:
                        ws_aruco_id = 0
                    
                    # 오늘 날짜 분류 라인(sg2_in_01)에서 완성되었을 경우 -> 포장 라인(sg2_out_00)으로
                    if curr_loc == 'sg2_in_01':
                        self.get_logger().info(f'[Scheduler] {ws_id}(ArUco: {ws_aruco_id}) 오늘 물량 적재 완료! 포장존(sg2_out_00) 이송 스케줄링 시작.')
                        self.trigger_workstation_move(ws_id, curr_loc, 'sg2_out_00', ws_aruco_id)
                    
                    # 내일/모레 분류 라인(sg2_in_02, sg2_in_03)에서 완성되었을 경우 -> 창고(warehouse)로
                    elif curr_loc in ['sg2_in_02', 'sg2_in_03']:
                        self.get_logger().info(f'[Scheduler] {ws_id}(ArUco: {ws_aruco_id}) 내일/모레 물량 적재 완료! 창고(warehouse) 보관 스케줄링 시작.')
                        self.trigger_workstation_move(ws_id, curr_loc, 'warehouse', ws_aruco_id)

        except Exception as e:
            self.get_logger().error(f'작업대 완충 체크 중 에러: {str(e)}')

    def trigger_workstation_move(self, workstation_id, start, target, workstation_aruco_id=0):
        """AMR에게 작업대 통째로 이송하도록 액션 골 전송 및 DB 위치 선점 업데이트"""
        actual_target = target

        # 1. 만약 목적지가 warehouse라면 빈 스팟을 조회해서 실제 target을 spot_XX로 변경
        if target == 'warehouse':
            if self.pg_conn:
                try:
                    with self.pg_conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;"
                        )
                        row = cursor.fetchone()
                        if row:
                            actual_target = row[0]
                            # 목적지 스팟을 선점(OCCUPIED) 및 workstation_id 설정
                            cursor.execute(
                                "UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s "
                                "WHERE spot_id = %s;",
                                (workstation_id, actual_target)
                            )
                            self.get_logger().info(f'[DB] 작업대 {workstation_id}의 입고 스팟 배정: {actual_target}')
                        else:
                            self.get_logger().error("경고: 창고에 빈 주차 공간이 없습니다! 임시로 'warehouse'로 지정합니다.")
                except Exception as e:
                    self.get_logger().error(f'입고 스팟 조회 및 업데이트 중 에러: {str(e)}')

        # 2. 만약 출발지가 창고 스팟(spot_XX)이라면 해당 스팟을 EMPTY로 비워줌
        if start.startswith('spot_'):
            if self.pg_conn:
                try:
                    with self.pg_conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL "
                            "WHERE spot_id = %s;",
                            (start,)
                        )
                        self.get_logger().info(f'[DB] 창고 스팟 {start} 해제 완료.')
                except Exception as e:
                    self.get_logger().error(f'출발 스팟 비우기 중 에러: {str(e)}')

        # 이송 작업이 중복으로 트리거되는 걸 방지하기 위해 DB 위치를 즉시 업데이트
        if self.pg_conn:
            try:
                with self.pg_conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE workstations SET current_location = %s WHERE workstation_id = %s;",
                        (f"MOVING_TO_{actual_target.upper()}", workstation_id)
                    )
            except Exception as e:
                self.get_logger().error(f'작업대 이동 상태 DB 업데이트 실패: {str(e)}')
                return

        # AMR 액션 호출
        goal_msg = ManageWorkstation.Goal()
        goal_msg.workstation_id = workstation_id
        goal_msg.start_location = start
        goal_msg.target_location = actual_target
        goal_msg.workstation_aruco_id = workstation_aruco_id

        self.get_logger().info(f'AMR에게 작업대 {workstation_id}(ArUco: {workstation_aruco_id}) 이송 액션 전송: {start} -> {actual_target}')
        self.manage_workstation_action_client.wait_for_server()
        
        # 액션 완료 시 결과를 받아 실제 DB 최종 위치를 수정하도록 콜백 설정
        send_goal_future = self.manage_workstation_action_client.send_goal_async(goal_msg)
        send_goal_future.add_done_callback(
            lambda future: self.workstation_move_response_callback(future, workstation_id, actual_target)
        )

    def workstation_move_response_callback(self, future, workstation_id, target):
        """AMR의 작업대 이송 액션 결과 확인 콜백"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn(f'작업대 {workstation_id} 이송 요청이 AMR에 의해 거절당했습니다.')
            return

        self.get_logger().info(f'작업대 {workstation_id} 이송 목표 수락됨. 이동 진행 중...')
        get_result_future = goal_handle.get_result_async()
        get_result_future.add_done_callback(
            lambda res_future: self.workstation_move_completed_callback(res_future, workstation_id, target)
        )

    def workstation_move_completed_callback(self, future, workstation_id, target):
        """AMR이 이송을 완료했을 때 최종적으로 DB 갱신"""
        result = future.result().result
        if result.success:
            self.get_logger().info(f'=== [성공] 작업대 {workstation_id} 최종 도착 완료: -> {target} ===')
            if self.pg_conn:
                try:
                    with self.pg_conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE workstations SET current_location = %s WHERE workstation_id = %s;",
                            (target, workstation_id)
                        )
                except Exception as e:
                    self.get_logger().error(f'도착지 DB 최종 반영 실패: {str(e)}')

            # 만약 포장 구역(sg2_out_00)에 안전하게 도착했다면 포장 공정(Action) 트리거
            if target == 'sg2_out_00':
                self.trigger_packaging_process(workstation_id)
        else:
            self.get_logger().error(f'[실패] 작업대 {workstation_id} 이송 중 에러 발생')

    # ==========================================
    # 포장 공정 액션 (sg2_out_00) 핸들링
    # ==========================================

    def trigger_packaging_process(self, workstation_id):
        """포장 로봇 sg2_out_00에게 포장 개시 명령 송신"""
        workstation_aruco_id = 0
        if self.pg_conn:
            try:
                with self.pg_conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT aruco_id FROM workstations WHERE workstation_id = %s;",
                        (workstation_id,)
                    )
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        workstation_aruco_id = row[0]
            except Exception as e:
                self.get_logger().error(f'포장 전 작업대 ArUco 조회 실패: {str(e)}')

        goal_msg = StartPackaging.Goal()
        goal_msg.workstation_id = workstation_id
        goal_msg.today_date = datetime.now().strftime('%Y%m%d')
        goal_msg.workstation_aruco_id = workstation_aruco_id

        self.get_logger().info(f'포장 로봇 sg2_out_00에게 {workstation_id}(ArUco: {workstation_aruco_id}) 포장 시작 명령 전송...')
        self.start_packaging_action_client.wait_for_server()
        
        send_goal_future = self.start_packaging_action_client.send_goal_async(
            goal_msg, 
            feedback_callback=self.packaging_feedback_callback
        )
        send_goal_future.add_done_callback(
            lambda future: self.packaging_response_callback(future, workstation_id)
        )

    def packaging_feedback_callback(self, feedback_msg):
        """포장 로봇의 실시간 피드백 핸들러 (3번째 칸 완료 감지용)"""
        feedback = feedback_msg.feedback
        completed_slots = feedback.completed_slots
        last_packed_slot = feedback.last_packed_slot

        self.get_logger().info(f'[포장 피드백] 현재 완료 슬롯 수: {completed_slots}/4, 최근 완료: {last_packed_slot}')

        # [Look-ahead 최적화] 3번째 칸 포장 완료 시 다음 작업대 사전 호출
        if completed_slots == 3:
            self.get_logger().info('[Look-ahead] 3번째 칸 포장 완료 감지! 다음 작업대 사전 호출을 예약합니다.')
            
            # 다음 포장 대기 중인 작업대를 창고에서 포장존으로 가져오도록 큐에 태스크 추가
            next_ws_id = 'WS02'
            next_ws_aruco_id = 12
            if self.pg_conn:
                try:
                    with self.pg_conn.cursor() as cursor:
                        # 완충되어 창고에 보관된 작업대를 우선순위로 조회
                        cursor.execute(
                            "SELECT workstation_id, aruco_id FROM workstations "
                            "WHERE current_location = 'warehouse' LIMIT 1;"
                        )
                        row = cursor.fetchone()
                        if row:
                            next_ws_id = row[0]
                            next_ws_aruco_id = row[1] if row[1] is not None else 0
                            self.get_logger().info(f'[Look-ahead] 다음 포장 대상 작업대 조회 성공: {next_ws_id}(ArUco: {next_ws_aruco_id})')
                except Exception as e:
                    self.get_logger().error(f'[Look-ahead] 다음 작업대 조회 중 오류: {str(e)}')

            self.push_amr_task({
                'task_type': 'PRE_FETCH_WORKSTATION',
                'workstation_id': next_ws_id,
                'from': 'warehouse',
                'to': 'sg2_out_00',
                'workstation_aruco_id': next_ws_aruco_id
            })

    def packaging_response_callback(self, future, workstation_id):
        """포장 명령 수락 콜백"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn(f'{workstation_id} 포장 시작 요청이 거절당했습니다.')
            return

        self.get_logger().info(f'{workstation_id} 포장 공정 목표 수락 완료. 결과 대기 중...')
        get_result_future = goal_handle.get_result_async()
        get_result_future.add_done_callback(
            lambda res_future: self.packaging_completed_callback(res_future, workstation_id)
        )

    def packaging_completed_callback(self, future, workstation_id):
        """모든 포장 완료 시 최종 처리 및 빈 작업대 회수"""
        result = future.result().result
        if result.success:
            self.get_logger().info(f'=== [완료] 작업대 {workstation_id} 모든 포장 완료! ===')
            self.get_logger().info(f'생성된 출고 ID 리스트: {result.final_output_ids}')

            if self.pg_conn:
                try:
                    with self.pg_conn.cursor() as cursor:
                        # 1. 작업대 슬롯 정보를 다시 EMPTY로 초기화
                        cursor.execute(
                            "UPDATE workstations SET "
                            "slot_1_customer = NULL, slot_1_status = 'EMPTY', "
                            "slot_2_customer = NULL, slot_2_status = 'EMPTY', "
                            "slot_3_customer = NULL, slot_3_status = 'EMPTY', "
                            "slot_4_customer = NULL, slot_4_status = 'EMPTY' "
                            "WHERE workstation_id = %s;",
                            (workstation_id,)
                        )
                        # 2. 해당 작업대에 매핑되었던 패키지들의 상태를 COMPLETED로 업데이트
                        raw_outbound_id = result.final_output_ids[0] if result.final_output_ids else 'OUT_ERR'
                        robot_prefix = "sg2_out_00_"
                        if raw_outbound_id != 'OUT_ERR' and not raw_outbound_id.startswith(robot_prefix):
                            formatted_outbound_id = f"{robot_prefix}{raw_outbound_id}"
                        else:
                            formatted_outbound_id = raw_outbound_id

                        cursor.execute(
                            "UPDATE packages SET status = 'COMPLETED', outbound_id = %s "
                            "WHERE workstation_id = %s AND status = 'IN_WORKSTATION';",
                            (formatted_outbound_id, workstation_id)
                        )
                except Exception as e:
                    self.get_logger().error(f'포장 완료 정보 DB 반영 실패: {str(e)}')

            # 3. 빈 작업대를 다시 인바운드 대기존으로 회수하는 AMR 태스크 발행
            ws_aruco_id = 0
            if self.pg_conn:
                try:
                    with self.pg_conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT aruco_id FROM workstations WHERE workstation_id = %s;",
                            (workstation_id,)
                        )
                        row = cursor.fetchone()
                        if row and row[0] is not None:
                            ws_aruco_id = row[0]
                except Exception as e:
                    self.get_logger().error(f'회수용 작업대 ArUco 조회 실패: {str(e)}')

            # 빈 작업대를 창고(warehouse)로 이동하도록 AMR에게 지시
            self.trigger_workstation_move(workstation_id, 'sg2_out_00', 'warehouse', ws_aruco_id)


def main(args=None):
    rclpy.init(args=args)
    node = ControlTowerNode()
    
    # 멀티스레드 실행기를 사용하여 DB 작업으로 인한 ROS2 틱 끊김 방지
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('관제 센터 노드 종료 중...')
    finally:
        if node.pg_conn:
            node.pg_conn.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

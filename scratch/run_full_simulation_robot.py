#!/usr/bin/env python3
import sys
import time
import os
import threading
import psycopg2
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.executors import MultiThreadedExecutor

from cobot3_interfaces.srv import GetPackageRoute, CheckWarehouseStatus, ReportInboundProgress
from cobot3_interfaces.action import ManageWorkstation, MovePackage, StartPackaging

# 모듈 경로 설정
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scratch.qr_handler import generate_qr_code, decode_qr_code

class MockFullRobotNode(Node):
    def __init__(self):
        super().__init__('mock_full_robot_node')
        self.get_logger().info('=== [Mock Robots] 통합 로봇 에뮬레이터 구동 시작 ===')

        # DB 연결 확인
        self.pg_conn = None
        self.connect_db()

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

    def execute_manage_ws(self, goal_handle):
        goal = goal_handle.request
        target = goal.target_location
        is_rotation = target.endswith('_ROTATE')

        if is_rotation:
            self.get_logger().info(f'🤖 [AMR] 작업대 {goal.workstation_id} 180도 제자리 회전 시작! (위치: {goal.start_location})')
        else:
            self.get_logger().info(
                f'🤖 [AMR] 작업대 이송 시작: {goal.workstation_id} '
                f'({goal.start_location} ➡️ {target})'
            )

        # 피드백 제공 시연
        feedback_msg = ManageWorkstation.Feedback()
        for i in range(3):
            time.sleep(0.5)
            feedback_msg.distance_remaining = float(3.0 - i)
            feedback_msg.status = "ROTATING" if is_rotation else "NAVIGATING"
            goal_handle.publish_feedback(feedback_msg)

        goal_handle.succeed()
        result = ManageWorkstation.Result()
        result.success = True
        if is_rotation:
            self.get_logger().info(f'🤖 [AMR] 작업대 {goal.workstation_id} 180도 회전 완료!')
        else:
            self.get_logger().info(f'🤖 [AMR] 작업대 {goal.workstation_id} 이송 완료!')
        return result

    def execute_move_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'🤖 [AMR] 단일 패키지 직송 시작: {goal.package_id} ➡️ {goal.destination_zone}')
        
        feedback_msg = MovePackage.Feedback()
        feedback_msg.current_position = "Moving"
        feedback_msg.progress = 50.0
        goal_handle.publish_feedback(feedback_msg)
        
        time.sleep(1.0)
        goal_handle.succeed()
        result = MovePackage.Result()
        result.success = True
        self.get_logger().info(f'🤖 [AMR] 단일 패키지 {goal.package_id} 직송 완료!')
        return result

    def execute_start_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'📦 [포장로봇] 작업대 {goal.workstation_id} 포장 지시 수신!')

        feedback_msg = StartPackaging.Feedback()
        for slot in range(1, 9):
            time.sleep(0.4) # 슬롯당 포장 시간
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
                        return res, False  # 성공 완료 (오프라인 아님)
                self.get_logger().warn(f'[{service_name}] 호출 실패, 재시도 진행... ({attempt}/{max_retries})')
            else:
                self.get_logger().warn(f'[{service_name}] 관제 서버 접속 지연/무응답 (시도 {attempt}/{max_retries})')
            time.sleep(0.5)

        self.get_logger().error(f'❌ [{service_name}] 관제 서버 접속 실패! 로컬 오프라인 룰베이스(Fail-safe)를 기동합니다.')
        fallback_res = fallback_callback(request)
        return fallback_res, True  # 오프라인 폴백 완료

    def fallback_route(self, request):
        val = sum(ord(c) for c in request.package_id)
        dates = ['2026-06-01', '2026-06-02', '2026-06-03']
        res = GetPackageRoute.Response()
        res.route_destination = dates[val % len(dates)]
        return res

    def fallback_check_warehouse(self, request):
        res = CheckWarehouseStatus.Response()
        res.is_already_in_warehouse = True  # 예외 회차로 이송을 유도하기 위해 True 반환
        return res

    def fallback_report_inbound(self, request):
        res = ReportInboundProgress.Response()
        res.success = True  # 벨트 정체 방지
        return res

def inbound_sim_loop(node):
    """분류기(bg2) 및 적재로봇(sg2_in_01~03)의 자율 운전 시나리오 루프"""
    time.sleep(5.0) # 관제탑 노드 기동 대기
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
                qr_file = generate_qr_code(pkg_id)
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

                # 목적지 날짜에 따른 적재 로봇 결정
                if dest_date == '2026-06-01':
                    target_robot = 'sg2_in_01'
                elif dest_date == '2026-06-02':
                    target_robot = 'sg2_in_02'
                elif dest_date == '2026-06-03':
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
                        node.get_logger().warn(f'[Scenario]   - {cust_name} 님의 물품이 이미 창고에 보관 중입니다! AMR 직송 명령 대기.')
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
                
                time.sleep(1.5) # 적재 주기 조절

        except Exception as e:
            node.get_logger().error(f'[Scenario Loop Error] {e}')
            time.sleep(2.0)

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
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

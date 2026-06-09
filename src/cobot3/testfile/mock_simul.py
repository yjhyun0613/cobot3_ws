import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.executors import MultiThreadedExecutor
import time
from datetime import datetime

# 커스텀 ROS2 인터페이스 임포트
from cobot3_interfaces.srv import GetPackageRoute, CheckWarehouseStatus, ReportInboundProgress
from cobot3_interfaces.action import MovePackage, ManageWorkstation, StartPackaging

class MockRobotSimulator(Node):
    def __init__(self):
        super().__init__('mock_robot_simulator')
        self.get_logger().info('=== 🤖 쿠팡 로봇 및 AMR 가상 시뮬레이터 구동 ===')

        # ----------------------------------------------------
        # 1. 액션 서버 등록 (관제탑 -> 로봇 명령 수신)
        # ----------------------------------------------------
        self._move_package_server = ActionServer(
            self, MovePackage, 'move_package', 
            execute_callback=self.execute_move_package_callback
        )
        self._manage_workstation_server = ActionServer(
            self, ManageWorkstation, 'manage_workstation', 
            execute_callback=self.execute_manage_workstation_callback
        )
        self._start_packaging_server = ActionServer(
            self, StartPackaging, 'start_packaging', 
            execute_callback=self.execute_start_packaging_callback
        )

        # ----------------------------------------------------
        # 2. 서비스 클라이언트 등록 (로봇 -> 관제탑 요청 발송)
        # ----------------------------------------------------
        self.route_client = self.create_client(GetPackageRoute, 'get_package_route')
        self.warehouse_status_client = self.create_client(CheckWarehouseStatus, 'check_warehouse_status')
        self.inbound_progress_client = self.create_client(ReportInboundProgress, 'report_inbound_progress')

        # ----------------------------------------------------
        # 3. 가상 물류 시나리오 구동 (10초마다 새로운 패키지 입고 시뮬레이션)
        # ----------------------------------------------------
        self.scenario_timer = self.create_timer(10.0, self.trigger_mock_inbound_scenario)
        self.package_counter = 1
        
        self.get_logger().info('모든 액션 서버 및 서비스 클라이언트 준비 완료.')

    # ========================================================
    # 🎯 [Action Server] 콜백 함수 구현
    # ========================================================

    def execute_move_package_callback(self, goal_handle):
        """AMR 단일 패키지 직송 명령 처리"""
        goal = goal_handle.request
        self.get_logger().info(f'[Action] 단일 패키지 직송 시작 -> ID: {goal.package_id}, 목적지: {goal.destination_zone}')
        
        feedback_msg = MovePackage.Feedback()
        for i in range(1, 4):
            time.sleep(1.0)
            feedback_msg.current_position = f"ZONE_PATH_{i}"
            feedback_msg.progress = float(i * 33.3)
            goal_handle.publish_feedback(feedback_msg)

        goal_handle.succeed()
        result = MovePackage.Result()
        result.success = True
        self.get_logger().info(f'[Action Completed] 단일 패키지 직송 완료.')
        return result

    def execute_manage_workstation_callback(self, goal_handle):
        """AMR 작업대 이송 및 제자리 회전 명령 처리"""
        goal = goal_handle.request
        self.get_logger().info(f'[Action] 작업대 {goal.workstation_id} 이송 시작 ({goal.start_location} -> {goal.target_location})')
        
        feedback_msg = ManageWorkstation.Feedback()
        feedback_msg.status = "NAVIGATING"
        
        for i in range(3, 0, -1):
            time.sleep(1.0)
            feedback_msg.distance_remaining = float(i * 0.5)
            goal_handle.publish_feedback(feedback_msg)

        goal_handle.succeed()
        result = ManageWorkstation.Result()
        result.success = True
        self.get_logger().info(f'[Action Completed] 작업대 {goal.workstation_id} 이송 완료.')
        return result

    def execute_start_packaging_callback(self, goal_handle):
        """출고 포장 로봇 sg2_out_00 포장 공정 처리 (관제탑 최적화 트리거링 핵심)"""
        goal = goal_handle.request
        self.get_logger().info(f'[Action] 포장 로봇 구동 개시 -> 작업대: {goal.workstation_id}')
        
        feedback_msg = StartPackaging.Feedback()
        output_ids = []
        
        # 1~8번 슬롯을 하나씩 포장하면서 관제탑에 피드백 전송 (관제탑은 3, 4번째에 최적화 로직 동작)
        for slot in range(1, 9):
            time.sleep(0.8)  # 포장 시간 시뮬레이션
            feedback_msg.completed_slots = slot
            feedback_msg.last_packed_slot = f"slot_{slot}"
            goal_handle.publish_feedback(feedback_msg)
            
            # 명세서 규격에 맞춘 출고 바코드 생성
            timestamp = datetime.now().strftime('%H%M%S')
            output_ids.append(f"sg2_out_00_{goal.workstation_id}_SLOT{slot}_{goal.today_date}_{timestamp}")

        goal_handle.succeed()
        result = StartPackaging.Result()
        result.success = True
        result.final_output_ids = output_ids
        self.get_logger().info(f'[Action Completed] 작업대 {goal.workstation_id} 모든 슬롯 포장 완료!')
        return result

    # ========================================================
    # 📡 [Service Client] 가상 호출 시나리오
    # ========================================================

    def trigger_mock_inbound_scenario(self):
        """주기적으로 발생하는 입고 상황 가상 시나리오"""
        pkg_id = f"PKG_MOCK_{self.package_counter}"
        cust_name = f"User_{self.package_counter}"
        qr_str = f"QR_MOCK_{self.package_counter}"
        self.package_counter += 1

        self.get_logger().info(f'\n--- 📦 [시나리오 시작] 신규 패키지 입고 감지: {pkg_id} ---')
        
        # 단계 1: bg2 로봇이 바코드를 찍어 배송 경로 조회
        if not self.route_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warn('관제탑의 get_package_route 서비스 서버가 켜져있지 않습니다.')
            return

        req_route = GetPackageRoute.Request()
        req_route.package_id = pkg_id
        req_route.customer_name = cust_name
        req_route.qr_id = qr_str
        
        future = self.route_client.call_async(req_route)
        future.add_done_callback(lambda f: self.response_route_callback(f, pkg_id, cust_name, qr_str))

    def response_route_callback(self, future, pkg_id, cust_name, qr_str):
        try:
            res = future.result()
            self.get_logger().info(f'[Service 응답] 목적지 분류 결과 수신 -> {res.route_destination}')
            
            # 단계 2: sg2_in 적재 로봇이 창고 중복 검사 수행
            if self.warehouse_status_client.wait_for_service(timeout_sec=1.0):
                req_status = CheckWarehouseStatus.Request()
                req_status.customer_name = cust_name
                req_status.package_id = pkg_id
                req_status.qr_id = qr_str
                
                f_status = self.warehouse_status_client.call_async(req_status)
                f_status.add_done_callback(lambda f: self.response_warehouse_status_callback(f, pkg_id, qr_str))
        except Exception as e:
            self.get_logger().error(f'Route 서비스 응답 처리 중 에러: {e}')

    def response_warehouse_status_callback(self, future, pkg_id, qr_str):
        try:
            res = future.result()
            if res.is_already_in_warehouse:
                self.get_logger().info(f'[시나리오 종료] 창고에 동일인 물품 존재 -> AMR 직송 처리됨 (적재 패스)')
            else:
                self.get_logger().info(f'[시나리오 진행] 창고에 물품 없음 -> 작업대에 순차 적재를 시작합니다.')
                # 단계 3: 순차적으로 슬롯을 채우는 보고를 보냄 (관제탑의 Look-ahead(3) 및 180도 회전(4) 유도)
                self.simulate_sequential_inbound_reports(pkg_id, qr_str)
        except Exception as e:
            self.get_logger().error(f'Warehouse Status 응답 처리 중 에러: {e}')

    def simulate_sequential_inbound_reports(self, pkg_id, qr_str):
        """작업대 칸이 차오르는 과정을 연속 보고하여 관제탑의 최적화 로직을 테스트합니다."""
        if not self.inbound_progress_client.wait_for_service(timeout_sec=1.0):
            return

        # 테스트 편의상 1번부터 4번 슬롯까지 순식간에 차오르는 상황을 시뮬레이션
        for slot in range(1, 5):
            req_progress = ReportInboundProgress.Request()
            req_progress.workstation_id = "WS01"
            req_progress.robot_id = "sg2_in_01"
            req_progress.filled_slots_count = slot
            req_progress.package_id = pkg_id
            req_progress.workstation_qr_id = "WORKSTATION_WS01"
            req_progress.package_qr_id = qr_str
            
            # 동기식 혹은 아주 짧은 간격으로 보고 전송
            self.get_logger().info(f'[Service 요청] sg2_in_01 -> WS01의 {slot}번째 슬롯 적재 완료 보고')
            self.inbound_progress_client.call_async(req_progress)
            time.sleep(0.2)

# ========================================================
# 🚀 메인 실행부
# ========================================================
def main(args=None):
    rclpy.init(args=args)
    node = MockRobotSimulator()
    
    # 멀티스레드 실행기를 사용하여 액션 처리와 서비스 요청이 엉키지 않도록 방지
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        print('시뮬레이터 종료 중...')
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
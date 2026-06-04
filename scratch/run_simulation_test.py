#!/usr/bin/env python3
import sys
import time
import threading
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.executors import MultiThreadedExecutor

from cobot3_interfaces.srv import GetPackageRoute, CheckWarehouseStatus, ReportInboundProgress
from cobot3_interfaces.action import ManageWorkstation, MovePackage, StartPackaging

class MockSystemNode(Node):
    def __init__(self):
        super().__init__('mock_system_node')
        self.get_logger().info('=== [Mock System] 시뮬레이션 환경 구축 시작 ===')

        # 1. Action Servers 호스팅 (관제탑이 호출할 액션들)
        self._manage_ws_server = ActionServer(
            self,
            ManageWorkstation,
            'manage_workstation',
            execute_callback=self.execute_manage_ws
        )
        self.get_logger().info('Action Server [manage_workstation] 준비 완료.')

        self._move_pkg_server = ActionServer(
            self,
            MovePackage,
            'move_package',
            execute_callback=self.execute_move_pkg
        )
        self.get_logger().info('Action Server [move_package] 준비 완료.')

        self._start_pkg_server = ActionServer(
            self,
            StartPackaging,
            'start_packaging',
            execute_callback=self.execute_start_pkg
        )
        self.get_logger().info('Action Server [start_packaging] 준비 완료.')

        # 2. Service Clients 생성 (관제탑 서비스 호출용)
        self.get_route_client = self.create_client(GetPackageRoute, 'get_package_route')
        self.check_warehouse_client = self.create_client(CheckWarehouseStatus, 'check_warehouse_status')
        self.report_inbound_client = self.create_client(ReportInboundProgress, 'report_inbound_progress')

    # 액션 콜백 함수 정의
    def execute_manage_ws(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(
            f'[Mock AMR] 작업대 이송 명령 접수! {goal.workstation_id}(QR: {goal.workstation_qr_id}) '
            f'이동 시작: {goal.start_location} -> {goal.target_location}'
        )
        
        # 1.5초 동안 이동하는 시뮬레이션
        time.sleep(1.5)
        goal_handle.succeed()
        
        result = ManageWorkstation.Result()
        result.success = True
        self.get_logger().info(f'[Mock AMR] 작업대 {goal.workstation_id} 이송 완료!')
        return result

    def execute_move_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'[Mock AMR] 단일 상자({goal.package_id}, QR: {goal.package_qr_id}) 직송 시작 -> {goal.destination_zone}')
        time.sleep(1.0)
        goal_handle.succeed()
        result = MovePackage.Result()
        result.success = True
        return result

    def execute_start_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'[Mock Packaging Robot] 작업대 {goal.workstation_id}(QR: {goal.workstation_qr_id}) 포장 시작!')
        time.sleep(2.0)
        goal_handle.succeed()
        result = StartPackaging.Result()
        result.success = True
        result.final_output_ids = [
            f"sg2_out_00_{goal.workstation_id}-1-{goal.today_date}1200",
            f"sg2_out_00_{goal.workstation_id}-2-{goal.today_date}1200",
            f"sg2_out_00_{goal.workstation_id}-3-{goal.today_date}1200",
            f"sg2_out_00_{goal.workstation_id}-4-{goal.today_date}1200",
        ]
        self.get_logger().info(f'[Mock Packaging Robot] 포장 완료! 생성 바코드: {result.final_output_ids}')
        return result

def run_client_scenario(node):
    """시뮬레이션 시나리오 실행 스레드"""
    time.sleep(4.0) # 관제탑 노드가 먼저 켜지기를 기다림
    
    node.get_logger().info('=== [Scenario] 시뮬레이션 시나리오 시작 ===')

    # 1. GetPackageRoute 호출 (분류 로봇이 택배 스캔)
    node.get_logger().info('[Scenario] ① 컨베이어 분류 로봇(bg2)이 택배 상자(QR: PKG_QR_001) 스캔 및 목적지 요청...')
    req = GetPackageRoute.Request()
    req.package_id = "PKG_RAND_001"
    req.customer_name = ""
    req.qr_id = "QR_PKG_001"
    future = node.get_route_client.call_async(req)
    while rclpy.ok() and not future.done():
        time.sleep(0.1)
    res = future.result()
    node.get_logger().info(f'[Scenario] 분류 목적지 응답 완료 -> {res.route_destination}')

    # 2. CheckWarehouseStatus 호출 (적재 로봇이 창고 검사)
    node.get_logger().info('[Scenario] ② 적재 로봇(sg2_in_01)이 적재 전 창고 중복 여부 조회(QR: QR_PKG_001)...')
    req2 = CheckWarehouseStatus.Request()
    req2.package_id = "PKG_RAND_001"
    req2.customer_name = ""
    req2.qr_id = "QR_PKG_001"
    future2 = node.check_warehouse_client.call_async(req2)
    while rclpy.ok() and not future2.done():
        time.sleep(0.1)
    res2 = future2.result()
    node.get_logger().info(f'[Scenario] 창고 중복 조회 응답 완료 -> {res2.is_already_in_warehouse}')

    # 3. ReportInboundProgress 1번째 슬롯 적재 보고 (WS01에 적재)
    node.get_logger().info('[Scenario] ③ 적재 로봇(sg2_in_01)이 작업대(QR: QR_WS01) 1번 슬롯에 적재 보고...')
    req3 = ReportInboundProgress.Request()
    req3.workstation_id = "WS01"
    req3.workstation_qr_id = "QR_WS01"  # WS01
    req3.package_id = "PKG_RAND_001"
    req3.package_qr_id = "QR_PKG_001"      # PKG_RAND_001
    req3.filled_slots_count = 1
    req3.robot_id = 'sg2_in_01'
    future3 = node.report_inbound_client.call_async(req3)
    while rclpy.ok() and not future3.done():
        time.sleep(0.1)
    
    # 4. ReportInboundProgress 2번째 슬롯 적재 보고
    node.get_logger().info('[Scenario] ④ 2번 슬롯 적재 보고...')
    req4 = ReportInboundProgress.Request()
    req4.workstation_id = "WS01"
    req4.workstation_qr_id = "QR_WS01"
    req4.package_id = "PKG_RAND_004"
    req4.package_qr_id = "QR_PKG_004"      # PKG_RAND_004 (오늘 날짜)
    req4.filled_slots_count = 2
    req4.robot_id = 'sg2_in_01'
    future4 = node.report_inbound_client.call_async(req4)
    while rclpy.ok() and not future4.done():
        time.sleep(0.1)

    # 5. ReportInboundProgress 3번째 슬롯 적재 보고 (Look-ahead 트리거 발생 구간!)
    node.get_logger().info('[Scenario] ⑤ 3번 슬롯 적재 보고 -> Look-ahead (사전 예비 배치) 트리거 유도!')
    req5 = ReportInboundProgress.Request()
    req5.workstation_id = "WS01"
    req5.workstation_qr_id = "QR_WS01"
    req5.package_id = "PKG_RAND_005"
    req5.package_qr_id = "QR_PKG_005"      # PKG_RAND_005 (오늘 날짜)
    req5.filled_slots_count = 3
    req5.robot_id = 'sg2_in_01'
    future5 = node.report_inbound_client.call_async(req5)
    while rclpy.ok() and not future5.done():
        time.sleep(0.1)
    
    node.get_logger().info('=== [Scenario] 시나리오 호출 종료. 백그라운드 작업 관찰 중... ===')

def main(args=None):
    rclpy.init(args=args)
    node = MockSystemNode()
    
    # 클라이언트 시나리오를 백그라운드 스레드에서 실행
    thread = threading.Thread(target=run_client_scenario, args=(node,))
    thread.daemon = True
    thread.start()

    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('시뮬레이션 종료 중...')
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

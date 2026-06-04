#!/usr/bin/env python3
import sys
import time
import os
import threading
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.executors import MultiThreadedExecutor

from cobot3_interfaces.srv import GetPackageRoute, CheckWarehouseStatus, ReportInboundProgress
from cobot3_interfaces.action import ManageWorkstation, MovePackage, StartPackaging

# 스크립트 실행 위치에 관계없이 모듈 임포트 가능하도록 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scratch.qr_handler import generate_qr_code, decode_qr_code

class MockQRSystemNode(Node):
    def __init__(self):
        super().__init__('mock_qr_system_node')
        self.get_logger().info('=== [Mock QR System] QR코드 물류 시뮬레이터 구동 시작 ===')

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

    def execute_manage_ws(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(
            f'[Mock AMR] 작업대 이송 명령 접수! {goal.workstation_id}(ArUco: {goal.workstation_aruco_id}) '
            f'이동 시작: {goal.start_location} -> {goal.target_location}'
        )
        time.sleep(1.5)
        goal_handle.succeed()
        result = ManageWorkstation.Result()
        result.success = True
        self.get_logger().info(f'[Mock AMR] 작업대 {goal.workstation_id} 이송 완료!')
        return result

    def execute_move_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'[Mock AMR] 단일 상자({goal.package_id}) 직송 시작 -> {goal.destination_zone}')
        time.sleep(1.0)
        goal_handle.succeed()
        result = MovePackage.Result()
        result.success = True
        return result

    def execute_start_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'[Mock Packaging Robot] 작업대 {goal.workstation_id} 포장 시작!')
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
    """실시간으로 QR코드를 생성하고 로봇 비전 인식 형태로 해독하여 ROS2 서비스를 호출하는 시나리오"""
    time.sleep(4.0)  # 관제탑 노드가 실행되기를 대기
    node.get_logger().info('=== [Scenario] QR코드 비전 인식 물류 시나리오 시작 ===')

    # 테스트용 입고 패키지 ID 리스트 (데이터베이스에 미리 삽입된 데이터 활용)
    test_packages = ["PKG_RAND_001", "PKG_RAND_004", "PKG_RAND_005"]
    
    # Step 1: 입고 예정 물량에 대한 QR코드 물리 라벨 이미지 동적 생성
    qr_paths = {}
    node.get_logger().info('[Scenario] ① 택배 입고 물량 라벨용 QR코드 파일 동적 생성 시작...')
    for pkg in test_packages:
        path = generate_qr_code(pkg)
        qr_paths[pkg] = path
        node.get_logger().info(f'  - [QR 인쇄] {pkg} QR코드 이미지 저장 완료: {path}')

    # Step 2: bg2 분류 로봇의 비전 카메라 QR코드 획득 및 해독 시뮬레이션
    target_pkg = test_packages[0]
    img_path = qr_paths[target_pkg]
    node.get_logger().info(f'[Scenario] ② 컨베이어 분류 로봇(bg2)이 택배 상자 QR코드 이미지 비전 인식 시도... (경로: {img_path})')
    
    # 비전 디코딩 함수 호출 (zxingcpp 기반)
    decoded_pkg_id = decode_qr_code(img_path)
    if decoded_pkg_id:
        node.get_logger().info(f'  - [비전 해독 성공] 디코딩된 택배 ID: "{decoded_pkg_id}"')
    else:
        node.get_logger().error('  - [비전 해독 실패] QR코드가 인식되지 않았습니다!')
        return

    # Step 3: GetPackageRoute 호출 (목적지 날짜 조회)
    node.get_logger().info(f'[Scenario] ③ 관제탑에 목적지 경로 조회 요청 (package_id: "{decoded_pkg_id}")...')
    req = GetPackageRoute.Request()
    req.package_id = decoded_pkg_id
    future = node.get_route_client.call_async(req)
    while rclpy.ok() and not future.done():
        time.sleep(0.1)
    res = future.result()
    node.get_logger().info(f'[Scenario] 목적지 응답 수신 완료 -> {res.route_destination}')

    # Step 4: 적재 로봇(sg2_in_01)이 적재 전 창고 중복 여부 조회
    node.get_logger().info(f'[Scenario] ④ 적재 로봇(sg2_in_01)이 적재 전 창고 보관 여부 조회 (package_id: "{decoded_pkg_id}")...')
    req2 = CheckWarehouseStatus.Request()
    req2.package_id = decoded_pkg_id
    future2 = node.check_warehouse_client.call_async(req2)
    while rclpy.ok() and not future2.done():
        time.sleep(0.1)
    res2 = future2.result()
    node.get_logger().info(f'[Scenario] 창고 보관 조회 응답 수신 완료 -> is_already_in_warehouse: {res2.is_already_in_warehouse}')

    # Step 5: 적재 로봇이 작업대 WS01에 패키지를 1번 슬롯부터 채워 나가는 진행 상태 보고
    # 1번째 슬롯 적재 보고
    node.get_logger().info(f'[Scenario] ⑤ 1번 슬롯 적재 보고 (WS01, package_id: "{test_packages[0]}")...')
    req3 = ReportInboundProgress.Request()
    req3.workstation_id = 'WS01'
    req3.package_id = test_packages[0]
    req3.filled_slots_count = 1
    req3.robot_id = 'sg2_in_01'
    future3 = node.report_inbound_client.call_async(req3)
    while rclpy.ok() and not future3.done():
        time.sleep(0.1)

    # 2번째 슬롯 적재 보고
    node.get_logger().info(f'[Scenario] ⑥ 2번 슬롯 적재 보고 (WS01, package_id: "{test_packages[1]}")...')
    req4 = ReportInboundProgress.Request()
    req4.workstation_id = 'WS01'
    req4.package_id = test_packages[1]
    req4.filled_slots_count = 2
    req4.robot_id = 'sg2_in_01'
    future4 = node.report_inbound_client.call_async(req4)
    while rclpy.ok() and not future4.done():
        time.sleep(0.1)

    # 3번째 슬롯 적재 보고 (Look-ahead 프리거 유도 지점!)
    node.get_logger().info(f'[Scenario] ⑦ 3번 슬롯 적재 보고 -> Look-ahead 빈 작업대 선점 트리거 유도 (WS01, package_id: "{test_packages[2]}")...')
    req5 = ReportInboundProgress.Request()
    req5.workstation_id = 'WS01'
    req5.package_id = test_packages[2]
    req5.filled_slots_count = 3
    req5.robot_id = 'sg2_in_01'
    future5 = node.report_inbound_client.call_async(req5)
    while rclpy.ok() and not future5.done():
        time.sleep(0.1)

    node.get_logger().info('=== [Scenario] QR코드 기반 시나리오 요청 종료. 백그라운드 스케줄러 처리 모니터링... ===')

def main(args=None):
    rclpy.init(args=args)
    node = MockQRSystemNode()
    
    # 백그라운드 스레드에서 시나리오 시작
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

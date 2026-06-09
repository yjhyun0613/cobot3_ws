#!/usr/bin/env python3
import sys
import time
import os
import threading
import psycopg2
import redis
from datetime import datetime, timedelta

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.executors import MultiThreadedExecutor

from cobot3_interfaces.srv import GetPackageRoute, CheckWarehouseStatus, ReportInboundProgress
from cobot3_interfaces.action import ManageWorkstation, MovePackage, StartPackaging

class MockSG2DevicesNode(Node):
    def __init__(self):
        super().__init__('mock_sg2_devices_node')
        self.get_logger().info('=== [Mock SG2 Devices Node] 로봇 및 설비 에뮬레이터 구동 ===')

        self.pg_conn = None
        self.redis_client = None
        self.connect_db()

        # bg2 로봇용 로컬 패키지 캐시 및 이전 영업 상태 저장용 변수
        self.package_cache = {}
        self.prev_day_status = 'WAITING_FOR_START'

        # 1. Action Servers 호스팅
        self._manage_ws_server = ActionServer(
            self,
            ManageWorkstation,
            'manage_workstation',
            execute_callback=self.execute_manage_ws
        )
        self.get_logger().info('Action Server [manage_workstation] 대기 중 (AMR 모의)')

        self._move_pkg_server = ActionServer(
            self,
            MovePackage,
            'move_package',
            execute_callback=self.execute_move_pkg
        )
        self.get_logger().info('Action Server [move_package] 대기 중 (패키지 직송 모의)')

        self._start_pkg_server = ActionServer(
            self,
            StartPackaging,
            'start_packaging',
            execute_callback=self.execute_start_pkg
        )
        self.get_logger().info('Action Server [start_packaging] 대기 중 (포장 로봇 모의)')

        # 2. Service Clients (관제탑 호출용)
        self.get_route_client = self.create_client(GetPackageRoute, 'get_package_route')
        self.check_warehouse_client = self.create_client(CheckWarehouseStatus, 'check_warehouse_status')
        self.report_inbound_client = self.create_client(ReportInboundProgress, 'report_inbound_progress')

        # 3. Heartbeat publisher for dashboard connection status (1Hz)
        self.heartbeat_timer = self.create_timer(1.0, self.publish_heartbeats)

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
            self.get_logger().info('PostgreSQL 연동 성공')
        except Exception as e:
            self.get_logger().error(f'PostgreSQL 연결 실패: {e}')
            
        try:
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True
            )
            self.get_logger().info('Redis 연동 성공')
        except Exception as e:
            self.get_logger().error(f'Redis 연결 실패: {e}')
            self.redis_client = None

    def publish_heartbeats(self):
        """대시보드 기기 연동 체크를 위한 주기적 Heartbeat 갱신 (만료 3초)"""
        if self.redis_client:
            try:
                self.redis_client.setex('device:bg2:heartbeat', 3, 'OK')
                self.redis_client.setex('device:sg2_in_01:heartbeat', 3, 'OK')
                self.redis_client.setex('device:sg2_in_02:heartbeat', 3, 'OK')
                self.redis_client.setex('device:sg2_in_03:heartbeat', 3, 'OK')
                self.redis_client.setex('device:sg2_out_00:heartbeat', 3, 'OK')
            except Exception as e:
                self.get_logger().error(f'Redis Heartbeat 갱신 중 에러: {e}')

    def load_package_cache(self):
        """오늘 영업 시작 시 당일 배송지 할당 패키지 정보를 일괄 조회하여 로컬 캐시에 저장"""
        self.package_cache = {}
        if not self.pg_conn:
            return
        try:
            with self.pg_conn.cursor() as cursor:
                cursor.execute("SELECT package_id, qr_id, route_zone FROM packages;")
                rows = cursor.fetchall()
                for row in rows:
                    pkg_id, qr_id, route_zone = row
                    if pkg_id:
                        self.package_cache[pkg_id] = route_zone
                    if qr_id:
                        self.package_cache[qr_id] = route_zone
            self.get_logger().info(f'=== [Cache] 로컬 패키지 {len(rows)}개 캐싱 완료 (bg2 Local Cache) ===')
        except Exception as e:
            self.get_logger().error(f'로컬 패키지 캐싱 중 오류 발생: {e}')

    # ==========================================
    # 🚀 Action Server: ManageWorkstation (AMR 이송)
    # ==========================================
    def execute_manage_ws(self, goal_handle):
        goal = goal_handle.request
        target = goal.target_location
        is_rotation = target.endswith('_ROTATE') or 'ROTATING' in target or 'ROTATING' in goal.start_location

        self.get_logger().info(f'🤖 [Mock AMR] 작업대 이송 명령 수신: {goal.workstation_id} ({goal.start_location} ➡️ {target})')

        # 피드백 전송 시뮬레이션
        feedback_msg = ManageWorkstation.Feedback()
        feedback_msg.status = "NAVIGATING"
        
        steps = 5
        for i in range(steps):
            if not rclpy.ok():
                break
            feedback_msg.distance_remaining = float(steps - i)
            goal_handle.publish_feedback(feedback_msg)
            time.sleep(0.3)

        # 180도 회전 동작의 경우, DB에서 해당 작업대의 위치를 sg2_out_00_A로 갱신하여 포장 로봇이 감지할 수 있게 함
        if is_rotation:
            try:
                with self.pg_conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE workstations SET current_location = 'sg2_out_00_A' WHERE workstation_id = %s;",
                        (goal.workstation_id,)
                    )
                    self.get_logger().info(f'🤖 [Mock AMR] 작업대 {goal.workstation_id} 180도 회전 완료 DB 갱신 완료.')
            except Exception as e:
                self.get_logger().error(f'회전 완료 DB 반영 중 에러: {e}')

        goal_handle.succeed()
        result = ManageWorkstation.Result()
        result.success = True
        self.get_logger().info(f'🤖 [Mock AMR] 이송 완료 보고: {goal.workstation_id}')
        return result

    # ==========================================
    # 🚀 Action Server: MovePackage (단일 직송)
    # ==========================================
    def execute_move_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'🤖 [Mock AMR] 단일 패키지 직송 수신: {goal.package_id} ➡️ {goal.destination_zone}')

        feedback_msg = MovePackage.Feedback()
        feedback_msg.current_position = "Moving"
        feedback_msg.progress = 0.0
        goal_handle.publish_feedback(feedback_msg)
        time.sleep(1.0)

        feedback_msg.progress = 100.0
        goal_handle.publish_feedback(feedback_msg)

        goal_handle.succeed()
        result = MovePackage.Result()
        result.success = True
        self.get_logger().info(f'🤖 [Mock AMR] 단일 패키지 이송 완료: {goal.package_id}')
        return result

    # ==========================================
    # 📦 Action Server: StartPackaging (포장 로봇)
    # ==========================================
    def execute_start_pkg(self, goal_handle):
        goal = goal_handle.request
        self.get_logger().info(f'📦 [Mock 포장로봇] 작업대 {goal.workstation_id} 포장 작업 시작!')

        feedback_msg = StartPackaging.Feedback()
        for slot in range(1, 9):
            # 4번째 포장이 끝났을 때 180도 회전 대기 모의
            if slot == 5:
                self.get_logger().info('📦 [Mock 포장로봇] 4개 슬롯 완료. 180도 회전 상태를 모니터링합니다...')
                rotated = False
                for _ in range(60): # 최대 30초
                    if not rclpy.ok():
                        break
                    try:
                        with self.pg_conn.cursor() as cursor:
                            cursor.execute(
                                "SELECT current_location FROM workstations WHERE workstation_id = %s;",
                                (goal.workstation_id,)
                            )
                            row = cursor.fetchone()
                            if row and row[0] == 'sg2_out_00_A':
                                rotated = True
                                self.get_logger().info(f'📦 [Mock 포장로봇] 작업대 {goal.workstation_id} 회전 완료 감지!')
                                break
                    except Exception as e:
                        self.get_logger().error(f'회전 감지 에러: {e}')
                    time.sleep(0.5)

                if not rotated:
                    self.get_logger().warn('📦 [Mock 포장로봇] 회전 완료 감지 시간 초과! 포장 강제 속행.')

            time.sleep(0.4) # 슬롯 하나 포장 소요 시간
            feedback_msg.completed_slots = slot
            feedback_msg.last_packed_slot = f"slot_{slot}"
            goal_handle.publish_feedback(feedback_msg)
            self.get_logger().info(f'📦 [Mock 포장로봇] {goal.workstation_id} 슬롯 {slot} 포장 완료...')

        goal_handle.succeed()
        result = StartPackaging.Result()
        result.success = True
        result.final_output_ids = [
            f"sg2_out_00_{goal.workstation_id}-{slot}-{goal.today_date}" for slot in range(1, 9)
        ]
        self.get_logger().info(f'📦 [Mock 포장로봇] 작업대 {goal.workstation_id} 전체 포장 및 출고ID 발행 완료!')
        return result

    # ==========================================
    # 📡 관제탑 호출용 Fail-safe & 동기 헬퍼
    # ==========================================
    def call_service_with_fail_safe(self, client, request, service_name, fallback_callback):
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            if client.wait_for_service(timeout_sec=1.0):
                future = client.call_async(request)
                start_time = time.time()
                while rclpy.ok() and not future.done():
                    time.sleep(0.05)
                    if time.time() - start_time > 2.0:
                        break
                if future.done():
                    res = future.result()
                    if res is not None:
                        return res
            time.sleep(0.2)
        return fallback_callback(request)

    def fallback_route(self, request):
        res = GetPackageRoute.Response()
        res.route_destination = '2026-06-06'
        return res

    def fallback_check_warehouse(self, request):
        res = CheckWarehouseStatus.Response()
        res.is_already_in_warehouse = False
        return res

    def fallback_report_inbound(self, request):
        res = ReportInboundProgress.Response()
        res.success = True
        return res


# ==========================================
# 🚚 인바운드 분류 및 적재 루프 스레드
# ==========================================
def inbound_sim_loop(node):
    time.sleep(2.0)
    node.get_logger().info('=== [Mock Inbound] 분류기 및 적재기 시뮬레이션 루프 시작 ===')

    while rclpy.ok():
        if not node.pg_conn:
            time.sleep(2.0)
            continue

        # 영업 시작 상태인지 감시
        day_status = 'RUNNING'
        if node.redis_client:
            try:
                val = node.redis_client.get('system:day_status')
                if val:
                    day_status = val if isinstance(val, str) else val.decode('utf-8')
            except Exception as e:
                node.get_logger().error(f'Redis day_status 조회 실패: {e}')
        
        # WAITING_FOR_START -> RUNNING 상태 전환 감지 시 캐시 로드
        if day_status == 'RUNNING' and node.prev_day_status != 'RUNNING':
            node.load_package_cache()
        node.prev_day_status = day_status
        
        if day_status != 'RUNNING':
            time.sleep(1.0)
            continue

        try:
            with node.pg_conn.cursor() as cursor:
                # 1. WAITING 상태 패키지 중 가장 앞선 것 가져오기
                cursor.execute("SELECT package_id, customer_name, qr_id FROM packages WHERE status = 'WAITING' LIMIT 1;")
                pkg_row = cursor.fetchone()
                
                if not pkg_row:
                    time.sleep(2.0)
                    continue

                pkg_id, cust_name, pkg_qr = pkg_row
                pkg_qr = pkg_qr or pkg_id

                # 2. 로컬 캐시 조회 (GetPackageRoute 서비스 호출 생략)
                dest_date = None
                if pkg_qr in node.package_cache:
                    dest_date = node.package_cache[pkg_qr]
                    node.get_logger().info(f'[Mock Inbound] [Cache Hit] QR: {pkg_qr} -> 목적지: {dest_date}')
                elif pkg_id in node.package_cache:
                    dest_date = node.package_cache[pkg_id]
                    node.get_logger().info(f'[Mock Inbound] [Cache Hit] ID: {pkg_id} -> 목적지: {dest_date}')

                if not dest_date:
                    # 캐시 미스 또는 조회 불가능 시, 4번 바이패스/반송 라인으로 처리
                    node.get_logger().warn(f'[Mock Inbound] [Cache Miss/Error] 패키지 {pkg_id} (QR: {pkg_qr})가 로컬 캐시에 존재하지 않습니다. 안전 회차 라인(4번 라인)으로 Bypass 이송합니다.')
                    cursor.execute(
                        "UPDATE packages SET status = 'IN_WAREHOUSE' WHERE package_id = %s AND status = 'WAITING';",
                        (pkg_id,)
                    )
                    time.sleep(1.0)
                    continue

                # 3. 오늘, 내일, 모레 날짜 계산
                today_date = node.redis_client.get('system:today_date') if node.redis_client else '2026-06-06'
                if not today_date:
                    today_date = '2026-06-06'
                
                try:
                    t_dt = datetime.strptime(today_date, '%Y-%m-%d')
                except ValueError:
                    t_dt = datetime.strptime(today_date, '%Y%m%d')
                
                tomorrow_date = (t_dt + timedelta(days=1)).strftime('%Y-%m-%d')
                day_after_date = (t_dt + timedelta(days=2)).strftime('%Y-%m-%d')

                if dest_date == today_date:
                    target_robot = 'sg2_in_01'
                elif dest_date == tomorrow_date:
                    target_robot = 'sg2_in_02'
                elif dest_date == day_after_date:
                    target_robot = 'sg2_in_03'
                else:
                    target_robot = 'sg2_in_01'

                # 4. 해당 적재 로봇의 A 구역에 작업대가 있는지 확인
                cursor.execute(
                    "SELECT workstation_id, qr_id FROM workstations WHERE current_location = %s LIMIT 1;",
                    (f"{target_robot}_A",)
                )
                ws_row = cursor.fetchone()
                if not ws_row:
                    time.sleep(1.5)
                    continue

                ws_id, ws_qr = ws_row

                # 5. 작업대 내 빈 슬롯 확인
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
                    time.sleep(1.5)
                    continue

                # 6. CheckWarehouseStatus 서비스 호출
                req_chk = CheckWarehouseStatus.Request()
                req_chk.package_id = pkg_id
                req_chk.customer_name = cust_name
                req_chk.qr_id = pkg_qr

                chk_res = node.call_service_with_fail_safe(
                    node.check_warehouse_client, req_chk, 'check_warehouse_status', node.fallback_check_warehouse
                )

                if chk_res.is_already_in_warehouse:
                    cursor.execute(
                        "UPDATE packages SET status = 'IN_WAREHOUSE' WHERE package_id = %s AND status = 'WAITING';",
                        (pkg_id,)
                    )
                    time.sleep(1.0)
                    continue

                # 7. ReportInboundProgress 서비스 호출 (적재 완료 보고)
                req_in = ReportInboundProgress.Request()
                req_in.workstation_id = ws_id
                req_in.robot_id = target_robot
                req_in.filled_slots_count = next_slot
                req_in.package_id = pkg_id
                req_in.workstation_qr_id = ws_qr
                req_in.package_qr_id = pkg_qr

                node.call_service_with_fail_safe(
                    node.report_inbound_client, req_in, 'report_inbound_progress', node.fallback_report_inbound
                )
                node.get_logger().info(f'[Mock Inbound] {target_robot} ➡️ 작업대 {ws_id} 슬롯 {next_slot} 적재 완료 (패키지: {pkg_id})')

                time.sleep(0.8) # 적재 시간 간격
        except Exception as e:
            node.get_logger().error(f'[Mock Inbound Loop Error] {e}')
            time.sleep(2.0)


def main(args=None):
    rclpy.init(args=args)
    node = MockSG2DevicesNode()

    # 인바운드 시뮬레이션 루프 스레드 실행
    inbound_thread = threading.Thread(target=inbound_sim_loop, args=(node,), daemon=True)
    inbound_thread.start()

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('[Mock SG2 Devices] 종료 중...')
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

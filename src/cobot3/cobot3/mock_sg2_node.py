#!/usr/bin/env python3
import time
import os
import redis
import json
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from datetime import datetime, timedelta
import threading

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import Bool

from cobot3_interfaces.action import StartPackaging
from cobot3_interfaces.srv import CheckWarehouseStatus, ReportInboundProgress

class MockSg2Node(Node):
    def __init__(self):
        super().__init__('mock_sg2_node')
        self.callback_group = ReentrantCallbackGroup()
        
        # 1. Infrastructure Setup (Redis & Postgres)
        redis_host = os.environ.get('REDIS_HOST', 'localhost')
        try:
            self.redis_client = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)
            self.get_logger().info(f"Mock SG2: Connected to Redis at {redis_host}:6379")
        except Exception as e:
            self.get_logger().error(f"Mock SG2: Redis connection error: {e}")
            self.redis_client = None

        pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
        try:
            self.pg_pool = ThreadedConnectionPool(
                1, 10,
                host=pg_host,
                port=5432,
                user='rokey',
                password='rokey_pass',
                database='warehouse_db'
            )
            self.get_logger().info(f"Mock SG2: Connected to PostgreSQL pool at {pg_host}")
        except Exception as e:
            self.get_logger().error(f"Mock SG2: PostgreSQL connection error: {e}")
            self.pg_pool = None

        # 2. Pause statuses for robots
        self.is_paused = {
            'sg2_in_01': False,
            'sg2_in_02': False,
            'sg2_in_03': False,
            'sg2_out_00': False
        }
        self.pause_subs = {}
        for robot_id in self.is_paused.keys():
            self.pause_subs[robot_id] = self.create_subscription(
                Bool,
                f'/{robot_id}/pause_status',
                lambda msg, r_id=robot_id: self.pause_callback(msg, r_id),
                10,
                callback_group=self.callback_group
            )

        # 3. Action Server: sg2_out_00 packaging process
        self._action_server = ActionServer(
            self,
            StartPackaging,
            'start_packaging',
            execute_callback=self.execute_packaging_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self.callback_group
        )

        # 4. Service Clients: sg2_in_XX inbound progress reporting
        self.warehouse_status_client = self.create_client(CheckWarehouseStatus, 'check_warehouse_status', callback_group=self.callback_group)
        self.inbound_progress_client = self.create_client(ReportInboundProgress, 'report_inbound_progress', callback_group=self.callback_group)

        # 5. Inbound loading state tracking
        self.active_loadings = set()  # workstation_ids currently being loaded by mock threads
        self.loading_lock = threading.Lock()

        # Timer to scan for workstations at inbound lines to start loading them
        self.inbound_scan_timer = self.create_timer(3.0, self.scan_and_load_inbound_workstations, callback_group=self.callback_group)

        self.get_logger().info('=== 🤖 Mock SG2 Combined Robot Node Ready (Local Testing) ===')
        self.get_logger().info('Features: Inbound Loading Simulation (sg2_in_01/02/03) & Outbound Packaging (sg2_out_00)')

    @contextmanager
    def get_db_conn(self):
        if not self.pg_pool:
            yield None
            return
        conn = None
        try:
            conn = self.pg_pool.getconn()
            conn.autocommit = True
            yield conn
        except Exception as e:
            self.get_logger().error(f"PG connection error: {e}")
            raise e
        finally:
            if conn:
                self.pg_pool.putconn(conn)

    def pause_callback(self, msg, robot_id):
        self.is_paused[robot_id] = msg.data
        if msg.data:
            self.get_logger().warn(f'🚨 [Mock SG2] {robot_id.upper()} robot paused (waiting for workstation swap/rotation)')
        else:
            self.get_logger().info(f'▶️ [Mock SG2] {robot_id.upper()} robot resumed')

    def goal_callback(self, goal_request):
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        return CancelResponse.ACCEPT

    def get_dates_for_lines(self):
        """Fetch today_date from Redis and calculate target dates for line 1, 2, 3"""
        today_date = None
        if self.redis_client:
            try:
                today_date = self.redis_client.get('system:today_date')
            except Exception:
                pass
        
        if not today_date:
            today_date = datetime.now().strftime('%Y-%m-%d')
            
        try:
            t_dt = datetime.strptime(today_date, '%Y-%m-%d')
        except ValueError:
            try:
                t_dt = datetime.strptime(today_date, '%Y%m%d')
            except Exception:
                t_dt = datetime.now()
                
        tomorrow_date = (t_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        day_after_date = (t_dt + timedelta(days=2)).strftime('%Y-%m-%d')
        return today_date, tomorrow_date, day_after_date

    def scan_and_load_inbound_workstations(self):
        """Check if any workstations are waiting at inbound lines, and start loading simulator threads"""
        # Ensure system:inbound_started is true
        if self.redis_client:
            val = self.redis_client.get('system:inbound_started')
            if not val or val != 'true':
                return

        with self.get_db_conn() as conn:
            if not conn:
                return
            try:
                with conn.cursor() as cursor:
                    # Find workstations at inbound active lines (sg2_in_01_A, sg2_in_02_A, sg2_in_03_A)
                    cursor.execute(
                        "SELECT workstation_id, current_location, qr_id FROM workstations "
                        "WHERE current_location IN ('sg2_in_01_A', 'sg2_in_02_A', 'sg2_in_03_A') AND status = 'WAITING';"
                    )
                    rows = cursor.fetchall()
                    for row in rows:
                        ws_id, location, ws_qr = row
                        
                        # Check if already loading
                        with self.loading_lock:
                            if ws_id in self.active_loadings:
                                continue
                            self.active_loadings.add(ws_id)
                        
                        # Start loading simulator thread for this workstation
                        robot_id = location.replace('_A', '')
                        t = threading.Thread(
                            target=self.simulate_inbound_loading_thread,
                            args=(ws_id, robot_id, ws_qr),
                            daemon=True
                        )
                        t.start()
            except Exception as e:
                self.get_logger().error(f"Error scanning inbound workstations: {e}")

    def simulate_inbound_loading_thread(self, ws_id, robot_id, ws_qr):
        self.get_logger().info(f"📥 [Mock SG2] Starting loading sequence for workstation {ws_id} at {robot_id}")
        
        # 1. Determine target date for the inbound line
        today, tomorrow, day_after = self.get_dates_for_lines()
        if robot_id == 'sg2_in_01':
            target_date = today
        elif robot_id == 'sg2_in_02':
            target_date = tomorrow
        else:
            target_date = day_after

        # 2. Query packages waiting for this date that are not loaded
        packages = []
        with self.get_db_conn() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT package_id, customer_name, qr_id FROM packages "
                            "WHERE status = 'WAITING' AND route_zone = %s ORDER BY package_id LIMIT 8;",
                            (target_date,)
                        )
                        rows = cursor.fetchall()
                        for row in rows:
                            packages.append({
                                'package_id': row[0],
                                'customer_name': row[1],
                                'qr_id': row[2] or ""
                            })
                except Exception as e:
                    self.get_logger().error(f"Error fetching packages for line {robot_id}: {e}")

        if not packages:
            self.get_logger().warn(f"⚠️ [Mock SG2] No packages found in database for date {target_date} ({robot_id})")
            with self.loading_lock:
                self.active_loadings.remove(ws_id)
            return

        self.get_logger().info(f"📦 [Mock SG2] Found {len(packages)} packages for {robot_id} to load onto {ws_id}")

        slot = 1
        for pkg in packages:
            pkg_id = pkg['package_id']
            cust_name = pkg['customer_name']
            pkg_qr = pkg['qr_id']

            # Check pause status (e.g. while 180-degree rotation is happening)
            while self.is_paused.get(robot_id, False):
                self.get_logger().info(f"⏸️ [Mock SG2] {robot_id.upper()} is paused. Waiting to resume...")
                time.sleep(0.5)

            # Simulate loading travel time
            time.sleep(1.5)

            # Call check_warehouse_status
            if not self.warehouse_status_client.wait_for_service(timeout_sec=2.0):
                self.get_logger().error(f"CheckWarehouseStatus service not available. Aborting loading thread.")
                break
                
            req = CheckWarehouseStatus.Request()
            req.customer_name = cust_name
            req.package_id = pkg_id
            req.qr_id = pkg_qr
            
            future = self.warehouse_status_client.call_async(req)
            # Wait for response synchronously in thread
            while not future.done():
                time.sleep(0.1)
                
            res = future.result()
            if res.is_already_in_warehouse:
                self.get_logger().info(f"➡️ [Mock SG2] Package {pkg_id} is already in warehouse (AMR direct route). Skipping slot loading.")
                # Update package to IN_WAREHOUSE status directly (bypassing workstation slot loading)
                with self.get_db_conn() as conn:
                    if conn:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                "UPDATE packages SET status = 'IN_WAREHOUSE' WHERE package_id = %s;",
                                (pkg_id,)
                            )
                continue

            # Load into slot
            with self.get_db_conn() as conn:
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                "UPDATE packages SET status = 'IN_WORKSTATION', workstation_id = %s, slot_number = %s WHERE package_id = %s;",
                                (ws_id, slot, pkg_id)
                            )
                    except Exception as e:
                        self.get_logger().error(f"Error loading package {pkg_id} in DB: {e}")
                        break

            # Report inbound progress
            if not self.inbound_progress_client.wait_for_service(timeout_sec=2.0):
                self.get_logger().error("ReportInboundProgress service not available.")
                break

            req_progress = ReportInboundProgress.Request()
            req_progress.workstation_id = ws_id
            req_progress.robot_id = robot_id
            req_progress.filled_slots_count = slot
            req_progress.package_id = pkg_id
            req_progress.workstation_qr_id = ws_qr
            req_progress.package_qr_id = pkg_qr

            future_progress = self.inbound_progress_client.call_async(req_progress)
            while not future_progress.done():
                time.sleep(0.1)

            self.get_logger().info(f"✨ [Mock SG2] {robot_id.upper()} loaded package {pkg_id} in slot {slot} of {ws_id}")
            slot += 1
            if slot > 8:
                break

        self.get_logger().info(f"✅ [Mock SG2] Completed loading WS {ws_id} at {robot_id}!")
        with self.loading_lock:
            self.active_loadings.remove(ws_id)

    def execute_packaging_callback(self, goal_handle):
        """Simulate packaging process for workstation slots on sg2_out_00"""
        goal = goal_handle.request
        workstation_id = goal.workstation_id
        today_date = goal.today_date
        
        self.get_logger().info(f"📦 [Mock SG2] starting packaging for workstation {workstation_id}...")
        
        feedback_msg = StartPackaging.Feedback()
        slot = 1
        
        while slot <= 8:
            # Check pause status (e.g. while 180-degree rotation is happening)
            if self.is_paused.get('sg2_out_00', False):
                self.get_logger().info('⏸️ [Mock SG2] Packaging robot paused. Waiting for rotation...')
                while self.is_paused.get('sg2_out_00', False):
                    time.sleep(0.1)
                self.get_logger().info('▶️ [Mock SG2] Packaging robot resumed.')

            # Simulate packaging time
            time.sleep(1.2)
            
            if self.is_paused.get('sg2_out_00', False):
                continue

            feedback_msg.completed_slots = slot
            feedback_msg.last_packed_slot = f"slot_{slot}"
            goal_handle.publish_feedback(feedback_msg)
            self.get_logger().info(f'✨ [Mock SG2] Packaged slot_{slot} of {workstation_id} ({slot}/8)')
            
            slot += 1

        goal_handle.succeed()
        
        # Return result with unique tracking IDs
        result = StartPackaging.Result()
        result.success = True
        timestamp = datetime.now().strftime('%H%M%S')
        result.final_output_ids = [
            f"sg2_out_00_{workstation_id}_SLOT{i}_{today_date}_{timestamp}" 
            for i in range(1, 9)
        ]
        self.get_logger().info(f'✅ [Mock SG2] Outbound packaging completed for workstation {workstation_id}!')
        return result

def main(args=None):
    rclpy.init(args=args)
    node = MockSg2Node()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

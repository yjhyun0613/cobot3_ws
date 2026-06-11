#!/usr/bin/env python3
import time
import json
import os
import re
import redis
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import String

# Import Custom ROS 2 interfaces
from cobot3_interfaces.action import MovePackage, ManageWorkstation

class MockAmrNode(Node):
    def __init__(self):
        super().__init__('mock_amr_node')
        
        self.callback_group = ReentrantCallbackGroup()
        
        # 1. Redis Connection Setup
        redis_host = os.environ.get('REDIS_HOST', 'localhost')
        try:
            self.redis_client = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)
            self.get_logger().info(f"Connected to Redis at {redis_host}:6379")
        except Exception as e:
            self.get_logger().error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

        # 2. PostgreSQL Connection Setup
        pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
        try:
            self.pg_pool = ThreadedConnectionPool(
                1, 5,
                host=pg_host,
                port=5432,
                user='rokey',
                password='rokey_pass',
                database='warehouse_db'
            )
            self.get_logger().info(f"Connected to PostgreSQL pool at {pg_host}")
        except Exception as e:
            self.get_logger().error(f"Failed to connect to PostgreSQL: {e}")
            self.pg_pool = None

        # 3. Initialize AMR states & positions
        self.amr_names = ["amr_01", "amr_02", "amr_03", "amr_04"]
        # Default start positions (Charging spots on the 2D grid)
        self.amr_positions = {
            "amr_01": "FLOOR_X_-6.0_Y_-9.0",  # charging_01
            "amr_02": "FLOOR_X_-6.0_Y_-7.5",  # charging_02
            "amr_03": "FLOOR_X_-6.0_Y_-6.0",  # charging_03
            "amr_04": "FLOOR_X_-6.0_Y_-4.5"   # charging_04
        }
        self.amr_carrying = {name: "" for name in self.amr_names}
        self.amr_states = {name: "IDLE" for name in self.amr_names}
        
        # Update Redis with initial idle states immediately
        self.update_all_redis_keys()

        # 4. Subscribe to task events to track which AMR is assigned to which task
        self.assignments = {}        # workstation_id -> assigned_amr
        self.pkg_assignments = {}    # package_id -> assigned_amr
        
        self.task_event_sub = self.create_subscription(
            String,
            '/fleet/task_events',
            self.task_event_callback,
            10,
            callback_group=self.callback_group
        )

        # 5. Start Action Servers
        self._manage_ws_server = ActionServer(
            self,
            ManageWorkstation,
            'manage_workstation',
            execute_callback=self.execute_manage_ws_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self.callback_group
        )
        
        self._move_pkg_server = ActionServer(
            self,
            MovePackage,
            'move_package',
            execute_callback=self.execute_move_pkg_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self.callback_group
        )

        # 6. Timer to refresh Redis keys periodically (keep alive, keep status green)
        self.redis_refresh_timer = self.create_timer(1.0, self.redis_refresh_callback, callback_group=self.callback_group)
        
        self.get_logger().info('=== 🤖 Mock AMR Fleet Node Ready (Local Testing) ===')
        self.get_logger().info('Action Servers: /manage_workstation, /move_package')
        self.get_logger().info('Subscribed to: /fleet/task_events')

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

    def update_all_redis_keys(self):
        if not self.redis_client:
            return
        try:
            for name in self.amr_names:
                redis_key = f"amr:{name}"
                state = self.amr_states[name]
                current_qr = self.amr_positions[name]
                carrying = self.amr_carrying[name]
                
                self.redis_client.hset(redis_key, mapping={
                    "state": state,
                    "current_qr_id": current_qr,
                    "carrying_workstation_id": carrying,
                    "battery": "100.0"
                })
        except Exception as e:
            self.get_logger().error(f"Redis update error: {e}")

    def redis_refresh_callback(self):
        """Keep Redis state updated so dashboard reflects AMR connectivity and position"""
        self.update_all_redis_keys()

    def task_event_callback(self, msg):
        """Parse task events to dynamically resolve which AMR is carrying what workstation/package"""
        try:
            event = json.loads(msg.data)
            status = event.get("status")
            task_type = event.get("type")
            assigned_amr = event.get("assigned_amr")
            
            if status == "ASSIGNED" and assigned_amr:
                # Normalize AMR name format (e.g. "amr_01")
                amr_normalized = assigned_amr.lower()
                if amr_normalized in self.amr_names:
                    if task_type == "MOVE_WORKSTATION":
                        ws_id = event.get("workstation_id")
                        if ws_id:
                            self.assignments[ws_id] = amr_normalized
                            self.get_logger().info(f"[Task Track] Workstation {ws_id} assigned to {amr_normalized}")
                    elif task_type == "DIRECT_WAREHOUSE":
                        pkg_id = event.get("package_id")
                        if pkg_id:
                            self.pkg_assignments[pkg_id] = amr_normalized
                            self.get_logger().info(f"[Task Track] Package {pkg_id} assigned to {amr_normalized}")
        except Exception as e:
            self.get_logger().error(f"Error parsing task event: {e}")

    def goal_callback(self, goal_request):
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        return CancelResponse.ACCEPT

    def parse_coords_from_qr(self, qr_id):
        """Parse float coordinates from floor QR ID string format FLOOR_X_coord_Y_coord"""
        if not qr_id or not qr_id.startswith("FLOOR_X_"):
            return None
        match = re.match(r"FLOOR_X_(-?\d+\.?\d*)_Y_(-?\d+\.?\d*)", qr_id)
        if match:
            return float(match.group(1)), float(match.group(2))
        return None

    def query_coords_by_location_name(self, loc_name):
        """Query floor_qr_map in DB to find physical coordinates of a location name"""
        with self.get_db_conn() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT qr_id, x_coord, y_coord FROM floor_qr_map WHERE location_name = %s;", (loc_name,))
                        row = cursor.fetchone()
                        if row:
                            return row[0], row[1], row[2]
                except Exception as e:
                    self.get_logger().error(f"DB query error for location {loc_name}: {e}")
        return None

    def execute_manage_ws_callback(self, goal_handle):
        """Simulate physical drive, updating Redis grid positions step-by-step"""
        goal = goal_handle.request
        ws_id = goal.workstation_id
        start_loc = goal.start_location
        target_loc = goal.target_location
        
        # 1. Determine which AMR is assigned
        assigned_amr = self.assignments.get(ws_id)
        if not assigned_amr:
            # Fallback: Find an IDLE amr
            for name in self.amr_names:
                if self.amr_states[name] == "IDLE":
                    assigned_amr = name
                    break
            if not assigned_amr:
                assigned_amr = "amr_01"

        self.get_logger().info(f"⚡ [Mock AMR] {assigned_amr.upper()} starting MOVE_WORKSTATION: {ws_id} ({start_loc} -> {target_loc})")
        
        # 2. Resolve start/end coords
        start_qr = self.amr_positions[assigned_amr]
        start_coords = self.parse_coords_from_qr(start_qr)
        if not start_coords:
            # Try to query start location name from DB
            row = self.query_coords_by_location_name(start_loc)
            if row:
                start_qr, sx, sy = row
                start_coords = (sx, sy)
            else:
                start_coords = (0.0, 0.0)

        # Resolve target coords
        target_qr = goal.target_qr_id
        target_coords = (goal.target_x, goal.target_y)
        if not target_qr or target_coords == (0.0, 0.0):
            row = self.query_coords_by_location_name(target_loc)
            if row:
                target_qr, tx, ty = row
                target_coords = (tx, ty)
            else:
                target_qr = "FLOOR_X_0.0_Y_0.0"
                target_coords = (0.0, 0.0)

        # 3. Simulate movement in 5 steps
        self.amr_states[assigned_amr] = "NAVIGATING"
        self.amr_carrying[assigned_amr] = ws_id
        
        x1, y1 = start_coords
        x2, y2 = target_coords
        
        steps = 5
        feedback_msg = ManageWorkstation.Feedback()
        feedback_msg.status = "NAVIGATING"
        
        for step in range(1, steps + 1):
            time.sleep(0.8)  # Travel time simulation per step
            
            # Linear interpolation
            ratio = step / steps
            curr_x = x1 + (x2 - x1) * ratio
            curr_y = y1 + (y2 - y1) * ratio
            
            # Snap to grid coordinate intervals of 1.5m
            snapped_x = round(curr_x / 1.5) * 1.5
            snapped_y = round(curr_y / 1.5) * 1.5
            
            curr_qr = f"FLOOR_X_{snapped_x:.1f}_Y_{snapped_y:.1f}"
            self.amr_positions[assigned_amr] = curr_qr
            
            # Update Redis
            self.update_all_redis_keys()
            
            # Distance remaining
            dist_remaining = ((x2 - curr_x)**2 + (y2 - curr_y)**2) ** 0.5
            feedback_msg.distance_remaining = float(dist_remaining)
            goal_handle.publish_feedback(feedback_msg)
            
            self.get_logger().info(f"  - {assigned_amr.upper()} at step {step}/{steps}: Position {curr_qr}")

        # 4. Arrived
        self.amr_states[assigned_amr] = "IDLE"
        self.amr_carrying[assigned_amr] = ""
        self.amr_positions[assigned_amr] = target_qr
        self.update_all_redis_keys()

        goal_handle.succeed()
        result = ManageWorkstation.Result()
        result.success = True
        self.get_logger().info(f"✅ [Mock AMR] {assigned_amr.upper()} successfully moved {ws_id} to {target_loc}!")
        return result

    def execute_move_pkg_callback(self, goal_handle):
        """Simulate single package direct shipment movement"""
        goal = goal_handle.request
        pkg_id = goal.package_id
        dest_zone = goal.destination_zone
        
        # 1. Determine which AMR is assigned
        assigned_amr = self.pkg_assignments.get(pkg_id)
        if not assigned_amr:
            for name in self.amr_names:
                if self.amr_states[name] == "IDLE":
                    assigned_amr = name
                    break
            if not assigned_amr:
                assigned_amr = "amr_01"

        self.get_logger().info(f"⚡ [Mock AMR] {assigned_amr.upper()} starting MOVE_PACKAGE: {pkg_id} to {dest_zone}")
        
        # 2. Resolve start/end coords
        start_qr = self.amr_positions[assigned_amr]
        start_coords = self.parse_coords_from_qr(start_qr) or (0.0, 0.0)
        
        # Resolve destination coords (e.g. spot_09, etc.)
        row = self.query_coords_by_location_name(dest_zone)
        if row:
            target_qr, tx, ty = row
            target_coords = (tx, ty)
        else:
            target_qr = "FLOOR_X_0.0_Y_0.0"
            target_coords = (0.0, 0.0)

        # 3. Simulate movement in 5 steps
        self.amr_states[assigned_amr] = "NAVIGATING"
        self.amr_carrying[assigned_amr] = f"PKG:{pkg_id}"
        
        x1, y1 = start_coords
        x2, y2 = target_coords
        
        steps = 5
        feedback_msg = MovePackage.Feedback()
        
        for step in range(1, steps + 1):
            time.sleep(0.8)
            
            ratio = step / steps
            curr_x = x1 + (x2 - x1) * ratio
            curr_y = y1 + (y2 - y1) * ratio
            
            snapped_x = round(curr_x / 1.5) * 1.5
            snapped_y = round(curr_y / 1.5) * 1.5
            
            curr_qr = f"FLOOR_X_{snapped_x:.1f}_Y_{snapped_y:.1f}"
            self.amr_positions[assigned_amr] = curr_qr
            
            self.update_all_redis_keys()
            
            feedback_msg.current_position = curr_qr
            feedback_msg.progress = float(ratio * 100.0)
            goal_handle.publish_feedback(feedback_msg)
            
            self.get_logger().info(f"  - {assigned_amr.upper()} (pkg) step {step}/{steps}: Position {curr_qr}")

        # 4. Arrived
        self.amr_states[assigned_amr] = "IDLE"
        self.amr_carrying[assigned_amr] = ""
        self.amr_positions[assigned_amr] = target_qr
        self.update_all_redis_keys()

        goal_handle.succeed()
        result = MovePackage.Result()
        result.success = True
        self.get_logger().info(f"✅ [Mock AMR] {assigned_amr.upper()} successfully delivered package {pkg_id} to {dest_zone}!")
        return result

def main(args=None):
    rclpy.init(args=args)
    node = MockAmrNode()
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

#!/usr/bin/env python3
import os
import sys
import time
import csv
import redis
from datetime import datetime, timedelta

import rclpy
from rclpy.node import Node
from cobot3_interfaces.srv import TransitPackage

class MockBG2Spawner(Node):
    def __init__(self):
        super().__init__('mock_bg2_spawner')
        self.get_logger().info("=========================================")
        self.get_logger().info("🚀 Mock BG2 Package Spawner Node Started")
        self.get_logger().info("=========================================")

        # Connect to Redis to check today's date & business status
        redis_host = os.environ.get('REDIS_HOST', 'localhost')
        redis_port = int(os.environ.get('REDIS_PORT', 6379))
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True,
                socket_timeout=2.0
            )
            self.get_logger().info(f"Connected to Redis at {redis_host}:{redis_port}")
        except Exception as e:
            self.get_logger().error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

        # Create service client for /sim/transit_package
        self.client = self.create_client(TransitPackage, '/sim/transit_package')
        while not self.client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Waiting for /sim/transit_package service to become available...')

        self.csv_path = '/home/yoon/cobot3_ws/scratch/packages_2026-06-08.csv'
        self.packages = []
        self.load_csv()

        # Index to keep track of packages in the list
        self.current_index = 0

        # Start timer loop (runs every 10.0 seconds)
        self.timer = self.create_timer(10.0, self.timer_callback)
        self.get_logger().info("Spawning timer initialized (10s interval).")

    def load_csv(self):
        if not os.path.exists(self.csv_path):
            self.get_logger().error(f"CSV file not found at {self.csv_path}")
            return
        
        try:
            with open(self.csv_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.packages.append({
                        'package_id': row['package_id'],
                        'route_zone': row['route_zone']
                    })
            self.get_logger().info(f"Successfully loaded {len(self.packages)} packages from CSV.")
        except Exception as e:
            self.get_logger().error(f"Error loading CSV file: {e}")

    def get_today_date(self):
        if self.redis_client:
            try:
                today = self.redis_client.get('system:today_date')
                if today:
                    return today
            except Exception as e:
                self.get_logger().warn(f"Failed to read system:today_date from Redis: {e}")
        return "2026-06-08"

    def is_inbound_started(self):
        if self.redis_client:
            try:
                val = self.redis_client.get('system:inbound_started')
                return val == 'true'
            except Exception as e:
                self.get_logger().warn(f"Failed to read system:inbound_started from Redis: {e}")
        return True # Default to True if Redis connection is not established

    def get_target_line(self, route_zone, today_str):
        try:
            t_dt = datetime.strptime(today_str, '%Y-%m-%d')
        except Exception:
            t_dt = datetime.strptime("2026-06-08", '%Y-%m-%d')
            
        tomorrow_str = (t_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        day_after_str = (t_dt + timedelta(days=2)).strftime('%Y-%m-%d')
        
        if route_zone == today_str:
            return 'sg2_in_01'
        elif route_zone == tomorrow_str:
            return 'sg2_in_02'
        elif route_zone == day_after_str:
            return 'sg2_in_03'
        else:
            return 'sg2_in_01'

    def timer_callback(self):
        # 1. Check if business has started
        if not self.is_inbound_started():
            self.get_logger().info("[Mock BG2] 영업이 개시되지 않았거나 중지되었습니다 (system:inbound_started=false). 대기 중...")
            return

        # 2. Check if all packages have been spawned
        if self.current_index >= len(self.packages):
            self.get_logger().info("[Mock BG2] 모든 CSV 패키지가 스폰되었습니다. 루프를 처음부터 재시작합니다.")
            self.current_index = 0

        if not self.packages:
            self.get_logger().warn("[Mock BG2] 스폰할 패키지 명단이 비어 있습니다.")
            return

        # 3. Get current package info
        pkg = self.packages[self.current_index]
        package_id = pkg['package_id']
        route_zone = pkg['route_zone']
        
        today_str = self.get_today_date()
        target_line = self.get_target_line(route_zone, today_str)

        self.get_logger().info(f"[Mock BG2] Spawning Package: {package_id} | Route Zone: {route_zone} | Target Line: {target_line}")

        # 4. Call /sim/transit_package service
        req = TransitPackage.Request()
        req.package_id = package_id
        req.target_line = target_line

        future = self.client.call_async(req)
        future.add_done_callback(self.service_response_callback)

        # Move to next index
        self.current_index += 1

    def service_response_callback(self, future):
        try:
            response = future.result()
            if response.success:
                self.get_logger().info(f"[Service Response] Success: {response.message}")
            else:
                self.get_logger().error(f"[Service Response] Failed: {response.message}")
        except Exception as e:
            self.get_logger().error(f"Service call failed: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = MockBG2Spawner()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Keyboard Interrupt detected. Shutting down...")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

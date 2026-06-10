#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from cobot3_interfaces.srv import ReportInboundProgress # 또는 커스텀 서비스 호환 사용
import psycopg2
import redis
import json
import os
import time

class SimSyncNode(Node):
    def __init__(self):
        super().__init__('sim_sync_node')
        self.get_logger().info('=== 🌐 분산 시뮬레이션 상자 동기화 전담 노드(SimSync) 구동 ===')

        # 1. DB 및 Redis 환경 변수 획득
        pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
        redis_host = os.environ.get('REDIS_HOST', 'localhost')

        try:
            self.conn = psycopg2.connect(
                host=pg_host, port=5432, user='rokey', password='rokey_pass', database='warehouse_db'
            )
            self.conn.autocommit = True
            self.redis_client = redis.Redis(host=redis_host, port=6379, decode_responses=True)
            self.get_logger().info('PostgreSQL 및 Redis 캐시 시스템 연동 완료.')
        except Exception as e:
            self.get_logger().error(f'인프라 연결 실패: {str(e)}')

        # 2. bg2 시뮬레이터로부터 '탈출 신호'를 수신할 ROS 2 토픽/서비스 정의
        # 확장성과 범용성을 위해 JSON 직렬화 문자열 토픽 채널 개설
        self.bg2_exit_sub = self.create_subscription(
            String,
            '/sim/bg2_exit_event',
            self.bg2_exit_callback,
            10
        )

        # 3. sg2 시뮬레이터에게 '소환 명령'을 하달할 ROS 2 퍼블리셔 정의
        self.sg2_spawn_pub = self.create_publisher(String, '/sim/sg2_spawn_trigger', 10)

    def bg2_exit_callback(self, msg):
        """bg2 벨트 끝단 접촉 시 트리거되는 코어 비동기 콜백"""
        try:
            data = json.loads(msg.data)
            package_id = data.get('package_id')
            target_line = data.get('target_line') # 예: 'sg2_in_01', 'sg2_in_02'

            self.get_logger().info(f'[싱크 통신] 상자 탈출 감지 ➔ ID: {package_id} | 목적라인: {target_line}')

            # 1. PostgreSQL DB 상태 마스킹 (이동 중 상태로 변환하여 데이터 정합성 보존)
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE packages SET status = 'TRANSIT_TO_SG2' WHERE package_id = %s;",
                (package_id,)
            )
            cursor.close()

            # 2. sg2 시뮬레이터 PC가 구독 중인 채널로 소환 명령 던지기
            spawn_payload = {
                "package_id": package_id,
                "target_line": target_line,
                "timestamp": time.time()
            }
            
            pub_msg = String()
            pub_msg.data = json.dumps(spawn_payload)
            self.sg2_spawn_pub.publish(pub_msg)
            self.get_logger().info(f'[싱크 통신] sg2 월드로 소환 이벤트 송신 완료 ➔ {package_id}')

        except Exception as e:
            self.get_logger().error(f'동기화 처리 루프 에러: {str(e)}')

def main(args=None):
    rclpy.init(args=args)
    node = SimSyncNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(node, 'conn'):
            node.conn.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""
🌐 분산 시뮬레이션 상자 동기화 전담 노드 (sim_sync_node)
==========================================================
Isaac Sim bg2(분류 라인)와 sg2(적재/포장 라인) 환경 간의
상자 순간이동(소멸 및 소환) 로직을 전담 제어하는 독립 ROS 2 노드.

관제탑(control_tower_node.py)과 완전히 분리되어,
시뮬레이션 환경에서만 구동하고 상용 환경에서는 비활성화합니다.

통신 채널:
  - [Service] /sim/transit_package  ← bg2가 상자 이송 요청
  - [Topic]   /sim/bg2_exit_event   ← bg2 벨트 끝단 접촉 감지 (대체 채널)
  - [Topic]   /sim/sg2_spawn_trigger → sg2에 상자 소환 명령 발행
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from cobot3_interfaces.srv import TransitPackage
import psycopg2
import redis
import json
import os
import time


class SimSyncNode(Node):
    """bg2 ↔ sg2 분산 시뮬레이션 환경 간 상자 동기화 전담 노드."""

    def __init__(self):
        super().__init__('sim_sync_node')
        self.get_logger().info(
            '=== 🌐 분산 시뮬레이션 상자 동기화 전담 노드(SimSync) 구동 ==='
        )

        # ──────────────────────────────────────────────
        # 1. DB 및 Redis 환경 변수 획득
        # ──────────────────────────────────────────────
        pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
        pg_port = int(os.environ.get('POSTGRES_PORT', '5432'))
        pg_user = os.environ.get('POSTGRES_USER', 'rokey')
        pg_pass = os.environ.get('POSTGRES_PASSWORD', 'rokey_pass')
        pg_db = os.environ.get('POSTGRES_DB', 'warehouse_db')
        redis_host = os.environ.get('REDIS_HOST', 'localhost')
        redis_port = int(os.environ.get('REDIS_PORT', '6379'))

        self.conn = None
        self.redis_client = None

        try:
            self.conn = psycopg2.connect(
                host=pg_host, port=pg_port,
                user=pg_user, password=pg_pass,
                database=pg_db
            )
            self.conn.autocommit = True
            self.redis_client = redis.Redis(
                host=redis_host, port=redis_port,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=3.0
            )
            self.get_logger().info(
                f'PostgreSQL({pg_host}:{pg_port}) 및 '
                f'Redis({redis_host}:{redis_port}) 캐시 시스템 연동 완료.'
            )
        except Exception as e:
            self.get_logger().error(f'인프라 연결 실패: {str(e)}')

        # ──────────────────────────────────────────────
        # 2. ROS 2 서비스 서버: bg2로부터 상자 이송 요청 수신
        #    isaac_sim.ipynb 계획서의 /sim/transit_package 규격
        # ──────────────────────────────────────────────
        self.transit_srv = self.create_service(
            TransitPackage,
            '/sim/transit_package',
            self.transit_package_callback
        )
        self.get_logger().info(
            '[서비스] /sim/transit_package 서비스 서버 등록 완료'
        )

        # ──────────────────────────────────────────────
        # 3. 토픽 채널 (대체/호환용)
        #    bg2 → 탈출 신호 수신 (JSON String)
        # ──────────────────────────────────────────────
        self.bg2_exit_sub = self.create_subscription(
            String,
            '/sim/bg2_exit_event',
            self.bg2_exit_callback,
            10
        )

        # ──────────────────────────────────────────────
        # 4. sg2 시뮬레이터에게 '소환 명령' 하달 퍼블리셔
        # ──────────────────────────────────────────────
        self.sg2_spawn_pub = self.create_publisher(
            String, '/sim/sg2_spawn_trigger', 10
        )

        self.get_logger().info(
            '[토픽] /sim/bg2_exit_event 구독 및 '
            '/sim/sg2_spawn_trigger 발행 채널 준비 완료'
        )

    # ──────────────────────────────────────────────────
    # 서비스 콜백: /sim/transit_package
    # ──────────────────────────────────────────────────
    def transit_package_callback(self, request, response):
        """bg2 시뮬레이터가 상자 이송을 요청할 때 호출되는 서비스 콜백."""
        package_id = request.package_id
        target_line = request.target_line

        self.get_logger().info(
            f'[서비스 수신] 상자 이송 요청 ➔ '
            f'ID: {package_id} | 목적라인: {target_line}'
        )

        try:
            # 1. PostgreSQL DB 상태 마스킹
            self._update_db_status(package_id, 'TRANSIT_TO_SG2')

            # 2. sg2 시뮬레이터로 소환 이벤트 발행
            self._publish_spawn_trigger(package_id, target_line)

            response.success = True
            response.message = (
                f'상자 {package_id}의 sg2 소환 이벤트 발행 완료 '
                f'(목적라인: {target_line})'
            )
            self.get_logger().info(
                f'[서비스 응답] ✅ {package_id} 이송 동기화 성공'
            )

        except Exception as e:
            response.success = False
            response.message = f'이송 동기화 실패: {str(e)}'
            self.get_logger().error(
                f'[서비스 응답] ❌ {package_id} 이송 동기화 실패: {str(e)}'
            )

        return response

    # ──────────────────────────────────────────────────
    # 토픽 콜백: /sim/bg2_exit_event (대체 채널)
    # ──────────────────────────────────────────────────
    def bg2_exit_callback(self, msg):
        """bg2 벨트 끝단 접촉 시 트리거되는 토픽 기반 비동기 콜백."""
        try:
            data = json.loads(msg.data)
            package_id = data.get('package_id')
            target_line = data.get('target_line')

            self.get_logger().info(
                f'[토픽 수신] 상자 탈출 감지 ➔ '
                f'ID: {package_id} | 목적라인: {target_line}'
            )

            # 1. PostgreSQL DB 상태 마스킹
            self._update_db_status(package_id, 'TRANSIT_TO_SG2')

            # 2. sg2 시뮬레이터로 소환 이벤트 발행
            self._publish_spawn_trigger(package_id, target_line)

        except Exception as e:
            self.get_logger().error(f'동기화 처리 루프 에러: {str(e)}')

    # ──────────────────────────────────────────────────
    # 내부 유틸리티 메서드
    # ──────────────────────────────────────────────────
    def _update_db_status(self, package_id, status):
        """PostgreSQL 데이터베이스의 패키지 상태를 갱신합니다."""
        if self.conn is None:
            self.get_logger().warn('DB 연결 없음 - 상태 갱신 생략')
            return

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE packages SET status = %s WHERE package_id = %s;",
                (status, package_id)
            )
            cursor.close()
            self.get_logger().info(
                f'[DB] {package_id} 상태 → {status} 갱신 완료'
            )
        except Exception as e:
            self.get_logger().error(f'[DB] 상태 갱신 실패: {str(e)}')

    def _publish_spawn_trigger(self, package_id, target_line):
        """sg2 시뮬레이터에 상자 소환 명령 토픽을 발행합니다."""
        spawn_payload = {
            "package_id": package_id,
            "target_line": target_line,
            "timestamp": time.time()
        }

        pub_msg = String()
        pub_msg.data = json.dumps(spawn_payload)
        self.sg2_spawn_pub.publish(pub_msg)
        self.get_logger().info(
            f'[토픽 발행] sg2 월드로 소환 이벤트 송신 완료 ➔ {package_id}'
        )


def main(args=None):
    rclpy.init(args=args)
    node = SimSyncNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(node, 'conn') and node.conn is not None:
            node.conn.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
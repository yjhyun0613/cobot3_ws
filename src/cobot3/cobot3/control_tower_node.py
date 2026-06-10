import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.action import ActionClient
import os
import threading

# 커스텀 ROS2 인터페이스 임포트
from cobot3_interfaces.srv import GetPackageRoute, CheckWarehouseStatus, ReportInboundProgress
from cobot3_interfaces.action import MovePackage, ManageWorkstation, StartPackaging
from std_msgs.msg import String, Bool

import json
import time
from datetime import datetime

# 데이터베이스 연동 라이브러리 임포트 시도
try:
    import psycopg2
    from psycopg2.pool import ThreadedConnectionPool
    import redis
    DB_LIBS_AVAILABLE = True
except ImportError:
    DB_LIBS_AVAILABLE = False

from contextlib import contextmanager


class ControlTowerNode(Node):
    def __init__(self):
        super().__init__('control_tower_node')
        self.get_logger().info('=== 쿠팡 물류창고 관제 센터(Control Tower) 노드 구동 시작 ===')

        # ----------------------------------------------------
        # 스레드 동기화 락 추가 (Race Condition 방지)
        # ----------------------------------------------------
        self.trigger_lock = threading.Lock()
        self.pre_fetch_triggered = set()
        self.rotation_triggered = set()

        # 1. 데이터베이스 연결 정보 설정
        self.pg_conn_pool = None
        self.redis_client = None
        self.init_databases()

        # 2. ROS2 서비스 서버 등록 (로봇들로부터의 요청 수신)
        self.route_service = self.create_service(
            GetPackageRoute,
            'get_package_route',
            self.get_package_route_callback
        )
        self.warehouse_status_service = self.create_service(
            CheckWarehouseStatus,
            'check_warehouse_status',
            self.check_warehouse_status_callback
        )
        self.inbound_progress_service = self.create_service(
            ReportInboundProgress,
            'report_inbound_progress',
            self.report_inbound_progress_callback
        )

        # 3. ROS2 액션 클라이언트 등록 (AMR 및 포장 로봇에게 명령 하달)
        self.move_package_action_client = ActionClient(self, MovePackage, 'move_package')
        self.manage_workstation_action_client = ActionClient(self, ManageWorkstation, 'manage_workstation')
        self.start_packaging_action_client = ActionClient(self, StartPackaging, 'start_packaging')

        # 3.5 fleet 상태 모니터링용 JSON 토픽 퍼블리셔 등록
        self.amr_states_pub = self.create_publisher(String, '/fleet/amr_states', 10)
        self.workstation_states_pub = self.create_publisher(String, '/fleet/workstation_states', 10)
        self.package_states_pub = self.create_publisher(String, '/fleet/package_states', 10)
        self.task_events_pub = self.create_publisher(String, '/fleet/task_events', 10)

        # 3.6 입고 및 출고 로봇(sg2_in, sg2_out) 일시 정지 제어 퍼블리셔 등록
        self.sg2_pause_pubs = {
            'sg2_in_01': self.create_publisher(Bool, '/sg2_in_01/pause_status', 10),
            'sg2_in_02': self.create_publisher(Bool, '/sg2_in_02/pause_status', 10),
            'sg2_in_03': self.create_publisher(Bool, '/sg2_in_03/pause_status', 10),
            'sg2_out_00': self.create_publisher(Bool, '/sg2_out_00/pause_status', 10)
        }

        # 4. 주기적 상태 체크 및 스케줄러 타이머 구동 (1초마다 실행)
        self.scheduler_timer = self.create_timer(1.0, self.task_scheduler_loop)
        # fleet 상태 브로드캐스트 타이머 구동 (1초마다 실행)
        self.fleet_states_timer = self.create_timer(1.0, self.publish_fleet_states_callback)
        
        self.get_logger().info('ROS2 서비스 서버, 액션 클라이언트 및 Fleet 퍼블리셔 준비 완료.')


    def init_databases(self):
        """데이터베이스 연결 초기화"""
        if not DB_LIBS_AVAILABLE:
            self.get_logger().error(
                'psycopg2 또는 redis 모듈이 설치되지 않았습니다. '
                '가상 시뮬레이션(Mock 모드)으로 동작합니다.'
            )
            return

        # ----------------------------------------------------
        # Docker 환경 변수 지원 (localhost 하드코딩 제거)
        # ----------------------------------------------------
        pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
        redis_host = os.environ.get('REDIS_HOST', 'localhost')

        try:
            # PostgreSQL 연결 풀 생성 (ThreadedConnectionPool)
            self.pg_conn_pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                host=pg_host,
                port=5432,
                user='rokey',
                password='rokey_pass',
                database='warehouse_db'
            )
            self.get_logger().info(f'PostgreSQL Threaded Connection Pool 생성 완료. (Host: {pg_host})')

            # Redis 연결
            self.redis_client = redis.Redis(
                host=redis_host,
                port=6379,
                decode_responses=True
            )
            self.get_logger().info(f'Redis 인메모리 데이터베이스 연결 완료. (Host: {redis_host})')

            # ----------------------------------------------------
            # 초기 상태값 설정 (대시보드 시작 버튼 제어용)
            # ----------------------------------------------------
            if not self.redis_client.exists('system:day_status'):
                self.redis_client.set('system:day_status', 'WAITING_FOR_START')
                self.get_logger().info("초기 시스템 상태를 'WAITING_FOR_START'로 설정했습니다.")
            if not self.redis_client.exists('system:inbound_started'):
                self.redis_client.set('system:inbound_started', 'false')
                self.get_logger().info("초기 인바운드 상태를 'false'로 설정했습니다.")
            
            # EOD Redis 카운터 초기화
            self.init_eod_counters()

        except Exception as e:
            self.get_logger().error(f'데이터베이스 연결 중 오류 발생: {str(e)}')
            self.get_logger().warn('데이터베이스 연결 실패로 가상 시뮬레이션(Mock 모드)으로 동작합니다.')
            self.pg_conn_pool = None
            self.redis_client = None

    def init_eod_counters(self, cursor=None):
        """오늘 날짜의 패키지 개수로 Redis 카운터 초기화"""
        if not self.redis_client:
            return
        
        def do_init(cur):
            today_date = self.redis_client.get('system:today_date')
            if not today_date:
                today_date = datetime.now().strftime('%Y-%m-%d')
            
            # 오늘 날짜 총 패키지 수 조회
            cur.execute("SELECT COUNT(*) FROM packages WHERE route_zone = %s;", (today_date,))
            total = cur.fetchone()[0]
            
            # 완료된 패키지 수 조회
            cur.execute("SELECT COUNT(*) FROM packages WHERE route_zone = %s AND status = 'COMPLETED';", (today_date,))
            completed = cur.fetchone()[0]
            
            self.redis_client.set('system:today_total_packages', total)
            self.redis_client.set('system:today_completed_count', completed)
            self.get_logger().info(f'[Redis Counter Init] 오늘({today_date})의 총 패키지 수: {total}, 완료된 수: {completed}')

        if cursor:
            do_init(cursor)
        else:
            with self.get_db_connection() as conn:
                if conn:
                    with conn.cursor() as cur:
                        do_init(cur)

    @contextmanager
    def get_db_connection(self):
        """커넥션 풀에서 커넥션을 안전하게 가져오고 반환하는 컨텍스트 매니저"""
        if not self.pg_conn_pool:
            yield None
            return
        conn = None
        try:
            conn = self.pg_conn_pool.getconn()
            conn.autocommit = True
            yield conn
        except Exception as e:
            self.get_logger().error(f'DB 커넥션 풀 사용 중 오류 발생: {str(e)}')
            raise e
        finally:
            if conn:
                self.pg_conn_pool.putconn(conn)

    # ==========================================
    # ROS2 서비스 콜백 함수 정의 (인바운드 라인)
    # ==========================================

    def get_package_route_callback(self, request, response):
        """bg2 로봇이 바코드를 찍어 목적지 날짜를 조회할 때 호출"""
        package_id = request.package_id
        customer_name = request.customer_name
        qr_id = request.qr_id
        self.get_logger().info(f'[GetPackageRoute] 입고 택배 바코드/QR 스캔 - ID: {package_id}, 수령인: {customer_name}, QR ID: {qr_id}')

        route_date = None
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        # 1. QR ID가 주어지면 QR ID로 먼저 조회
                        if qr_id != "":
                            cursor.execute(
                                "SELECT route_zone, package_id, customer_name FROM packages WHERE qr_id = %s;",
                                (qr_id,)
                            )
                            row = cursor.fetchone()
                            if row:
                                route_date = row[0]
                                package_id = row[1]
                                customer_name = row[2]
                                self.get_logger().info(f'[GetPackageRoute] QR ID {qr_id}로 조회 성공 - 패키지 ID: {package_id}')

                        # 2. QR ID로 조회에 실패했거나 제공되지 않은 경우 기존 package_id로 조회
                        if not route_date and package_id:
                            cursor.execute(
                                "SELECT route_zone, customer_name, qr_id FROM packages WHERE package_id = %s;",
                                (package_id,)
                            )
                            row = cursor.fetchone()
                            if row:
                                route_date = row[0]
                                customer_name = row[1]
                                if row[2] is not None:
                                    qr_id = row[2]
                                self.get_logger().info(f'[GetPackageRoute] Package ID {package_id}로 조회 성공 - QR ID: {qr_id}')

                        # 3. 데이터베이스에 없는 새로운 패키지인 경우 자동 등록
                        if not route_date:
                            route_date = datetime.now().strftime('%Y-%m-%d')
                            if not package_id:
                                package_id = f"PKG_QR_{qr_id}" if qr_id else f"PKG_RAND_{int(time.time())}"
                            if not customer_name:
                                customer_name = f"Customer_{qr_id}" if qr_id else "Unknown"

                            if qr_id != "":
                                cursor.execute(
                                    "INSERT INTO packages (package_id, customer_name, route_zone, status, qr_id) "
                                    "VALUES (%s, %s, %s, 'WAITING', %s);"  ,
                                    (package_id, customer_name, route_date, qr_id)
                                )
                            else:
                                cursor.execute(
                                    "INSERT INTO packages (package_id, customer_name, route_zone, status) "
                                    "VALUES (%s, %s, %s, 'WAITING');",
                                    (package_id, customer_name, route_date)
                                )
                            self.get_logger().info(f'[GetPackageRoute] 신규 패키지 등록 완료 - ID: {package_id}, QR: {qr_id}')
                except Exception as e:
                    self.get_logger().error(f'GetPackageRoute DB 조회 중 오류: {str(e)}')

        # DB 미연결 또는 예외 시 Mock 값 대응
        if not route_date:
            route_date = datetime.now().strftime('%Y-%m-%d')

        response.route_destination = route_date
        self.get_logger().info(f'[GetPackageRoute] 목적지 분류 결과 전송 -> {route_date}')
        return response

    def check_warehouse_status_callback(self, request, response):
        """sg2_in_XX 로봇이 적재 전 해당 수령인의 물품이 창고에 있는지 조회"""
        customer_name = request.customer_name
        package_id = request.package_id
        qr_id = request.qr_id
        self.get_logger().info(f'[CheckWarehouseStatus] 적재 검사 - 수령인: {customer_name}, 택배ID: {package_id}, QR ID: {qr_id}')

        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        # 1. QR ID가 들어왔고 다른 정보가 부족하면 DB에서 정보를 채운다
                        if qr_id != "" and (not customer_name or not package_id):
                            cursor.execute(
                                "SELECT customer_name, package_id FROM packages WHERE qr_id = %s;",
                                (qr_id,)
                            )
                            row = cursor.fetchone()
                            if row:
                                customer_name = row[0]
                                package_id = row[1]
                                self.get_logger().info(f'[CheckWarehouseStatus] QR ID {qr_id} 매핑 완료 -> ID: {package_id}, 수령인: {customer_name}')

                        # 2. 만약 package_id만 들어오고 customer_name이 없으면 DB에서 조회
                        if package_id and not customer_name:
                            cursor.execute(
                                "SELECT customer_name, qr_id FROM packages WHERE package_id = %s;",
                                (package_id,)
                            )
                            row = cursor.fetchone()
                            if row:
                                customer_name = row[0]
                                if row[1] is not None:
                                    qr_id = row[1]
                except Exception as e:
                    self.get_logger().error(f'CheckWarehouseStatus 매핑 및 DB 조회 중 오류: {str(e)}')

        is_already_in_warehouse = False
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        # 창고(IN_WAREHOUSE)에 동일한 수령인의 물건이 있는지 확인
                        cursor.execute(
                            "SELECT COUNT(*) FROM packages WHERE customer_name = %s AND status = 'IN_WAREHOUSE';",
                            (customer_name,)
                        )
                        count = cursor.fetchone()[0]
                        if count > 0:
                            is_already_in_warehouse = True
                except Exception as e:
                    self.get_logger().error(f'CheckWarehouseStatus DB 조회 중 오류: {str(e)}')

        response.is_already_in_warehouse = is_already_in_warehouse
        
        if is_already_in_warehouse:
            self.get_logger().info(f'[CheckWarehouseStatus] {customer_name}님의 기존 물품이 창고에 감지되었습니다. 창고 직송을 결정합니다.')
            # [AMR 직송 태스크 추가] 관제탑이 즉시 Redis 큐에 AMR 직송 명령을 적재 (QR ID 포함)
            self.push_amr_task({
                'task_type': 'DIRECT_WAREHOUSE',
                'package_id': package_id,
                'customer_name': customer_name,
                'destination_zone': 'ZONE_A', # 기본 보관 구역 A
                'package_qr_id': qr_id
            })
        else:
            self.get_logger().info(f'[CheckWarehouseStatus] 기존 물품이 창고에 없습니다. 작업대 적재 진행.')

        return response

    def report_inbound_progress_callback(self, request, response):
        """sg2_in_XX 로봇이 작업대 칸 적재 완료 시 진척도를 보고"""
        workstation_id = request.workstation_id
        robot_id = request.robot_id
        filled_slots_count = request.filled_slots_count
        package_id = request.package_id
        workstation_qr_id = request.workstation_qr_id
        package_qr_id = request.package_qr_id

        self.get_logger().info(
            f'[ReportInboundProgress] {robot_id} 보고 - 작업대: {workstation_id} (QR: {workstation_qr_id}), '
            f'적재 수량: {filled_slots_count}/8, 택배 ID: {package_id} (QR: {package_qr_id})'
        )

        # DB에 작업대 및 패키지 정보 업데이트
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        # 1. QR ID가 제공된 경우, ID 조회하여 매핑
                        if workstation_qr_id != "":
                            cursor.execute(
                                "SELECT workstation_id FROM workstations WHERE qr_id = %s;",
                                (workstation_qr_id,)
                            )
                            row = cursor.fetchone()
                            if row:
                                workstation_id = row[0]
                                self.get_logger().info(f'[ReportInboundProgress] workstation_qr_id {workstation_qr_id} ➡️ workstation_id {workstation_id}')

                        if package_qr_id != "":
                            cursor.execute(
                                "SELECT package_id FROM packages WHERE qr_id = %s;",
                                (package_qr_id,)
                            )
                            row = cursor.fetchone()
                            if row:
                                package_id = row[0]
                                self.get_logger().info(f'[ReportInboundProgress] package_qr_id {package_qr_id} ➡️ package_id {package_id}')

                        # 2. 패키지 소유 수령인 조회
                        cursor.execute(
                            "SELECT customer_name FROM packages WHERE package_id = %s;",
                            (package_id,)
                        )
                        row = cursor.fetchone()
                        customer_name = row[0] if row else 'UNKNOWN'

                        # 3. 개별 패키지 위치 정보 매핑 및 상태 갱신
                        cursor.execute(
                            "UPDATE packages SET workstation_id = %s, slot_number = %s, status = 'IN_WORKSTATION' "
                            "WHERE package_id = %s;",
                            (workstation_id, filled_slots_count, package_id)
                        )
                except Exception as e:
                    self.get_logger().error(f'ReportInboundProgress DB 업데이트 중 오류: {str(e)}')

        # [JIT 일시 정지] 8번째 칸 적재 완료 시 대상 로봇 일시 정지 토픽 발행
        if filled_slots_count == 8:
            msg = Bool()
            msg.data = True
            if robot_id in self.sg2_pause_pubs:
                self.sg2_pause_pubs[robot_id].publish(msg)
                self.get_logger().info(f'[Pause Robot] {robot_id} 일시 정지 명령 발행 (8칸 완충)')

        # [180도 회전 최적화] 4번째 칸 적재 완료 시 제자리 180도 회전 수행 및 로봇 대기 유도
        if filled_slots_count == 4:
            with self.trigger_lock:
                if workstation_id not in self.rotation_triggered:
                    self.rotation_triggered.add(workstation_id)
                    self.get_logger().info(f'[Rotation Trigger] {workstation_id}의 4번째 슬롯 적재 감지! 180도 회전 태스크 추가 및 일시 정지 상태 적용.')
                    
                    # 로봇 일시 정지 지시 (회전하는 동안)
                    msg = Bool()
                    msg.data = True
                    if robot_id in self.sg2_pause_pubs:
                        self.sg2_pause_pubs[robot_id].publish(msg)
                        
                    with self.get_db_connection() as conn:
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    cursor.execute(
                                        "UPDATE workstations SET current_location = %s WHERE workstation_id = %s;",
                                        (f"{robot_id}_A_ROTATING", workstation_id)
                                    )
                            except Exception as db_err:
                                self.get_logger().error(f'Rotation 상태 변경 실패: {db_err}')

                    self.push_amr_task({
                        'task_type': 'ROTATE_WORKSTATION',
                        'workstation_id': workstation_id,
                        'from': f"{robot_id}_A_ROTATING",
                        'to': f"{robot_id}_A",
                        'description': f"{robot_id} 앞 작업대 {workstation_id} 180도 제자리 회전 (앞/뒤 슬롯 교체)",
                        'workstation_qr_id': workstation_qr_id
                    })

        response.success = True
        return response

    # ==========================================
    # Redis 작업 큐 핸들링 함수
    # ==========================================

    def get_task_priority(self, task_type):
        """태스크 종류별 우선순위 점수 반환"""
        if task_type in ['DIRECT_WAREHOUSE', 'RETRIEVE_FULL_WORKSTATION', 'ROTATE_WORKSTATION']:
            return 100
        elif task_type == 'DEPLOY_EMPTY_WORKSTATION':
            return 90
        elif task_type in ['DEPLOY_PACKAGING_WORKSTATION', 'FETCH_FOR_PACKAGING']:
            return 80
        elif task_type == 'RETRIEVE_EMPTY_WORKSTATION':
            return 20
        return 30

    def get_idle_amr(self):
        """Redis에서 IDLE 상태인 사용 가능한 AMR을 찾아 반환"""
        if not self.redis_client:
            return 'AMR_01'  # Fallback for mock mode
        try:
            keys = self.redis_client.keys("amr:*")
            for key in keys:
                if key == "queue:amr_tasks":
                    continue
                parts = key.split(":")
                if len(parts) > 1:
                    amr_id = parts[1]
                    val = self.redis_client.hgetall(key)
                    if val:
                        state = val.get("state", "IDLE").upper()
                        available = val.get("available", "true").lower() in ["true", "1", "yes"]
                        if state == "IDLE" and available:
                            return amr_id
        except Exception as e:
            self.get_logger().error(f'Redis에서 Idle AMR 조회 중 에러: {str(e)}')
        return None

    def is_task_queued(self, task_type, workstation_id=None, target=None):
        """Redis 큐에 동일한 유형의 태스크가 이미 대기 중인지 검사"""
        if not self.redis_client:
            return False
        try:
            tasks_raw = self.redis_client.zrevrange('queue:amr_tasks', 0, -1)
            for t_raw in tasks_raw:
                try:
                    task = json.loads(t_raw)
                    if task.get('task_type') == task_type:
                        if workstation_id and task.get('workstation_id') == workstation_id:
                            return True
                        if target and task.get('to') == target:
                            return True
                        if not workstation_id and not target:
                            return True
                except Exception:
                    pass
        except Exception as e:
            self.get_logger().error(f'Redis 큐 중복 확인 중 오류: {e}')
        return False

    def push_amr_task(self, task_dict):
        """AMR 작업 명령을 Redis 대기 큐(Sorted Set)에 집어넣음"""
        import uuid
        task_uuid = str(uuid.uuid4())
        task_dict['uuid'] = task_uuid
        task_type = task_dict.get('task_type', 'TASK')
        score = self.get_task_priority(task_type)

        if self.redis_client:
            try:
                self.redis_client.zadd('queue:amr_tasks', {json.dumps(task_dict): score})
                self.get_logger().info(f'[Redis Queue] AMR 태스크 추가(Score: {score}) -> {task_type}')
            except Exception as e:
                # 타입 에러 대응: 기존에 queue:amr_tasks가 List 타입일 경우 삭제 후 재시도
                if "WRONGTYPE" in str(e):
                    self.redis_client.delete('queue:amr_tasks')
                    self.redis_client.zadd('queue:amr_tasks', {json.dumps(task_dict): score})
                    self.get_logger().info(f'[Redis Queue] 기존 리스트 삭제 후 AMR 태스크 추가(Score: {score}) -> {task_type}')
                else:
                    self.get_logger().error(f'Redis Push 실패: {str(e)}')
        else:
            self.get_logger().warn(f'[Mock Queue] AMR 태스크 추가 (DB 미연결) -> {task_dict}')

        # task_events 토픽 발행 (QUEUED)
        self.publish_task_event(
            task_id=task_uuid,
            task_type=task_type,
            priority=score,
            workstation_id=task_dict.get('workstation_id', ''),
            workstation_qr_id=task_dict.get('workstation_qr_id', ''),
            start_location=task_dict.get('from', ''),
            target_location=task_dict.get('to', ''),
            status='QUEUED'
        )

    def publish_task_event(self, task_id, task_type, priority, workstation_id, workstation_qr_id, start_location, target_location, status, assigned_amr=None):
        """Task 상태 변경 이벤트를 JSON 형식으로 /fleet/task_events 토픽에 발행"""
        event = {
            "schema_version": "1.0",
            "timestamp": time.time(),
            "task_id": task_id,
            "type": task_type,
            "priority": priority,
            "workstation_id": workstation_id,
            "workstation_qr_id": workstation_qr_id,
            "start_location": start_location,
            "target_location": target_location,
            "status": status,
            "assigned_amr": assigned_amr
        }
        msg = String()
        msg.data = json.dumps(event)
        self.task_events_pub.publish(msg)
        self.get_logger().info(f"[Task Event Published] Task {task_id} -> {status}")


    # ==========================================
    # 주기적 스케줄링 및 액션 제어 루프
    # ==========================================

    def task_scheduler_loop(self):
        """주기적으로 시스템 상태 및 Redis 큐를 체크하여 AMR/로봇 액션 구동"""
        if not self.redis_client:
            return

        try:
            # Day Transition 상태 확인
            day_status = 'WAITING_FOR_START' # 기본값 변경
            if self.redis_client:
                try:
                    val = self.redis_client.get('system:day_status')
                    if val:
                        day_status = val if isinstance(val, str) else val.decode('utf-8')
                except Exception as e:
                    self.get_logger().error(f'Redis day_status 조회 실패: {str(e)}')

            if day_status != 'RUNNING':
                # 영업 중이 아니면 (WAITING_FOR_START 또는 PENDING_TRANSITION) 아무 작업도 수행하지 않음
                return

            # 1. Redis 큐에서 최고 우선순위 AMR 태스크가 있는지 조회 (zpopmax)
            try:
                task_data = self.redis_client.zpopmax('queue:amr_tasks')
                if task_data:
                    member, score = task_data[0]
                    task = json.loads(member)
                    self.get_logger().info(f'[Scheduler] Redis 큐에서 최고 우선순위 태스크 감지 (Score: {score}) -> {task["task_type"]}')
                    self.execute_amr_task(task)
            except Exception as q_err:
                if "WRONGTYPE" in str(q_err):
                    self.redis_client.delete('queue:amr_tasks')
                else:
                    self.get_logger().error(f'Redis Pop 실패: {str(q_err)}')

            # 2. 작업대 8칸이 모두 찼을 때의 이송 스케줄링 체크
            self.check_completed_workstations()

            # 3. Keep-Alive 작업대 분배기 구동 (A/B구역 상시 관리)
            self.dispatch_workstations_keepalive()

        except Exception as e:
            self.get_logger().error(f'스케줄러 루프 실행 중 에러 발생: {str(e)}')

    def execute_amr_task(self, task):
        """큐에서 꺼낸 태스크 종류에 맞춰 ROS2 액션 명령 하달"""
        task_type = task.get('task_type')
        task_id = task.get('uuid')

        assigned_amr = task.get('assigned_amr', 'AMR_01') 

        if task_type == 'DIRECT_WAREHOUSE':
            # 단일 패키지 창고 직송 액션 전송
            goal_msg = MovePackage.Goal()
            goal_msg.package_id = task.get('package_id', '')
            goal_msg.customer_name = task.get('customer_name', '')
            goal_msg.destination_zone = task.get('destination_zone', '')
            goal_msg.package_qr_id = task.get('package_qr_id', '')

            self.get_logger().info(f'{assigned_amr}에게 단일 택배({goal_msg.package_id}, QR: {goal_msg.package_qr_id}) 창고 직송 액션 전송 중...')
            if not self.move_package_action_client.wait_for_server(timeout_sec=5.0):
                self.get_logger().error('AMR Action Server (move_package) is NOT available! Skipping DIRECT_WAREHOUSE.')
                self.publish_task_event(
                    task_id=task_id,
                    task_type="DIRECT_WAREHOUSE",
                    priority=100,
                    workstation_id="",
                    workstation_qr_id="",
                    start_location="bg2",
                    target_location=goal_msg.destination_zone,
                    status='FAILED',
                    assigned_amr=assigned_amr
                )
                return
            # task_events 토픽 발행 (ASSIGNED)
            self.publish_task_event(
                task_id=task_id,
                task_type="DIRECT_WAREHOUSE",
                priority=100,
                workstation_id="",
                workstation_qr_id="",
                start_location="bg2",
                target_location=goal_msg.destination_zone,
                status='ASSIGNED',
                assigned_amr=assigned_amr
            )
            self.move_package_action_client.send_goal_async(goal_msg)

    def check_completed_workstations(self):
        """8개 칸이 모두 채워진 완성된 작업대를 파악해 이동 명령(AMR) 스케줄링"""
        if not self.pg_conn_pool:
            return

        try:
            with self.get_db_connection() as conn:
                if conn:
                    with conn.cursor() as cursor:
                        # 8칸 모두 FULL인 작업대 조회 (qr_id 추가 선택)
                        cursor.execute(
                            "SELECT w.workstation_id, w.current_location, w.qr_id "
                            "FROM workstations w "
                            "JOIN packages p ON w.workstation_id = p.workstation_id AND p.status = 'IN_WORKSTATION' "
                            "GROUP BY w.workstation_id, w.current_location, w.qr_id "
                            "HAVING COUNT(p.package_id) = 8;"
                        )
                        rows = list(cursor.fetchall())
                        
                        # 오늘 날짜 구하기 및 마지막 남은 작업대(8칸 미만) 체크
                        today_date = self.redis_client.get('system:today_date') if self.redis_client else datetime.now().strftime('%Y-%m-%d')
                        if not today_date:
                            today_date = datetime.now().strftime('%Y-%m-%d')
                        cursor.execute("SELECT COUNT(*) FROM packages WHERE route_zone = %s AND status = 'WAITING';", (today_date,))
                        waiting_today_count = cursor.fetchone()[0]
                        
                        inbound_started = self.redis_client.get('system:inbound_started') == 'true' if self.redis_client else False
                        
                        if waiting_today_count == 0 and inbound_started:
                            cursor.execute("""
                                SELECT w.workstation_id, w.current_location, w.qr_id
                                FROM workstations w
                                JOIN packages p ON w.workstation_id = p.workstation_id AND p.status = 'IN_WORKSTATION'
                                WHERE w.current_location = 'sg2_in_01_A' AND p.route_zone = %s
                                GROUP BY w.workstation_id, w.current_location, w.qr_id
                                HAVING COUNT(p.package_id) > 0 AND COUNT(p.package_id) < 8;
                            """, (today_date,))
                            extra_rows = cursor.fetchall()
                            for er in extra_rows:
                                if er not in rows:
                                    rows.append(er)
                                    self.get_logger().info(f'[Scheduler] 오늘({today_date})의 대기 패키지가 없으므로, sg2_in_01_A의 마지막 작업대 {er[0]} 이송을 결정합니다.')

                        for row in rows:
                            ws_id, curr_loc, ws_qr_id = row[0], row[1], row[2]
                            if ws_qr_id is None:
                                ws_qr_id = ""
                            
                            # 오늘 날짜 분류 라인(sg2_in_01_A)에서 완성되었을 경우 -> 포장 라인(sg2_out_00_A) 또는 출고 대기 구역(staging)으로
                            if curr_loc == 'sg2_in_01_A':
                                cursor.execute(
                                    "SELECT COUNT(*) FROM workstations "
                                    "WHERE current_location = 'sg2_out_00_A' OR current_location = 'MOVING_TO_SG2_OUT_00_A';"
                                )
                                out_a_count = cursor.fetchone()[0]
                                
                                if out_a_count == 0:
                                    target_out = 'sg2_out_00_A'
                                else:
                                    target_out = 'staging'

                                if not self.is_task_queued('RETRIEVE_FULL_WORKSTATION', workstation_id=ws_id):
                                    self.get_logger().info(f'[Scheduler] {ws_id}(QR: {ws_qr_id}) 오늘 물량 적재 완료! 대상지({target_out}) 회수 태스크 큐 추가.')
                                    self.push_amr_task({
                                        'workstation_id': ws_id,
                                        'task_type': 'RETRIEVE_FULL_WORKSTATION',
                                        'from': curr_loc,
                                        'to': target_out,
                                        'description': f'완충 작업대 {ws_id} 회수 ➡️ {target_out}',
                                        'workstation_qr_id': ws_qr_id
                                    })
                            
                            # 내일 분류 라인(sg2_in_02_A) -> 출고 대기 구역(staging)으로
                            elif curr_loc == 'sg2_in_02_A':
                                if not self.is_task_queued('RETRIEVE_FULL_WORKSTATION', workstation_id=ws_id):
                                    self.get_logger().info(f'[Scheduler] {ws_id}(QR: {ws_qr_id}) 내일 물량 적재 완료! 출고 대기 구역(staging) 회수 태스크 큐 추가.')
                                    self.push_amr_task({
                                        'workstation_id': ws_id,
                                        'task_type': 'RETRIEVE_FULL_WORKSTATION',
                                        'from': curr_loc,
                                        'to': 'staging',
                                        'description': f'내일 완충 작업대 {ws_id} 회수 ➡️ staging',
                                        'workstation_qr_id': ws_qr_id
                                    })

                            # 모레 분류 라인(sg2_in_03_A) -> 보관 창고(warehouse)로
                            elif curr_loc == 'sg2_in_03_A':
                                if not self.is_task_queued('RETRIEVE_FULL_WORKSTATION', workstation_id=ws_id):
                                    self.get_logger().info(f'[Scheduler] {ws_id}(QR: {ws_qr_id}) 모레 물량 적재 완료! 보관 창고(warehouse) 회수 태스크 큐 추가.')
                                    self.push_amr_task({
                                        'workstation_id': ws_id,
                                        'task_type': 'RETRIEVE_FULL_WORKSTATION',
                                        'from': curr_loc,
                                        'to': 'warehouse',
                                        'description': f'모레 완충 작업대 {ws_id} 회수 ➡️ warehouse',
                                        'workstation_qr_id': ws_qr_id
                                    })

        except Exception as e:
            self.get_logger().error(f'작업대 완충 체크 중 에러: {str(e)}')

    def dispatch_workstations_keepalive(self):
        """인바운드 라인별 작업대 개수 및 아웃바운드 포장존 상태를 감시하여 동적 공급 조율 (단일 슬롯 A 전용)"""
        if not self.pg_conn_pool:
            return

        inbound_lines = ['sg2_in_01', 'sg2_in_02', 'sg2_in_03']

        try:
            with self.get_db_connection() as conn:
                if conn:
                    with conn.cursor() as cursor:
                        # 현재 모든 작업대의 위치 및 QR 정보 조회
                        cursor.execute("SELECT workstation_id, current_location, qr_id FROM workstations;")
                        workstations = cursor.fetchall()
                        
                        # 라인별 작업대 매핑 (A구역, 이동 중인 작업대만 추적)
                        line_status = {line: {'A': [], 'MOVING_A': []} for line in inbound_lines}
                        # 포장존 상태 매핑 (A구역만)
                        sg2_out_status = {'A': [], 'MOVING_A': []}
                        
                        for ws_id, loc, qr_id in workstations:
                            ws_qr = qr_id if qr_id is not None else ""
                            # 1. 인바운드 라인 상태 분석
                            for line in inbound_lines:
                                if loc == f"{line}_A" or loc == f"{line}_A_ROTATING":
                                    line_status[line]['A'].append((ws_id, ws_qr))
                                elif loc == f"MOVING_TO_{line.upper()}_A":
                                    line_status[line]['MOVING_A'].append((ws_id, ws_qr))
                            
                            # 2. 아웃바운드 포장존 상태 분석
                            if loc == 'sg2_out_00_A' or loc == 'sg2_out_00_A_ROTATING':
                                sg2_out_status['A'].append((ws_id, ws_qr))
                            elif loc == 'MOVING_TO_SG2_OUT_00_A':
                                sg2_out_status['MOVING_A'].append((ws_id, ws_qr))

                        # 인바운드 동적 배치 (단일 슬롯 A 구역 전용)
                        for line in inbound_lines:
                            # A구역에 작업대가 없고, A구역으로 이동 중인 작업대도 없는 경우
                            if not line_status[line]['A'] and not line_status[line]['MOVING_A']:
                                if not self.is_task_queued('DEPLOY_EMPTY_WORKSTATION', target=f"{line}_A"):
                                    self.get_logger().info(f'[Keep-Alive] {line}의 A구역이 비어 있습니다. 빈 작업대 공급 태스크 추가를 검사합니다.')
                                    cursor.execute(
                                        "SELECT workstation_id, current_location, qr_id FROM workstations "
                                        "WHERE current_location LIKE 'spot_%%' "
                                        "AND workstation_id NOT IN ("
                                        "    SELECT DISTINCT workstation_id FROM packages "
                                        "    WHERE workstation_id IS NOT NULL AND status IN ('IN_WORKSTATION', 'IN_WAREHOUSE')"
                                        ") LIMIT 1;"
                                    )
                                    row = cursor.fetchone()
                                    if row:
                                        ws_id, start_loc, ws_qr = row[0], row[1], row[2] if row[2] is not None else ""
                                        self.get_logger().info(f'[Keep-Alive] {ws_id}(출발지: {start_loc}) ➡️ {line}_A 빈 작업대 공급 태스크를 큐에 추가합니다.')
                                        self.push_amr_task({
                                            'workstation_id': ws_id,
                                            'task_type': 'DEPLOY_EMPTY_WORKSTATION',
                                            'from': start_loc,
                                            'to': f"{line}_A",
                                            'description': f'빈 작업대 {ws_id} 공급 ➡️ {line}_A',
                                            'workstation_qr_id': ws_qr
                                        })
                                    else:
                                        self.get_logger().warn(f"[Keep-Alive] {line}에 공급할 창고 내 빈 작업대가 부족합니다.")

                        # 아웃바운드 포장존 동적 배치 (단일 슬롯 A 구역 전용 — B구역 없음)
                        if not sg2_out_status['A'] and not sg2_out_status['MOVING_A']:
                            today_date = self.redis_client.get('system:today_date') if self.redis_client else datetime.now().strftime('%Y-%m-%d')
                            if not today_date:
                                today_date = datetime.now().strftime('%Y-%m-%d')

                            cursor.execute("SELECT COUNT(*) FROM packages WHERE route_zone = %s AND status = 'WAITING';", (today_date,))
                            waiting_today = cursor.fetchone()[0]
                            cursor.execute(
                                "SELECT COUNT(*) FROM packages WHERE route_zone = %s AND status = 'IN_WORKSTATION' "
                                "AND workstation_id IN (SELECT workstation_id FROM workstations WHERE current_location = 'sg2_in_01_A');",
                                (today_date,)
                            )
                            inbound_today_packages = cursor.fetchone()[0]
                            
                            having_cond = "HAVING COUNT(p.package_id) = 8"
                            inbound_started = self.redis_client.get('system:inbound_started') == 'true' if self.redis_client else False
                            if waiting_today == 0 and inbound_today_packages == 0 and inbound_started:
                                having_cond = "HAVING COUNT(p.package_id) > 0"

                            cursor.execute(
                                f"SELECT w.workstation_id, w.current_location, w.qr_id "
                                f"FROM workstations w "
                                f"JOIN packages p ON w.workstation_id = p.workstation_id AND p.status = 'IN_WAREHOUSE' "
                                f"WHERE (w.current_location LIKE 'spot_%%' OR w.current_location LIKE 'stage_%%') AND p.route_zone = %s "
                                f"GROUP BY w.workstation_id, w.current_location, w.qr_id "
                                f"{having_cond} "
                                f"ORDER BY CASE WHEN w.current_location LIKE 'stage_%%' THEN 0 ELSE 1 END ASC, w.current_location ASC "
                                f"LIMIT 1;",
                                (today_date,)
                            )
                            row = cursor.fetchone()
                            if row:
                                ws_id, start_loc, ws_qr = row[0], row[1], row[2] if row[2] is not None else ""
                                if not self.is_task_queued('FETCH_FOR_PACKAGING', target='sg2_out_00_A'):
                                    self.get_logger().info(f'[Keep-Alive] 포장존 A가 비어 있어 창고에서 완충 작업대 {ws_id}를 A구역으로 공급하는 태스크 추가.')
                                    # 패키지 상태 복원
                                    cursor.execute(
                                        "UPDATE packages SET status = 'IN_WORKSTATION' WHERE workstation_id = %s AND status = 'IN_WAREHOUSE';",
                                        (ws_id,)
                                    )
                                    self.push_amr_task({
                                        'workstation_id': ws_id,
                                        'task_type': 'FETCH_FOR_PACKAGING',
                                        'from': start_loc,
                                        'to': 'sg2_out_00_A',
                                        'description': f'완충 작업대 {ws_id} 포장존 공급 ➡️ sg2_out_00_A',
                                        'workstation_qr_id': ws_qr
                                    })
        except Exception as e:
            self.get_logger().error(f'Keep-Alive Dispatcher 실행 중 에러: {str(e)}')

    def trigger_workstation_move(self, workstation_id, start, target, workstation_qr_id="", task_id=None, assigned_amr="AMR_01"):
        """AMR에게 작업대 통째로 이송하도록 액션 골 전송 및 DB 위치 선점 업데이트"""
        import uuid
        if not task_id:
            task_id = f"AUTO_{str(uuid.uuid4())[:8]}"

        actual_target = target
        actual_start = start

        # 0. 만약 출발지가 warehouse/staging 또는 유사 구역명이라면 DB에서 실제 현재 위치를 조회해서 사용
        if start in ['warehouse', 'staging'] or not start.startswith('spot_') and not start.startswith('stage_') and not start.startswith('sg2_'):
            with self.get_db_connection() as conn:
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT current_location FROM workstations WHERE workstation_id = %s;", (workstation_id,))
                            row = cursor.fetchone()
                            if row and row[0] is not None:
                                actual_start = row[0]
                                self.get_logger().info(f'[DB] 작업대 {workstation_id}의 실제 출발지 식별: {actual_start}')
                    except Exception as e:
                        self.get_logger().error(f'출발지 조회 실패: {str(e)}')

        # 1. 만약 목적지가 warehouse 또는 staging 이라면 빈 스팟을 조회해서 실제 target을 spot_XX / stage_XX로 변경
        if target in ['warehouse', 'staging']:
            with self.get_db_connection() as conn:
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            if target == 'warehouse':
                                cursor.execute(
                                    "SELECT spot_id FROM warehouse_locations WHERE spot_id LIKE 'spot_%%' AND status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;"
                                )
                            else: # staging
                                cursor.execute(
                                    "SELECT spot_id FROM warehouse_locations WHERE spot_id LIKE 'stage_%%' AND status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;"
                                )
                            row = cursor.fetchone()
                            if row:
                                actual_target = row[0]
                                # 목적지 스팟을 선점(OCCUPIED) 및 workstation_id 설정
                                cursor.execute(
                                    "UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s "
                                    "WHERE spot_id = %s;",
                                    (workstation_id, actual_target)
                                )
                                self.get_logger().info(f'[DB] 작업대 {workstation_id}의 스팟 배정: {actual_target}')
                            else:
                                self.get_logger().error(f"경고: {target} 구역에 빈 주차 공간이 없습니다! 임시로 '{target}'으로 지정합니다.")
                    except Exception as e:
                        self.get_logger().error(f'{target} 스팟 조회 및 업데이트 중 에러: {str(e)}')

        # 2. 만약 출발지가 창고/대기 스팟(spot_XX / stage_XX)이라면 해당 스팟을 EMPTY로 비워줌
        if actual_start.startswith('spot_') or actual_start.startswith('stage_'):
            with self.get_db_connection() as conn:
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                "UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL "
                                "WHERE spot_id = %s;",
                                (actual_start,)
                            )
                            self.get_logger().info(f'[DB] 스팟 {actual_start} 해제 완료.')
                    except Exception as e:
                        self.get_logger().error(f'출발 스팟 비우기 중 에러: {str(e)}')

        # 이송 작업이 중복으로 트리거되는 걸 방지하기 위해 DB 위치 및 상태 즉시 업데이트
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE workstations SET current_location = %s, status = 'PROCESSING', reserved_by = %s WHERE workstation_id = %s;",
                            (f"MOVING_TO_{actual_target.upper()}", assigned_amr, workstation_id)
                        )
                except Exception as e:
                    self.get_logger().error(f'작업대 이동 상태 DB 업데이트 실패: {str(e)}')
                    return

        # 3. floor_qr_map 테이블을 조회하여 물리 좌표 및 바닥 QR ID 동적 획득
        target_qr_id = ""
        target_x = 0.0
        target_y = 0.0
        target_yaw = 0.0

        start_coords_str = "Unknown"
        target_coords_str = "Unknown"
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        # 출발지 물리 정보 조회
                        cursor.execute(
                            "SELECT qr_id, x_coord, y_coord FROM floor_qr_map WHERE location_name = %s;",
                            (actual_start,)
                        )
                        row = cursor.fetchone()
                        if row:
                            start_coords_str = f"{row[0]} ({row[1]}, {row[2]})"
                        
                        # 목적지 물리 정보 조회
                        cursor.execute(
                            "SELECT qr_id, x_coord, y_coord FROM floor_qr_map WHERE location_name = %s;",
                            (actual_target,)
                        )
                        row = cursor.fetchone()
                        if row:
                            target_qr_id = row[0]
                            target_x = row[1]
                            target_y = row[2]
                            target_coords_str = f"{target_qr_id} ({target_x}, {target_y})"
                except Exception as db_err:
                    self.get_logger().error(f'[DB] 위치 물리 좌표 조회 중 오류: {db_err}')

        # AMR 액션 호출
        goal_msg = ManageWorkstation.Goal()
        goal_msg.workstation_id = workstation_id
        goal_msg.start_location = actual_start
        goal_msg.target_location = actual_target
        goal_msg.workstation_qr_id = workstation_qr_id
        goal_msg.target_qr_id = target_qr_id
        goal_msg.target_x = target_x
        goal_msg.target_y = target_y
        goal_msg.target_yaw = target_yaw

        self.get_logger().info(
            f'{assigned_amr}에게 작업대 {workstation_id}(QR: {workstation_qr_id}) 이송 액션 전송:\n'
            f'  - 출발지: {actual_start} [{start_coords_str}]\n'
            f'  - 목적지: {actual_target} [{target_coords_str}]'
        )
        if not self.manage_workstation_action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error(f'AMR Action Server (manage_workstation) is NOT available! Skipping move for {workstation_id}.')
            self.publish_task_event(
                task_id=task_id,
                task_type="MOVE_WORKSTATION",
                priority=80,
                workstation_id=workstation_id,
                workstation_qr_id=workstation_qr_id,
                start_location=actual_start,
                target_location=actual_target,
                status='FAILED',
                assigned_amr=assigned_amr
            )
            # Reset workstation status in PG
            self.recover_workstation_move_db_state(workstation_id, actual_start, actual_target)
            return
        
        # task_events 토픽 발행 (ASSIGNED)
        self.publish_task_event(
            task_id=task_id,
            task_type="MOVE_WORKSTATION",
            priority=80,
            workstation_id=workstation_id,
            workstation_qr_id=workstation_qr_id,
            start_location=actual_start,
            target_location=actual_target,
            status='ASSIGNED',
            assigned_amr=assigned_amr
        )

        # 액션 완료 시 결과를 받아 실제 DB 최종 위치를 수정하도록 콜백 설정
        send_goal_future = self.manage_workstation_action_client.send_goal_async(goal_msg)
        send_goal_future.add_done_callback(
            lambda future: self.workstation_move_response_callback(future, workstation_id, actual_start, actual_target, task_id, assigned_amr)
        )

    def recover_workstation_move_db_state(self, workstation_id, start, target):
        """이송 실패 또는 거절 시 데이터베이스 상태 복구 (롤백)"""
        if not self.pg_conn_pool:
            return
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        # 1. 작업대 위치 및 상태 원상 복구
                        cursor.execute(
                            "UPDATE workstations SET current_location = %s, status = 'WAITING', reserved_by = NULL WHERE workstation_id = %s;",
                            (start, workstation_id)
                        )
                        self.get_logger().info(f'[DB 복구] 작업대 {workstation_id} 상태 롤백 -> 위치: {start}, 상태: WAITING')
                        
                        # 2. 출발지가 창고 스팟이었던 경우 다시 점유 상태로 복구
                        if start.startswith('spot_') or start.startswith('stage_'):
                            cursor.execute(
                                "UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;",
                                (workstation_id, start)
                            )
                            self.get_logger().info(f'[DB 복구] 출발지 스팟 {start} 재점유 설정 완료.')
                        
                        # 3. 목적지가 창고 스팟이었던 경우 선점했던 공간 해제
                        if target.startswith('spot_') or target.startswith('stage_'):
                            cursor.execute(
                                "UPDATE warehouse_locations SET status = 'EMPTY', workstation_id = NULL WHERE spot_id = %s;",
                                (target,)
                            )
                            self.get_logger().info(f'[DB 복구] 목적지 스팟 {target} 선점 해제 완료.')
                except Exception as e:
                    self.get_logger().error(f'[DB 복구] 복구 쿼리 실행 중 에러 발생: {str(e)}')

    def workstation_move_response_callback(self, future, workstation_id, start, target, task_id, assigned_amr):
        """AMR의 작업대 이송 액션 결과 확인 콜백"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn(f'작업대 {workstation_id} 이송 요청이 AMR에 의해 거절당했습니다.')
            # task_events 토픽 발행 (FAILED)
            self.publish_task_event(
                task_id=task_id,
                task_type="MOVE_WORKSTATION",
                priority=80,
                workstation_id=workstation_id,
                workstation_qr_id="",
                start_location=start,
                target_location=target,
                status='FAILED',
                assigned_amr=assigned_amr
            )
            self.recover_workstation_move_db_state(workstation_id, start, target)
            return

        self.get_logger().info(f'작업대 {workstation_id} 이송 목표 수락됨. 이동 진행 중...')
        get_result_future = goal_handle.get_result_async()
        get_result_future.add_done_callback(
            lambda res_future: self.workstation_move_completed_callback(res_future, workstation_id, start, target, task_id, assigned_amr)
        )

    def workstation_move_completed_callback(self, future, workstation_id, start, target, task_id, assigned_amr):
        """AMR이 이송을 완료했을 때 최종적으로 DB 갱신 및 완료 이벤트 전송"""
        result = future.result().result
        if result.success:
            self.get_logger().info(f'=== [성공] 작업대 {workstation_id} 최종 도착 완료: -> {target} ===')
            with self.get_db_connection() as conn:
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            new_status = 'PROCESSING' if target == 'sg2_out_00_A' else 'WAITING'
                            cursor.execute(
                                "UPDATE workstations SET current_location = %s, status = %s, reserved_by = NULL WHERE workstation_id = %s;",
                                (target, new_status, workstation_id)
                            )
                            # 만약 창고 스팟(spot_XX) 또는 출고 대기 구역(stage_XX)에 도착했다면 패키지 상태를 IN_WAREHOUSE로 변경
                            if target.startswith('spot_') or target.startswith('stage_'):
                                cursor.execute(
                                    "UPDATE packages SET status = 'IN_WAREHOUSE' WHERE workstation_id = %s AND status = 'IN_WORKSTATION';",
                                    (workstation_id,)
                                )
                                self.get_logger().info(f'[DB] 작업대 {workstation_id} 내 패키지들 상태를 IN_WAREHOUSE로 업데이트 완료.')
                    except Exception as e:
                        self.get_logger().error(f'도착지 DB 최종 반영 실패: {str(e)}')

            # JIT 스와핑 대응: 인바운드/아웃바운드 A구역에 작업대가 도달했을 경우, 해당 로봇에게 Resume 신호(False) 전송
            if target and target.endswith('_A'):
                line = target.replace('_A', '')
                # sg2_out_00_A 의 경우 line 은 sg2_out_00 이 됨
                msg = Bool()
                msg.data = False
                if line in self.sg2_pause_pubs:
                    self.sg2_pause_pubs[line].publish(msg)
                    self.get_logger().info(f'[Resume Robot] {line} 로봇 작업 재개 명령 발행 (작업대 배치/회전 완료)')

            # task_events 토픽 발행 (COMPLETED)
            self.publish_task_event(
                task_id=task_id,
                task_type="MOVE_WORKSTATION",
                priority=80,
                workstation_id=workstation_id,
                workstation_qr_id="",
                start_location=start,
                target_location=target,
                status='COMPLETED',
                assigned_amr=assigned_amr
            )

            # 만약 포장 구역 A(sg2_out_00_A)에 안전하게 도착했고, 180도 회전 동작이 아니었다면 포장 공정(Action) 트리거
            if target == 'sg2_out_00_A' and not (start == 'sg2_out_00_A_ROTATING' or 'ROTATING' in start):
                self.trigger_packaging_process(workstation_id)
        else:
            self.get_logger().error(f'[실패] 작업대 {workstation_id} 이송 중 에러 발생')
            self.recover_workstation_move_db_state(workstation_id, start, target)

            # task_events 토픽 발행 (FAILED)
            self.publish_task_event(
                task_id=task_id,
                task_type="MOVE_WORKSTATION",
                priority=80,
                workstation_id=workstation_id,
                workstation_qr_id="",
                start_location=start,
                target_location=target,
                status='FAILED',
                assigned_amr=assigned_amr
            )

        # AMR 상태 Redis 업데이트 (IDLE)
        if self.redis_client:
            try:
                self.redis_client.hset(f"amr:{assigned_amr}", "state", "IDLE")
            except Exception as e:
                self.get_logger().error(f'AMR 상태 Redis IDLE 업데이트 실패: {str(e)}')


    # ==========================================
    # 포장 공정 액션 (sg2_out_00) 핸들링
    # ==========================================

    def trigger_packaging_process(self, workstation_id):
        """포장 로봇 sg2_out_00에게 포장 개시 명령 송신"""
        workstation_qr_id = ""
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT qr_id FROM workstations WHERE workstation_id = %s;",
                            (workstation_id,)
                        )
                        row = cursor.fetchone()
                        if row and row[0] is not None:
                            workstation_qr_id = row[0]
                except Exception as e:
                    self.get_logger().error(f'포장 전 작업대 QR 조회 실패: {str(e)}')

        goal_msg = StartPackaging.Goal()
        goal_msg.workstation_id = workstation_id
        goal_msg.today_date = datetime.now().strftime('%Y%m%d')
        goal_msg.workstation_qr_id = workstation_qr_id

        self.get_logger().info(f'포장 로봇 sg2_out_00에게 {workstation_id}(QR: {workstation_qr_id}) 포장 시작 명령 전송...')
        if not self.start_packaging_action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('Packaging Action Server (start_packaging) is NOT available! Skipping packaging process.')
            with self.get_db_connection() as conn:
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                "UPDATE workstations SET status = 'WAITING', reserved_by = NULL WHERE workstation_id = %s;",
                                (workstation_id,)
                            )
                    except Exception as e:
                        self.get_logger().error(f'복구 실패: {str(e)}')
            return
        
        send_goal_future = self.start_packaging_action_client.send_goal_async(
            goal_msg, 
            feedback_callback=self.packaging_feedback_callback
        )
        send_goal_future.add_done_callback(
            lambda future: self.packaging_response_callback(future, workstation_id)
        )

    def packaging_feedback_callback(self, feedback_msg):
        """포장 로봇의 실시간 피드백 핸들러 (3번째 칸 완료 감지용 및 4번째 칸 회전용)"""
        feedback = feedback_msg.feedback
        completed_slots = feedback.completed_slots
        last_packed_slot = feedback.last_packed_slot

        self.get_logger().info(f'[포장 피드백] 현재 완료 슬롯 수: {completed_slots}/8, 최근 완료: {last_packed_slot}')

        # 현재 포장 중인 작업대 조회
        workstation_id = ""
        workstation_qr_id = ""
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT workstation_id, qr_id FROM workstations "
                            "WHERE current_location IN ('sg2_out_00_A', 'sg2_out_00_A_ROTATING');"
                        )
                        row = cursor.fetchone()
                        if row:
                            workstation_id = row[0]
                            workstation_qr_id = row[1] or ""
                except Exception as e:
                    self.get_logger().error(f'피드백 처리 중 작업대 조회 실패: {str(e)}')

        if not workstation_id:
            return

        # [단일 슬롯 전환] B구역 사전 호출(Look-ahead)은 더 이상 사용하지 않음.
        # A구역이 비는 즉시 Keep-Alive 디스패처가 창고에서 다음 작업대를 자동 공급합니다.


        # [180도 회전 최적화] 4번째 칸 포장 완료 시 제자리 180도 회전 수행 및 로봇 대기 유도
        if completed_slots == 4:
            with self.trigger_lock:
                if workstation_id not in self.rotation_triggered:
                    self.rotation_triggered.add(workstation_id)
                    self.get_logger().info(f'[Rotation Trigger] 작업대 {workstation_id}의 4번째 슬롯 포장 감지! 180도 회전 태스크 추가 및 일시 정지 상태 적용.')
                    
                    # 포장 로봇 일시 정지 지시 (회전하는 동안)
                    msg = Bool()
                    msg.data = True
                    if 'sg2_out_00' in self.sg2_pause_pubs:
                        self.sg2_pause_pubs['sg2_out_00'].publish(msg)

                    with self.get_db_connection() as conn:
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    cursor.execute(
                                        "UPDATE workstations SET current_location = 'sg2_out_00_A_ROTATING' WHERE workstation_id = %s;",
                                        (workstation_id,)
                                    )
                            except Exception as db_err:
                                self.get_logger().error(f'Rotation 상태 변경 실패: {db_err}')

                    self.push_amr_task({
                        'task_type': 'ROTATE_WORKSTATION',
                        'workstation_id': workstation_id,
                        'from': 'sg2_out_00_A_ROTATING',
                        'to': 'sg2_out_00_A',
                        'description': f"포장존 A구역 작업대 {workstation_id} 180도 제자리 회전 (앞/뒤 슬롯 교체)",
                        'workstation_qr_id': workstation_qr_id
                    })

    def packaging_response_callback(self, future, workstation_id):
        """포장 명령 수락 콜백"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn(f'{workstation_id} 포장 시작 요청이 거절당했습니다.')
            return

        self.get_logger().info(f'{workstation_id} 포장 공정 목표 수락 완료. 결과 대기 중...')
        get_result_future = goal_handle.get_result_async()
        get_result_future.add_done_callback(
            lambda res_future: self.packaging_completed_callback(res_future, workstation_id)
        )

    def packaging_completed_callback(self, future, workstation_id):
        """모든 포장 완료 시 최종 처리 및 빈 작업대 회수"""
        result = future.result().result
        if result.success:
            self.get_logger().info(f'=== [완료] 작업대 {workstation_id} 모든 포장 완료! ===')
            self.get_logger().info(f'생성된 출고 ID 리스트: {result.final_output_ids}')

            # Trigger가 초기화되도록 세트에서 제거
            with self.trigger_lock:
                if workstation_id in self.pre_fetch_triggered:
                    self.pre_fetch_triggered.remove(workstation_id)
                if workstation_id in self.rotation_triggered:
                    self.rotation_triggered.remove(workstation_id)

            updated_count = 0
            with self.get_db_connection() as conn:
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            # 1. 해당 작업대에 매핑되었던 패키지들의 상태를 COMPLETED로 업데이트
                            raw_outbound_id = result.final_output_ids[0] if result.final_output_ids else 'OUT_ERR'
                            robot_prefix = "sg2_out_00_"
                            if raw_outbound_id != 'OUT_ERR' and not raw_outbound_id.startswith(robot_prefix):
                                formatted_outbound_id = f"{robot_prefix}{raw_outbound_id}"
                            else:
                                formatted_outbound_id = raw_outbound_id

                            cursor.execute(
                                "UPDATE packages SET status = 'COMPLETED', outbound_id = %s, workstation_id = NULL, slot_number = NULL "
                                "WHERE workstation_id = %s AND status = 'IN_WORKSTATION';",
                                (formatted_outbound_id, workstation_id)
                            )
                            updated_count = cursor.rowcount

                            # 오늘 날짜를 구함
                            today_date = self.redis_client.get('system:today_date') if self.redis_client else datetime.now().strftime('%Y-%m-%d')
                            if not today_date:
                                today_date = datetime.now().strftime('%Y-%m-%d')

                            if today_date:
                                # Event-Driven Redis counter system 적용
                                if self.redis_client:
                                    try:
                                        completed_count = self.redis_client.incrby('system:today_completed_count', updated_count)
                                        total_str = self.redis_client.get('system:today_total_packages')
                                        if not total_str or int(total_str) == 0:
                                            cursor.execute("SELECT COUNT(*) FROM packages WHERE route_zone = %s;", (today_date,))
                                            total_count = cursor.fetchone()[0]
                                            self.redis_client.set('system:today_total_packages', total_count)
                                        else:
                                            total_count = int(total_str)
                                        
                                        self.get_logger().info(f'[Redis EOD Check] 오늘 남은 물량 검사: {completed_count}/{total_count} (업데이트 건수: {updated_count})')
                                        
                                        if total_count > 0 and completed_count >= total_count:
                                             # 오늘 물량 정리 완료! Day Transition 트리거!
                                             self.get_logger().info(f'=== 🎉 [Day Finished] 오늘({today_date})의 모든 물량 포장 완료! 일자 전환 모드 진입. ===')
                                             self.write_daily_report(today_date, cursor)
                                             self.redis_client.set('system:day_status', 'PENDING_TRANSITION')
                                             self.redis_client.set('system:completed_day', today_date)
                                    except Exception as redis_err:
                                        self.get_logger().error(f'Redis EOD 처리 중 에러: {redis_err}')

                    except Exception as e:
                        self.get_logger().error(f'포장 완료 정보 DB 반영 실패: {str(e)}')

            # 3. 빈 작업대를 다시 인바운드 대기존으로 회수하는 AMR 태스크 발행
            ws_qr_id = ""
            target_spot = 'warehouse'
            with self.get_db_connection() as conn:
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                "SELECT qr_id FROM workstations WHERE workstation_id = %s;",
                                (workstation_id,)
                            )
                            row = cursor.fetchone()
                            if row and row[0] is not None:
                                ws_qr_id = row[0]
                                
                            # DB에서 비어있는 창고 스팟 조회
                            cursor.execute("SELECT spot_id FROM warehouse_locations WHERE status = 'EMPTY' ORDER BY spot_id ASC LIMIT 1;")
                            spot_row = cursor.fetchone()
                            if spot_row:
                                target_spot = spot_row[0]
                                cursor.execute("UPDATE warehouse_locations SET status = 'OCCUPIED', workstation_id = %s WHERE spot_id = %s;", (workstation_id, target_spot))
                    except Exception as e:
                        self.get_logger().error(f'회수용 작업대 QR 및 스팟 조회 실패: {str(e)}')

            # 빈 작업대 회수 태스크 큐에 추가
            self.push_amr_task({
                'workstation_id': workstation_id,
                'task_type': 'RETRIEVE_EMPTY_WORKSTATION',
                'from': 'sg2_out_00_A',
                'to': target_spot,
                'description': f'포장 완료 빈 작업대 {workstation_id} 회수 ➡️ {target_spot}',
                'workstation_qr_id': ws_qr_id
            })

    def write_daily_report(self, date_str, cursor):
        """오늘 일자의 물류 운영 통계 보고서 작성 및 파일 저장"""
        try:
            # 1. 오늘 날짜에 포장 완료된 패키지 리스트 조회
            cursor.execute(
                "SELECT package_id, customer_name, outbound_id FROM packages WHERE route_zone = %s AND status = 'COMPLETED';",
                (date_str,)
            )
            completed_pkgs = cursor.fetchall()
            
            # 2. 현재 작업대들의 위치 상태 조회
            cursor.execute(
                "SELECT workstation_id, current_location, status FROM workstations ORDER BY workstation_id;"
            )
            ws_states = cursor.fetchall()
            
            # 3. 마크다운 내용 구성
            report_content = []
            report_content.append(f"# 📋 물류창고 일자 운영 보고서 (Daily Operations Report)")
            report_content.append(f"- **운영 일자**: `{date_str}`")
            report_content.append(f"- **보고서 생성 시각**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
            report_content.append("\n## 📊 완료된 패키지 현황")
            report_content.append(f"- **총 포장 완료 건수**: `{len(completed_pkgs)}` 건")
            report_content.append("\n| 패키지 ID | 수령인 | 출고 ID |")
            report_content.append("| :--- | :--- | :--- |")
            for pkg_id, cust, out_id in completed_pkgs:
                report_content.append(f"| {pkg_id} | {cust} | {out_id} |")
                
            report_content.append("\n## 🚛 현재 작업대 위치 현황 (Carry-over 상태)")
            report_content.append("| 작업대 ID | 현재 위치 | 상태 |")
            report_content.append("| :--- | :--- | :--- |")
            for ws_id, loc, stat in ws_states:
                report_content.append(f"| {ws_id} | {loc} | {stat} |")
                
            report_content.append("\n---\n*본 보고서는 관제 센터 노드(control_tower)에 의해 자동 생성되었습니다. 다음 영업일 운영을 개시하려면 대시보드에서 [Next Day Transition] 단추를 누르십시오.*")
            
            # 4. 파일 쓰기
            home_dir = os.path.expanduser('~')
            workspace_dir = os.path.join(home_dir, 'cobot3_ws')
            if not os.path.exists(workspace_dir):
                workspace_dir = os.getcwd()
            filename = os.path.join(workspace_dir, f"daily_report_{date_str}.md")
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("\n".join(report_content))
                
            self.get_logger().info(f'[Report] 일자 운영 보고서 저장 완료: {filename}')
            
        except Exception as e:
            self.get_logger().error(f'보고서 파일 작성 중 오류: {str(e)}')

    def publish_fleet_states_callback(self):
        """1초 주기로 플릿 상태(AMR, 작업대, 패키지)를 직렬화하여 각 토픽에 발행"""
        # 1. AMR States
        amr_states = {}
        if self.redis_client:
            try:
                keys = self.redis_client.keys("amr:*")
                for key in keys:
                    # Skip queue key
                    if key == "queue:amr_tasks":
                        continue
                    parts = key.split(":")
                    if len(parts) > 1:
                        amr_id = parts[1]
                        # Try hash first
                        val = self.redis_client.hgetall(key)
                        if val:
                            try:
                                battery_val = val.get("battery", "100.0")
                                battery_float = float(battery_val) if battery_val.strip() else 100.0
                            except (ValueError, TypeError):
                                battery_float = 100.0

                            amr_states[amr_id] = {
                                "state": val.get("state", "IDLE"),
                                "current_qr_id": val.get("current_qr_id", ""),
                                "target_qr_id": val.get("target_qr_id", ""),
                                "carrying_workstation_id": val.get("carrying_workstation_id", None) or None,
                                "battery": battery_float,
                                "available": val.get("available", "true").lower() in ["true", "1", "yes"]
                            }
                        else:
                            val_str = self.redis_client.get(key)
                            if val_str:
                                try:
                                    amr_states[amr_id] = json.loads(val_str)
                                except json.JSONDecodeError:
                                    pass
            except Exception as e:
                self.get_logger().error(f'Redis에서 AMR 상태 로드 중 에러: {str(e)}')

        if not amr_states:
            # Fallback mock for demo/dashboard
            amr_states = {
                "AMR_01": {
                    "state": "IDLE",
                    "current_qr_id": "QR_0030",
                    "target_qr_id": "",
                    "carrying_workstation_id": None,
                    "battery": 82.5,
                    "available": True
                }
            }

        amr_msg = String()
        amr_msg.data = json.dumps(amr_states)
        self.amr_states_pub.publish(amr_msg)

        # 2. Workstation States (JOIN floor_qr_map and packages occupied slots)
        workstations_list = []
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        # w.status, w.reserved_by가 새로 추가됨
                        cursor.execute(
                            "SELECT w.workstation_id, w.qr_id, COALESCE(f.qr_id, w.current_location) as current_location_qr, "
                            "       w.status, w.reserved_by, "
                            "       COALESCE(array_to_json(array_agg(p.slot_number ORDER BY p.slot_number) FILTER (WHERE p.slot_number IS NOT NULL AND p.status = 'IN_WORKSTATION')), '[]'::json) as filled_slots "
                            "FROM workstations w "
                            "LEFT JOIN floor_qr_map f ON w.current_location = f.location_name "
                            "LEFT JOIN packages p ON w.workstation_id = p.workstation_id "
                            "GROUP BY w.workstation_id, w.current_location, f.qr_id, w.qr_id, w.status, w.reserved_by;"
                        )
                        rows = cursor.fetchall()
                        for row in rows:
                            workstations_list.append({
                                "workstation_id": row[0],
                                "workstation_qr_id": row[1] or "",
                                "current_location": row[2],
                                "status": row[3] or "WAITING",
                                "slot_count": 8,
                                "filled_slots": row[5] if isinstance(row[5], list) else json.loads(row[5] or '[]'),
                                "reserved_by": row[4]
                            })
                except Exception as e:
                    self.get_logger().error(f'PostgreSQL에서 작업대 상태 로드 중 에러: {str(e)}')

        ws_msg = String()
        ws_msg.data = json.dumps({"workstations": workstations_list})
        self.workstation_states_pub.publish(ws_msg)

        # 3. Package States (only WAITING, IN_WORKSTATION, IN_WAREHOUSE status)
        packages_list = []
        with self.get_db_connection() as conn:
            if conn:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT package_id, customer_name, route_zone, status, outbound_id, workstation_id, slot_number, qr_id "
                            "FROM packages WHERE status != 'COMPLETED';"
                        )
                        rows = cursor.fetchall()
                        for row in rows:
                            packages_list.append({
                                "package_id": row[0],
                                "customer_name": row[1],
                                "route_zone": row[2],
                                "status": row[3],
                                "outbound_id": row[4],
                                "workstation_id": row[5],
                                "slot_number": row[6],
                                "qr_id": row[7] or ""
                            })
                except Exception as e:
                    self.get_logger().error(f'PostgreSQL에서 패키지 상태 로드 중 에러: {str(e)}')

        pkg_msg = String()
        pkg_msg.data = json.dumps({"packages": packages_list})
        self.package_states_pub.publish(pkg_msg)

        # 오늘 물량 완료 검사는 패키지 포장 완료 시 Event-Driven 방식으로 직접 처리되므로
        # 매초 high-frequency DB 폴링 검사는 진행하지 않습니다.
        pass

    def destroy_node(self):
        """노드 종료 시 백그라운드 타이머를 먼저 정지하고 데이터베이스 풀을 해제하여 자원 경합을 방지"""
        if hasattr(self, 'scheduler_timer') and self.scheduler_timer:
            try:
                self.scheduler_timer.cancel()
            except Exception:
                pass
        if hasattr(self, 'fleet_states_timer') and self.fleet_states_timer:
            try:
                self.fleet_states_timer.cancel()
            except Exception:
                pass

        if hasattr(self, 'pg_conn_pool') and self.pg_conn_pool:
            try:
                self.pg_conn_pool.closeall()
                print('[control_tower_node] PostgreSQL connection pool closed successfully.')
            except Exception as pool_err:
                print(f'[control_tower_node] Error closing PostgreSQL connection pool: {pool_err}')

        super().destroy_node()


def main(args=None):

    rclpy.init(args=args)
    node = ControlTowerNode()
    
    # 멀티스레드 실행기를 사용하여 DB 작업으로 인한 ROS2 틱 끊김 방지
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        print('[control_tower_node] 관제 센터 노드 종료 중 (SIGINT 수신)...')
    finally:
        # 1. 타이머가 백그라운드 스레드에서 새로 구동되는 것을 방지하기 위해 먼저 취소
        if hasattr(node, 'scheduler_timer') and node.scheduler_timer:
            try:
                node.scheduler_timer.cancel()
            except Exception:
                pass
        if hasattr(node, 'fleet_states_timer') and node.fleet_states_timer:
            try:
                node.fleet_states_timer.cancel()
            except Exception:
                pass

        # 2. 실행기를 먼저 종료(shutdown)하여 현재 동작 중인 스레드가 완료(join)되기를 대기
        executor.shutdown()
        
        # 3. 노드를 실행기에서 제거하고 안전하게 파괴 (DB 커넥션 풀 종료 포함)
        executor.remove_node(node)
        node.destroy_node()
        
        # 4. rclpy shutdown
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
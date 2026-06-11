#!/usr/bin/env python3
import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import Bool

from cobot3_interfaces.action import StartPackaging

class MockSg2OutNode(Node):
    def __init__(self):
        super().__init__('mock_sg2_out_node')
        
        self.is_paused = False
        self.callback_group = ReentrantCallbackGroup()
        
        # 1. 일시정지/재개 상태 구독 (관제탑 제어 수신)
        self.pause_sub = self.create_subscription(
            Bool,
            '/sg2_out_00/pause_status',
            self.pause_callback,
            10,
            callback_group=self.callback_group
        )
        
        # 2. 포장 액션 서버 구동
        self._action_server = ActionServer(
            self,
            StartPackaging,
            'start_packaging',
            execute_callback=self.execute_callback,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self.callback_group
        )
        
        self.get_logger().info('=== 🤖 Mock SG2 OUT 포장 로봇 준비 완료 ===')
        self.get_logger().info('인터페이스: /sg2_out_00/pause_status [Sub], start_packaging [Action]')

    def pause_callback(self, msg):
        self.is_paused = msg.data
        if self.is_paused:
            self.get_logger().warn('🚨 [Mock SG2 OUT] 일시 정지(Pause) 상태 적용됨')
        else:
            self.get_logger().info('▶️ [Mock SG2 OUT] 작업 재개(Resume) 상태 적용됨')

    def goal_callback(self, goal_request):
        self.get_logger().info(f'📥 포장 요청 수신: 작업대 {goal_request.workstation_id}')
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        self.get_logger().info('🚫 포장 요청 취소 접수')
        return CancelResponse.ACCEPT

    def execute_callback(self, goal_handle):
        self.get_logger().info('📦 포장 공정을 시작합니다...')
        
        goal = goal_handle.request
        workstation_id = goal.workstation_id
        today_date = goal.today_date
        
        feedback_msg = StartPackaging.Feedback()
        
        slot = 1
        # 1초 단위로 루프를 돌며 슬롯 포장 수행
        while slot <= 8:
            # 1. 일시 정지 감지 시 루프 대기
            if self.is_paused:
                self.get_logger().info('⏸️ [Mock SG2 OUT] 일시정지 중... 회전 완료 대기')
                while self.is_paused:
                    time.sleep(0.1)
                self.get_logger().info('▶️ [Mock SG2 OUT] 일시정지 해제됨. 포장 재개.')

            # 2. 1.2초간 포장 가동 시뮬레이션
            time.sleep(1.2)
            
            # 대기하는 도중에 pause 신호가 들어왔다면 카운트를 반영하지 않고 루프 재검사
            if self.is_paused:
                continue

            # 3. 피드백 발송
            feedback_msg.completed_slots = slot
            feedback_msg.last_packed_slot = f"slot_{slot}"
            goal_handle.publish_feedback(feedback_msg)
            self.get_logger().info(f'✨ [Mock SG2 OUT] {workstation_id} - slot_{slot} 포장 완료 ({slot}/8)')
            
            slot += 1

        goal_handle.succeed()
        
        # 최종 결과 전송
        result = StartPackaging.Result()
        result.success = True
        result.final_output_ids = [f"{workstation_id}_{i}_{today_date}" for i in range(1, 9)]
        self.get_logger().info(f'✅ [Mock SG2 OUT] {workstation_id} 모든 포장 공정 완료 및 결과 전송 완료')
        return result

def main(args=None):
    rclpy.init(args=args)
    node = MockSg2OutNode()
    
    # 멀티스레드 실행기로 액션 서버와 서브스크라이버의 병렬 비차단 스핀 보장
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

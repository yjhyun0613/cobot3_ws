#!/usr/bin/env python3
import json
import os
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.action import ActionServer

from cobot3_interfaces.action import ManageWorkstation
try:
    from cobot3_interfaces.action import MovePackage
except Exception:
    MovePackage = None


BRIDGE_QUEUE_DIR = Path('/home/rokey/isaaclab_ws/isaac_aruco/amr/bridge_queue')
COMMAND_DIR = BRIDGE_QUEUE_DIR / 'commands'
STATUS_DIR = BRIDGE_QUEUE_DIR / 'status'
RESULT_DIR = BRIDGE_QUEUE_DIR / 'results'
CANCEL_DIR = BRIDGE_QUEUE_DIR / 'cancel'
DONE_DIR = BRIDGE_QUEUE_DIR / 'done'

ACTION_NAME = 'manage_workstation'
MOVE_PACKAGE_ACTION_NAME = 'move_package'
FEEDBACK_PERIOD_SEC = 0.25
TASK_TIMEOUT_SEC = 300.0
BRIDGE_EXECUTOR_THREADS = max(1, int(os.environ.get('AMR_BRIDGE_EXECUTOR_THREADS', '2')))


def ensure_dirs():
    for d in [COMMAND_DIR, STATUS_DIR, RESULT_DIR, CANCEL_DIR, DONE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def safe_write_json(path: Path, data: Dict):
    tmp = path.with_suffix(path.suffix + f'.{uuid.uuid4().hex}.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def safe_read_json(path: Path) -> Optional[Dict]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def goal_to_command_dict(command_id: str, goal) -> Dict:
    data = {
        'command_id': command_id,
        'workstation_id': str(getattr(goal, 'workstation_id', '') or ''),
        'start_location': str(getattr(goal, 'start_location', '') or ''),
        'target_location': str(getattr(goal, 'target_location', '') or ''),
        'workstation_qr_id': str(getattr(goal, 'workstation_qr_id', '') or ''),
        'target_qr_id': str(getattr(goal, 'target_qr_id', '') or ''),
        'target_x': float(getattr(goal, 'target_x', 0.0) or 0.0) if hasattr(goal, 'target_x') else None,
        'target_y': float(getattr(goal, 'target_y', 0.0) or 0.0) if hasattr(goal, 'target_y') else None,
        'target_yaw': float(getattr(goal, 'target_yaw', 0.0) or 0.0) if hasattr(goal, 'target_yaw') else 0.0,
        'created_at': time.time(),
    }
    return data


class FleetManagerBridgeNode(Node):
    def __init__(self):
        super().__init__('fleet_manager_bridge_node')
        ensure_dirs()
        self.action_server = ActionServer(
            self,
            ManageWorkstation,
            ACTION_NAME,
            self.execute_manage_workstation_callback,
        )
        self.move_package_action_server = None
        if MovePackage is not None:
            self.move_package_action_server = ActionServer(
                self,
                MovePackage,
                MOVE_PACKAGE_ACTION_NAME,
                self.execute_move_package_callback,
            )
        self.get_logger().info(f'AMR Fleet Bridge V18 ActionServer ready: /{ACTION_NAME}')
        if MovePackage is not None:
            self.get_logger().info(f'AMR Fleet Bridge V18 ActionServer ready: /{MOVE_PACKAGE_ACTION_NAME}')
        else:
            self.get_logger().warn('MovePackage action interface not available. /move_package server not started.')
        self.get_logger().info(f'Bridge queue dir: {BRIDGE_QUEUE_DIR}')
        self.get_logger().info(f'Bridge executor threads: {BRIDGE_EXECUTOR_THREADS}')
        self.get_logger().info('Run Isaac Sim GPU controller inside Isaac Sim Script Editor.')

    def execute_move_package_callback(self, goal_handle):
        """Logical MovePackage action server.

        Current Isaac Sim stage controls AMRs and workstations. Package meshes are not
        modeled as physical carried objects in this stage, so this server acknowledges
        package transport commands and publishes progress/result for Control Tower
        integration compatibility.
        """
        goal = goal_handle.request
        command_id = f'PKG_{uuid.uuid4().hex[:12]}'
        package_id = str(getattr(goal, 'package_id', '') or '')
        customer_name = str(getattr(goal, 'customer_name', '') or '')
        destination_zone = str(getattr(goal, 'destination_zone', '') or '')
        package_qr_id = str(getattr(goal, 'package_qr_id', '') or '')

        self.get_logger().info(
            'MovePackage received | '
            f'command_id={command_id} '
            f'package_id={package_id} '
            f'customer={customer_name} '
            f'destination={destination_zone} '
            f'package_qr_id={package_qr_id}'
        )

        result_msg = MovePackage.Result()

        feedback_steps = [
            ('ACCEPTED', 0.0),
            ('ASSIGNED_TO_AMR_LOGICAL', 35.0),
            ('MOVING_TO_DESTINATION_LOGICAL', 75.0),
            ('COMPLETED', 100.0),
        ]
        for position, progress in feedback_steps:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                if hasattr(result_msg, 'success'):
                    result_msg.success = False
                if hasattr(result_msg, 'error_msg'):
                    result_msg.error_msg = 'MovePackage canceled'
                self.get_logger().warn(f'MovePackage canceled | command_id={command_id}')
                return result_msg

            feedback_msg = MovePackage.Feedback()
            if hasattr(feedback_msg, 'current_position'):
                feedback_msg.current_position = position
            if hasattr(feedback_msg, 'progress'):
                feedback_msg.progress = float(progress)
            goal_handle.publish_feedback(feedback_msg)
            time.sleep(0.2)

        goal_handle.succeed()
        if hasattr(result_msg, 'success'):
            result_msg.success = True
        if hasattr(result_msg, 'error_msg'):
            result_msg.error_msg = ''
        self.get_logger().info(f'MovePackage completed | command_id={command_id}')
        return result_msg

    def execute_manage_workstation_callback(self, goal_handle):
        goal = goal_handle.request
        command_id = f'CMD_{uuid.uuid4().hex[:12]}'
        command_path = COMMAND_DIR / f'{command_id}.json'
        status_path = STATUS_DIR / f'{command_id}.json'
        result_path = RESULT_DIR / f'{command_id}.json'
        cancel_path = CANCEL_DIR / f'{command_id}.json'

        command = goal_to_command_dict(command_id, goal)
        self.get_logger().info(
            'ManageWorkstation received | '
            f"command_id={command_id} "
            f"workstation_id={command['workstation_id']} "
            f"start={command['start_location']} "
            f"target={command['target_location']}"
        )

        # Remove stale files if the same command id somehow exists.
        for p in [status_path, result_path, cancel_path]:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

        safe_write_json(command_path, command)

        result_msg = ManageWorkstation.Result()
        start_time = time.time()

        while rclpy.ok():
            if goal_handle.is_cancel_requested:
                safe_write_json(cancel_path, {
                    'command_id': command_id,
                    'cancel_requested_at': time.time(),
                })
                goal_handle.canceled()
                if hasattr(result_msg, 'success'):
                    result_msg.success = False
                self.get_logger().warn(f'ManageWorkstation canceled | command_id={command_id}')
                return result_msg

            result_data = safe_read_json(result_path)
            if result_data is not None:
                success = bool(result_data.get('success', False))
                status = str(result_data.get('status', 'UNKNOWN'))
                message = str(result_data.get('message', ''))

                if success:
                    goal_handle.succeed()
                    if hasattr(result_msg, 'success'):
                        result_msg.success = True
                    self.get_logger().info(f'ManageWorkstation completed | command_id={command_id} status={status}')
                    return result_msg

                goal_handle.abort()
                if hasattr(result_msg, 'success'):
                    result_msg.success = False
                self.get_logger().error(f'ManageWorkstation failed | command_id={command_id} status={status} message={message}')
                return result_msg

            status_data = safe_read_json(status_path)
            feedback_msg = ManageWorkstation.Feedback()
            if status_data is not None:
                if hasattr(feedback_msg, 'distance_remaining'):
                    feedback_msg.distance_remaining = float(status_data.get('distance_remaining', 0.0) or 0.0)
                if hasattr(feedback_msg, 'status'):
                    feedback_msg.status = str(status_data.get('status', 'RUNNING'))
            else:
                if hasattr(feedback_msg, 'distance_remaining'):
                    feedback_msg.distance_remaining = 0.0
                if hasattr(feedback_msg, 'status'):
                    feedback_msg.status = 'WAITING_FOR_ISAAC_SIM'

            goal_handle.publish_feedback(feedback_msg)

            if time.time() - start_time > TASK_TIMEOUT_SEC:
                safe_write_json(cancel_path, {
                    'command_id': command_id,
                    'cancel_requested_at': time.time(),
                    'reason': 'timeout',
                })
                goal_handle.abort()
                if hasattr(result_msg, 'success'):
                    result_msg.success = False
                self.get_logger().error(f'ManageWorkstation timeout | command_id={command_id}')
                return result_msg

            time.sleep(FEEDBACK_PERIOD_SEC)

        goal_handle.abort()
        if hasattr(result_msg, 'success'):
            result_msg.success = False
        return result_msg


def main(args=None):
    rclpy.init(args=args)
    node = FleetManagerBridgeNode()
    executor = MultiThreadedExecutor(num_threads=BRIDGE_EXECUTOR_THREADS)
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info('AMR Fleet Bridge shutting down...')
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()

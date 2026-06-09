#!/bin/bash

echo "=========================================="
echo "🧹 터미널 찌꺼기 노드 강제 종료 스크립트"
echo "=========================================="

echo "1. ROS 2 데몬 및 네트워크 캐시 초기화 중..."
ros2 daemon stop > /dev/null 2>&1

echo "2. 관제탑(Control Tower) 관련 프로세스 종료 중..."
pkill -9 -f "control_tower"
pkill -9 -f "ros2 run cobot3"

echo "3. 대시보드 웹 서버는 유지합니다 (GUI 맵 보존)."
# pkill -9 -f "dashboard_server.py" (주석 처리: 대시보드가 꺼지지 않도록 보호)

echo "4. AMR 브릿지 노드 종료 중..."
pkill -9 -f "fleet_manager_bridge_node"

echo "5. 기타 잔류 ROS 2 백그라운드 노드 정리 중..."
pkill -9 -f "/opt/ros/humble/bin/ros2"

echo "=========================================="
echo "✅ 모든 노드 정리가 완료되었습니다!"
echo "=========================================="

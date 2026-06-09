#!/usr/bin/env bash
set -e
export ROS_DOMAIN_ID=119
export ROS_LOCALHOST_ONLY=0
source /opt/ros/humble/setup.bash
source "$HOME/cobot3_ws/install/setup.bash"
ros2 action list | grep -E "manage_workstation|move_package" || true

#!/usr/bin/env bash
set -e

deactivate 2>/dev/null || true

export ROS_DOMAIN_ID=119
export ROS_LOCALHOST_ONLY=0

source /opt/ros/humble/setup.bash

if [ -f "$HOME/cobot3_ws/install/setup.bash" ]; then
  source "$HOME/cobot3_ws/install/setup.bash"
else
  echo "[ERROR] ~/cobot3_ws/install/setup.bash not found"
  echo "Build/source cobot3_interfaces first."
  exit 1
fi

if [ -f "/opt/ros/humble/lib/librmw_cyclonedds_cpp.so" ]; then
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
else
  unset RMW_IMPLEMENTATION
  echo "[WARN] rmw_cyclonedds_cpp not installed. Using default RMW."
fi

/usr/bin/python3 /home/rokey/cobot3_ws/src/cobot3/amr/fleet_manager_bridge_node.py

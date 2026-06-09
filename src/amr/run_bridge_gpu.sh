#!/usr/bin/env bash
set -e

deactivate 2>/dev/null || true

export ROS_DOMAIN_ID=119
export ROS_LOCALHOST_ONLY=0

# GPU/OpenCV runtime policy for the Isaac-side controller when this shell exports envs.
# The bridge itself is ROS/file I/O and cannot use GPU, but these envs are kept consistent.
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export AMR_GPU_ENABLED="${AMR_GPU_ENABLED:-1}"
export AMR_QR_GPU_PREPROCESS_ENABLED="${AMR_QR_GPU_PREPROCESS_ENABLED:-1}"
export AMR_QR_CUDA_DEVICE_ID="${AMR_QR_CUDA_DEVICE_ID:-0}"
export AMR_OPENCV_CPU_THREADS="${AMR_OPENCV_CPU_THREADS:-1}"
export AMR_BRIDGE_EXECUTOR_THREADS="${AMR_BRIDGE_EXECUTOR_THREADS:-2}"
export __GLX_VENDOR_LIBRARY_NAME="${__GLX_VENDOR_LIBRARY_NAME:-nvidia}"
export __NV_PRIME_RENDER_OFFLOAD="${__NV_PRIME_RENDER_OFFLOAD:-1}"

if [ -f "$HOME/.ros/cyclonedds_thunderbolt.xml" ]; then
  export CYCLONEDDS_URI="file://$HOME/.ros/cyclonedds_thunderbolt.xml"
fi

source /opt/ros/humble/setup.bash

if [ -f "$HOME/amr_ros_ws/install/setup.bash" ]; then
  source "$HOME/amr_ros_ws/install/setup.bash"
else
  echo "[ERROR] ~/amr_ros_ws/install/setup.bash not found"
  echo "Build/source cobot3_interfaces first."
  exit 1
fi

if [ -f "/opt/ros/humble/lib/librmw_cyclonedds_cpp.so" ]; then
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
else
  unset RMW_IMPLEMENTATION
  echo "[WARN] rmw_cyclonedds_cpp not installed. Using default RMW."
fi

cd "$HOME/isaaclab_ws/isaac_aruco/amr"
exec /usr/bin/python3 fleet_manager_bridge_node_gpu.py

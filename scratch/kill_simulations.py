import os
import signal

keywords = [
    "dashboard_server.py", 
    "control_tower", 
    "run_full_simulation_robot.py", 
    "amr_redis_test_publisher.py", 
    "isaac_only_amr_connector.py",
    "isaac_amr_connector.py",
    "control_tower_node",
    "uvicorn"
]

print("Scanning /proc for simulation and control tower processes...")
killed_count = 0

for name in os.listdir('/proc'):
    if name.isdigit():
        pid = int(name)
        try:
            # cmdline 파일 읽기
            with open(os.path.join('/proc', name, 'cmdline'), 'r') as f:
                cmdline = f.read().replace('\x00', ' ')
            
            # 키워드 매칭
            match = False
            for kw in keywords:
                if kw in cmdline:
                    match = True
                    break
            
            # 자기 자신은 제외
            if match and "kill_simulations.py" not in cmdline:
                print(f"Found match: PID {pid} -> {cmdline.strip()}")
                try:
                    os.kill(pid, signal.SIGKILL)
                    print(f"Successfully killed PID {pid}")
                    killed_count += 1
                except ProcessLookupError:
                    print(f"PID {pid} already dead")
                except PermissionError:
                    print(f"Permission denied to kill PID {pid}")
        except Exception as e:
            pass

print(f"Done. Total killed: {killed_count} processes.")

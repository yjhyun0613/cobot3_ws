import os
import signal
import sys

keywords = [
    "dashboard_server.py", 
    "control_tower", 
    "run_full_simulation_robot.py", 
    "amr_redis_test_publisher.py", 
    "isaac_only_amr_connector.py",
    "isaac_amr_connector.py",
    "control_tower_node",
    "uvicorn",
    "mock_simul.py"
]

print("Scanning /proc for simulation and control tower processes...")
killed_pids = set()
killed_count = 0

# 1. 8009 포트를 점유하고 있는 프로세스 먼저 감지 및 종료
try:
    import subprocess
    output = subprocess.check_output(["lsof", "-t", "-i", ":8009"], text=True)
    for line in output.strip().split("\n"):
        if line.strip().isdigit():
            port_pid = int(line.strip())
            if port_pid not in killed_pids and port_pid != os.getpid():
                print(f"Found process listening on port 8009: PID {port_pid}")
                try:
                    os.kill(port_pid, signal.SIGKILL)
                    print(f"Successfully killed port listener PID {port_pid}")
                    killed_pids.add(port_pid)
                    killed_count += 1
                except Exception as e:
                    print(f"Failed to kill port listener PID {port_pid}: {e}")
except Exception:
    pass

# 2. 키워드 매칭을 통한 프로세스 검색 및 종료
pids = [int(name) for name in os.listdir('/proc') if name.isdigit()]

for pid in pids:
    if pid == os.getpid() or pid in killed_pids:
        continue
    try:
        # cmdline 파일 읽기
        with open(os.path.join('/proc', str(pid), 'cmdline'), 'r') as f:
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
                killed_pids.add(pid)
                killed_count += 1
            except ProcessLookupError:
                pass
            except PermissionError:
                print(f"Permission denied to kill PID {pid}")
    except Exception:
        pass

# 3. 종료된 프로세스의 자식 프로세스들(예: multiprocessing spawn 자식들) 추적 및 종료
for _ in range(3):
    found_child = False
    current_pids = [int(name) for name in os.listdir('/proc') if name.isdigit()]
    for pid in current_pids:
        if pid == os.getpid() or pid in killed_pids:
            continue
        try:
            with open(os.path.join('/proc', str(pid), 'stat'), 'r') as f:
                stat_parts = f.read().split()
                ppid = int(stat_parts[3])
            if ppid in killed_pids:
                print(f"Found child process of killed parent: PID {pid} (Parent: {ppid})")
                try:
                    os.kill(pid, signal.SIGKILL)
                    print(f"Successfully killed child PID {pid}")
                    killed_pids.add(pid)
                    killed_count += 1
                    found_child = True
                except Exception:
                    pass
        except Exception:
            pass
    if not found_child:
        break

print(f"Done. Total killed: {killed_count} processes.")

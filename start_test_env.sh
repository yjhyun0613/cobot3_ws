#!/usr/bin/env bash
set -e

# ANSI 색상 코드 정의
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 외부에서 ROS_LOCALHOST_ONLY를 설정하지 않았을 경우 기본값 1(로컬 전용) 사용
if [ -z "$ROS_LOCALHOST_ONLY" ]; then
    export ROS_LOCALHOST_ONLY=1
fi

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}   🚀 쿠팡 물류창고 Multi-AMR 통합 관제 시뮬레이션 테스트 가동   ${NC}"
echo -e "${BLUE}================================================================${NC}"

# 1. 작업 디렉토리 확보
cd "$(dirname "$0")"

# 2. Docker 컨테이너 상태 점검 및 실행
echo -e "\n${YELLOW}[Step 1] Docker 컨테이너 (PostgreSQL & Redis) 점검 중...${NC}"
if ! docker ps | grep -q "warehouse_postgres" || ! docker ps | grep -q "warehouse_redis"; then
    echo -e "${YELLOW}데이터베이스 컨테이너가 실행 중이지 않습니다. 컨테이너를 가동합니다...${NC}"
    docker compose -f docker/docker-compose.yml up -d
    echo -e "${GREEN}컨테이너 가동 성공! DB 초기화를 위해 3초 대기합니다...${NC}"
    sleep 3
else
    echo -e "${GREEN}Docker 컨테이너가 정상 구동 중입니다.${NC}"
fi

# 3. 데이터베이스 및 캐시 상태 완전 초기화
echo -e "\n${YELLOW}[Step 2] 데이터베이스 테이블 구조 및 Redis 캐시 정비 시작...${NC}"
python3 scratch/reset_db.py

# 4. ROS 2 빌드 및 소스 확인
echo -e "\n${YELLOW}[Step 3] ROS 2 워크스페이스 빌드 확인 중...${NC}"
if [ ! -f "install/setup.bash" ]; then
    echo -e "${RED}[경고] install/setup.bash 파일이 없습니다. 빌드를 수행합니다...${NC}"
    colcon build --symlink-install
fi

# 5. 실행 방식 선택 및 분할 구동
echo -e "\n${YELLOW}[Step 4] 실행 모드를 선택하세요:${NC}"
echo "1) 새 터미널 창들을 자동으로 띄워 통합 실행 (추천 - GUI 환경용)"
echo "2) 현재 터미널에서 백그라운드로 실행하고 로그 확인하기"
echo "3) 각 노드를 수동으로 구동하기 위해 명령어 목록만 보기"
read -p "선택 (1/2/3): " RUN_MODE

case $RUN_MODE in
    1)
        if command -v gnome-terminal >/dev/null 2>&1; then
            echo -e "${GREEN}gnome-terminal을 통해 3개의 노드를 독립 탭으로 실행합니다.${NC}"
            
            # 대시보드 서버 실행
            gnome-terminal --tab --title="FastAPI Dashboard" -- bash -c "python3 scratch/dashboard_server.py; exec bash"
            
            # ROS 2 관제 노드 실행
            gnome-terminal --tab --title="ROS2 Control Tower" -- bash -c "source install/setup.bash && export ROS_DOMAIN_ID=119 && export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY && ros2 run cobot3 control_tower; exec bash"
            
            # 로봇 시뮬레이터 실행
            gnome-terminal --tab --title="Robot Simulation (A*)" -- bash -c "source install/setup.bash && export ROS_DOMAIN_ID=119 && export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY && python3 scratch/run_full_simulation_robot.py; exec bash"
            
        elif command -v x-terminal-emulator >/dev/null 2>&1; then
            echo -e "${GREEN}x-terminal-emulator를 통해 실행합니다.${NC}"
            x-terminal-emulator -e bash -c "python3 scratch/dashboard_server.py" &
            sleep 0.5
            x-terminal-emulator -e bash -c "source install/setup.bash && export ROS_DOMAIN_ID=119 && export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY && ros2 run cobot3 control_tower" &
            sleep 0.5
            x-terminal-emulator -e bash -c "source install/setup.bash && export ROS_DOMAIN_ID=119 && export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY && python3 scratch/run_full_simulation_robot.py" &
        else
            echo -e "${RED}새 터미널 창을 띄울 수 있는 도구(gnome-terminal 등)를 찾지 못했습니다.${NC}"
            echo -e "백그라운드 실행 모드로 전환합니다."
            RUN_MODE=2
        fi
        ;;
esac

if [ "$RUN_MODE" = "2" ]; then
    echo -e "${GREEN}백그라운드에서 백엔드, 관제탑, 로봇 시뮬레이션을 구동합니다...${NC}"
    
    # 기존 백그라운드 프로세스가 있다면 안전하게 정리
    pkill -f "scratch/dashboard_server.py" || true
    pkill -f "cobot3/control_tower" || true
    pkill -f "scratch/run_full_simulation_robot.py" || true
    
    # 로그 디렉토리 생성
    mkdir -p log
    
    # 1. 대시보드 서버 백그라운드 구동
    echo "  - FastAPI 대시보드 서버 가동 중 (로그: log/dashboard.log)"
    nohup python3 scratch/dashboard_server.py > log/dashboard.log 2>&1 &
    sleep 1
    
    # 2. ROS 2 관제탑 구동
    echo "  - ROS 2 관제탑 노드 가동 중 (로그: log/control_tower.log)"
    source install/setup.bash
    export ROS_DOMAIN_ID=119
    export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY
    nohup ros2 run cobot3 control_tower > log/control_tower.log 2>&1 &
    sleep 1
    
    # 3. 로봇 시뮬레이터 구동
    echo "  - 로봇 및 A* AMR 시뮬레이터 가동 중 (로그: log/simulation.log)"
    nohup python3 scratch/run_full_simulation_robot.py > log/simulation.log 2>&1 &
    
    echo -e "${GREEN}모든 백그라운드 노드 가동 완료!${NC}"
    echo -e "종료하려면 터미널에 ${YELLOW}killall python3${NC} 또는 개별 프로세스를 정지하세요."
    echo -e "실시간 로그를 확인하려면 다음 명령어를 사용하세요: ${BLUE}tail -f log/simulation.log${NC}"
fi

if [ "$RUN_MODE" = "3" ] || [ -z "$RUN_MODE" ]; then
    echo -e "\n${YELLOW}아래 명령어를 각각 새 터미널 창에 입력하여 개별 구동하세요:${NC}"
    echo -e "${BLUE}[터미널 1] FastAPI 웹 대시보드 서버 구동${NC}"
    echo "  python3 scratch/dashboard_server.py"
    
    echo -e "${BLUE}[터미널 2] ROS 2 관제탑(Control Tower) 구동${NC}"
    echo "  source install/setup.bash"
    echo "  export ROS_DOMAIN_ID=119"
    echo "  export ROS_LOCALHOST_ONLY=\$ROS_LOCALHOST_ONLY"
    echo "  ros2 run cobot3 control_tower"
    
    echo -e "${BLUE}[터미널 3] 5대 AMR 및 로봇 시뮬레이션 구동${NC}"
    echo "  source install/setup.bash"
    echo "  export ROS_DOMAIN_ID=119"
    echo "  export ROS_LOCALHOST_ONLY=\$ROS_LOCALHOST_ONLY"
    echo "  python3 scratch/run_full_simulation_robot.py"
fi

echo -e "\n${BLUE}================================================================${NC}"
echo -e "${GREEN}💡 통합 테스트 준비 완료!${NC}"
echo -e "1. 브라우저에서 ${YELLOW}http://localhost:8009${NC} 에 접속합니다."
echo -e "2. 상단 우측의 [CSV 입고 명단 업로드] 버튼을 눌러"
echo -e "   ${YELLOW}scratch/packages_2026-06-08.csv${NC} 파일을 업로드합니다."
echo -e "3. CSV 업로드 즉시 시뮬레이션 동작 및 AMR 주행이 시작됩니다."
echo -e "${BLUE}================================================================${NC}"

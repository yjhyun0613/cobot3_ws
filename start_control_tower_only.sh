#!/usr/bin/env bash
set -e

# ANSI 색상 코드 정의
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 외부에서 ROS_LOCALHOST_ONLY를 설정하지 않았을 경우 기본값 0(다른 PC와 분산 통신) 사용
if [ -z "$ROS_LOCALHOST_ONLY" ]; then
    export ROS_LOCALHOST_ONLY=0
fi

# 다른 PC와 통신 시 CycloneDDS 설정파일 경로 지정
if [ "$ROS_LOCALHOST_ONLY" = "0" ]; then
    export CYCLONEDDS_URI="file://$HOME/.ros/cyclonedds_wifi.xml"
fi

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}   🚀 [Core + SG2 Out] 관제탑 코어, 백엔드 및 가상 SG2 Out 가동 스크립트   ${NC}"
if [ "$ROS_LOCALHOST_ONLY" = "0" ]; then
    echo -e "${BLUE}   📡 모드: 다른 PC와 분산 통신 (ROS_LOCALHOST_ONLY=0)${NC}"
    echo -e "${BLUE}   🔗 설정: CYCLONEDDS_URI=$CYCLONEDDS_URI${NC}"
else
    echo -e "${BLUE}   💻 모드: 로컬 전용 테스트 (ROS_LOCALHOST_ONLY=1)${NC}"
fi
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

# 3. 데이터베이스 및 캐시 상태 완전 초기화 (6월 8일 날짜 및 이월 재고 상태 적용)
echo -e "\n${YELLOW}[Step 2] 데이터베이스 테이블 구조 및 Redis 캐시 정비 (6월 8일 기준) 시작...${NC}"
python3 scratch/reset_db.py
python3 docker/init_june_8th_state.py

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
            echo -e "${GREEN}gnome-terminal을 통해 3개의 프로세스를 독립 탭으로 실행합니다.${NC}"
            
            # 대시보드 서버 실행
            gnome-terminal --tab --title="FastAPI Dashboard" -- bash -c "python3 scratch/dashboard_server.py; exec bash"
            
            # ROS 2 관제 노드 실행
            gnome-terminal --tab --title="ROS2 Control Tower" -- bash -c "source install/setup.bash && export ROS_DOMAIN_ID=119 && export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY && [ -n \"$CYCLONEDDS_URI\" ] && export CYCLONEDDS_URI=\"$CYCLONEDDS_URI\"; ros2 run cobot3 control_tower; exec bash"
            
            # ROS 2 가상 SG2 Out 포장 로봇 실행
            gnome-terminal --tab --title="ROS2 Mock SG2 Out" -- bash -c "source install/setup.bash && export ROS_DOMAIN_ID=119 && export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY && [ -n \"$CYCLONEDDS_URI\" ] && export CYCLONEDDS_URI=\"$CYCLONEDDS_URI\"; ros2 run cobot3 mock_sg2_out; exec bash"
            
        elif command -v x-terminal-emulator >/dev/null 2>&1; then
            echo -e "${GREEN}x-terminal-emulator를 통해 실행합니다.${NC}"
            x-terminal-emulator -e bash -c "python3 scratch/dashboard_server.py" &
            sleep 0.5
            x-terminal-emulator -e bash -c "source install/setup.bash && export ROS_DOMAIN_ID=119 && export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY && [ -n \"$CYCLONEDDS_URI\" ] && export CYCLONEDDS_URI=\"$CYCLONEDDS_URI\"; ros2 run cobot3 control_tower" &
            sleep 0.5
            x-terminal-emulator -e bash -c "source install/setup.bash && export ROS_DOMAIN_ID=119 && export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY && [ -n \"$CYCLONEDDS_URI\" ] && export CYCLONEDDS_URI=\"$CYCLONEDDS_URI\"; ros2 run cobot3 mock_sg2_out" &
        else
            echo -e "${RED}새 터미널 창을 띄울 수 있는 도구(gnome-terminal 등)를 찾지 못했습니다.${NC}"
            echo -e "백그라운드 실행 모드로 전환합니다."
            RUN_MODE=2
        fi
        ;;
esac

if [ "$RUN_MODE" = "2" ]; then
    echo -e "${GREEN}백그라운드에서 백엔드, 관제탑 코어, 가상 SG2 Out을 구동합니다...${NC}"
    
    # 기존 백그라운드 프로세스가 있다면 안전하게 정리
    pkill -f "scratch/dashboard_server.py" || true
    pkill -f "cobot3/control_tower" || true
    pkill -f "cobot3/mock_sg2_out" || true
    
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
    if [ -n "$CYCLONEDDS_URI" ]; then
        export CYCLONEDDS_URI="$CYCLONEDDS_URI"
    fi
    nohup ros2 run cobot3 control_tower > log/control_tower.log 2>&1 &
    sleep 1

    # 3. ROS 2 가상 SG2 Out 구동
    echo "  - ROS 2 가상 SG2 Out 포장 로봇 가동 중 (로그: log/mock_sg2_out.log)"
    nohup ros2 run cobot3 mock_sg2_out > log/mock_sg2_out.log 2>&1 &
    
    echo -e "${GREEN}모든 백그라운드 노드 가동 완료!${NC}"
    echo -e "종료하려면 터미널에 ${YELLOW}pkill -f dashboard_server.py${NC}, ${YELLOW}pkill -f control_tower${NC} 및 ${YELLOW}pkill -f mock_sg2_out${NC}를 수행하세요."
    echo -e "실시간 로그를 확인하려면 다음 명령어를 사용하세요: ${BLUE}tail -f log/control_tower.log${NC}"
fi

if [ "$RUN_MODE" = "3" ] || [ -z "$RUN_MODE" ]; then
    echo -e "\n${YELLOW}아래 명령어를 각각 새 터미널 창에 입력하여 개별 구동하세요:${NC}"
    echo -e "${BLUE}[터미널 1] FastAPI 웹 대시보드 서버 구동${NC}"
    echo "  python3 scratch/dashboard_server.py"
    
    echo -e "${BLUE}[터미널 2] ROS 2 관제탑(Control Tower) 구동${NC}"
    echo "  source install/setup.bash"
    echo "  export ROS_DOMAIN_ID=119"
    echo "  export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY"
    if [ -n "$CYCLONEDDS_URI" ]; then
        echo "  export CYCLONEDDS_URI=\"$CYCLONEDDS_URI\""
    fi
    echo "  ros2 run cobot3 control_tower"

    echo -e "${BLUE}[터미널 3] ROS 2 가상 SG2 Out 포장 로봇 구동${NC}"
    echo "  source install/setup.bash"
    echo "  export ROS_DOMAIN_ID=119"
    echo "  export ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY"
    if [ -n "$CYCLONEDDS_URI" ]; then
        echo "  export CYCLONEDDS_URI=\"$CYCLONEDDS_URI\""
    fi
    echo "  ros2 run cobot3 mock_sg2_out"
fi

echo -e "\n${BLUE}================================================================${NC}"
echo -e "${GREEN}💡 관제탑 코어 및 가상 SG2 Out 준비 완료!${NC}"
echo -e "6월 8일 초기 데이터(이월 재고 및 레이아웃)가 정상 적재되었습니다."
echo -e "대시보드는 ${YELLOW}http://localhost:8009${NC} 에서 모니터링 가능합니다."
echo -e "${BLUE}================================================================${NC}"

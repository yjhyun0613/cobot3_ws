-- 1. 테이블 초기화
DROP TABLE IF EXISTS packages;
DROP TABLE IF EXISTS workstations;
DROP TABLE IF EXISTS robots;

-- 2. robots 테이블 생성
CREATE TABLE robots (
    robot_id VARCHAR(50) PRIMARY KEY,
    robot_type VARCHAR(50) NOT NULL
);

-- 3. workstations 테이블 생성
CREATE TABLE workstations (
    workstation_id VARCHAR(50) PRIMARY KEY,
    current_location VARCHAR(50) NOT NULL, -- sg2_in_01, warehouse, sg2_out_00, etc.
    slot_1_customer VARCHAR(100),
    slot_1_status VARCHAR(20) DEFAULT 'EMPTY', -- EMPTY, FILLING, FULL
    slot_2_customer VARCHAR(100),
    slot_2_status VARCHAR(20) DEFAULT 'EMPTY',
    slot_3_customer VARCHAR(100),
    slot_3_status VARCHAR(20) DEFAULT 'EMPTY',
    slot_4_customer VARCHAR(100),
    slot_4_status VARCHAR(20) DEFAULT 'EMPTY'
);

-- 4. packages 테이블 생성
CREATE TABLE packages (
    package_id VARCHAR(50) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    route_zone VARCHAR(20) NOT NULL, -- 날짜 형식 (YYYY-MM-DD)
    status VARCHAR(50) DEFAULT 'WAITING', -- WAITING, IN_WORKSTATION, IN_WAREHOUSE, COMPLETED
    outbound_id VARCHAR(100), -- [작업대ID]+[칸번호]+[날짜]+[시간]
    workstation_id VARCHAR(50), -- 적재된 작업대 ID (어디에 있는지 추적)
    slot_number INT             -- 작업대 내 슬롯 번호 (1~4)
);

-- 5. 기본 데이터 삽입 (Mock Data)
-- 로봇 등록
INSERT INTO robots (robot_id, robot_type) VALUES
('bg2', 'CONVEYOR_SORTER'),
('sg2_in_01', 'MANIPULATOR'),
('sg2_in_02', 'MANIPULATOR'),
('sg2_in_03', 'MANIPULATOR'),
('sg2_out_00', 'MANIPULATOR');

-- 작업대 등록 (WS01, WS02, WS03)
INSERT INTO workstations (workstation_id, current_location) VALUES
('WS01', 'sg2_in_01'),  -- 오늘(2026-06-01) 분류 라인 대기 중
('WS02', 'sg2_in_02'),  -- 내일(2026-06-02) 분류 라인 대기 중
('WS03', 'sg2_in_03');  -- 모레(2026-06-03) 분류 라인 대기 중

-- 초기 입고 예정 택배 데이터 (2026-06-01 기준)
INSERT INTO packages (package_id, customer_name, route_zone, status) VALUES
('PKG_RAND_001', '김철수', '2026-06-01', 'WAITING'),
('PKG_RAND_002', '이영희', '2026-06-02', 'WAITING'),
('PKG_RAND_003', '박민수', '2026-06-03', 'WAITING'),
('PKG_RAND_004', '김철수', '2026-06-01', 'WAITING'),
('PKG_RAND_005', '최독고', '2026-06-01', 'WAITING'),
('PKG_RAND_006', '이영희', '2026-06-02', 'WAITING'),
('PKG_RAND_007', '홍길동', '2026-06-01', 'WAITING'),
('PKG_RAND_008', '김철수', '2026-06-01', 'WAITING');

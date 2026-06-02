-- 1. 테이블 초기화
DROP TABLE IF EXISTS packages;
DROP TABLE IF EXISTS warehouse_locations;
DROP TABLE IF EXISTS workstations;
DROP TABLE IF EXISTS robots;

-- 2. robots 테이블 생성
CREATE TABLE robots (
    robot_id VARCHAR(50) PRIMARY KEY,
    robot_type VARCHAR(50) NOT NULL,
    aruco_id INT UNIQUE
);

-- 3. workstations 테이블 생성
CREATE TABLE workstations (
    workstation_id VARCHAR(50) PRIMARY KEY,
    current_location VARCHAR(50) NOT NULL, -- sg2_in_01, warehouse, sg2_out_00, spot_XX, etc.
    aruco_id INT UNIQUE,
    slot_1_customer VARCHAR(100),
    slot_1_status VARCHAR(20) DEFAULT 'EMPTY', -- EMPTY, FILLING, FULL
    slot_2_customer VARCHAR(100),
    slot_2_status VARCHAR(20) DEFAULT 'EMPTY',
    slot_3_customer VARCHAR(100),
    slot_3_status VARCHAR(20) DEFAULT 'EMPTY',
    slot_4_customer VARCHAR(100),
    slot_4_status VARCHAR(20) DEFAULT 'EMPTY'
);

-- 4. warehouse_locations 테이블 생성
CREATE TABLE warehouse_locations (
    spot_id VARCHAR(50) PRIMARY KEY,
    workstation_id VARCHAR(50) REFERENCES workstations(workstation_id),
    status VARCHAR(20) DEFAULT 'EMPTY'
);

-- 5. packages 테이블 생성
CREATE TABLE packages (
    package_id VARCHAR(50) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    route_zone VARCHAR(20) NOT NULL, -- 날짜 형식 (YYYY-MM-DD)
    status VARCHAR(50) DEFAULT 'WAITING', -- WAITING, IN_WORKSTATION, IN_WAREHOUSE, COMPLETED
    outbound_id VARCHAR(100), -- [로봇ID]_[작업대ID]+[칸번호]+[날짜]+[시간]
    workstation_id VARCHAR(50) REFERENCES workstations(workstation_id),
    slot_number INT,            -- 작업대 내 슬롯 번호 (1~4)
    aruco_id INT UNIQUE
);

-- 6. 기본 데이터 삽입 (Mock Data)
-- 로봇 등록
INSERT INTO robots (robot_id, robot_type, aruco_id) VALUES
('bg2', 'CONVEYOR_SORTER', 1),
('sg2_in_01', 'MANIPULATOR', 2),
('sg2_in_02', 'MANIPULATOR', 3),
('sg2_in_03', 'MANIPULATOR', 4),
('sg2_out_00', 'MANIPULATOR', 5);

-- 작업대 등록 (WS01 ~ WS10)
INSERT INTO workstations (workstation_id, current_location, aruco_id) VALUES
('WS01', 'spot_01', 11),
('WS02', 'spot_02', 12),
('WS03', 'spot_03', 13),
('WS04', 'spot_04', 14),
('WS05', 'spot_05', 15),
('WS06', 'spot_06', 16),
('WS07', 'spot_07', 17),
('WS08', 'spot_08', 18),
('WS09', 'spot_09', 19),
('WS10', 'spot_10', 20);

-- 창고 스팟 등록 및 작업대 주차 (spot_01 ~ spot_10)
INSERT INTO warehouse_locations (spot_id, workstation_id, status) VALUES
('spot_01', 'WS01', 'OCCUPIED'),
('spot_02', 'WS02', 'OCCUPIED'),
('spot_03', 'WS03', 'OCCUPIED'),
('spot_04', 'WS04', 'OCCUPIED'),
('spot_05', 'WS05', 'OCCUPIED'),
('spot_06', 'WS06', 'OCCUPIED'),
('spot_07', 'WS07', 'OCCUPIED'),
('spot_08', 'WS08', 'OCCUPIED'),
('spot_09', 'WS09', 'OCCUPIED'),
('spot_10', 'WS10', 'OCCUPIED');

-- 초기 입고 예정 택배 데이터 (2026-06-01 기준)
INSERT INTO packages (package_id, customer_name, route_zone, status, aruco_id) VALUES
('PKG_RAND_001', '김철수', '2026-06-01', 'WAITING', 101),
('PKG_RAND_002', '이영희', '2026-06-02', 'WAITING', 102),
('PKG_RAND_003', '박민수', '2026-06-03', 'WAITING', 103),
('PKG_RAND_004', '김철수', '2026-06-01', 'WAITING', 104),
('PKG_RAND_005', '최독고', '2026-06-01', 'WAITING', 105),
('PKG_RAND_006', '이영희', '2026-06-02', 'WAITING', 106),
('PKG_RAND_007', '홍길동', '2026-06-01', 'WAITING', 107),
('PKG_RAND_008', '김철수', '2026-06-01', 'WAITING', 108);

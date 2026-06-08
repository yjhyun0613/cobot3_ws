-- 1. 테이블 초기화
DROP TABLE IF EXISTS packages;
DROP TABLE IF EXISTS warehouse_locations;
DROP TABLE IF EXISTS workstations;
DROP TABLE IF EXISTS robots;
DROP TABLE IF EXISTS floor_qr_map;

-- 2. robots 테이블 생성
CREATE TABLE robots (
    robot_id VARCHAR(50) PRIMARY KEY,
    robot_type VARCHAR(50) NOT NULL,
    qr_id VARCHAR(100) UNIQUE
);

-- 3. workstations 테이블 생성
CREATE TABLE workstations (
    workstation_id VARCHAR(50) PRIMARY KEY,
    current_location VARCHAR(50) NOT NULL, -- sg2_in_01, warehouse, sg2_out_00, spot_XX, etc.
    qr_id VARCHAR(100) UNIQUE,
    status VARCHAR(50) DEFAULT 'WAITING',
    reserved_by VARCHAR(50)
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
    slot_number INT,            -- 작업대 내 슬롯 번호 (1~8)
    qr_id VARCHAR(100) UNIQUE
);

-- 6. floor_qr_map 테이블 생성
CREATE TABLE floor_qr_map (
    qr_id VARCHAR(100) PRIMARY KEY,
    x_coord DOUBLE PRECISION NOT NULL,
    y_coord DOUBLE PRECISION NOT NULL,
    z_coord DOUBLE PRECISION DEFAULT 0.0,
    location_name VARCHAR(50),
    location_type VARCHAR(50),
    description TEXT
);

-- 7. 기본 데이터 삽입 (Mock Data)
-- 로봇 등록
INSERT INTO robots (robot_id, robot_type, qr_id) VALUES
('bg2', 'CONVEYOR_SORTER', 'ROBOT_bg2'),
('sg2_in_01', 'MANIPULATOR', 'ROBOT_sg2_in_01'),
('sg2_in_02', 'MANIPULATOR', 'ROBOT_sg2_in_02'),
('sg2_in_03', 'MANIPULATOR', 'ROBOT_sg2_in_03'),
('sg2_out_00', 'MANIPULATOR', 'ROBOT_sg2_out_00');

-- 작업대 등록 (WS01 ~ WS10)
INSERT INTO workstations (workstation_id, current_location, qr_id) VALUES
('WS01', 'spot_01', 'WORKSTATION_WS01'),
('WS02', 'spot_02', 'WORKSTATION_WS02'),
('WS03', 'spot_03', 'WORKSTATION_WS03'),
('WS04', 'spot_04', 'WORKSTATION_WS04'),
('WS05', 'spot_05', 'WORKSTATION_WS05'),
('WS06', 'spot_06', 'WORKSTATION_WS06'),
('WS07', 'spot_07', 'WORKSTATION_WS07'),
('WS08', 'spot_08', 'WORKSTATION_WS08'),
('WS09', 'spot_09', 'WORKSTATION_WS09'),
('WS10', 'spot_10', 'WORKSTATION_WS10');


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


-- 출고 대기 구역 등록 (stage_01 ~ stage_04)
INSERT INTO warehouse_locations (spot_id, workstation_id, status) VALUES
('stage_01', NULL, 'EMPTY'),
('stage_02', NULL, 'EMPTY'),
('stage_03', NULL, 'EMPTY'),
('stage_04', NULL, 'EMPTY');


-- 8. 초기 패키지 데이터 (웹 대시보드 CSV 업로드를 통해 동적으로 적재됩니다.)


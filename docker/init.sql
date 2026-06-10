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

-- 6.5. 성능 인덱스 생성 (패키지 누적 시 Full Table Scan 방지)
CREATE INDEX idx_packages_status ON packages(status);
CREATE INDEX idx_packages_route_zone ON packages(route_zone);
CREATE INDEX idx_packages_workstation ON packages(workstation_id);
CREATE INDEX idx_workstations_location ON workstations(current_location);
CREATE INDEX idx_floor_qr_location ON floor_qr_map(location_name);

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

-- INSERT INTO workstations (workstation_id, current_location, qr_id) VALUES
-- ('WS01', 'spot_09', 'WORKSTATION_WS01'),
-- ('WS02', 'spot_10', 'WORKSTATION_WS02'),
-- ('WS03', 'spot_07', 'WORKSTATION_WS03'),
-- ('WS04', 'spot_08', 'WORKSTATION_WS04'),
-- ('WS05', 'spot_05', 'WORKSTATION_WS05'),
-- ('WS06', 'spot_06', 'WORKSTATION_WS06'),
-- ('WS07', 'spot_03', 'WORKSTATION_WS07'),
-- ('WS08', 'spot_04', 'WORKSTATION_WS08'),
-- ('WS09', 'spot_01', 'WORKSTATION_WS09'),
-- ('WS10', 'spot_02', 'WORKSTATION_WS10');


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

-- INSERT INTO warehouse_locations (spot_id, workstation_id, status) VALUES
-- ('spot_01', 'WS09', 'OCCUPIED'),
-- ('spot_02', 'WS10', 'OCCUPIED'),
-- ('spot_03', 'WS07', 'OCCUPIED'),
-- ('spot_04', 'WS08', 'OCCUPIED'),
-- ('spot_05', 'WS05', 'OCCUPIED'),
-- ('spot_06', 'WS06', 'OCCUPIED'),
-- ('spot_07', 'WS03', 'OCCUPIED'),
-- ('spot_08', 'WS04', 'OCCUPIED'),
-- ('spot_09', 'WS01', 'OCCUPIED'),
-- ('spot_10', 'WS02', 'OCCUPIED');


-- 출고 대기 구역 등록 (stage_01 ~ stage_04)
INSERT INTO warehouse_locations (spot_id, workstation_id, status) VALUES
('stage_01', NULL, 'EMPTY'),
('stage_02', NULL, 'EMPTY'),
('stage_03', NULL, 'EMPTY'),
('stage_04', NULL, 'EMPTY');


-- 8. 바닥 QR 격자 맵 시드 데이터 (floor_qr_map)
-- 좌표 출처: PHYSICAL_LAYOUT.md (맵 중심: 3.0, 0.0 / X 크기 13.5m, Y 크기 20m)
-- 관제탑 노드의 trigger_workstation_move 함수가 이 테이블에서 물리 좌표를 조회합니다.

-- 8-1. 메인 보관 창고 스팟 (spot_01 ~ spot_10)
-- INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, location_name, location_type, description) VALUES
-- ('FLOOR_X_1.5_Y_3.0',   1.5,   3.0, 'spot_01', 'PARKING_SPOT', '메인 창고 1행 1열'),
-- ('FLOOR_X_0.0_Y_3.0',   0.0,   3.0, 'spot_02', 'PARKING_SPOT', '메인 창고 1행 2열'),
-- ('FLOOR_X_1.5_Y_0.0',   1.5,   0.0, 'spot_03', 'PARKING_SPOT', '메인 창고 2행 1열'),
-- ('FLOOR_X_0.0_Y_0.0',   0.0,   0.0, 'spot_04', 'PARKING_SPOT', '메인 창고 2행 2열'),
-- ('FLOOR_X_1.5_Y_-3.0',  1.5,  -3.0, 'spot_05', 'PARKING_SPOT', '메인 창고 3행 1열'),
-- ('FLOOR_X_0.0_Y_-3.0',  0.0,  -3.0, 'spot_06', 'PARKING_SPOT', '메인 창고 3행 2열'),
-- ('FLOOR_X_1.5_Y_-6.0',  1.5,  -6.0, 'spot_07', 'PARKING_SPOT', '메인 창고 4행 1열'),
-- ('FLOOR_X_0.0_Y_-6.0',  0.0,  -6.0, 'spot_08', 'PARKING_SPOT', '메인 창고 4행 2열'),
-- ('FLOOR_X_1.5_Y_-9.0',  1.5,  -9.0, 'spot_09', 'PARKING_SPOT', '메인 창고 5행 1열'),
-- ('FLOOR_X_0.0_Y_-9.0',  0.0,  -9.0, 'spot_10', 'PARKING_SPOT', '메인 창고 5행 2열');
INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, location_name, location_type, description) VALUES
('FLOOR_X_1.5_Y_3.0',   1.5,  -9.0, 'spot_01', 'PARKING_SPOT', '메인 창고 1행 1열'),
('FLOOR_X_0.0_Y_3.0',   0.0,  -9.0, 'spot_02', 'PARKING_SPOT', '메인 창고 1행 2열'),
('FLOOR_X_1.5_Y_0.0',   1.5,  -6.0, 'spot_03', 'PARKING_SPOT', '메인 창고 2행 1열'),
('FLOOR_X_0.0_Y_0.0',   0.0,  -6.0, 'spot_04', 'PARKING_SPOT', '메인 창고 2행 2열'),
('FLOOR_X_1.5_Y_-3.0',  1.5,  -3.0, 'spot_05', 'PARKING_SPOT', '메인 창고 3행 1열'),
('FLOOR_X_0.0_Y_-3.0',  0.0,  -3.0, 'spot_06', 'PARKING_SPOT', '메인 창고 3행 2열'),
('FLOOR_X_1.5_Y_-6.0',  1.5,   0.0, 'spot_07', 'PARKING_SPOT', '메인 창고 4행 1열'),
('FLOOR_X_0.0_Y_-6.0',  0.0,   0.0, 'spot_08', 'PARKING_SPOT', '메인 창고 4행 2열'),
('FLOOR_X_1.5_Y_-9.0',  1.5,   3.0, 'spot_09', 'PARKING_SPOT', '메인 창고 5행 1열'),
('FLOOR_X_0.0_Y_-9.0',  0.0,   3.0, 'spot_10', 'PARKING_SPOT', '메인 창고 5행 2열');

-- 8-2. 입고 분류 라인 A/B (sg2_in_01 ~ sg2_in_03)
INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, location_name, location_type, description) VALUES
('FLOOR_X_7.5_Y_1.5',   7.5,   1.5, 'sg2_in_01_A', 'LOADING_SPOT', '1번 입고라인 Active 버퍼 (오늘)'),
('FLOOR_X_6.0_Y_1.5',   6.0,   1.5, 'sg2_in_01_B', 'LOADING_SPOT', '1번 입고라인 Standby 버퍼 (오늘)'),
('FLOOR_X_7.5_Y_-3.0',  7.5,  -3.0, 'sg2_in_02_A', 'LOADING_SPOT', '2번 입고라인 Active 버퍼 (내일)'),
('FLOOR_X_6.0_Y_-3.0',  6.0,  -3.0, 'sg2_in_02_B', 'LOADING_SPOT', '2번 입고라인 Standby 버퍼 (내일)'),
('FLOOR_X_7.5_Y_-7.5',  7.5,  -7.5, 'sg2_in_03_A', 'LOADING_SPOT', '3번 입고라인 Active 버퍼 (모레)'),
('FLOOR_X_6.0_Y_-7.5',  6.0,  -7.5, 'sg2_in_03_B', 'LOADING_SPOT', '3번 입고라인 Standby 버퍼 (모레)');

-- 8-3. 출고 대기 창고 / 스테이징 구역 (stage_01 ~ stage_04)
INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, location_name, location_type, description) VALUES
('FLOOR_X_4.5_Y_9.0',   4.5,   9.0, 'stage_01', 'STAGING_SPOT', '출고 대기 창고 스팟 1'),
('FLOOR_X_4.5_Y_7.5',   4.5,   7.5, 'stage_02', 'STAGING_SPOT', '출고 대기 창고 스팟 2'),
('FLOOR_X_7.5_Y_9.0',   7.5,   9.0, 'stage_03', 'STAGING_SPOT', '출고 대기 창고 스팟 3'),
('FLOOR_X_7.5_Y_7.5',   7.5,   7.5, 'stage_04', 'STAGING_SPOT', '출고 대기 창고 스팟 4');

-- 8-4. 출고 포장 라인 A/B (sg2_out_00)
INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, location_name, location_type, description) VALUES
('FLOOR_X_0.0_Y_9.0',   0.0,   9.0, 'sg2_out_00_A', 'PACKAGING_SPOT', '출고 포장 A라인 Active 버퍼'),
('FLOOR_X_0.0_Y_7.5',   0.0,   7.5, 'sg2_out_00_B', 'PACKAGING_SPOT', '출고 포장 B라인 Standby 버퍼');

-- 8-5. AMR 충전 위치 (charging_01 ~ charging_05)
INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, location_name, location_type, description) VALUES
('FLOOR_X_-3.0_Y_-9.0', -3.0,  -9.0, 'charging_01', 'CHARGING_SPOT', 'AMR 충전기 스팟 1'),
('FLOOR_X_-3.0_Y_-7.5', -3.0,  -7.5, 'charging_02', 'CHARGING_SPOT', 'AMR 충전기 스팟 2'),
('FLOOR_X_-3.0_Y_-6.0', -3.0,  -6.0, 'charging_03', 'CHARGING_SPOT', 'AMR 충전기 스팟 3'),
('FLOOR_X_-3.0_Y_-4.5', -3.0,  -4.5, 'charging_04', 'CHARGING_SPOT', 'AMR 충전기 스팟 4'),
('FLOOR_X_-3.0_Y_-3.0', -3.0,  -3.0, 'charging_05', 'CHARGING_SPOT', 'AMR 충전기 스팟 5');

-- 8-6. AMR 주행 경로 격자 (PATHWAY / STATIC_OBSTACLE) - 1.5m 간격
INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, location_name, location_type, description) VALUES
('FLOOR_X_-3.0_Y_9.0',  -3.0,  9.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_-1.5_Y_9.0',  -1.5,  9.0, NULL, 'STATIC_OBSTACLE', 'SG2_OUT 포장 로봇 영역'),
('FLOOR_X_1.5_Y_9.0',    1.5,  9.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_9.0',    3.0,  9.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_9.0',    6.0,  9.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_9.0',    9.0,  9.0, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-1.5_Y_7.5',  -1.5,  7.5, NULL, 'STATIC_OBSTACLE', 'SG2_OUT 포장 로봇 영역'),
('FLOOR_X_1.5_Y_7.5',    1.5,  7.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_7.5',    3.0,  7.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_7.5',    6.0,  7.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_7.5',    9.0,  7.5, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-3.0_Y_6.0',  -3.0,  6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_-1.5_Y_6.0',  -1.5,  6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_0.0_Y_6.0',    0.0,  6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_1.5_Y_6.0',    1.5,  6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_6.0',    3.0,  6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_6.0',    4.5,  6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_6.0',    6.0,  6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_7.5_Y_6.0',    7.5,  6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_6.0',    9.0,  6.0, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-3.0_Y_4.5',  -3.0,  4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_-1.5_Y_4.5',  -1.5,  4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_0.0_Y_4.5',    0.0,  4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_1.5_Y_4.5',    1.5,  4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_4.5',    3.0,  4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_4.5',    4.5,  4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_4.5',    6.0,  4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_7.5_Y_4.5',    7.5,  4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_4.5',    9.0,  4.5, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-3.0_Y_3.0',  -3.0,  3.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_-1.5_Y_3.0',  -1.5,  3.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_3.0',    3.0,  3.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_3.0',    4.5,  3.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_3.0',    6.0,  3.0, NULL, 'STATIC_OBSTACLE', 'SG2_IN_1 입고 로봇 영역'),
('FLOOR_X_7.5_Y_3.0',    7.5,  3.0, NULL, 'STATIC_OBSTACLE', 'SG2_IN_1 입고 로봇 영역'),
('FLOOR_X_9.0_Y_3.0',    9.0,  3.0, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-3.0_Y_1.5',  -3.0,  1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_-1.5_Y_1.5',  -1.5,  1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_0.0_Y_1.5',    0.0,  1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_1.5_Y_1.5',    1.5,  1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_1.5',    3.0,  1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_1.5',    4.5,  1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_1.5',    9.0,  1.5, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-3.0_Y_0.0',  -3.0,  0.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_-1.5_Y_0.0',  -1.5,  0.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_0.0',    3.0,  0.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_0.0',    4.5,  0.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_0.0',    6.0,  0.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_7.5_Y_0.0',    7.5,  0.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_0.0',    9.0,  0.0, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-3.0_Y_-1.5', -3.0, -1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_-1.5_Y_-1.5', -1.5, -1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_0.0_Y_-1.5',   0.0, -1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_1.5_Y_-1.5',   1.5, -1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_-1.5',   3.0, -1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_-1.5',   4.5, -1.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_-1.5',   6.0, -1.5, NULL, 'STATIC_OBSTACLE', 'SG2_IN_2 입고 로봇 영역'),
('FLOOR_X_7.5_Y_-1.5',   7.5, -1.5, NULL, 'STATIC_OBSTACLE', 'SG2_IN_2 입고 로봇 영역'),
('FLOOR_X_9.0_Y_-1.5',   9.0, -1.5, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-1.5_Y_-3.0', -1.5, -3.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_-3.0',   3.0, -3.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_-3.0',   4.5, -3.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_-3.0',   9.0, -3.0, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-1.5_Y_-4.5', -1.5, -4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_0.0_Y_-4.5',   0.0, -4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_1.5_Y_-4.5',   1.5, -4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_-4.5',   3.0, -4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_-4.5',   4.5, -4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_-4.5',   6.0, -4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_7.5_Y_-4.5',   7.5, -4.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_-4.5',   9.0, -4.5, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-1.5_Y_-6.0', -1.5, -6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_-6.0',   3.0, -6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_-6.0',   4.5, -6.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_-6.0',   6.0, -6.0, NULL, 'STATIC_OBSTACLE', 'SG2_IN_3 입고 로봇 영역'),
('FLOOR_X_7.5_Y_-6.0',   7.5, -6.0, NULL, 'STATIC_OBSTACLE', 'SG2_IN_3 입고 로봇 영역'),
('FLOOR_X_9.0_Y_-6.0',   9.0, -6.0, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-1.5_Y_-7.5', -1.5, -7.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_0.0_Y_-7.5',   0.0, -7.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_1.5_Y_-7.5',   1.5, -7.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_-7.5',   3.0, -7.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_-7.5',   4.5, -7.5, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_-7.5',   9.0, -7.5, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트'),
('FLOOR_X_-1.5_Y_-9.0', -1.5, -9.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_3.0_Y_-9.0',   3.0, -9.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_4.5_Y_-9.0',   4.5, -9.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_6.0_Y_-9.0',   6.0, -9.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_7.5_Y_-9.0',   7.5, -9.0, NULL, 'PATHWAY', NULL),
('FLOOR_X_9.0_Y_-9.0',   9.0, -9.0, NULL, 'STATIC_OBSTACLE', '컨베이어 벨트');

-- 9. 초기 패키지 데이터 (웹 대시보드 CSV 업로드를 통해 동적으로 적재됩니다.)


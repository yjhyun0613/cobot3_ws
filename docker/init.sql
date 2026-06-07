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


-- 창고 스팟 등록 및 작업대 주차 (spot_01 ~ spot_10) 및 빈 스팟 등록 (spot_11 ~ spot_12)
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
('spot_10', 'WS10', 'OCCUPIED'),
('spot_11', NULL, 'EMPTY'),
('spot_12', NULL, 'EMPTY');


-- 출고 대기 구역 등록 (stage_01 ~ stage_06)
INSERT INTO warehouse_locations (spot_id, workstation_id, status) VALUES
('stage_01', NULL, 'EMPTY'),
('stage_02', NULL, 'EMPTY'),
('stage_03', NULL, 'EMPTY'),
('stage_04', NULL, 'EMPTY'),
('stage_05', NULL, 'EMPTY'),
('stage_06', NULL, 'EMPTY');


-- 초기 입고 예정 택배 데이터 (2026-06-01 기준)
INSERT INTO packages (package_id, customer_name, route_zone, status, qr_id) VALUES
('PKG_RAND_001', '김태희', '2026-06-01', 'WAITING', 'PKG_RAND_001'),
('PKG_RAND_002', '김철수', '2026-06-03', 'WAITING', 'PKG_RAND_002'),
('PKG_RAND_003', '이경규', '2026-06-01', 'WAITING', 'PKG_RAND_003'),
('PKG_RAND_004', '유재석', '2026-06-01', 'WAITING', 'PKG_RAND_004'),
('PKG_RAND_005', '공유', '2026-06-01', 'WAITING', 'PKG_RAND_005'),
('PKG_RAND_006', '송혜교', '2026-06-03', 'WAITING', 'PKG_RAND_006'),
('PKG_RAND_007', '조인성', '2026-06-02', 'WAITING', 'PKG_RAND_007'),
('PKG_RAND_008', '박민수', '2026-06-02', 'WAITING', 'PKG_RAND_008'),
('PKG_RAND_009', '김숙', '2026-06-01', 'WAITING', 'PKG_RAND_009'),
('PKG_RAND_010', '김철수', '2026-06-01', 'WAITING', 'PKG_RAND_010'),
('PKG_RAND_011', '강호동', '2026-06-01', 'WAITING', 'PKG_RAND_011'),
('PKG_RAND_012', '아이유', '2026-06-02', 'WAITING', 'PKG_RAND_012'),
('PKG_RAND_013', '김철수', '2026-06-02', 'WAITING', 'PKG_RAND_013'),
('PKG_RAND_014', '강호동', '2026-06-03', 'WAITING', 'PKG_RAND_014'),
('PKG_RAND_015', '김태희', '2026-06-03', 'WAITING', 'PKG_RAND_015'),
('PKG_RAND_016', '수지', '2026-06-02', 'WAITING', 'PKG_RAND_016'),
('PKG_RAND_017', '유재석', '2026-06-02', 'WAITING', 'PKG_RAND_017'),
('PKG_RAND_018', '박보검', '2026-06-01', 'WAITING', 'PKG_RAND_018'),
('PKG_RAND_019', '정우성', '2026-06-01', 'WAITING', 'PKG_RAND_019'),
('PKG_RAND_020', '이정재', '2026-06-01', 'WAITING', 'PKG_RAND_020'),
('PKG_RAND_021', '전지현', '2026-06-02', 'WAITING', 'PKG_RAND_021'),
('PKG_RAND_022', '장도연', '2026-06-01', 'WAITING', 'PKG_RAND_022'),
('PKG_RAND_023', '홍길동', '2026-06-01', 'WAITING', 'PKG_RAND_023'),
('PKG_RAND_024', '이정재', '2026-06-01', 'WAITING', 'PKG_RAND_024'),
('PKG_RAND_025', '최독고', '2026-06-01', 'WAITING', 'PKG_RAND_025'),
('PKG_RAND_026', '송은이', '2026-06-01', 'WAITING', 'PKG_RAND_026'),
('PKG_RAND_027', '박나래', '2026-06-01', 'WAITING', 'PKG_RAND_027'),
('PKG_RAND_028', '현빈', '2026-06-01', 'WAITING', 'PKG_RAND_028'),
('PKG_RAND_029', '정우성', '2026-06-01', 'WAITING', 'PKG_RAND_029'),
('PKG_RAND_030', '공유', '2026-06-02', 'WAITING', 'PKG_RAND_030'),
('PKG_RAND_031', '수지', '2026-06-01', 'WAITING', 'PKG_RAND_031'),
('PKG_RAND_032', '강동원', '2026-06-02', 'WAITING', 'PKG_RAND_032'),
('PKG_RAND_033', '박민수', '2026-06-02', 'WAITING', 'PKG_RAND_033'),
('PKG_RAND_034', '신동엽', '2026-06-03', 'WAITING', 'PKG_RAND_034'),
('PKG_RAND_035', '현빈', '2026-06-02', 'WAITING', 'PKG_RAND_035'),
('PKG_RAND_036', '박보검', '2026-06-01', 'WAITING', 'PKG_RAND_036'),
('PKG_RAND_037', '전지현', '2026-06-01', 'WAITING', 'PKG_RAND_037'),
('PKG_RAND_038', '이영희', '2026-06-03', 'WAITING', 'PKG_RAND_038'),
('PKG_RAND_039', '유재석', '2026-06-03', 'WAITING', 'PKG_RAND_039'),
('PKG_RAND_040', '신동엽', '2026-06-01', 'WAITING', 'PKG_RAND_040'),
('PKG_RAND_041', '하정우', '2026-06-01', 'WAITING', 'PKG_RAND_041'),
('PKG_RAND_042', '하정우', '2026-06-01', 'WAITING', 'PKG_RAND_042'),
('PKG_RAND_043', '송은이', '2026-06-01', 'WAITING', 'PKG_RAND_043'),
('PKG_RAND_044', '임재범', '2026-06-03', 'WAITING', 'PKG_RAND_044'),
('PKG_RAND_045', '황정민', '2026-06-02', 'WAITING', 'PKG_RAND_045'),
('PKG_RAND_046', '정수민', '2026-06-02', 'WAITING', 'PKG_RAND_046'),
('PKG_RAND_047', '박나래', '2026-06-01', 'WAITING', 'PKG_RAND_047'),
('PKG_RAND_048', '송혜교', '2026-06-01', 'WAITING', 'PKG_RAND_048'),
('PKG_RAND_049', '전지현', '2026-06-03', 'WAITING', 'PKG_RAND_049'),
('PKG_RAND_050', '김태희', '2026-06-01', 'WAITING', 'PKG_RAND_050'),
('PKG_RAND_051', '현빈', '2026-06-03', 'WAITING', 'PKG_RAND_051'),
('PKG_RAND_052', '정수민', '2026-06-02', 'WAITING', 'PKG_RAND_052'),
('PKG_RAND_053', '공유', '2026-06-01', 'WAITING', 'PKG_RAND_053'),
('PKG_RAND_054', '정수민', '2026-06-02', 'WAITING', 'PKG_RAND_054'),
('PKG_RAND_055', '송은이', '2026-06-01', 'WAITING', 'PKG_RAND_055'),
('PKG_RAND_056', '강동원', '2026-06-03', 'WAITING', 'PKG_RAND_056'),
('PKG_RAND_057', '전지현', '2026-06-02', 'WAITING', 'PKG_RAND_057'),
('PKG_RAND_058', '유재석', '2026-06-03', 'WAITING', 'PKG_RAND_058'),
('PKG_RAND_059', '장도연', '2026-06-03', 'WAITING', 'PKG_RAND_059'),
('PKG_RAND_060', '이정재', '2026-06-01', 'WAITING', 'PKG_RAND_060'),
('PKG_RAND_061', '유재석', '2026-06-01', 'WAITING', 'PKG_RAND_061'),
('PKG_RAND_062', '정우성', '2026-06-01', 'WAITING', 'PKG_RAND_062'),
('PKG_RAND_063', '송은이', '2026-06-01', 'WAITING', 'PKG_RAND_063'),
('PKG_RAND_064', '박민수', '2026-06-01', 'WAITING', 'PKG_RAND_064'),
('PKG_RAND_065', '강동원', '2026-06-02', 'WAITING', 'PKG_RAND_065'),
('PKG_RAND_066', '조인성', '2026-06-03', 'WAITING', 'PKG_RAND_066'),
('PKG_RAND_067', '장도연', '2026-06-01', 'WAITING', 'PKG_RAND_067'),
('PKG_RAND_068', '김태희', '2026-06-02', 'WAITING', 'PKG_RAND_068'),
('PKG_RAND_069', '송은이', '2026-06-03', 'WAITING', 'PKG_RAND_069'),
('PKG_RAND_070', '임재범', '2026-06-01', 'WAITING', 'PKG_RAND_070'),
('PKG_RAND_071', '이경규', '2026-06-01', 'WAITING', 'PKG_RAND_071'),
('PKG_RAND_072', '유재석', '2026-06-03', 'WAITING', 'PKG_RAND_072'),
('PKG_RAND_073', '수지', '2026-06-02', 'WAITING', 'PKG_RAND_073'),
('PKG_RAND_074', '이경규', '2026-06-03', 'WAITING', 'PKG_RAND_074'),
('PKG_RAND_075', '박보검', '2026-06-02', 'WAITING', 'PKG_RAND_075'),
('PKG_RAND_076', '조인성', '2026-06-02', 'WAITING', 'PKG_RAND_076'),
('PKG_RAND_077', '송은이', '2026-06-02', 'WAITING', 'PKG_RAND_077'),
('PKG_RAND_078', '유재석', '2026-06-01', 'WAITING', 'PKG_RAND_078'),
('PKG_RAND_079', '아이유', '2026-06-02', 'WAITING', 'PKG_RAND_079'),
('PKG_RAND_080', '박민수', '2026-06-03', 'WAITING', 'PKG_RAND_080'),
('PKG_RAND_081', '이영희', '2026-06-01', 'WAITING', 'PKG_RAND_081'),
('PKG_RAND_082', '홍길동', '2026-06-03', 'WAITING', 'PKG_RAND_082'),
('PKG_RAND_083', '정수민', '2026-06-03', 'WAITING', 'PKG_RAND_083'),
('PKG_RAND_084', '김숙', '2026-06-02', 'WAITING', 'PKG_RAND_084'),
('PKG_RAND_085', '박민수', '2026-06-02', 'WAITING', 'PKG_RAND_085'),
('PKG_RAND_086', '송은이', '2026-06-02', 'WAITING', 'PKG_RAND_086'),
('PKG_RAND_087', '임재범', '2026-06-02', 'WAITING', 'PKG_RAND_087'),
('PKG_RAND_088', '이경규', '2026-06-02', 'WAITING', 'PKG_RAND_088'),
('PKG_RAND_089', '하정우', '2026-06-01', 'WAITING', 'PKG_RAND_089'),
('PKG_RAND_090', '송혜교', '2026-06-03', 'WAITING', 'PKG_RAND_090'),
('PKG_RAND_091', '최독고', '2026-06-03', 'WAITING', 'PKG_RAND_091'),
('PKG_RAND_092', '조인성', '2026-06-02', 'WAITING', 'PKG_RAND_092'),
('PKG_RAND_093', '이정재', '2026-06-01', 'WAITING', 'PKG_RAND_093'),
('PKG_RAND_094', '이정재', '2026-06-03', 'WAITING', 'PKG_RAND_094'),
('PKG_RAND_095', '장도연', '2026-06-01', 'WAITING', 'PKG_RAND_095'),
('PKG_RAND_096', '신동엽', '2026-06-02', 'WAITING', 'PKG_RAND_096'),
('PKG_RAND_097', '정수민', '2026-06-02', 'WAITING', 'PKG_RAND_097'),
('PKG_RAND_098', '김철수', '2026-06-03', 'WAITING', 'PKG_RAND_098'),
('PKG_RAND_099', '조인성', '2026-06-03', 'WAITING', 'PKG_RAND_099'),
('PKG_RAND_100', '이경규', '2026-06-02', 'WAITING', 'PKG_RAND_100');

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
('PKG_RAND_001', '김태희', '2026-06-01', 'WAITING', 101),
('PKG_RAND_002', '김철수', '2026-06-03', 'WAITING', 102),
('PKG_RAND_003', '이경규', '2026-06-01', 'WAITING', 103),
('PKG_RAND_004', '유재석', '2026-06-01', 'WAITING', 104),
('PKG_RAND_005', '공유', '2026-06-01', 'WAITING', 105),
('PKG_RAND_006', '송혜교', '2026-06-03', 'WAITING', 106),
('PKG_RAND_007', '조인성', '2026-06-02', 'WAITING', 107),
('PKG_RAND_008', '박민수', '2026-06-02', 'WAITING', 108),
('PKG_RAND_009', '김숙', '2026-06-01', 'WAITING', 109),
('PKG_RAND_010', '김철수', '2026-06-01', 'WAITING', 110),
('PKG_RAND_011', '강호동', '2026-06-01', 'WAITING', 111),
('PKG_RAND_012', '아이유', '2026-06-02', 'WAITING', 112),
('PKG_RAND_013', '김철수', '2026-06-02', 'WAITING', 113),
('PKG_RAND_014', '강호동', '2026-06-03', 'WAITING', 114),
('PKG_RAND_015', '김태희', '2026-06-03', 'WAITING', 115),
('PKG_RAND_016', '수지', '2026-06-02', 'WAITING', 116),
('PKG_RAND_017', '유재석', '2026-06-02', 'WAITING', 117),
('PKG_RAND_018', '박보검', '2026-06-01', 'WAITING', 118),
('PKG_RAND_019', '정우성', '2026-06-01', 'WAITING', 119),
('PKG_RAND_020', '이정재', '2026-06-01', 'WAITING', 120),
('PKG_RAND_021', '전지현', '2026-06-02', 'WAITING', 121),
('PKG_RAND_022', '장도연', '2026-06-01', 'WAITING', 122),
('PKG_RAND_023', '홍길동', '2026-06-01', 'WAITING', 123),
('PKG_RAND_024', '이정재', '2026-06-01', 'WAITING', 124),
('PKG_RAND_025', '최독고', '2026-06-01', 'WAITING', 125),
('PKG_RAND_026', '송은이', '2026-06-01', 'WAITING', 126),
('PKG_RAND_027', '박나래', '2026-06-01', 'WAITING', 127),
('PKG_RAND_028', '현빈', '2026-06-01', 'WAITING', 128),
('PKG_RAND_029', '정우성', '2026-06-01', 'WAITING', 129),
('PKG_RAND_030', '공유', '2026-06-02', 'WAITING', 130),
('PKG_RAND_031', '수지', '2026-06-01', 'WAITING', 131),
('PKG_RAND_032', '강동원', '2026-06-02', 'WAITING', 132),
('PKG_RAND_033', '박민수', '2026-06-02', 'WAITING', 133),
('PKG_RAND_034', '신동엽', '2026-06-03', 'WAITING', 134),
('PKG_RAND_035', '현빈', '2026-06-02', 'WAITING', 135),
('PKG_RAND_036', '박보검', '2026-06-01', 'WAITING', 136),
('PKG_RAND_037', '전지현', '2026-06-01', 'WAITING', 137),
('PKG_RAND_038', '이영희', '2026-06-03', 'WAITING', 138),
('PKG_RAND_039', '유재석', '2026-06-03', 'WAITING', 139),
('PKG_RAND_040', '신동엽', '2026-06-01', 'WAITING', 140),
('PKG_RAND_041', '하정우', '2026-06-01', 'WAITING', 141),
('PKG_RAND_042', '하정우', '2026-06-01', 'WAITING', 142),
('PKG_RAND_043', '송은이', '2026-06-01', 'WAITING', 143),
('PKG_RAND_044', '임재범', '2026-06-03', 'WAITING', 144),
('PKG_RAND_045', '황정민', '2026-06-02', 'WAITING', 145),
('PKG_RAND_046', '정수민', '2026-06-02', 'WAITING', 146),
('PKG_RAND_047', '박나래', '2026-06-01', 'WAITING', 147),
('PKG_RAND_048', '송혜교', '2026-06-01', 'WAITING', 148),
('PKG_RAND_049', '전지현', '2026-06-03', 'WAITING', 149),
('PKG_RAND_050', '김태희', '2026-06-01', 'WAITING', 150),
('PKG_RAND_051', '현빈', '2026-06-03', 'WAITING', 151),
('PKG_RAND_052', '정수민', '2026-06-02', 'WAITING', 152),
('PKG_RAND_053', '공유', '2026-06-01', 'WAITING', 153),
('PKG_RAND_054', '정수민', '2026-06-02', 'WAITING', 154),
('PKG_RAND_055', '송은이', '2026-06-01', 'WAITING', 155),
('PKG_RAND_056', '강동원', '2026-06-03', 'WAITING', 156),
('PKG_RAND_057', '전지현', '2026-06-02', 'WAITING', 157),
('PKG_RAND_058', '유재석', '2026-06-03', 'WAITING', 158),
('PKG_RAND_059', '장도연', '2026-06-03', 'WAITING', 159),
('PKG_RAND_060', '이정재', '2026-06-01', 'WAITING', 160),
('PKG_RAND_061', '유재석', '2026-06-01', 'WAITING', 161),
('PKG_RAND_062', '정우성', '2026-06-01', 'WAITING', 162),
('PKG_RAND_063', '송은이', '2026-06-01', 'WAITING', 163),
('PKG_RAND_064', '박민수', '2026-06-01', 'WAITING', 164),
('PKG_RAND_065', '강동원', '2026-06-02', 'WAITING', 165),
('PKG_RAND_066', '조인성', '2026-06-03', 'WAITING', 166),
('PKG_RAND_067', '장도연', '2026-06-01', 'WAITING', 167),
('PKG_RAND_068', '김태희', '2026-06-02', 'WAITING', 168),
('PKG_RAND_069', '송은이', '2026-06-03', 'WAITING', 169),
('PKG_RAND_070', '임재범', '2026-06-01', 'WAITING', 170),
('PKG_RAND_071', '이경규', '2026-06-01', 'WAITING', 171),
('PKG_RAND_072', '유재석', '2026-06-03', 'WAITING', 172),
('PKG_RAND_073', '수지', '2026-06-02', 'WAITING', 173),
('PKG_RAND_074', '이경규', '2026-06-03', 'WAITING', 174),
('PKG_RAND_075', '박보검', '2026-06-02', 'WAITING', 175),
('PKG_RAND_076', '조인성', '2026-06-02', 'WAITING', 176),
('PKG_RAND_077', '송은이', '2026-06-02', 'WAITING', 177),
('PKG_RAND_078', '유재석', '2026-06-01', 'WAITING', 178),
('PKG_RAND_079', '아이유', '2026-06-02', 'WAITING', 179),
('PKG_RAND_080', '박민수', '2026-06-03', 'WAITING', 180),
('PKG_RAND_081', '이영희', '2026-06-01', 'WAITING', 181),
('PKG_RAND_082', '홍길동', '2026-06-03', 'WAITING', 182),
('PKG_RAND_083', '정수민', '2026-06-03', 'WAITING', 183),
('PKG_RAND_084', '김숙', '2026-06-02', 'WAITING', 184),
('PKG_RAND_085', '박민수', '2026-06-02', 'WAITING', 185),
('PKG_RAND_086', '송은이', '2026-06-02', 'WAITING', 186),
('PKG_RAND_087', '임재범', '2026-06-02', 'WAITING', 187),
('PKG_RAND_088', '이경규', '2026-06-02', 'WAITING', 188),
('PKG_RAND_089', '하정우', '2026-06-01', 'WAITING', 189),
('PKG_RAND_090', '송혜교', '2026-06-03', 'WAITING', 190),
('PKG_RAND_091', '최독고', '2026-06-03', 'WAITING', 191),
('PKG_RAND_092', '조인성', '2026-06-02', 'WAITING', 192),
('PKG_RAND_093', '이정재', '2026-06-01', 'WAITING', 193),
('PKG_RAND_094', '이정재', '2026-06-03', 'WAITING', 194),
('PKG_RAND_095', '장도연', '2026-06-01', 'WAITING', 195),
('PKG_RAND_096', '신동엽', '2026-06-02', 'WAITING', 196),
('PKG_RAND_097', '정수민', '2026-06-02', 'WAITING', 197),
('PKG_RAND_098', '김철수', '2026-06-03', 'WAITING', 198),
('PKG_RAND_099', '조인성', '2026-06-03', 'WAITING', 199),
('PKG_RAND_100', '이경규', '2026-06-02', 'WAITING', 200);

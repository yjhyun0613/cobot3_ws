#!/usr/bin/env python3
import os
import psycopg2

def generate_layout_nodes():
    xs = [-6.0, -4.5, -3.0, -1.5, 0.0, 1.5, 3.0, 4.5, 6.0, 7.5, 9.0]
    ys = [9.0, 7.5, 6.0, 4.5, 3.0, 1.5, 0.0, -1.5, -3.0, -4.5, -6.0, -7.5, -9.0]
    
    # Define logical spot locations (x, y) -> (name, type, desc, logical_y)
    spots = {}
    
    # 1. Main Warehouse Spots (spot_01 ~ spot_10)
    # y_coord in database:
    # spot_01/02 -> -9.0 (logical Y=3.0)
    # spot_03/04 -> -6.0 (logical Y=0.0)
    # spot_05/06 -> -3.0 (logical Y=-3.0)
    # spot_07/08 -> 0.0  (logical Y=-6.0)
    # spot_09/10 -> 3.0  (logical Y=-9.0)
    spots[(-1.5, -9.0)] = ('spot_01', 'PARKING_SPOT', '메인 창고 1행 1열', -9.0)
    spots[(-3.0, -9.0)] = ('spot_02', 'PARKING_SPOT', '메인 창고 1행 2열', -9.0)
    spots[(-1.5, -6.0)] = ('spot_03', 'PARKING_SPOT', '메인 창고 2행 1열', -6.0)
    spots[(-3.0, -6.0)] = ('spot_04', 'PARKING_SPOT', '메인 창고 2행 2열', -6.0)
    spots[(-1.5, -3.0)] = ('spot_05', 'PARKING_SPOT', '메인 창고 3행 1열', -3.0)
    spots[(-3.0, -3.0)] = ('spot_06', 'PARKING_SPOT', '메인 창고 3행 2열', -3.0)
    spots[(-1.5, 0.0)]  = ('spot_07', 'PARKING_SPOT', '메인 창고 4행 1열', 0.0)
    spots[(-3.0, 0.0)]  = ('spot_08', 'PARKING_SPOT', '메인 창고 4행 2열', 0.0)
    spots[(-1.5, 3.0)]  = ('spot_09', 'PARKING_SPOT', '메인 창고 5행 1열', 3.0)
    spots[(-3.0, 3.0)]  = ('spot_10', 'PARKING_SPOT', '메인 창고 5행 2열', 3.0)
    
    # 2. Charging Spots (charging_01 ~ charging_05)
    spots[(-6.0, -9.0)] = ('charging_01', 'CHARGING_SPOT', 'AMR 충전기 스팟 1', -9.0)
    spots[(-6.0, -7.5)] = ('charging_02', 'CHARGING_SPOT', 'AMR 충전기 스팟 2', -7.5)
    spots[(-6.0, -6.0)] = ('charging_03', 'CHARGING_SPOT', 'AMR 충전기 스팟 3', -6.0)
    spots[(-6.0, -4.5)] = ('charging_04', 'CHARGING_SPOT', 'AMR 충전기 스팟 4', -4.5)
    spots[(-6.0, -3.0)] = ('charging_05', 'CHARGING_SPOT', 'AMR 충전기 스팟 5', -3.0)
    
    # 3. Inbound Lines (sg2_in_01 ~ sg2_in_03 A/B)
    spots[(7.5, 1.5)]  = ('sg2_in_01_A', 'LOADING_SPOT', '1번 입고라인 Active 버퍼 (오늘)', 1.5)
    spots[(6.0, 1.5)]  = ('sg2_in_01_B', 'LOADING_SPOT', '1번 입고라인 Standby 버퍼 (오늘)', 1.5)
    spots[(7.5, -3.0)] = ('sg2_in_02_A', 'LOADING_SPOT', '2번 입고라인 Active 버퍼 (내일)', -3.0)
    spots[(6.0, -3.0)] = ('sg2_in_02_B', 'LOADING_SPOT', '2번 입고라인 Standby 버퍼 (내일)', -3.0)
    spots[(7.5, -7.5)] = ('sg2_in_03_A', 'LOADING_SPOT', '3번 입고라인 Active 버퍼 (모레)', -7.5)
    spots[(6.0, -7.5)] = ('sg2_in_03_B', 'LOADING_SPOT', '3번 입고라인 Standby 버퍼 (모레)', -7.5)
    
    # 4. Staging Spots (stage_01 ~ stage_04)
    spots[(4.5, 9.0)] = ('stage_01', 'STAGING_SPOT', '출고 대기 창고 스팟 1', 9.0)
    spots[(4.5, 7.5)] = ('stage_02', 'STAGING_SPOT', '출고 대기 창고 스팟 2', 7.5)
    spots[(7.5, 9.0)] = ('stage_03', 'STAGING_SPOT', '출고 대기 창고 스팟 3', 9.0)
    spots[(7.5, 7.5)] = ('stage_04', 'STAGING_SPOT', '출고 대기 창고 스팟 4', 7.5)
    
    # 5. Outbound Spots (sg2_out_00_A/B)
    spots[(-4.5, 9.0)] = ('sg2_out_00_A', 'PACKAGING_SPOT', '출고 포장 A라인 Active 버퍼', 9.0)
    spots[(-4.5, 7.5)] = ('sg2_out_00_B', 'PACKAGING_SPOT', '출고 포장 B라인 Standby 버퍼', 7.5)
    
    # Static Obstacles definitions
    conveyor_x = 9.0
    sg2_out_robot_zone = {(-6.0, 9.0), (-6.0, 7.5)}
    sg2_in_1_zone = {(6.0, 3.0), (7.5, 3.0)}
    sg2_in_2_zone = {(6.0, -1.5), (7.5, -1.5)}
    sg2_in_3_zone = {(6.0, -6.0), (7.5, -6.0)}
    
    nodes = []
    
    for y in ys:
        for x in xs:
            # Check if this cell is a logical spot
            if (x, y) in spots:
                name, typ, desc, logical_y = spots[(x, y)]
                qr_id = f"FLOOR_X_{x:.1f}_Y_{logical_y:.1f}"
                # Clean up .0 suffix for integers
                qr_id = qr_id.replace('.0_Y_', '_Y_').replace('.0', '')
                nodes.append((qr_id, x, y, name, typ, desc))
            elif x == conveyor_x:
                qr_id = f"FLOOR_X_{x:.1f}_Y_{y:.1f}".replace('.0_Y_', '_Y_').replace('.0', '')
                nodes.append((qr_id, x, y, None, 'STATIC_OBSTACLE', '컨베이어 벨트'))
            elif (x, y) in sg2_out_robot_zone:
                qr_id = f"FLOOR_X_{x:.1f}_Y_{y:.1f}".replace('.0_Y_', '_Y_').replace('.0', '')
                nodes.append((qr_id, x, y, None, 'STATIC_OBSTACLE', 'SG2_OUT 포장 로봇 영역'))
            elif (x, y) in sg2_in_1_zone:
                qr_id = f"FLOOR_X_{x:.1f}_Y_{y:.1f}".replace('.0_Y_', '_Y_').replace('.0', '')
                nodes.append((qr_id, x, y, None, 'STATIC_OBSTACLE', 'SG2_IN_1 입고 로봇 영역'))
            elif (x, y) in sg2_in_2_zone:
                qr_id = f"FLOOR_X_{x:.1f}_Y_{y:.1f}".replace('.0_Y_', '_Y_').replace('.0', '')
                nodes.append((qr_id, x, y, None, 'STATIC_OBSTACLE', 'SG2_IN_2 입고 로봇 영역'))
            elif (x, y) in sg2_in_3_zone:
                qr_id = f"FLOOR_X_{x:.1f}_Y_{y:.1f}".replace('.0_Y_', '_Y_').replace('.0', '')
                nodes.append((qr_id, x, y, None, 'STATIC_OBSTACLE', 'SG2_IN_3 입고 로봇 영역'))
            else:
                qr_id = f"FLOOR_X_{x:.1f}_Y_{y:.1f}".replace('.0_Y_', '_Y_').replace('.0', '')
                nodes.append((qr_id, x, y, None, 'PATHWAY', None))
                
    return nodes

def update_init_sql(nodes):
    init_sql_path = "docker/init.sql"
    if not os.path.exists(init_sql_path):
        print("docker/init.sql not found!")
        return
        
    with open(init_sql_path, 'r') as f:
        content = f.read()
        
    # Find start and end of floor_qr_map inserts
    # It starts around: -- 8. 바닥 QR 격자 맵 시드 데이터 (floor_qr_map)
    header_idx = content.find("-- 8. 바닥 QR 격자 맵 시드 데이터")
    if header_idx == -1:
        print("Header comment not found in init.sql")
        return
        
    # We will rewrite from "-- 8. 바닥 QR 격자 맵 시드 데이터 (floor_qr_map)" to the end (excluding CSV upload/packages data)
    # Let's find the start of the INSERT statement
    insert_start = content.find("INSERT INTO floor_qr_map", header_idx)
    if insert_start == -1:
        print("INSERT INTO floor_qr_map statement not found")
        return
        
    # Format the insert statement
    sql_inserts = "INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, location_name, location_type, description) VALUES\n"
    value_lines = []
    for node in nodes:
        qr_id, x, y, name, typ, desc = node
        name_str = f"'{name}'" if name else "NULL"
        desc_str = f"'{desc}'" if desc else "NULL"
        value_lines.append(f"('{qr_id}', {x:5.1f}, {y:5.1f}, {name_str:15s}, '{typ:15s}', {desc_str})")
        
    sql_inserts += ",\n".join(value_lines) + ";\n"
    
    # We will replace from insert_start to the end of the SQL file or before packages data
    packages_start = content.find("-- 9. 초기 패키지 데이터", insert_start)
    if packages_start == -1:
        # Just replace to the end
        new_content = content[:insert_start] + sql_inserts
    else:
        new_content = content[:insert_start] + sql_inserts + "\n" + content[packages_start:]
        
    with open(init_sql_path, 'w') as f:
        f.write(new_content)
    print("docker/init.sql updated successfully!")

def update_active_db(nodes):
    pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
    try:
        conn = psycopg2.connect(
            host=pg_host,
            database="warehouse_db",
            user="rokey",
            password="rokey_pass",
            port=5432
        )
        conn.autocommit = True
        with conn.cursor() as cursor:
            # Delete old floor_qr_map entries
            cursor.execute("TRUNCATE TABLE floor_qr_map CASCADE;")
            
            # Insert new ones
            for node in nodes:
                qr_id, x, y, name, typ, desc = node
                cursor.execute(
                    "INSERT INTO floor_qr_map (qr_id, x_coord, y_coord, location_name, location_type, description) VALUES (%s, %s, %s, %s, %s, %s);",
                    (qr_id, x, y, name, typ, desc)
                )
            print("PostgreSQL active database floor_qr_map table updated successfully!")
        conn.close()
    except Exception as e:
        print(f"Error updating active DB: {e}")

def main():
    nodes = generate_layout_nodes()
    print(f"Generated {len(nodes)} floor nodes.")
    update_init_sql(nodes)
    update_active_db(nodes)

if __name__ == "__main__":
    main()

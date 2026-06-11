import psycopg2

def main():
    import os
    pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
    try:
        # Connect to DB
        conn = psycopg2.connect(
            host=pg_host,
            database="warehouse_db",
            user="rokey",
            password="rokey_pass",
            port=5432
        )
        conn.autocommit = True
        
        with conn.cursor() as cursor:
            print("1. Querying current workstation locations...")
            cursor.execute("SELECT workstation_id, current_location FROM workstations;")
            workstations = cursor.fetchall()
            
            # Map location -> workstation
            occupancy = {}
            for ws_id, cur_loc in workstations:
                if cur_loc:
                    occupancy[cur_loc.lower()] = ws_id
            
            print(f"Current occupancy mapping: {occupancy}")
            
            print("2. Re-creating warehouse_locations table content...")
            # We want to clear the old table completely
            cursor.execute("TRUNCATE TABLE warehouse_locations CASCADE;")
            
            # Insert spot_01 ~ spot_12
            for i in range(1, 13):
                spot_id = f"spot_{i:02d}"
                occupied_by = occupancy.get(spot_id, None)
                status = "OCCUPIED" if occupied_by else "EMPTY"
                cursor.execute(
                    "INSERT INTO warehouse_locations (spot_id, workstation_id, status) VALUES (%s, %s, %s);",
                    (spot_id, occupied_by, status)
                )
                
            # Insert stage_01 ~ stage_06
            for i in range(1, 7):
                stage_id = f"stage_{i:02d}"
                occupied_by = occupancy.get(stage_id, None)
                status = "OCCUPIED" if occupied_by else "EMPTY"
                cursor.execute(
                    "INSERT INTO warehouse_locations (spot_id, workstation_id, status) VALUES (%s, %s, %s);",
                    (stage_id, occupied_by, status)
                )
                
            print("Successfully migrated warehouse_locations to 12 spots and 6 staging areas!")
            
            # Verify
            cursor.execute("SELECT COUNT(*) FROM warehouse_locations;")
            count = cursor.fetchone()[0]
            print(f"Total entries in warehouse_locations: {count}")
            
        conn.close()
    except Exception as e:
        print(f"Error during migration: {e}")

if __name__ == "__main__":
    main()

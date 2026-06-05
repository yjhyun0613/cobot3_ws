import psycopg2

def get_db_connections():
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="warehouse_db",
            user="rokey",
            password="rokey_pass",
            port=5432
        )
        return conn
    except Exception as e:
        print("Db connection failed:", e)
        return None

def main():
    conn = get_db_connections()
    if not conn:
        return
    with conn.cursor() as cursor:
        print("=== Packages Status Count ===")
        cursor.execute("SELECT status, count(*) FROM packages GROUP BY status;")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")

        print("=== Workstations Location ===")
        cursor.execute("SELECT workstation_id, current_location, status FROM workstations ORDER BY workstation_id;")
        for row in cursor.fetchall():
            print(f"  {row[0]}: location={row[1]}, status={row[2]}")

        print("=== Warehouse Spots Status ===")
        cursor.execute("SELECT spot_id, workstation_id, status FROM warehouse_locations ORDER BY spot_id;")
        for row in cursor.fetchall():
            if row[2] == 'OCCUPIED':
                print(f"  {row[0]}: occupied by {row[1]}")
    conn.close()

if __name__ == "__main__":
    main()

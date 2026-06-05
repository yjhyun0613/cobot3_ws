import urllib.request
import urllib.parse
import json
import os

def call_api(endpoint, data=None, is_json=True, method='POST'):
    url = f"http://localhost:8000{endpoint}"
    req = urllib.request.Request(url, method=method)
    if data:
        if is_json:
            req.add_header('Content-Type', 'application/json')
            req.data = json.dumps(data).encode('utf-8')
        else:
            req.add_header('Content-Type', 'text/plain; charset=utf-8')
            req.data = data.encode('utf-8')
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception as e:
        print(f"Error calling {endpoint}: {e}")
        return None

def main():
    print("1. Resetting database...")
    res = call_api("/api/reset", method='POST')
    print("Reset response:", res)

    print("2. Uploading test packages...")
    csv_path = "/home/rokey/cobot3_ws/scratch/large_test_packages.csv"
    if not os.path.exists(csv_path):
        print("large_test_packages.csv not found, generating first...")
        # Fallback to test_packages.csv or run generator inline
        import csv
        import random
        dates = ["2026-06-01", "2026-06-02", "2026-06-03"]
        first_names = ["민준", "서준", "도윤", "예준", "시우"]
        last_names = ["김", "이", "박", "최"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["package_id", "customer_name", "route_zone", "qr_id"])
            for i in range(1, 101):
                writer.writerow([f"PKG_TEST_{i:03d}", f"{random.choice(last_names)}{random.choice(first_names)}", random.choice(dates), f"QR_TEST_{i:03d}"])
    
    with open(csv_path, "r", encoding="utf-8") as f:
        csv_content = f.read()
    
    res = call_api("/api/upload_packages", data=csv_content, is_json=False, method='POST')
    print("Upload response:", res)

    print("3. Triggering simulation inbound...")
    res = call_api("/api/simulate", method='POST')
    print("Simulate response:", res)

if __name__ == "__main__":
    main()

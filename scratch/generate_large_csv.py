import csv
import random

# List of common Korean names to generate realistic customer names
first_names = ["민준", "서준", "도윤", "예준", "시우", "하준", "주원", "지호", "지후", "준우", "서연", "서현", "민서", "하은", "지우", "지민", "윤서", "채원", "수아", "다은"]
last_names = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신", "권", "황", "안", "송", "전", "홍"]

# Target dates (representing Today, Tomorrow, Day After Tomorrow)
dates = ["2026-06-01", "2026-06-02", "2026-06-03"]

output_file = "/home/rokey/cobot3_ws/scratch/large_test_packages.csv"
num_records = 150  # Generate 150 packages

with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    # Header
    writer.writerow(["package_id", "customer_name", "route_zone", "qr_id"])
    
    for i in range(1, num_records + 1):
        package_id = f"PKG_LARGE_{i:03d}"
        customer_name = f"{random.choice(last_names)}{random.choice(first_names)}"
        route_zone = random.choice(dates)
        qr_id = f"QR_LARGE_{i:03d}"
        writer.writerow([package_id, customer_name, route_zone, qr_id])

print(f"Successfully generated {num_records} packages in {output_file}")

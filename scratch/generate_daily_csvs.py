import csv
import random
from datetime import datetime, timedelta

# List of common Korean names
first_names = ["민준", "서준", "도윤", "예준", "시우", "하준", "주원", "지호", "지후", "준우", "서연", "서현", "민서", "하은", "지우", "지민", "윤서", "채원", "수아", "다은"]
last_names = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신", "권", "황", "안", "송", "전", "홍"]

def main():
    random.seed(12345) # Seed for reproducibility
    start_date = datetime(2026, 6, 6)
    
    # Generate CSV files from June 6th to June 12th (7 days)
    for day_offset in range(7):
        current_date = start_date + timedelta(days=day_offset)
        date_str = current_date.strftime("%Y-%m-%d")
        date_id_str = current_date.strftime("%Y%m%d")
        
        output_file = f"/home/yoon/cobot3_ws/scratch/packages_{date_str}.csv"
        
        # Exactly 20 packages per daily file
        num_records = 20
        
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Header
            writer.writerow(["package_id", "customer_name", "route_zone", "qr_id"])
            
            for i in range(1, num_records + 1):
                package_id = f"PKG_{date_id_str}_{i:03d}"
                customer_name = f"{random.choice(last_names)}{random.choice(first_names)}"
                
                # Randomly assign route_zone to today, tomorrow, or day after tomorrow
                # Today: 50%, Tomorrow: 30%, Day after tomorrow: 20%
                rand_val = random.random()
                if rand_val < 0.5:
                    pkg_offset = 0
                elif rand_val < 0.8:
                    pkg_offset = 1
                else:
                    pkg_offset = 2
                    
                target_date = current_date + timedelta(days=pkg_offset)
                route_zone = target_date.strftime("%Y-%m-%d")
                qr_id = f"QR_{date_id_str}_{i:03d}"
                writer.writerow([package_id, customer_name, route_zone, qr_id])
                
        print(f"Generated {num_records} packages in {output_file}")

if __name__ == "__main__":
    main()

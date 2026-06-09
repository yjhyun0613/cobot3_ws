#!/usr/bin/env python3
import os
import csv
import qrcode

def main():
    scratch_dir = "/home/rokey/cobot3_ws/scratch"
    qr_codes_dir = os.path.join(scratch_dir, "qr_codes")
    os.makedirs(qr_codes_dir, exist_ok=True)

    csv_filenames = [
        "packages_2026-06-06.csv",
        "packages_2026-06-07.csv",
        "packages_2026-06-08.csv",
        "packages_2026-06-09.csv",
        "packages_2026-06-10.csv",
        "packages_2026-06-11.csv",
        "packages_2026-06-12.csv"
    ]

    active_qr_ids = set()

    # 1. CSV 파일들 읽어서 active_qr_id 수집
    for csv_file in csv_filenames:
        csv_path = os.path.join(scratch_dir, csv_file)
        if not os.path.exists(csv_path):
            print(f"[Warning] CSV file not found: {csv_path}")
            continue

        print(f"Reading: {csv_file}")
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # qr_id 필드가 있으면 사용하고, 없으면 package_id 사용
                qr_id = row.get("qr_id", row.get("package_id"))
                if qr_id:
                    qr_id = qr_id.strip()
                    if qr_id:
                        active_qr_ids.add(qr_id)

    print(f"Total active QR IDs identified: {len(active_qr_ids)}")

    # 2. QR 코드 이미지 생성
    generated_count = 0
    for qr_id in active_qr_ids:
        filename = f"{qr_id}.png"
        path = os.path.join(qr_codes_dir, filename)
        
        # 중복 생성 방지를 위한 조건 (없거나 다시 갱신)
        # 덮어쓰기 방식으로 생성
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_id)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(path)
        generated_count += 1

    print(f"Successfully generated/updated {generated_count} QR codes.")

    # 3. 안 쓰는 QR 코드 이미지 파일 삭제
    deleted_count = 0
    for file in os.listdir(qr_codes_dir):
        if file.endswith(".png"):
            qr_id = os.path.splitext(file)[0]
            if qr_id not in active_qr_ids:
                file_path = os.path.join(qr_codes_dir, file)
                try:
                    os.remove(file_path)
                    print(f"Deleted unused QR: {file}")
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete {file}: {e}")

    print(f"Deleted {deleted_count} unused QR code files.")
    print("Sync complete!")

if __name__ == "__main__":
    main()

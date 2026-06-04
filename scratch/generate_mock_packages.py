import random

names = [
    '김철수', '이영희', '박민수', '최독고', '홍길동', '정수민', '강호동', '유재석', '이경규', '신동엽',
    '장도연', '박나래', '송은이', '김숙', '임재범', '조용필', '아이유', '수지', '박보검', '현빈',
    '김태희', '송혜교', '전지현', '공유', '이정재', '정우성', '황정민', '하정우', '조인성', '강동원'
]

dates = ['2026-06-01', '2026-06-02', '2026-06-03']
# 분포: 2026-06-01 (45%), 2026-06-02 (35%), 2026-06-03 (20%)
date_pool = ['2026-06-01'] * 45 + ['2026-06-02'] * 35 + ['2026-06-03'] * 20
random.seed(42) # 재현성을 위해 시드 고정

lines = []
for i in range(1, 101):
    pkg_id = f"PKG_RAND_{i:03d}"
    customer = random.choice(names)
    route_zone = random.choice(date_pool)
    qr_id = f"QR_PKG_{i:03d}"
    lines.append(f"('{pkg_id}', '{customer}', '{route_zone}', 'WAITING', '{qr_id}')")

sql_insert = "INSERT INTO packages (package_id, customer_name, route_zone, status, qr_id) VALUES\n" + ",\n".join(lines) + ";"
print(sql_insert)

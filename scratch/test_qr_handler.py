#!/usr/bin/env python3
import sys
import os

# 스크립트 실행 위치가 scratch여도 최상위 경로를 모듈 경로에 포함하도록 함
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scratch.qr_handler import generate_qr_code, decode_qr_code

def main():
    print("=== QR코드 핸들러(QR Handler) 테스트 시작 ===")
    
    test_packages = [
        "PKG_RAND_001",
        "PKG_RAND_042",
        "PKG_RAND_099",
        "PKG_SPECIAL_TEST_123"
    ]
    
    for pkg in test_packages:
        print(f"\n[테스트] 패키지 ID: {pkg}")
        
        # 1. QR코드 생성
        img_path = generate_qr_code(pkg)
        print(f"  └─ QR코드 생성 완료: {img_path}")
        
        # 2. QR코드 디코딩
        decoded_val = decode_qr_code(img_path)
        print(f"  └─ QR코드 디코딩 완료: {decoded_val}")
        
        if pkg == decoded_val:
            print("  └─ [성공] 원본과 디코딩된 값이 일치합니다! (OK)")
        else:
            print("  └─ [실패] 원본과 디코딩된 값이 다릅니다! (FAIL)")
            
    print("\n=== QR코드 핸들러 테스트 성공 완료 ===")

if __name__ == "__main__":
    main()

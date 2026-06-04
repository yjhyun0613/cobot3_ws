#!/usr/bin/env python3
import os
import qrcode
import cv2

def generate_qr_code(package_id, output_dir="scratch/qr_codes"):
    """
    택배 고유 ID(package_id)를 담고 있는 QR코드 이미지를 생성하여 지정된 디렉토리에 저장합니다.
    """
    os.makedirs(output_dir, exist_ok=True)
    img_path = os.path.join(output_dir, f"{package_id}.png")
    
    # QR코드 생성기 인스턴스 생성
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(package_id)
    qr.make(fit=True)
    
    # 이미지 생성 및 저장 (Pillow 활용)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(img_path)
    return img_path

import zxingcpp

def decode_qr_code(frame_or_path):
    """
    zxingcpp 라이브러리를 활용하여 이미지 파일 경로 또는 cv2 이미지 프레임으로부터 QR코드를 디코딩합니다.
    해독된 package_id 문자열을 반환하며, 실패 시 None을 반환합니다.
    """
    if isinstance(frame_or_path, str):
        # 파일 경로가 들어온 경우 이미지 로드
        if not os.path.exists(frame_or_path):
            return None
        frame = cv2.imread(frame_or_path)
        if frame is None:
            return None
    else:
        frame = frame_or_path
        
    # zxingcpp를 사용하여 바코드/QR코드 검출 및 디코딩
    results = zxingcpp.read_barcodes(frame)
    for barcode in results:
        # QR코드 포맷 필터링 (선택 사항이나 보통 안정성을 위해 데이터 유무만 확인)
        if barcode.text:
            return barcode.text
            
    return None


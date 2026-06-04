#!/usr/bin/env python3
import os
import cv2

def generate_aruco_marker(marker_id, output_path, size=400):
    """
    DICT_6X6_250 사전(Dictionary)을 사용하여 특정 ID의 ArUco 마커 이미지를 생성하고 저장합니다.
    """
    # 6x6 해상도, 250개 ID를 지원하는 standard ArUco 딕셔너리 사용
    dictionary = cv2.aruco.Dictionary_get(cv2.aruco.DICT_6X6_250)
    
    # 마커 그리기 (픽셀 크기 설정, 테두리 여백 포함)
    marker_img = cv2.aruco.drawMarker(dictionary, marker_id, size)
    
    # 파일로 저장
    cv2.imwrite(output_path, marker_img)

def main():
    print("=== 고정 인프라용 ArUco 마커 이미지 생성 시작 ===")
    
    output_dir = "scratch/aruco_markers"
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. 로봇 매핑 데이터 (ID: 1 ~ 5)
    robots = [
        {"name": "robot_bg2", "id": 1},
        {"name": "robot_sg2_in_01", "id": 2},
        {"name": "robot_sg2_in_02", "id": 3},
        {"name": "robot_sg2_in_03", "id": 4},
        {"name": "robot_sg2_out_00", "id": 5},
    ]
    
    print("\n[1] 로봇용 영구 ArUco 마커 생성 중...")
    for robot in robots:
        filename = f"{robot['name']}_id{robot['id']:02d}.png"
        filepath = os.path.join(output_dir, filename)
        generate_aruco_marker(robot['id'], filepath)
        print(f"  └─ 생성 완료: {filepath} (ArUco ID: {robot['id']})")
        
    # 2. 작업대 매핑 데이터 (ID: 11 ~ 20)
    print("\n[2] 작업대(Workstation)용 영구 ArUco 마커 생성 중...")
    for i in range(1, 11):
        ws_name = f"WS{i:02d}"
        ws_id = 10 + i
        filename = f"workstation_{ws_name}_id{ws_id}.png"
        filepath = os.path.join(output_dir, filename)
        generate_aruco_marker(ws_id, filepath)
        print(f"  └─ 생성 완료: {filepath} (ArUco ID: {ws_id})")
        
    print(f"\n=== ArUco 마커 생성 완료! 저장 경로: {output_dir} ===")

if __name__ == "__main__":
    main()

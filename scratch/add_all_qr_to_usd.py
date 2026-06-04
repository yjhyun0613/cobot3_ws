#!/usr/bin/env python3
import os
import sys
import yaml
import cv2

# Start Isaac Sim headless
from omni.isaac.kit import SimulationApp
sim = SimulationApp({"headless": True})

import omni.usd
from pxr import Usd, UsdGeom, Sdf, Gf, UsdShade

def load_map_info(yaml_path):
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    resolution = data['resolution']
    origin = data['origin']
    img_filename = data['image']
    img_path = os.path.join(os.path.dirname(yaml_path), img_filename)
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Could not load map image at {img_path}")
    height, width = img.shape[:2]
    return {
        "resolution": resolution,
        "origin_x": origin[0],
        "origin_y": origin[1],
        "width_px": width,
        "height_px": height,
        "width_m": width * resolution,
        "height_m": height * resolution
    }

def create_plane_mesh(stage, prim_path, size=0.3):
    """
    지정한 경로에 1개의 flat quad mesh (plane)를 직접 정의하여 생성합니다.
    """
    mesh = UsdGeom.Mesh.Define(stage, Sdf.Path(prim_path))
    
    # Z축 기준 0.005m(5mm) 띄운 상태로 바닥면 평면 구성
    w = size / 2.0
    points = [
        Gf.Vec3f(-w, -w, 0.0),
        Gf.Vec3f(w, -w, 0.0),
        Gf.Vec3f(w, w, 0.0),
        Gf.Vec3f(-w, w, 0.0)
    ]
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    
    # UV 좌표 (st) 바인딩
    primvar_api = UsdGeom.PrimvarsAPI(mesh.GetPrim())
    tex_coords = primvar_api.CreatePrimvar("st", Sdf.ValueTypeNames.Float2Array, UsdGeom.Tokens.varying)

    tex_coords.Set([
        Gf.Vec2f(0.0, 0.0),
        Gf.Vec2f(1.0, 0.0),
        Gf.Vec2f(1.0, 1.0),
        Gf.Vec2f(0.0, 1.0)
    ])
    
    return mesh

def create_textured_material(stage, material_path, texture_file_path):
    """
    UsdPreviewSurface 규격을 사용하여 텍스처가 적용된 standard PBR 재질을 생성합니다.
    """
    # Material 생성
    material = UsdShade.Material.Define(stage, Sdf.Path(material_path))
    
    # PBR Shader 생성
    pbr_shader = UsdShade.Shader.Define(stage, Sdf.Path(f"{material_path}/PBRShader"))
    pbr_shader.CreateIdAttr("UsdPreviewSurface")
    material.CreateSurfaceOutput().ConnectToSource(pbr_shader.ConnectableAPI(), "surface")
    
    # Texture Shader 생성
    texture_shader = UsdShade.Shader.Define(stage, Sdf.Path(f"{material_path}/diffuseTexture"))
    texture_shader.CreateIdAttr("UsdUVTexture")
    texture_shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(texture_file_path)
    
    # Connect texture output to PBR input
    texture_shader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    pbr_shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture_shader.ConnectableAPI(), "rgb"
    )
    
    # UV Reader (stReader) 생성
    st_reader = UsdShade.Shader.Define(stage, Sdf.Path(f"{material_path}/stReader"))
    st_reader.CreateIdAttr("UsdPrimvarReader_float2")
    st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    st_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    
    texture_shader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
        st_reader.ConnectableAPI(), "result"
    )
    
    return material

def main():
    print("=== USD 바닥 QR코드 생성 스크립트 실행 ===")
    yaml_path = "/home/rokey/cobot3_ws/src/cobot3/resource/map/warehouse.yaml"
    usd_path = "/home/rokey/cobot3_ws/src/cobot3/resource/map.usd"
    
    # 1. 맵 데이터 로드
    try:
        map_info = load_map_info(yaml_path)
    except Exception as e:
        print(f"맵 정보 로드 실패: {e}")
        sim.close()
        return

    # 2. USD Stage 로드
    usd_context = omni.usd.get_context()
    opened = usd_context.open_stage(usd_path)
    if not opened:
        print(f"USD 파일을 열 수 없습니다: {usd_path}")
        sim.close()
        return
        
    stage = usd_context.get_stage()
    print(f"성공적으로 USD 스테이지를 열었습니다: {usd_path}")

    # 기존 테스트용 임시 프리미티브 청소
    if stage.GetPrimAtPath("/World/TestPlane"):
        stage.RemovePrim("/World/TestPlane")
    if stage.GetPrimAtPath("/World/Looks/TestMaterial"):
        stage.RemovePrim("/World/Looks/TestMaterial")

    # 기존 바닥 QR코드 그룹 청소 (Idempotency 보장)
    floor_qrs_root = "/World/FloorQRs"
    if stage.GetPrimAtPath(floor_qrs_root):
        print(f"기존에 존재하는 {floor_qrs_root} 프리미티브를 제거하고 새로 구성합니다.")
        stage.RemovePrim(floor_qrs_root)
        
    # 새로운 FloorQRs root xform 정의
    UsdGeom.Xform.Define(stage, Sdf.Path(floor_qrs_root))

    # 3. 격자 좌표 연산
    margin = 2.0
    spacing = 1.5
    
    x_start = map_info['origin_x'] + margin
    y_start = map_info['origin_y'] + margin
    x_end = map_info['origin_x'] + map_info['width_m'] - margin
    y_end = map_info['origin_y'] + map_info['height_m'] - margin

    x_coords = []
    x = x_start
    while x <= x_end:
        x_coords.append(round(x, 3))
        x += spacing

    y_coords = []
    y = y_start
    while y <= y_end:
        y_coords.append(round(y, 3))
        y += spacing

    print(f"바닥 격자 구성 정보:")
    print(f"  - X 범위: {x_coords[0]} ~ {x_coords[-1]} (총 {len(x_coords)}개)")
    print(f"  - Y 범위: {y_coords[0]} ~ {y_coords[-1]} (총 {len(y_coords)}개)")
    print(f"  - 총 QR 마커 개수: {len(x_coords) * len(y_coords)}개")

    # 4. 루프를 돌며 각 좌표에 mesh와 material 생성 및 연결
    count = 0
    total = len(x_coords) * len(y_coords)
    
    # 텍스처 폴더 경로
    texture_dir = "/home/rokey/cobot3_ws/scratch/qr_assets/floor"
    
    # UsdEdit 시작
    for col_idx, xc in enumerate(x_coords):
        for row_idx, yc in enumerate(y_coords):
            # 경로 이름 지정 (USD 경로 규칙 상 특수문자는 언더바로 치환)
            xc_str = str(xc).replace('.', '_').replace('-', 'm')
            yc_str = str(yc).replace('.', '_').replace('-', 'm')
            
            prim_name = f"QR_c{col_idx}_r{row_idx}"
            mesh_path = f"{floor_qrs_root}/{prim_name}"
            material_path = f"/World/Looks/Material_c{col_idx}_r{row_idx}"
            
            # QR 이미지 파일명 구성
            qr_filename = f"FLOOR_X_{xc}_Y_{yc}.png"
            qr_filepath = os.path.join(texture_dir, qr_filename)
            
            # 이미지 파일이 실제로 디스크에 존재하는지 검사
            if not os.path.exists(qr_filepath):
                # 존재하지 않으면 건너뛰거나 기본 생성
                continue
                
            # 1) Mesh 생성
            mesh = create_plane_mesh(stage, mesh_path, size=0.3)
            
            # 2) Mesh 위치 이동 (X, Y좌표 지정, 바닥 밀착을 위해 Z는 0.005)
            xform = UsdGeom.XformCommonAPI(mesh)
            xform.SetTranslate(Gf.Vec3d(xc, yc, 0.005))
            
            # 3) Material 생성
            material = create_textured_material(stage, material_path, qr_filepath)
            
            # 4) Material 바인딩
            UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(material)
            
            count += 1
            if count % 500 == 0:
                print(f"  └─ 생성 진행률: {count}/{total}개 완료...")

    # 5. 스테이지 저장
    print(f"총 {count}개의 QR코드 노드를 USD 스테이지에 성공적으로 추가하였습니다.")
    print("USD 파일을 저장하고 있습니다...")
    usd_context.save_stage()
    
    sim.close()
    print("=== USD 바닥 QR코드 적용 완료! ===")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import os
import sys

# Start Isaac Sim headless
from omni.isaac.kit import SimulationApp
sim = SimulationApp({"headless": True})

import omni.usd
from pxr import Usd, UsdGeom, Sdf, Gf, UsdShade

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
    print("=== [20x20m 맵 전용] USD 바닥 QR코드 적용 스크립트 실행 ===")
    usd_path = "/home/rokey/cobot3_ws/src/cobot3/resource/Small_map/World3.usd"
    
    if not os.path.exists(usd_path):
        print(f"[에러] USD 파일이 경로에 존재하지 않습니다: {usd_path}")
        sim.close()
        return

    # 1. USD Stage 로드
    usd_context = omni.usd.get_context()
    opened = usd_context.open_stage(usd_path)
    if not opened:
        print(f"USD 파일을 열 수 없습니다: {usd_path}")
        sim.close()
        return
        
    stage = usd_context.get_stage()
    print(f"성공적으로 USD 스테이지를 열었습니다: {usd_path}")

    # 기존 바닥 QR코드 그룹 청소 (Idempotency 보장)
    floor_qrs_root = "/World/FloorQRs"
    if stage.GetPrimAtPath(floor_qrs_root):
        print(f"기존에 존재하는 {floor_qrs_root} 프리미티브를 제거하고 새로 구성합니다.")
        stage.RemovePrim(floor_qrs_root)
        
    # 새로운 FloorQRs root xform 정의
    UsdGeom.Xform.Define(stage, Sdf.Path(floor_qrs_root))

    # 2. 1.5m 간격 격자 좌표 생성
    coords = []
    val = -9.0
    while val <= 9.01:
        coords.append(round(val, 2))
        val += 1.5

    print(f"격자 생성 대역: {coords}")
    print(f"총 생성 마커 개수: {len(coords) * len(coords)}개")

    # 3. 루프를 돌며 각 좌표에 mesh와 material 생성 및 연결
    count = 0
    total = len(coords) * len(coords)
    
    # 텍스처 폴더 경로
    texture_dir = "/home/rokey/cobot3_ws/scratch/qr_assets/floor"
    
    # UsdEdit 시작
    for col_idx, xc in enumerate(coords):
        for row_idx, yc in enumerate(coords):
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
            if count % 50 == 0:
                print(f"  └─ 생성 진행률: {count}/{total}개 완료...")

    # 4. 스테이지 저장
    print(f"총 {count}개의 QR코드 노드를 USD 스테이지({usd_path})에 성공적으로 추가하였습니다.")
    print("USD 파일을 저장하고 있습니다...")
    usd_context.save_stage()
    
    sim.close()
    print("=== USD 바닥 QR코드 적용 완료! ===")

if __name__ == "__main__":
    main()

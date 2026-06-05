#!/usr/bin/env python3
import os
import sys
import yaml
import cv2

# Start Isaac Sim headless (오버헤드 방지를 위해 백그라운드 모드로 구동)
from omni.isaac.kit import SimulationApp
sim = SimulationApp({"headless": True})

import omni.usd
from pxr import Usd, UsdGeom, Sdf, Gf, UsdShade

def load_map_info(yaml_path):
    """ROS2 가상 맵 YAML 설정을 파싱하여 물리적인 미터 단위 범위 계산"""
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

def create_plane_mesh(stage, prim_path, size=0.25):
    """
    마스터로 사용할 단 1개의 규격 평면 메쉬(Quad Mesh) 프로토타입을 정의합니다.
    사용자 요청 사양에 맞춰 기본 크기를 0.25m (25cm)로 고정합니다.
    """
    mesh = UsdGeom.Mesh.Define(stage, Sdf.Path(prim_path))
    
    # Z축 기준 0.005m(5mm) 띄운 상태로 자율주행 AMR 바닥 밀착 평면 구성
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
    
    # UV 기본 좌표 (st 바인딩) 생성
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
    """UsdPreviewSurface 규격을 준수하여 반사를 최적화한 가벼운 PBR 재질을 컴파일합니다."""
    # Material 정의
    material = UsdShade.Material.Define(stage, Sdf.Path(material_path))
    
    # PBR Shader 노드 정의
    pbr_shader = UsdShade.Shader.Define(stage, Sdf.Path(f"{material_path}/PBRShader"))
    pbr_shader.CreateIdAttr("UsdPreviewSurface")
    material.CreateSurfaceOutput().ConnectToSource(pbr_shader.ConnectableAPI(), "surface")
    
    # Texture Image 파일 연결 Shader 노드 정의
    texture_shader = UsdShade.Shader.Define(stage, Sdf.Path(f"{material_path}/diffuseTexture"))
    texture_shader.CreateIdAttr("UsdUVTexture")
    texture_shader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(texture_file_path)
    
    # 텍스처 컬러 아웃풋을 PBR 디퓨즈 속성에 물리적으로 연결
    texture_shader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    pbr_shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture_shader.ConnectableAPI(), "rgb"
    )
    
    # UV 좌표 파싱용 리더 컴파일 및 연결
    st_reader = UsdShade.Shader.Define(stage, Sdf.Path(f"{material_path}/stReader"))
    st_reader.CreateIdAttr("UsdPrimvarReader_float2")
    st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    st_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    
    texture_shader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
        st_reader.ConnectableAPI(), "result"
    )
    
    return material

def main():
    print("=== [최적화 엔진] USD 인스턴싱 기반 바닥 QR 격자 배치 스크립트 실행 ===")
    
    # 환경 사양 경로 동기화 (사용자 지정 floor.usd 타겟 고정)
    yaml_path = "/home/rokey/cobot3_ws/src/cobot3/resource/map/warehouse.yaml"
    usd_path = "/home/rokey/cobot3_ws/src/cobot3/resource/floor.usd"
    texture_dir = "/home/rokey/cobot3_ws/scratch/qr_assets/floor"
    floor_qrs_root = "/World/FloorQRs"
    proto_path = f"{floor_qrs_root}/PrototypePlane"
    
    # 1. ROS2 가상 물류창고 기반 맵 해상도 데이터 로드
    try:
        map_info = load_map_info(yaml_path)
    except Exception as e:
        print(f"맵 정보 로드 실패: {e}")
        sim.close()
        return

    # 2. OpenUSD Context 및 Stage 인터페이스 로드
    usd_context = omni.usd.get_context()
    opened = usd_context.open_stage(usd_path)
    if not opened:
        print(f"USD 파일을 열 수 없습니다: {usd_path}")
        sim.close()
        return
        
    stage = usd_context.get_stage()
    print(f"성공적으로 타겟 USD 스테이지를 활성화했습니다: {usd_path}")

    # 3. 데이터 멱등성(Idempotency) 확보를 위해 기존 찌꺼기 노드 및 재질 청소
    if stage.GetPrimAtPath(floor_qrs_root):
        print(f"안정적인 재구축을 위해 기존 맵에 등록된 {floor_qrs_root} 트리 노드를 TRUNCATE(삭제)합니다.")
        stage.RemovePrim(floor_qrs_root)
    
    # Looks 마티리얼 컨테이너 하위 청소
    looks_root = "/World/Looks"
    if stage.GetPrimAtPath(looks_root):
        stage.RemovePrim(looks_root)
        
    # 새로운 깔끔한 루트 및 마티리얼 부모 노드 선언
    UsdGeom.Xform.Define(stage, Sdf.Path(floor_qrs_root))
    stage.DefinePrim(looks_root, "Scope")

    # 4. 단 1개의 25cm 표준 규격 마스터 프로토타입 메쉬(Prototype) 빌드
    print(f"⚙️ 기준 마스터 프로토타입 평면(크기: 25cm)을 선언합니다 -> {proto_path}")
    create_plane_mesh(stage, proto_path, size=0.25)

    # 5. 창고 영역 바운딩 박스 제한 필터 기준 수립 (1,813개 격자 정합성 유지)
    margin = 2.0
    spacing = 1.5
    
    x_start = map_info['origin_x'] + margin
    y_start = map_info['origin_y'] + margin
    x_end = map_info['origin_x'] + map_info['width_m'] - margin
    y_end = map_info['origin_y'] + map_info['height_m'] - margin

    x_min, x_max = -38.0, 38.0
    y_min, y_max = -36.08472, 30.0

    x_coords = []
    x = x_start
    while x <= x_end:
        rx = round(x, 3)
        if x_min <= rx <= x_max:
            x_coords.append(rx)
        x += spacing

    y_coords = []
    y = y_start
    while y <= y_end:
        ry = round(y, 3)
        if y_min <= ry <= y_max:
            y_coords.append(ry)
        y += spacing

    total_expected = len(x_coords) * len(y_coords)
    print(f"격자 생성 타겟 사양: X열 {len(x_coords)}개 * Y행 {len(y_coords)}개 = 총 {total_expected}개 마커")

    # 6. 고속 대량 인스턴싱 루프 구동
    count = 0
    
    for col_idx, xc in enumerate(x_coords):
        for row_idx, yc in enumerate(y_coords):
            prim_name = f"QR_c{col_idx}_r{row_idx}"
            mesh_path = f"{floor_qrs_root}/{prim_name}"
            material_path = f"{looks_root}/Material_c{col_idx}_r{row_idx}"
            
            # 물리 디스크 내 고유 QR 이미지 매핑 확인
            qr_filename = f"FLOOR_X_{xc}_Y_{yc}.png"
            qr_filepath = os.path.join(texture_dir, qr_filename)
            
            if not os.path.exists(qr_filepath):
                continue
                
            # [핵심 최적화]: 메쉬를 새로 만들지 않고, 빈 프림을 선언한 뒤 PrototypePlane을 내부 참조 처리!
            instance_prim = stage.DefinePrim(Sdf.Path(mesh_path))
            instance_prim.GetReferences().AddInternalReference(Sdf.Path(proto_path))
            
            # OpenUSD 가속 기능인 인스턴싱 구조체 활성화 활성화! (VRAM 폭발 원천 차단)
            instance_prim.SetInstanceable(True)
            
            # 참조된 인스턴스의 물리 월드 좌표 오프셋 설정 (Z축은 바닥 렌더링 겹침 깨짐 방지를 위해 0.005 유지)
            xform = UsdGeom.XformCommonAPI(instance_prim)
            xform.SetTranslate(Gf.Vec3d(xc, yc, 0.005))
            
            # 개별 고유 QR 코드 이미지 바인딩용 셰이더 컴파일
            material = create_textured_material(stage, material_path, qr_filepath)
            
            # 인스턴스 프리미티브에 고유 머티리얼 링크 완료
            UsdShade.MaterialBindingAPI(instance_prim).Bind(material)
            
            count += 1
            if count % 500 == 0:
                print(f"  └─ 초고속 인스턴싱 매핑 진행률: [{count}/{total_expected}] 노드 메모리 정규화 완료...")

    # 7. 최적화 완료 스테이지 직렬화 및 물리 디스크 저장
    print(f"🎉 성공적으로 총 {count}개의 격자 노드를 단 1개의 메쉬 용량으로 인스턴싱 빌드 완료했습니다!")
    print(" floor.usd 파일 스냅샷을 영구 저장하는 중입니다...")
    usd_context.save_stage()
    
    sim.close()
    print("=== OpenUSD 씬 인스턴싱 가속화 최적화 공정 종료 ===")

if __name__ == "__main__":
    main()
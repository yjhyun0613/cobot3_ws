#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
관제탑 시뮬레이션용 QR 코드 상자 USD 에셋 생성기
==================================================
- 크기: 10cm × 10cm × 10cm
- 색상: 노란색/오렌지 계열 diffuse_color=(0.85, 0.38, 0.08)
- 충돌체: 단순 Box Collider (Triangle Mesh 사용 금지)
- 질량: 1.5 kg
- 정지 마찰력: 2.0 / 동마찰력: 1.8 / friction_combine_mode: max
- QR 코드: 앞면(Front face, -Y 면) 1면에만 배치
"""

# 1. Isaac Sim 백그라운드 구동 초기화
from omni.isaac.kit import SimulationApp
simulation_app = SimulationApp({"headless": True})

import os
import re
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, UsdPhysics


def create_sh5_qr_box(package_id, qr_image_path, output_dir):
    """
    글로벌 시뮬레이션 무대를 오염시키지 않고, 오직 해당 파일 내부에만
    오렌지색 재질과 앞면(Front, -Y) 1면 QR코드를 순수 OpenUSD API로
    완벽히 격리 빌드합니다.

    상자 조건:
      - 크기: 0.10 × 0.10 × 0.10 m
      - 색상: (0.85, 0.38, 0.08) 오렌지 계열
      - Collider: 단순 Box Collider (Mesh Collider 렌더링 절대 금지)
      - 질량: 1.5 kg
      - 정지 마찰력: 2.0 / 동마찰력: 1.8 / friction_combine_mode: max
      - QR: 앞면(Face 2, -Y 방향) 1면에만 부착
    """
    output_usd_path = os.path.join(output_dir, f"{package_id}.usd")
    stage = Usd.Stage.CreateNew(output_usd_path)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)

    # ================================================================
    # 1. 📦 [Root Xform] 독립된 개체 트리 구성
    # ================================================================
    root_path = f"/{package_id}"
    root_xform = UsdGeom.Xform.Define(stage, root_path)
    stage.SetDefaultPrim(root_xform.GetPrim())

    root_prim = root_xform.GetPrim()
    UsdPhysics.RigidBodyAPI.Apply(root_prim)
    mass_api = UsdPhysics.MassAPI.Apply(root_prim)
    mass_api.CreateMassAttr().Set(1.5)  # 1.5kg 설정

    # ================================================================
    # 2. 🧱 [Collision] 단순 Box Collider (Triangle Mesh 에러 차단)
    #    ※ 복잡한 Mesh Collider 렌더링 절대 금지 조건 준수
    # ================================================================
    collision_path = f"{root_path}/CollisionCube"
    collision_cube = UsdGeom.Cube.Define(stage, collision_path)
    collision_cube.GetSizeAttr().Set(0.1)  # 10cm 큐브
    collision_cube.CreatePurposeAttr(UsdGeom.Tokens.guide)  # 시각적 숨김 처리

    col_prim = collision_cube.GetPrim()
    UsdPhysics.CollisionAPI.Apply(col_prim)

    # 물리 재질 정의: 높은 마찰력으로 안정적 파지(Grasping) 보장
    mat_phys_path = f"{root_path}/PhysicsMaterial"
    mat_prim = stage.DefinePrim(mat_phys_path, "Material")
    phys_mat = UsdPhysics.MaterialAPI.Apply(mat_prim)
    phys_mat.CreateStaticFrictionAttr().Set(2.0)   # 정지 마찰력
    phys_mat.CreateDynamicFrictionAttr().Set(1.8)   # 동마찰력
    # friction_combine_mode = "max" 설정
    mat_prim.CreateAttribute(
        "physxMaterial:frictionCombineMode", Sdf.ValueTypeNames.Token
    ).Set("max")
    col_prim.CreateRelationship("physics:materialBinding").SetTargets(
        [Sdf.Path(mat_phys_path)]
    )

    # ================================================================
    # 3. 🎨 [Visual] 렌더링용 Mesh 생성 및 UV 매핑 좌표계 주입
    #    QR 코드는 앞면(Face 2, -Y 방향)에만 1:1 UV 안착
    # ================================================================
    mesh_path = f"{root_path}/VisualMesh"
    mesh_geom = UsdGeom.Mesh.Define(stage, mesh_path)

    h = 0.05  # half-size = 5cm → 전체 10cm
    #
    # 면 인덱스 정의 (Z-up 좌표계):
    #   Face 0: 윗면   (Z = +h)   — 오렌지색
    #   Face 1: 아랫면  (Z = -h)   — 오렌지색
    #   Face 2: 앞면   (Y = -h)   — ★ QR 코드 면 ★
    #   Face 3: 뒷면   (Y = +h)   — 오렌지색
    #   Face 4: 우측면  (X = +h)   — 오렌지색
    #   Face 5: 좌측면  (X = -h)   — 오렌지색
    #
    vertices = [
        # Face 0: 윗면 (Z=+h)
        Gf.Vec3f(-h, -h,  h), Gf.Vec3f( h, -h,  h),
        Gf.Vec3f( h,  h,  h), Gf.Vec3f(-h,  h,  h),
        # Face 1: 아랫면 (Z=-h)
        Gf.Vec3f(-h,  h, -h), Gf.Vec3f( h,  h, -h),
        Gf.Vec3f( h, -h, -h), Gf.Vec3f(-h, -h, -h),
        # Face 2: 앞면 (Y=-h) ← QR 코드 부착면
        Gf.Vec3f(-h, -h, -h), Gf.Vec3f( h, -h, -h),
        Gf.Vec3f( h, -h,  h), Gf.Vec3f(-h, -h,  h),
        # Face 3: 뒷면 (Y=+h)
        Gf.Vec3f( h,  h, -h), Gf.Vec3f(-h,  h, -h),
        Gf.Vec3f(-h,  h,  h), Gf.Vec3f( h,  h,  h),
        # Face 4: 우측면 (X=+h)
        Gf.Vec3f( h, -h, -h), Gf.Vec3f( h,  h, -h),
        Gf.Vec3f( h,  h,  h), Gf.Vec3f( h, -h,  h),
        # Face 5: 좌측면 (X=-h)
        Gf.Vec3f(-h,  h, -h), Gf.Vec3f(-h, -h, -h),
        Gf.Vec3f(-h, -h,  h), Gf.Vec3f(-h,  h,  h),
    ]
    mesh_geom.CreatePointsAttr(vertices)
    mesh_geom.CreateFaceVertexCountsAttr([4] * 6)
    mesh_geom.CreateFaceVertexIndicesAttr(list(range(24)))

    # UV 좌표: Face 2(앞면)에만 QR 텍스처 1:1 매핑, 나머지는 (0,0) 단색
    uvs = [
        # Face 0: 윗면 — 단색
        Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0),
        # Face 1: 아랫면 — 단색
        Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0),
        # Face 2: 앞면(Y=-h) — ★ QR 1:1 UV 안착 좌표 ★
        Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1),
        # Face 3: 뒷면 — 단색
        Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0),
        # Face 4: 우측면 — 단색
        Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0),
        # Face 5: 좌측면 — 단색
        Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0), Gf.Vec2f(0, 0),
    ]
    primvars_api = UsdGeom.PrimvarsAPI(mesh_geom.GetPrim())
    st_primvar = primvars_api.CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    )
    st_primvar.Set(uvs)

    # ================================================================
    # 4. 🖌️ [Material] 격리형 OmniPBR 셰이더 정의
    #    기본색: 오렌지 (0.85, 0.38, 0.08)
    # ================================================================
    def setup_pbr_material(mat_name, is_qr=False):
        mat_path = f"{root_path}/{mat_name}"
        material = UsdShade.Material.Define(stage, mat_path)
        shader = UsdShade.Shader.Define(stage, f"{mat_path}/Shader")

        # 최신 Isaac Sim 렌더러 호환 ID 및 소스 바인딩
        shader.CreateIdAttr("OmniPBR")
        shader.SetSourceAsset("OmniPBR.mdl", "mdl")
        shader.SetSourceAssetSubIdentifier("OmniPBR", "mdl")

        # 기본 디퓨즈 색상: 오렌지 계열 (0.85, 0.38, 0.08)
        shader.CreateInput(
            "diffuse_color_constant", Sdf.ValueTypeNames.Color3f
        ).Set(Gf.Vec3f(0.85, 0.38, 0.08))

        if is_qr and os.path.exists(qr_image_path):
            shader.CreateInput(
                "diffuse_texture", Sdf.ValueTypeNames.Asset
            ).Set(qr_image_path)
            shader.CreateInput(
                "project_uvw", Sdf.ValueTypeNames.Bool
            ).Set(False)

        # 🎯 실시간 렌더러 타겟 출력 채널 명시적 연결
        shader_out = shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
        material.CreateOutput(
            "mdl:surface", Sdf.ValueTypeNames.Token
        ).ConnectToSource(shader_out)
        material.CreateOutput(
            "mdl:displacement", Sdf.ValueTypeNames.Token
        ).ConnectToSource(shader_out)
        material.CreateOutput(
            "mdl:volume", Sdf.ValueTypeNames.Token
        ).ConnectToSource(shader_out)
        return material

    base_material = setup_pbr_material("VisualMaterial_Base", is_qr=False)
    qr_material = setup_pbr_material("VisualMaterial_QR", is_qr=True)

    # ================================================================
    # 5. 🎯 서브셋 분리 및 순수 로컬 재질 결합
    #    전체 면: 오렌지 기본 셰이더
    #    앞면(Face 2)만: QR코드 머티리얼 정밀 주입
    # ================================================================
    # 전체 메쉬 표면에는 기본 오렌지 쉐이더 장착
    UsdShade.MaterialBindingAPI(mesh_geom.GetPrim()).Bind(base_material)

    # 앞면(Face 2, Y=-h) 영역만 단독 패밀리 서브셋으로 분리
    subset = UsdGeom.Subset.Define(stage, f"{mesh_path}/FrontFaceSubset")
    subset.CreateElementTypeAttr().Set(UsdGeom.Tokens.face)
    subset.CreateIndicesAttr().Set([2])  # Face index 2 = 앞면(Y=-h)
    subset.CreateFamilyNameAttr().Set(UsdShade.Tokens.materialBind)

    # 분리된 앞면 서브셋에만 QR코드 머티리얼 정밀 주입
    UsdShade.MaterialBindingAPI(subset.GetPrim()).Bind(qr_material)

    stage.GetRootLayer().Save()
    print(f"✨ [OpenUSD 생성 완료] {package_id}.usd "
          f"(오렌지색 + 앞면 QR | 1.5kg | 마찰 2.0/1.8)")


def main():
    home_dir = os.path.expanduser("~")
    qr_dir = os.path.join(home_dir, "cobot3_ws/scratch/qr_codes")
    output_dir = os.path.join(home_dir, "cobot3_ws/scratch/box_assets")

    # 꼬임 방지를 위해 기존 디렉토리 내부 완전 초기화
    if os.path.exists(output_dir):
        print("🗑️ 이전 빌드에서 꼬인 찌꺼기 USD 에셋들을 강제 초기화합니다...")
        for filename in os.listdir(output_dir):
            if filename.endswith(".usd"):
                os.remove(os.path.join(output_dir, filename))
    else:
        os.makedirs(output_dir)

    if not os.path.exists(qr_dir):
        print(f"❌ 오류: QR 폴더를 찾을 수 없습니다: {qr_dir}")
        return

    # QR_YYYYMMDD_NNN.png 패턴의 모든 QR 파일 대상
    png_files = [
        f for f in os.listdir(qr_dir)
        if f.endswith(".png") and f.startswith("QR_")
    ]
    # 6/6 ~ 6/12 날짜 전체 범위 포함
    target_date_pattern = re.compile(
        r'QR_(20260606|20260607|20260608|20260609|20260610|20260611|20260612)_\d+'
    )
    filtered_files = [f for f in png_files if target_date_pattern.search(f)]

    print(f"🚀 총 {len(filtered_files)}개의 독립 격리형 "
          f"오렌지 QR 상자 생성을 시작합니다.")
    print(f"   조건: 10cm³ | 1.5kg | 마찰(정지2.0/동1.8) | "
          f"앞면 QR | Box Collider")

    for file_name in sorted(filtered_files):
        qr_path = os.path.join(qr_dir, file_name)
        package_id = file_name.replace("QR_", "PKG_").replace(".png", "")
        create_sh5_qr_box(package_id, qr_path, output_dir)

    print(f"\n🏁 전체 {len(filtered_files)}개 상자 USD 에셋 생성 완료!")
    print(f"   출력 경로: {output_dir}")


if __name__ == "__main__":
    main()
    simulation_app.close()
#!/usr/bin/env python3
"""
바닥 QR코드 생성 및 GroundPlane.usd 통합 스크립트 (Material/Texture 포함)
=========================================================================
- 맵 중심: (1.5, 0.0), 크기: 17.5m x 20m
- 1.5m 간격으로 전체 바닥 격자에 QR코드 생성 (11 x 13 = 143개)
- 기존 미사용 QR코드 이미지 삭제
- GroundPlane.usd에 QR코드 Mesh + Material(UsdPreviewSurface) + Texture 배치
"""

import os
import shutil
import qrcode
from PIL import Image
from pxr import Usd, UsdGeom, UsdShade, Gf, Sdf

# ─────────────────────────────────────────────────────
# 1. 설정
# ─────────────────────────────────────────────────────
MAP_CENTER_X = 1.5
MAP_CENTER_Y = 0.0
MAP_WIDTH = 17.5   # X 크기
MAP_HEIGHT = 20.0  # Y 크기
GRID_SPACING = 1.5

# 맵 경계
X_MIN = MAP_CENTER_X - MAP_WIDTH / 2   # -7.25
X_MAX = MAP_CENTER_X + MAP_WIDTH / 2   # 10.25
Y_MIN = MAP_CENTER_Y - MAP_HEIGHT / 2  # -10.0
Y_MAX = MAP_CENTER_Y + MAP_HEIGHT / 2  # 10.0

# QR코드 크기 (USD 내에서의 한 변 크기, 미터 단위)
QR_SIZE = 0.3  # 30cm x 30cm

# 경로
WORKSPACE = os.path.expanduser("~/cobot3_ws")
USD_PATH = os.path.join(WORKSPACE, "src/cobot3/resource/GroundPlane.usd")
QR_IMG_DIR = os.path.join(WORKSPACE, "scratch/qr_assets/floor")
# QR 텍스처를 USD 파일과 같은 디렉토리의 하위 폴더에 저장 (상대 경로 참조용)
QR_TEX_DIR = os.path.join(WORKSPACE, "src/cobot3/resource/floor_qr_textures")


def generate_grid_coords():
    """1.5m 간격의 격자 좌표 생성 (맵 범위 내)"""
    coords = []
    x = -6.0
    while x <= 9.0 + 0.01:
        if X_MIN <= x <= X_MAX:
            y = -9.0
            while y <= 9.0 + 0.01:
                if Y_MIN <= y <= Y_MAX:
                    coords.append((round(x, 1), round(y, 1)))
                y += GRID_SPACING
        x += GRID_SPACING
    return coords


def qr_id_from_coord(x, y):
    """좌표로부터 QR ID 문자열 생성"""
    if x == 0.0:
        x = 0.0
    if y == 0.0:
        y = 0.0
    return f"FLOOR_X_{x}_Y_{y}"


def safe_prim_name(qr_id):
    """QR ID를 USD prim 이름으로 변환 (마침표/마이너스 대체)"""
    return qr_id.replace(".", "p").replace("-", "n")


def generate_qr_image(data_str, output_path, box_size=10, border=2):
    """QR코드 이미지를 생성하여 RGB PNG로 저장 (텍스처용)"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    # RGB로 변환하여 저장 (Isaac Sim 텍스처 호환성)
    img_rgb = img.convert("RGB")
    img_rgb.save(output_path)


def clean_old_qr_images(valid_ids):
    """유효한 QR ID 목록에 없는 이미지 파일 삭제"""
    total_deleted = 0
    for dir_path in [QR_IMG_DIR, QR_TEX_DIR]:
        if not os.path.exists(dir_path):
            continue
        for filename in os.listdir(dir_path):
            if filename.endswith(".png"):
                qr_name = filename[:-4]
                if qr_name not in valid_ids:
                    try:
                        os.remove(os.path.join(dir_path, filename))
                        total_deleted += 1
                    except Exception as e:
                        print(f"  [경고] 삭제 실패 ({filename}): {e}")
    return total_deleted


def build_usd_with_qr(coords):
    """GroundPlane.usd에 바닥 QR코드 Mesh + Material + Texture 추가"""

    stage = Usd.Stage.Open(USD_PATH)

    # 기존 FloorQRCodes 삭제 후 재생성
    qr_parent_path = Sdf.Path("/Root/GroundPlane/FloorQRCodes")
    if stage.GetPrimAtPath(qr_parent_path):
        stage.RemovePrim(qr_parent_path)

    # 기존 FloorQRMaterials 삭제 후 재생성
    mat_parent_path = Sdf.Path("/Root/GroundPlane/FloorQRMaterials")
    if stage.GetPrimAtPath(mat_parent_path):
        stage.RemovePrim(mat_parent_path)

    # 부모 Xform 생성
    UsdGeom.Xform.Define(stage, qr_parent_path)
    UsdGeom.Xform.Define(stage, mat_parent_path)

    print(f"\n  USD에 {len(coords)}개의 QR코드 (Mesh + Material + Texture) 배치 중...")

    # 텍스처 파일의 상대 경로 기준 (USD 파일 위치 기준)
    usd_dir = os.path.dirname(USD_PATH)

    for x, y in coords:
        qr_id = qr_id_from_coord(x, y)
        safe_name = safe_prim_name(qr_id)
        mesh_path = qr_parent_path.AppendChild(safe_name)
        mat_prim_path = mat_parent_path.AppendChild(f"Mat_{safe_name}")

        # ── 텍스처 파일 경로 (USD 파일 기준 상대경로) ──
        tex_filename = f"{qr_id}.png"
        tex_rel_path = f"floor_qr_textures/{tex_filename}"

        # ── Material 생성 ──
        material = UsdShade.Material.Define(stage, mat_prim_path)

        # Shader (UsdPreviewSurface)
        shader_path = mat_prim_path.AppendChild("PreviewSurface")
        shader = UsdShade.Shader.Define(stage, shader_path)
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.9)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)

        # Diffuse Color를 텍스처에서 가져오기
        diffuse_input = shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f)

        # Texture Reader (UsdUVTexture)
        tex_reader_path = mat_prim_path.AppendChild("DiffuseTexture")
        tex_reader = UsdShade.Shader.Define(stage, tex_reader_path)
        tex_reader.CreateIdAttr("UsdUVTexture")
        tex_reader.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(
            Sdf.AssetPath(f"./{tex_rel_path}")
        )
        tex_reader.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
        tex_reader.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
        tex_reader.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

        # UV Coord Reader (UsdPrimvarReader_float2)
        uv_reader_path = mat_prim_path.AppendChild("UVReader")
        uv_reader = UsdShade.Shader.Define(stage, uv_reader_path)
        uv_reader.CreateIdAttr("UsdPrimvarReader_float2")
        uv_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        uv_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)

        # 연결: UVReader -> Texture -> Shader -> Material
        tex_reader.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            uv_reader.ConnectableAPI(), "result"
        )
        diffuse_input.ConnectToSource(tex_reader.ConnectableAPI(), "rgb")
        material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(), "surface"
        )

        # ── Mesh 생성 ──
        half = QR_SIZE / 2.0
        mesh = UsdGeom.Mesh.Define(stage, mesh_path)
        mesh.CreateFaceVertexCountsAttr([4])
        mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        mesh.CreatePointsAttr([
            Gf.Vec3f(-half, -half, 0.001),
            Gf.Vec3f( half, -half, 0.001),
            Gf.Vec3f( half,  half, 0.001),
            Gf.Vec3f(-half,  half, 0.001),
        ])
        mesh.CreateNormalsAttr([
            Gf.Vec3f(0, 0, 1), Gf.Vec3f(0, 0, 1),
            Gf.Vec3f(0, 0, 1), Gf.Vec3f(0, 0, 1),
        ])
        mesh.CreateDoubleSidedAttr(False)

        # UV 좌표
        primvars_api = UsdGeom.PrimvarsAPI(mesh)
        texcoords = primvars_api.CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.varying
        )
        texcoords.Set([
            Gf.Vec2f(0, 0), Gf.Vec2f(1, 0),
            Gf.Vec2f(1, 1), Gf.Vec2f(0, 1),
        ])

        # Transform
        xformable = UsdGeom.Xformable(mesh)
        xformable.ClearXformOpOrder()
        translate_op = xformable.AddTranslateOp()
        translate_op.Set(Gf.Vec3d(x, y, 0))

        # QR ID 커스텀 어트리뷰트
        mesh.GetPrim().CreateAttribute(
            "custom:qrId", Sdf.ValueTypeNames.String
        ).Set(qr_id)

        # Material 바인딩
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim())
        UsdShade.MaterialBindingAPI(mesh).Bind(material)

    # 저장
    stage.GetRootLayer().Save()
    print(f"  ✅ USD 저장 완료: {USD_PATH}")


def main():
    print("=" * 60)
    print("  바닥 QR코드 생성 및 GroundPlane.usd 통합 (v2 - Texture)")
    print("=" * 60)

    # 1. 격자 좌표 생성
    coords = generate_grid_coords()
    print(f"\n[1] 격자 좌표 생성: {len(coords)}개 (1.5m 간격)")
    print(f"    X 범위: {min(c[0] for c in coords)} ~ {max(c[0] for c in coords)}")
    print(f"    Y 범위: {min(c[1] for c in coords)} ~ {max(c[1] for c in coords)}")

    # 2. QR코드 이미지 생성 (RGB PNG)
    os.makedirs(QR_IMG_DIR, exist_ok=True)
    os.makedirs(QR_TEX_DIR, exist_ok=True)
    valid_ids = set()
    print(f"\n[2] QR코드 이미지 생성 ({len(coords)}개, RGB PNG)...")

    for x, y in coords:
        qr_id = qr_id_from_coord(x, y)
        valid_ids.add(qr_id)
        # scratch 디렉토리에 원본
        img_path = os.path.join(QR_IMG_DIR, f"{qr_id}.png")
        generate_qr_image(qr_id, img_path)
        # USD 텍스처 디렉토리에도 복사
        tex_path = os.path.join(QR_TEX_DIR, f"{qr_id}.png")
        shutil.copy2(img_path, tex_path)

    print(f"    ✅ {len(valid_ids)}개 QR코드 이미지 생성 완료")
    print(f"    📁 텍스처 디렉토리: {QR_TEX_DIR}")

    # 3. 미사용 QR코드 삭제
    print(f"\n[3] 미사용 바닥 QR코드 정리...")
    deleted = clean_old_qr_images(valid_ids)
    print(f"    🗑️  {deleted}개 미사용 QR코드 삭제 완료")

    # 4. USD에 QR코드 배치 (Material + Texture 포함)
    print(f"\n[4] GroundPlane.usd에 QR코드 Mesh + Material 배치...")
    build_usd_with_qr(coords)

    # 5. 검증
    print(f"\n[5] 검증...")
    stage = Usd.Stage.Open(USD_PATH)
    qr_prims = [p for p in stage.Traverse()
                 if p.GetPath().pathString.startswith('/Root/GroundPlane/FloorQRCodes/')
                 and p.GetTypeName() == 'Mesh']
    mat_prims = [p for p in stage.Traverse()
                 if p.GetPath().pathString.startswith('/Root/GroundPlane/FloorQRMaterials/')
                 and p.GetTypeName() == 'Material']
    print(f"    QR Mesh: {len(qr_prims)}개")
    print(f"    Materials: {len(mat_prims)}개")

    # 바인딩 확인
    sample = qr_prims[0] if qr_prims else None
    if sample:
        binding = UsdShade.MaterialBindingAPI(sample)
        mat, _ = binding.ComputeBoundMaterial()
        if mat:
            print(f"    샘플 바인딩 확인: {sample.GetPath()} -> {mat.GetPath()}")
        else:
            print(f"    ⚠️ 샘플 바인딩 실패: {sample.GetPath()}")

    tex_count = len([f for f in os.listdir(QR_TEX_DIR) if f.endswith('.png')])
    print(f"    텍스처 파일: {tex_count}개")

    print(f"\n{'=' * 60}")
    print(f"  ✅ 완료!")
    print(f"  - QR 텍스처: {QR_TEX_DIR}")
    print(f"  - USD 파일: {USD_PATH}")
    print(f"  - 총 배치: {len(coords)}개 (Mesh + Material + Texture)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

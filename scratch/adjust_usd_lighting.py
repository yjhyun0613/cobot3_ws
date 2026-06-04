#!/usr/bin/env python3
import os
import sys

# Start Isaac Sim headless
from omni.isaac.kit import SimulationApp
sim = SimulationApp({"headless": True})

import omni.usd
from pxr import Usd, UsdGeom, UsdLux, Sdf, Gf

def main():
    print("=== USD 조명 최적화 스크립트 실행 ===")
    usd_path = "/home/rokey/cobot3_ws/src/cobot3/resource/map.usd"
    
    # USD Stage 로드
    usd_context = omni.usd.get_context()
    opened = usd_context.open_stage(usd_path)
    if not opened:
        print(f"USD 파일을 열 수 없습니다: {usd_path}")
        sim.close()
        return
        
    stage = usd_context.get_stage()
    
    # 1. 기존 DistantLight (/Environment/defaultLight) 세기 낮추기
    # 너무 강한 직사광선(3000.0)은 바닥 반사로 인해 QR코드 검출을 방해하므로, 부드러운 하이라이트 수준(600.0)으로 조절합니다.
    default_light_prim = stage.GetPrimAtPath("/Environment/defaultLight")
    if default_light_prim:
        default_light = UsdLux.DistantLight(default_light_prim)
        default_light.GetIntensityAttr().Set(600.0)
        print("  - 기존 직사광(/Environment/defaultLight) 세기를 3000.0 -> 600.0으로 완화했습니다.")
    else:
        print("  - 기존 defaultLight를 찾을 수 없습니다.")

    # 2. 부드러운 환경광(DomeLight) 추가/조정
    # 사방에서 균일하게 빛을 뿌려 그림자를 지우고 과노출을 방지하여 비전 인식률을 높입니다.
    dome_light_path = "/Environment/domeLight"
    dome_light = UsdLux.DomeLight.Define(stage, Sdf.Path(dome_light_path))
    dome_light.GetIntensityAttr().Set(1200.0)
    dome_light.GetColorAttr().Set(Gf.Vec3f(1.0, 1.0, 1.0))
    print(f"  - 환경광({dome_light_path})을 세기 1200.0으로 추가/설정 완료했습니다.")
    
    # 3. 변경 사항 저장
    print("USD 조명 설정을 저장하고 있습니다...")
    usd_context.save_stage()
    
    sim.close()
    print("=== USD 조명 최적화 적용 완료! ===")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from omni.isaac.kit import SimulationApp
sim = SimulationApp({"headless": True})

import omni.usd
from pxr import Usd, UsdGeom

def main():
    usd_path = "/home/rokey/cobot3_ws/src/cobot3/resource/map.usd"
    usd_context = omni.usd.get_context()
    opened = usd_context.open_stage(usd_path)
    if not opened:
        print("Failed to open stage")
        sim.close()
        return
        
    stage = usd_context.get_stage()
    print("=== USD Stage Primitives (Filtered) ===")
    
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        # Filter out floor QRs, looks, and repetitive assets
        if any(x in path for x in ["FloorQRs", "Looks", "SM_", "light", "DiskLight", "OmniverseKit", "Environment"]):
            continue
        
        print(f"Path: {path} (Type: {prim.GetTypeName()})")
        # Try getting scale, translate
        translationAttr = prim.GetAttribute("xformOp:translate")
        scaleAttr = prim.GetAttribute("xformOp:scale")
        if translationAttr and translationAttr.HasValue():
            print(f"  Translate: {translationAttr.Get()}")
        if scaleAttr and scaleAttr.HasValue():
            print(f"  Scale: {scaleAttr.Get()}")
            
    sim.close()

if __name__ == "__main__":
    main()

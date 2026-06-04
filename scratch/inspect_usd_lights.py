#!/usr/bin/env python3
from omni.isaac.kit import SimulationApp
sim = SimulationApp({"headless": True})

import omni.usd
from pxr import Usd, UsdGeom, UsdLux

def main():
    usd_path = "/home/rokey/cobot3_ws/src/cobot3/resource/map.usd"
    usd_context = omni.usd.get_context()
    opened = usd_context.open_stage(usd_path)
    if not opened:
        print("Failed to open stage")
        sim.close()
        return
        
    stage = usd_context.get_stage()
    print("=== USD Stage Light Primitives ===")
    
    # Traverse stage for all light prims
    for prim in stage.Traverse():
        if prim.IsA(UsdLux.LightAPI) or prim.GetTypeName() in ["DistantLight", "DomeLight", "SphereLight", "RectLight"]:
            print(f"Path: {prim.GetPath()}")
            print(f"  Type: {prim.GetTypeName()}")
            # Print attributes
            for attr in prim.GetAttributes():
                if "inputs:intensity" in attr.GetName() or "inputs:exposure" in attr.GetName() or "inputs:color" in attr.GetName():
                    print(f"  {attr.GetName()}: {attr.Get()}")
                    
    sim.close()

if __name__ == "__main__":
    main()

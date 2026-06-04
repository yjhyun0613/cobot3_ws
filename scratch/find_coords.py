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
    print("=== Searching for coordinates in stage ===")
    
    targets = [38.0, 25.0, -38.0, -36.08472, 1.19036, 5.08575]
    
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        for attr in prim.GetAttributes():
            val = attr.Get()
            if val is not None:
                val_str = str(val)
                if any(str(t) in val_str for t in targets):
                    print(f"Match found at Prim: {path}")
                    print(f"  Attribute: {attr.GetName()} = {val}")
                    
    sim.close()

if __name__ == "__main__":
    main()

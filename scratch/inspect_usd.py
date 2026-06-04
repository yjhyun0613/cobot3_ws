from omni.isaac.kit import SimulationApp
sim = SimulationApp({"headless": True})

from pxr import Usd, UsdGeom, Gf

def inspect_usd():
    usd_path = "/home/rokey/cobot3_ws/src/cobot3/resource/customrack.usd"
    stage = Usd.Stage.Open(usd_path)
    if not stage:
        print("Failed to open stage")
        return
    
    print("USD Stage hierarchy:")
    for prim in stage.Traverse():
        print(f"Prim: {prim.GetPath()} ({prim.GetTypeName()})")
        if prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            points = mesh.GetPointsAttr().Get()
            if points:
                print(f"  - Mesh points count: {len(points)}")
    
    # Calculate bounding box
    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    root_prim = stage.GetPseudoRoot()
    bbox = bbox_cache.ComputeWorldBound(root_prim)
    range_val = bbox.ComputeAlignedRange()
    min_pt = range_val.GetMin()
    max_pt = range_val.GetMax()
    print(f"\nBounding Box:")
    print(f"  Min: {min_pt}")
    print(f"  Max: {max_pt}")
    print(f"  Center: {range_val.GetMidpoint()}")
    print(f"  Bottom-Center: {Gf.Vec3d(range_val.GetMidpoint()[0], range_val.GetMidpoint()[1], min_pt[2])}")

inspect_usd()
sim.close()

import sys, os
# Suppress Omniverse logs
os.environ["OMNI_LOG_LEVEL"] = "ERROR"

from omni.isaac.kit import SimulationApp
sim = SimulationApp({"headless": True})
from pxr import Usd, UsdGeom, Gf

stage = Usd.Stage.Open('/home/rokey/cobot3_ws/src/cobot3/resource/Small_map/World3.usd')

results = []
results.append("=== Top-level Prims (depth <=3) ===")
for prim in stage.Traverse():
    path = prim.GetPath().pathString
    if path.count('/') <= 3:
        results.append(f"  {path}  [{prim.GetTypeName()}]")

results.append("\n=== custom_rack prims (depth <=5) ===")
for prim in stage.Traverse():
    path = prim.GetPath().pathString
    if "custom_rack" in path and "Looks" not in path and path.count('/') <= 5:
        # Try to get translate
        try:
            xform = UsdGeom.XformCommonAPI(prim)
            translate, _, _, _, _ = xform.GetXformVectors(0)
            results.append(f"  {path}  [{prim.GetTypeName()}] pos=({translate[0]:.2f}, {translate[1]:.2f}, {translate[2]:.2f})")
        except:
            results.append(f"  {path}  [{prim.GetTypeName()}]")

results.append("\n=== MAIN_storage prims (depth <=5) ===")
for prim in stage.Traverse():
    path = prim.GetPath().pathString
    if "MAIN_storage" in path and path.count('/') <= 5:
        try:
            xform = UsdGeom.XformCommonAPI(prim)
            translate, _, _, _, _ = xform.GetXformVectors(0)
            results.append(f"  {path}  [{prim.GetTypeName()}] pos=({translate[0]:.2f}, {translate[1]:.2f}, {translate[2]:.2f})")
        except:
            results.append(f"  {path}  [{prim.GetTypeName()}]")

# Write results to a file instead of stdout
with open('/home/rokey/cobot3_ws/scratch/usd_prim_report.txt', 'w') as f:
    f.write('\n'.join(results))
print(f"Report written to scratch/usd_prim_report.txt ({len(results)} lines)")
sim.close()

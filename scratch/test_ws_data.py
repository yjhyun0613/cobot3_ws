#!/usr/bin/env python3
import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8009/ws"
    async with websockets.connect(uri) as websocket:
        # Wait for the first message
        message = await websocket.recv()
        data = json.loads(message)
        
        print("WORKSTATIONS:")
        for ws in data.get('workstations', []):
            print(f"  {ws['workstation_id']}: {ws['current_location']}")
            
        print("\nGRID CELLS (spots only):")
        for cell in data.get('grid_cells', []):
            if cell.get('location_name') and cell['location_name'].startswith('spot_'):
                print(f"  {cell['location_name']}: x={cell['x']}, y={cell['y']}, qr_id={cell['qr_id']}")
                
        print("\nLOCATIONS CACHE:")
        for loc, info in data.get('locations', {}).items():
            if loc.startswith('spot_'):
                print(f"  {loc}: x={info['x']}, y={info['y']}")

async def main():
    try:
        await asyncio.wait_for(test_ws(), timeout=5.0)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Quick test script for batch endpoint - tests 3 batches with 10 companies each
Simple version for quick testing
"""

import asyncio
import httpx
import time
from datetime import datetime


BASE_URL = "https://fb-ai-prospecting-container-test-335810878975.us-central1.run.app"  # Base URL - endpoint will be appended  

# Organization numbers extracted from batch_id 31
ORG_NUMBERS_BATCH_1 = ["5569389827", "5569919656", "5592924343", "5592424484", "5591812606", "5567806533", "5568555865"]


ORG_NUMBERS_BATCH_2 = ["5567225650", "5592052756", "5563135150", "5591372130", "5568708563", "5568591688"]

ORG_NUMBERS_BATCH_3 = [
    "559218-4930", "5567513261", "5567536502", "5567099121", "5594665639", "5592155658", "5593835308", "5564639770"
]

CRITERIA = "get me contacts of CEOs for companies which have office in stockholm"


async def test_batch(batch_id: int, org_numbers: list):
    """Test a single batch"""
    print(f"\n{'='*60}")
    print(f"Testing Batch {batch_id}")
    print(f"{'='*60}")
    
    payload = {
        "org_numbers": org_numbers,
        "batch_id": str(9000 + batch_id),  # Use numeric batch_id (9001, 9002, 9003) for test batches
        "batch_size": 10,
        "criteria": CRITERIA
    }
    
    start = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(f"{BASE_URL}/evaluate-batch", json=payload)
            elapsed = time.time() - start
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Success! Time: {elapsed:.2f}s")
                if "summary" in result:
                    s = result["summary"]
                    print(f"   Total: {s.get('total')}, Success: {s.get('successful')}, Failed: {s.get('failed')}")
                    if s.get('matches') is not None:
                        print(f"   Matches: {s.get('matches')}")
                return {"success": True, "time": elapsed}
            else:
                print(f"❌ Failed! Status: {response.status_code}, Time: {elapsed:.2f}s")
                print(f"   Error: {response.text[:200]}")
                return {"success": False, "time": elapsed}
                
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ Error: {str(e)}, Time: {elapsed:.2f}s")
        return {"success": False, "time": elapsed}


async def main():
    """Run 3 batch tests"""
    print("\n" + "="*60)
    print("QUICK BATCH TEST - 3 Batches, 10 Companies Each")
    print("="*60)
    print(f"URL: {BASE_URL}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Test batches sequentially
    results = []
    for i, org_nums in enumerate([ORG_NUMBERS_BATCH_1, ORG_NUMBERS_BATCH_2, ORG_NUMBERS_BATCH_3], 1):
        result = await test_batch(i, org_nums)
        results.append(result)
        if i < 3:
            await asyncio.sleep(2)  # Small delay between batches
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    total_time = sum(r["time"] for r in results)
    successful = sum(1 for r in results if r["success"])
    print(f"Total batches: 3")
    print(f"Successful: {successful}")
    print(f"Failed: {3 - successful}")
    print(f"Total time: {total_time:.2f}s")
    print(f"Average time: {total_time/3:.2f}s")
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


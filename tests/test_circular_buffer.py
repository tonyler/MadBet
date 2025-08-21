#!/usr/bin/env python3
"""
Test script for circular buffer bet storage logic
"""

def get_bet_storage_key(bet_id: int, max_bets: int = 100) -> str:
    """Get circular buffer storage key for bet ID"""
    storage_slot = bet_id % max_bets
    if storage_slot == 0:
        storage_slot = max_bets
    return str(storage_slot)

def test_circular_buffer():
    """Test that circular buffer works as expected"""
    print("🧪 Testing Circular Buffer Logic (MAX_BETS = 100)")
    print("=" * 50)
    
    # Test normal range (1-100)
    test_cases = [
        (1, "1"),
        (50, "50"), 
        (99, "99"),
        (100, "100"),
        # Test overflow (101+)
        (101, "1"),   # Should overwrite slot 1
        (150, "50"),  # Should overwrite slot 50
        (200, "100"), # Should overwrite slot 100
        (201, "1"),   # Should overwrite slot 1 again
        (299, "99"),
        (300, "100"),
        (301, "1"),
    ]
    
    print("Bet ID → Storage Slot")
    print("-" * 20)
    
    all_passed = True
    for bet_id, expected_slot in test_cases:
        actual_slot = get_bet_storage_key(bet_id)
        status = "✅" if actual_slot == expected_slot else "❌"
        print(f"#{bet_id:3d} → slot {actual_slot:3s} {status}")
        
        if actual_slot != expected_slot:
            print(f"    Expected: {expected_slot}, Got: {actual_slot}")
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Circular buffer works correctly.")
        print("\n📊 Summary:")
        print("• Bets #1-100 use slots 1-100")
        print("• Bet #101 overwrites slot 1") 
        print("• Bet #200 overwrites slot 100")
        print("• Bet #201 overwrites slot 1 again")
        print("• Only most recent 100 bets are kept")
    else:
        print("❌ SOME TESTS FAILED! Check implementation.")
    
    return all_passed

def test_storage_simulation():
    """Simulate actual storage behavior"""
    print("\n🗂️  Storage Simulation Test")
    print("=" * 30)
    
    # Simulate storage dictionary
    storage = {}
    
    # Add first 5 bets
    for bet_id in range(1, 6):
        slot = get_bet_storage_key(bet_id)
        storage[slot] = f"Bet #{bet_id} data"
    
    print("After adding bets #1-5:")
    for slot in sorted(storage.keys(), key=int):
        print(f"  Slot {slot}: {storage[slot]}")
    
    # Add bet #101 (should overwrite slot 1)
    slot_101 = get_bet_storage_key(101)
    storage[slot_101] = "Bet #101 data"
    
    print(f"\nAfter adding bet #101 (overwrites slot {slot_101}):")
    for slot in sorted(storage.keys(), key=int):
        print(f"  Slot {slot}: {storage[slot]}")
    
    # Verify slot 1 now contains bet #101
    if storage["1"] == "Bet #101 data":
        print("✅ Overwrite successful: Bet #101 overwrote Bet #1")
    else:
        print("❌ Overwrite failed")

if __name__ == "__main__":
    # Run tests
    test_passed = test_circular_buffer()
    test_storage_simulation()
    
    print(f"\n🏁 Final Result: {'PASS' if test_passed else 'FAIL'}")
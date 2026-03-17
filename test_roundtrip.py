#!/usr/bin/env python3
"""
test_roundtrip.py — Verify decode → re-encode → decode roundtrip produces identical JSON.
"""
import json
import sys
sys.path.insert(0, ".")

from decoder_core import decode_moveset, encode_to_string


def test_roundtrip(name: str, encoded_input: str):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")

    # Step 1: Decode
    r1 = decode_moveset(encoded_input)
    assert r1.success, f"First decode failed: {r1.error}"
    assert r1.detected_type == "json", f"Expected JSON, got {r1.detected_type}"
    algo = r1.detected_algorithm
    print(f"  ✔ Decoded → {len(r1.raw_json_text):,} chars raw JSON (algo: {algo})")

    # Step 2: Re-encode with same algorithm using the raw JSON text
    r_enc = encode_to_string(r1.raw_json_text, algorithm=algo)
    assert r_enc.success, f"Encode failed: {r_enc.error}"
    print(f"  ✔ Re-encoded → {r_enc.encoded_size:,} chars")

    # Step 3: Decode the re-encoded string
    r2 = decode_moveset(r_enc.encoded_string)
    assert r2.success, f"Second decode failed: {r2.error}"
    assert r2.detected_type == "json", f"Expected JSON, got {r2.detected_type}"
    print(f"  ✔ Re-decoded → {len(r2.raw_json_text):,} chars raw JSON")

    # Step 4: Compare raw JSON (canonical minified form)
    json1 = json.loads(r1.raw_json_text)
    json2 = json.loads(r2.raw_json_text)

    if json1 == json2:
        print(f"  ✅ PASS — JSON is identical after roundtrip!")
    else:
        print(f"  ❌ FAIL — JSON differs after roundtrip!")
        # Show first difference
        s1 = json.dumps(json1, sort_keys=True, ensure_ascii=False)
        s2 = json.dumps(json2, sort_keys=True, ensure_ascii=False)
        for i, (a, b) in enumerate(zip(s1, s2)):
            if a != b:
                print(f"    First diff at char {i}: '{s1[max(0,i-20):i+20]}' vs '{s2[max(0,i-20):i+20]}'")
                break
        return False

    # Also verify string-level identity of raw text
    if r1.raw_json_text == r2.raw_json_text:
        print(f"  ✅ PASS — raw_json_text is byte-identical!")
    else:
        print(f"  ⚠️  raw_json_text differs (but JSON is semantically equal)")

    return True


def main():
    # Read test data
    with open("test.txt", "r") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    all_passed = True
    for i, line in enumerate(lines):
        passed = test_roundtrip(f"Line {i+1} ({len(line)} chars)", line)
        if not passed:
            all_passed = False

    print(f"\n{'='*60}")
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("💥 SOME TESTS FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()

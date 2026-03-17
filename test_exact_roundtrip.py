#!/usr/bin/env python3
"""Verify exact roundtrip: decode → encode with original → get same string."""
import sys
sys.path.insert(0, ".")
from decoder_core import decode_moveset, encode_to_string

with open("test.txt", "r") as f:
    lines = f.readlines()

original_str = lines[0].split(":", 1)[1].strip()

print(f"Original: {len(original_str)} chars")

# Step 1: Decode
r = decode_moveset(original_str)
assert r.success
print(f"Decoded → {len(r.raw_json_text)} chars JSON, algo={r.detected_algorithm}")
print(f"Original preserved: {r.original_encoded_input == original_str}")

# Step 2: Re-encode with original context (simulating the GUI flow)
enc = encode_to_string(
    r.raw_json_text,
    algorithm=r.detected_algorithm,
    original_encoded=r.original_encoded_input,
    original_raw_json=r.raw_json_text,
)
assert enc.success
print(f"Re-encoded: {enc.encoded_size} chars")
print(f"EXACT MATCH: {enc.encoded_string == original_str}")

if enc.encoded_string == original_str:
    print("\n🎉 PERFECT ROUNDTRIP — byte-identical output!")
else:
    print("\n❌ STILL DIFFERENT")
    print(f"  Original : {original_str[:80]}...")
    print(f"  Encoded  : {enc.encoded_string[:80]}...")

# Also test that editing JSON produces a NEW (re-compressed) output
import json
j = json.loads(r.raw_json_text)
if isinstance(j, dict):
    j["__test_modified__"] = True
modified_text = json.dumps(j, separators=(",", ":"), ensure_ascii=False)

enc2 = encode_to_string(
    modified_text,
    algorithm=r.detected_algorithm,
    original_encoded=r.original_encoded_input,
    original_raw_json=r.raw_json_text,
)
assert enc2.success
print(f"\nModified JSON re-encoded: {enc2.encoded_size} chars")
print(f"Different from original (expected): {enc2.encoded_string != original_str}")

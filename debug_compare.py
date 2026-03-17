#!/usr/bin/env python3
"""Compare original vs re-encoded to find the source of mismatch."""
import json, sys
sys.path.insert(0, ".")
from decoder_core import decode_moveset

with open("test.txt", "r") as f:
    lines = f.readlines()

# Parse the test.txt format
original_str = lines[0].split(":", 1)[1].strip()
reencoded_str = lines[1].split(":", 1)[1].strip()

print(f"Original length : {len(original_str)} chars")
print(f"Re-encoded length: {len(reencoded_str)} chars")
print(f"Strings match    : {original_str == reencoded_str}")
print()

# Decode both
r1 = decode_moveset(original_str)
r2 = decode_moveset(reencoded_str)

print(f"Original algo    : {r1.detected_algorithm}")
print(f"Re-encoded algo  : {r2.detected_algorithm}")
print(f"Original JSON len: {len(r1.raw_json_text)} chars")
print(f"Re-enc JSON len  : {len(r2.raw_json_text)} chars")
print(f"Raw JSON match   : {r1.raw_json_text == r2.raw_json_text}")
print()

# Compare JSON objects
j1 = json.loads(r1.raw_json_text)
j2 = json.loads(r2.raw_json_text)
print(f"JSON obj match   : {j1 == j2}")

if r1.raw_json_text != r2.raw_json_text:
    print("\n--- RAW JSON DIFF ---")
    s1 = r1.raw_json_text
    s2 = r2.raw_json_text
    # Find first difference
    min_len = min(len(s1), len(s2))
    for i in range(min_len):
        if s1[i] != s2[i]:
            start = max(0, i - 50)
            print(f"First diff at char {i}:")
            print(f"  Original : ...{s1[start:i+50]}...")
            print(f"  Re-enc   : ...{s2[start:i+50]}...")
            break
    else:
        if len(s1) != len(s2):
            print(f"Same up to char {min_len}, but lengths differ: {len(s1)} vs {len(s2)}")

if j1 != j2:
    print("\n--- JSON OBJECT DIFF ---")
    # Find differing keys
    def find_diff(a, b, path=""):
        if type(a) != type(b):
            print(f"  Type mismatch at {path}: {type(a).__name__} vs {type(b).__name__}")
            print(f"    Original : {str(a)[:200]}")
            print(f"    Re-enc   : {str(b)[:200]}")
            return
        if isinstance(a, dict):
            for k in set(list(a.keys()) + list(b.keys())):
                if k not in a:
                    print(f"  Missing in original: {path}.{k}")
                elif k not in b:
                    print(f"  Missing in re-encoded: {path}.{k}")
                elif a[k] != b[k]:
                    find_diff(a[k], b[k], f"{path}.{k}")
        elif isinstance(a, list):
            if len(a) != len(b):
                print(f"  List length mismatch at {path}: {len(a)} vs {len(b)}")
            for i in range(min(len(a), len(b))):
                if a[i] != b[i]:
                    find_diff(a[i], b[i], f"{path}[{i}]")
        else:
            if a != b:
                print(f"  Value mismatch at {path}:")
                print(f"    Original : {str(a)[:200]}")
                print(f"    Re-enc   : {str(b)[:200]}")
    find_diff(j1, j2)

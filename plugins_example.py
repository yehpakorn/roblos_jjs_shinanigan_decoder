# Jujutsu Shenanigans — Moveset Decoder Plugin Example
# ─────────────────────────────────────────────────────
# Drop this file next to main.py, then import and register
# your custom decoder before calling decode_moveset().

from decoder_core import register_decoder


# Example: a custom XOR-cipher decoder
def my_xor_decoder(data: bytes) -> bytes:
    """XOR every byte with 0xAA (example custom decoder)."""
    return bytes(b ^ 0xAA for b in data)


# Register it — it will be tried after the built-in decompressors
register_decoder("custom-xor", my_xor_decoder)


# ─────────────────────────────────────────────────────
# Another example: reverse-bytes decoder
def reverse_bytes(data: bytes) -> bytes:
    return data[::-1]


register_decoder("reverse-bytes", reverse_bytes)

"""
decoder_core.py
───────────────
Core decoding pipeline for Jujutsu Shenanigans moveset codes.
Modular, extensible, and safe — will not crash on bad input.
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import logging
import lzma
import struct
import zlib
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("JJS.decoder")

# ──────────────────────────────────────────────────────────────────────────────
# Result Dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class DecodeStep:
    step_name: str
    success: bool
    detail: str
    output_bytes: Optional[bytes] = None
    output_text: Optional[str] = None


@dataclass
class DecodeResult:
    success: bool
    steps: list[DecodeStep] = field(default_factory=list)
    final_bytes: Optional[bytes] = None
    final_text: Optional[str] = None
    detected_type: str = "unknown"          # json | zip | binary | text
    json_data: Optional[dict | list] = None
    zip_entries: Optional[list[str]] = None
    error: Optional[str] = None
    raw_json_text: Optional[str] = None     # original JSON before nested expansion
    detected_algorithm: Optional[str] = None  # compression algo detected during decode
    original_encoded_input: Optional[str] = None  # original encoded string for exact roundtrip

    def log_summary(self) -> str:
        lines = []
        for s in self.steps:
            icon = "OK " if s.success else "ERR"
            lines.append(f"  [{icon}] [{s.step_name}]  {s.detail}")
        lines.append("")
        lines.append(f"  Type detected : {self.detected_type.upper()}")
        if self.zip_entries:
            lines.append(f"  Archive files : {', '.join(self.zip_entries)}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ──────────────────────────────────────────────────────────────────────────────

def _safe(func: Callable, *args, **kwargs):
    """Run a function, returning (result, None) or (None, error_str)."""
    try:
        return func(*args, **kwargs), None
    except Exception as exc:
        return None, str(exc)


def _is_base64(text: str) -> bool:
    """Heuristic: all chars belong to the Base64 alphabet (incl. padding)."""
    import re
    stripped = text.strip().replace("\n", "").replace("\r", "").replace(" ", "")
    return bool(re.fullmatch(r"[A-Za-z0-9+/=_\-]+", stripped))


def _fix_base64_padding(text: str) -> str:
    text = text.strip().replace("\n", "").replace("\r", "").replace(" ", "")
    # Convert URL-safe variant
    text = text.replace("-", "+").replace("_", "/")
    # Restore padding
    remainder = len(text) % 4
    if remainder == 2:
        text += "=="
    elif remainder == 3:
        text += "="
    return text


def _try_json(data: bytes) -> Optional[dict | list]:
    try:
        return json.loads(data.decode("utf-8", errors="replace"))
    except Exception:
        return None


def _try_json_str(text: str) -> Optional[dict | list]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _expand_nested_json(obj, _depth=0):
    """Recursively parse any string values that are valid JSON objects/arrays."""
    if _depth > 10:
        return obj
    if isinstance(obj, dict):
        return {k: _expand_nested_json(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_nested_json(v, _depth + 1) for v in obj]
    if isinstance(obj, str) and len(obj) > 2 and obj.strip()[:1] in ('{', '['):
        try:
            parsed = json.loads(obj)
            return _expand_nested_json(parsed, _depth + 1)
        except (json.JSONDecodeError, ValueError):
            return obj
    return obj


def _is_zip(data: bytes) -> bool:
    return data[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _is_gzip(data: bytes) -> bool:
    return data[:2] == b"\x1f\x8b"


def _is_zstd(data: bytes) -> bool:
    return data[:4] == b"\x28\xb5\x2f\xfd"


def _is_lzma(data: bytes) -> bool:
    return data[:6] == b"\xfd7zXZ\x00"


def _list_zip_entries(data: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return zf.namelist()
    except Exception:
        return []


def _extract_zip(data: bytes, output_dir: str) -> list[str]:
    import os
    extracted = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            out_path = os.path.join(output_dir, name)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with zf.open(name) as src, open(out_path, "wb") as dst:
                dst.write(src.read())
            extracted.append(out_path)
    return extracted


# ──────────────────────────────────────────────────────────────────────────────
# Decompression backends
# ──────────────────────────────────────────────────────────────────────────────

def _decompress_zstd(data: bytes) -> bytes:
    import zstandard as zstd
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(data, max_output_size=512 * 1024 * 1024)


def _decompress_gzip(data: bytes) -> bytes:
    return gzip.decompress(data)


def _decompress_zlib(data: bytes) -> bytes:
    return zlib.decompress(data)


def _decompress_zlib_raw(data: bytes) -> bytes:
    return zlib.decompress(data, -15)


def _decompress_lzma(data: bytes) -> bytes:
    return lzma.decompress(data)


def _decompress_brotli(data: bytes) -> bytes:
    import brotli  # optional
    return brotli.decompress(data)


DECOMPRESSORS: list[tuple[str, Callable]] = [
    ("zstd", _decompress_zstd),
    ("gzip", _decompress_gzip),
    ("zlib", _decompress_zlib),
    ("zlib-raw", _decompress_zlib_raw),
    ("lzma/xz", _decompress_lzma),
]

try:
    import brotli
    DECOMPRESSORS.append(("brotli", _decompress_brotli))
except ImportError:
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Plugin Registry (extensible decoder system)
# ──────────────────────────────────────────────────────────────────────────────

_PLUGIN_DECODERS: list[tuple[str, Callable[[bytes], bytes]]] = []


def register_decoder(name: str, func: Callable[[bytes], bytes]) -> None:
    """Register a custom decompressor plugin."""
    _PLUGIN_DECODERS.append((name, func))
    logger.info(f"Plugin decoder registered: {name}")


# ──────────────────────────────────────────────────────────────────────────────
# Main Decode Pipeline
# ──────────────────────────────────────────────────────────────────────────────

def decode_moveset(raw_input: str, progress_cb: Optional[Callable[[str], None]] = None) -> DecodeResult:
    """
    Full auto-detect decode pipeline.
    progress_cb(message) is called for each step so the GUI can log it live.
    """

    def emit(msg: str):
        logger.info(msg)
        if progress_cb:
            progress_cb(msg)

    result = DecodeResult(success=False)
    text = raw_input.strip()
    result.original_encoded_input = text  # preserve for exact roundtrip

    if not text:
        result.error = "Empty input."
        return result

    emit(f"-> Input length: {len(text):,} characters")

    # ── Step 1: Attempt Base64 decode ─────────────────────────────────────────
    raw_bytes: Optional[bytes] = None

    if _is_base64(text):
        emit(">> Input looks like Base64 - attempting decode...")
        fixed = _fix_base64_padding(text)
        decoded, err = _safe(base64.b64decode, fixed)
        if decoded is not None:
            step = DecodeStep("base64-decode", True, f"Decoded to {len(decoded):,} bytes")
            result.steps.append(step)
            emit(f"  [OK] Base64 -> {len(decoded):,} bytes")
            raw_bytes = decoded
        else:
            result.steps.append(DecodeStep("base64-decode", False, f"Failed: {err}"))
            emit(f"  [ERR] Base64 failed: {err}")
    else:
        emit(">> Input does not appear to be Base64 - treating as raw bytes")

    # If Base64 failed or wasn't applicable, try treating raw text as UTF-8 bytes
    if raw_bytes is None:
        raw_bytes = text.encode("utf-8", errors="replace")
        result.steps.append(DecodeStep("raw-encode", True, "Using raw UTF-8 bytes"))
        emit(f"  [OK] Using raw bytes: {len(raw_bytes):,} bytes")

    # ── Step 2: Magic-byte pre-check ──────────────────────────────────────────
    if _is_zstd(raw_bytes):
        emit(">> Magic bytes: ZSTD stream detected")
    elif _is_gzip(raw_bytes):
        emit(">> Magic bytes: GZIP stream detected")
    elif _is_zip(raw_bytes):
        emit(">> Magic bytes: ZIP archive detected")
    elif _is_lzma(raw_bytes):
        emit(">> Magic bytes: LZMA/XZ stream detected")
    else:
        emit(f">> Magic bytes: {raw_bytes[:8].hex()} (unknown)")

    # ── Step 3: Try all decompressors (+ plugins) ─────────────────────────────
    decompressed: Optional[bytes] = None
    all_decompressors = DECOMPRESSORS + _PLUGIN_DECODERS

    for name, decomp_fn in all_decompressors:
        emit(f"  -> Trying {name} decompression...")
        out, err = _safe(decomp_fn, raw_bytes)
        if out is not None:
            step = DecodeStep(f"decompress-{name}", True, f"-> {len(out):,} bytes")
            result.steps.append(step)
            emit(f"  [OK] [{name}] Success -> {len(out):,} bytes")
            decompressed = out
            result.detected_algorithm = name
            break
        else:
            result.steps.append(DecodeStep(f"decompress-{name}", False, str(err)[:120]))
            emit(f"  [ERR] [{name}] {str(err)[:80]}")

    # ── Step 4: Work with whatever we have ────────────────────────────────────
    working = decompressed if decompressed is not None else raw_bytes

    # Possibly another round of Base64 inside the decompressed payload
    try:
        inner_text = working.decode("utf-8", errors="strict").strip()
        if _is_base64(inner_text) and decompressed is not None:
            emit(">> Decompressed payload looks like Base64 - second-pass decode...")
            fixed2 = _fix_base64_padding(inner_text)
            decoded2, err2 = _safe(base64.b64decode, fixed2)
            if decoded2:
                emit(f"  [OK] Second-pass Base64 -> {len(decoded2):,} bytes")
                result.steps.append(DecodeStep("base64-2nd-pass", True, f"{len(decoded2):,} bytes"))
                # Try decompressing again
                for name2, decomp_fn2 in all_decompressors:
                    out2, err2b = _safe(decomp_fn2, decoded2)
                    if out2 is not None:
                        emit(f"  [OK] 2nd-pass [{name2}] -> {len(out2):,} bytes")
                        result.steps.append(DecodeStep(f"2nd-decompress-{name2}", True, f"{len(out2):,} bytes"))
                        working = out2
                        break
                else:
                    working = decoded2
    except UnicodeDecodeError:
        pass

    result.final_bytes = working

    # ── Step 5: Type detection ─────────────────────────────────────────────────
    json_obj = _try_json(working)
    if json_obj is not None:
        result.detected_type = "json"
        # Store the raw (unexpanded) JSON for faithful roundtrip re-encoding
        result.raw_json_text = json.dumps(json_obj, separators=(",", ":"), ensure_ascii=False)
        result.json_data = json_obj
        # Expand nested JSON strings for display only
        expanded = _expand_nested_json(json_obj)
        result.final_text = json.dumps(expanded, indent=2, ensure_ascii=False)
        result.steps.append(DecodeStep("type-detect", True, "JSON detected and parsed (nested strings expanded for display)"))
        emit("  -> Type: JSON - pretty-printing (with nested expansion)...")

    elif _is_zip(working):
        result.detected_type = "zip"
        result.zip_entries = _list_zip_entries(working)
        result.steps.append(DecodeStep("type-detect", True, f"ZIP archive with {len(result.zip_entries)} entries"))
        emit(f"  -> Type: ZIP archive ({len(result.zip_entries)} files)")

    else:
        # Try decoding as text
        try:
            decoded_text = working.decode("utf-8")
            result.detected_type = "text"
            result.final_text = decoded_text
            result.steps.append(DecodeStep("type-detect", True, "Plain UTF-8 text"))
            emit("  -> Type: UTF-8 text")
        except UnicodeDecodeError:
            result.detected_type = "binary"
            result.steps.append(DecodeStep("type-detect", True, "Binary data"))
            emit("  -> Type: Binary data")

    result.success = True
    emit("-> Decode pipeline complete.")
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Hex viewer helper
# ──────────────────────────────────────────────────────────────────────────────

def bytes_to_hex_view(data: bytes, cols: int = 16, max_rows: int = 256) -> str:
    """Return a classic hex+ASCII dump string."""
    lines = []
    for i in range(0, min(len(data), cols * max_rows), cols):
        chunk = data[i:i + cols]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08X}  {hex_part:<{cols * 3}}  {asc_part}")
    if len(data) > cols * max_rows:
        lines.append(f"... ({len(data):,} total bytes, truncated at {cols * max_rows * cols:,})")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Save helpers
# ──────────────────────────────────────────────────────────────────────────────

def save_json(result: DecodeResult, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        if result.final_text is not None:
            f.write(result.final_text)
        elif result.json_data is not None:
            json.dump(result.json_data, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError("No text/JSON output to save.")


def save_binary(result: DecodeResult, path: str) -> None:
    if result.final_bytes is None:
        raise ValueError("No binary data to save.")
    with open(path, "wb") as f:
        f.write(result.final_bytes)


def extract_archive(result: DecodeResult, output_dir: str) -> list[str]:
    if result.detected_type != "zip" or result.final_bytes is None:
        raise ValueError("Result is not a ZIP archive.")
    return _extract_zip(result.final_bytes, output_dir)


# ──────────────────────────────────────────────────────────────────────────────
# Encode Pipeline  (JSON / text / binary  →  compressed + Base64 string)
# ──────────────────────────────────────────────────────────────────────────────

COMPRESSION_ALGORITHMS = ["zlib", "gzip", "zstd", "lzma"]


@dataclass
class EncodeResult:
    success: bool
    algorithm: str = ""
    encoded_string: str = ""
    original_size: int = 0
    compressed_size: int = 0
    encoded_size: int = 0
    ratio: float = 0.0
    error: Optional[str] = None

    @property
    def summary(self) -> str:
        if not self.success:
            return f"Encode failed: {self.error}"
        return (
            f"  Algorithm      :  {self.algorithm.upper()}\n"
            f"  Original size  :  {self.original_size:,} bytes\n"
            f"  Compressed     :  {self.compressed_size:,} bytes\n"
            f"  Encoded string :  {self.encoded_size:,} chars\n"
            f"  Ratio          :  {self.ratio:.1f}% of original\n"
        )


def _compress_zlib(data: bytes, level: int = 9) -> bytes:
    return zlib.compress(data, level)


def _compress_gzip(data: bytes, level: int = 9) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=level) as f:
        f.write(data)
    return buf.getvalue()


def _compress_zstd(data: bytes, level: int = 19) -> bytes:
    import zstandard as zstd
    cctx = zstd.ZstdCompressor(level=level)
    return cctx.compress(data)


def _compress_lzma(data: bytes) -> bytes:
    return lzma.compress(data, preset=9)


COMPRESSORS: dict = {
    "zlib": _compress_zlib,
    "gzip": _compress_gzip,
    "zstd": _compress_zstd,
    "lzma": _compress_lzma,
}


def encode_to_string(
    input_text: str,
    algorithm: str = "zstd",
    progress_cb=None,
    original_encoded: Optional[str] = None,
    original_raw_json: Optional[str] = None,
) -> "EncodeResult":
    """
    Encode JSON (or any text) into a compressed + Base64 moveset string.
    Steps: validate JSON → UTF-8 bytes → compress → Base64.
    """

    def emit(msg: str):
        logger.info(msg)
        if progress_cb:
            progress_cb(msg)

    result = EncodeResult(success=False, algorithm=algorithm)

    if not input_text.strip():
        result.error = "Input is empty."
        return result

    algorithm = algorithm.lower()
    if algorithm not in COMPRESSORS:
        result.error = f"Unknown algorithm '{algorithm}'. Choose: {', '.join(COMPRESSORS)}"
        return result

    emit(f"{'-'*58}")
    emit(f"-> Starting encode (algorithm: {algorithm.upper()})")

    # Step 1: Validate / minify JSON if applicable
    try:
        parsed = json.loads(input_text)
        canonical = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
        emit(f"  [OK] Valid JSON - minified to {len(canonical):,} chars")
        raw_bytes = canonical.encode("utf-8")

        # If the JSON content is unchanged from the original decode, return the
        # original encoded string to guarantee byte-identical roundtrip
        if original_encoded and original_raw_json and canonical == original_raw_json:
            emit("  >> JSON unchanged from original - reusing original encoded string")
            result.original_size = len(raw_bytes)
            result.encoded_string = original_encoded
            result.encoded_size = len(original_encoded)
            result.compressed_size = 0
            result.ratio = 0.0
            result.success = True
            emit(f"  [OK] Original encoded string: {result.encoded_size:,} chars")
            emit("-> Encode complete (exact roundtrip).")
            return result
    except json.JSONDecodeError:
        emit("  >> Not JSON - encoding as plain UTF-8 text")
        raw_bytes = input_text.encode("utf-8")

    result.original_size = len(raw_bytes)
    emit(f"  [OK] Raw bytes: {result.original_size:,}")

    # Step 2: Compress
    compress_fn = COMPRESSORS[algorithm]
    compressed, err = _safe(compress_fn, raw_bytes)
    if compressed is None:
        result.error = f"Compression failed ({algorithm}): {err}"
        emit(f"  [ERR] {result.error}")
        return result

    result.compressed_size = len(compressed)
    emit(f"  [OK] Compressed ({algorithm}): {result.compressed_size:,} bytes")

    # Step 3: Base64 encode
    encoded_bytes, err2 = _safe(base64.b64encode, compressed)
    if encoded_bytes is None:
        result.error = f"Base64 encoding failed: {err2}"
        return result

    result.encoded_string = encoded_bytes.decode("ascii")
    result.encoded_size = len(result.encoded_string)
    result.ratio = (result.compressed_size / result.original_size * 100) if result.original_size else 0.0

    emit(f"  [OK] Base64 encoded: {result.encoded_size:,} chars")
    emit(f"  -> Compression ratio: {result.ratio:.1f}% of original")
    emit("-> Encode complete.")

    result.success = True
    return result


def encode_file_to_string(
    file_path: str,
    algorithm: str = "zstd",
    progress_cb=None,
) -> "EncodeResult":
    """Read a JSON/text file and encode it to a moveset code string."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        r = EncodeResult(success=False, algorithm=algorithm)
        r.error = str(exc)
        return r
    return encode_to_string(content, algorithm=algorithm, progress_cb=progress_cb)

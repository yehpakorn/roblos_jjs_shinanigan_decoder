/**
 * decoder_core.js
 * ───────────────
 * Core decoding/encoding pipeline for Jujutsu Shenanigans moveset codes.
 * Direct port of decoder_core.py to browser JavaScript.
 *
 * Dependencies (loaded via CDN in index.html):
 *   - pako        (gzip / zlib / zlib-raw)
 *   - fzstd       (zstandard)
 *   - LZMA        (lzma-js)
 */

// ──────────────────────────────────────────────────────────────────────────────
// Result Classes
// ──────────────────────────────────────────────────────────────────────────────

class DecodeStep {
  constructor(stepName, success, detail) {
    this.stepName = stepName;
    this.success = success;
    this.detail = detail;
  }
}

class DecodeResult {
  constructor() {
    this.success = false;
    this.steps = [];
    this.finalBytes = null;       // Uint8Array
    this.finalText = null;
    this.detectedType = "unknown"; // json | zip | binary | text
    this.jsonData = null;
    this.zipEntries = null;
    this.error = null;
    this.rawJsonText = null;       // original JSON before nested expansion
    this.detectedAlgorithm = null;
    this.originalEncodedInput = null;
  }

  logSummary() {
    const lines = [];
    for (const s of this.steps) {
      const icon = s.success ? "OK " : "ERR";
      lines.push(`  [${icon}] [${s.stepName}]  ${s.detail}`);
    }
    lines.push("");
    lines.push(`  Type detected : ${this.detectedType.toUpperCase()}`);
    if (this.zipEntries) {
      lines.push(`  Archive files : ${this.zipEntries.join(", ")}`);
    }
    return lines.join("\n");
  }
}

class EncodeResult {
  constructor() {
    this.success = false;
    this.algorithm = "";
    this.encodedString = "";
    this.originalSize = 0;
    this.compressedSize = 0;
    this.encodedSize = 0;
    this.ratio = 0.0;
    this.error = null;
  }

  get summary() {
    if (!this.success) return `Encode failed: ${this.error}`;
    return (
      `  Algorithm      :  ${this.algorithm.toUpperCase()}\n` +
      `  Original size  :  ${this.originalSize.toLocaleString()} bytes\n` +
      `  Compressed     :  ${this.compressedSize.toLocaleString()} bytes\n` +
      `  Encoded string :  ${this.encodedSize.toLocaleString()} chars\n` +
      `  Ratio          :  ${this.ratio.toFixed(1)}% of original\n`
    );
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Helper Utilities
// ──────────────────────────────────────────────────────────────────────────────

function _safe(func, ...args) {
  try {
    return [func(...args), null];
  } catch (e) {
    return [null, e.message || String(e)];
  }
}

function _isBase64(text) {
  const stripped = text.trim().replace(/[\n\r\s]/g, "");
  return /^[A-Za-z0-9+/=_\-]+$/.test(stripped) && stripped.length > 0;
}

function _fixBase64Padding(text) {
  let t = text.trim().replace(/[\n\r\s]/g, "");
  // Convert URL-safe variant
  t = t.replace(/-/g, "+").replace(/_/g, "/");
  // Restore padding
  const remainder = t.length % 4;
  if (remainder === 2) t += "==";
  else if (remainder === 3) t += "=";
  return t;
}

/** Decode base64 string to Uint8Array */
function base64Decode(b64) {
  const binStr = atob(b64);
  const bytes = new Uint8Array(binStr.length);
  for (let i = 0; i < binStr.length; i++) {
    bytes[i] = binStr.charCodeAt(i);
  }
  return bytes;
}

/** Encode Uint8Array to base64 string */
function base64Encode(bytes) {
  let binStr = "";
  for (let i = 0; i < bytes.length; i++) {
    binStr += String.fromCharCode(bytes[i]);
  }
  return btoa(binStr);
}

/** Decode Uint8Array to UTF-8 string */
function uint8ToStr(bytes) {
  return new TextDecoder("utf-8").decode(bytes);
}

/** Encode string to Uint8Array (UTF-8) */
function strToUint8(str) {
  return new TextEncoder().encode(str);
}

function _tryJson(data) {
  try {
    return JSON.parse(uint8ToStr(data));
  } catch {
    return null;
  }
}

function _tryJsonStr(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function _expandNestedJson(obj, depth = 0) {
  if (depth > 10) return obj;
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    const result = {};
    for (const [k, v] of Object.entries(obj)) {
      result[k] = _expandNestedJson(v, depth + 1);
    }
    return result;
  }
  if (Array.isArray(obj)) {
    return obj.map(v => _expandNestedJson(v, depth + 1));
  }
  if (typeof obj === "string" && obj.length > 2) {
    const first = obj.trim()[0];
    if (first === "{" || first === "[") {
      try {
        const parsed = JSON.parse(obj);
        return _expandNestedJson(parsed, depth + 1);
      } catch {
        return obj;
      }
    }
  }
  return obj;
}

function _isZip(data) {
  if (data.length < 4) return false;
  return (
    (data[0] === 0x50 && data[1] === 0x4b && data[2] === 0x03 && data[3] === 0x04) ||
    (data[0] === 0x50 && data[1] === 0x4b && data[2] === 0x05 && data[3] === 0x06) ||
    (data[0] === 0x50 && data[1] === 0x4b && data[2] === 0x07 && data[3] === 0x08)
  );
}

function _isGzip(data) {
  return data.length >= 2 && data[0] === 0x1f && data[1] === 0x8b;
}

function _isZstd(data) {
  return data.length >= 4 && data[0] === 0x28 && data[1] === 0xb5 && data[2] === 0x2f && data[3] === 0xfd;
}

function _isLzma(data) {
  return data.length >= 6 &&
    data[0] === 0xfd && data[1] === 0x37 && data[2] === 0x7a &&
    data[3] === 0x58 && data[4] === 0x5a && data[5] === 0x00;
}

// ──────────────────────────────────────────────────────────────────────────────
// Decompression Backends
// ──────────────────────────────────────────────────────────────────────────────

// Zstd Initialization (Synchronous execution for JS bundle)
let zstdSimple = null;
if (typeof window !== "undefined" && window.ZstdCodec) {
  window.ZstdCodec.run(zstd => {
    zstdSimple = new zstd.Simple();
  });
}

function _decompressZstd(data) {
  if (!zstdSimple) throw new Error("zstd library not loaded or initialized yet. Try again in a moment.");
  return zstdSimple.decompress(data);
}

function _decompressGzip(data) {
  return pako.ungzip(data);
}

function _decompressZlib(data) {
  return pako.inflate(data);
}

function _decompressZlibRaw(data) {
  return pako.inflateRaw(data);
}

function _decompressLzma(data) {
  if (typeof LZMA === "undefined") throw new Error("LZMA library not loaded");
  // lzma-js expects a regular array
  const arr = Array.from(data);
  const result = LZMA.decompress(arr);
  if (typeof result === "string") {
    return strToUint8(result);
  }
  return new Uint8Array(result);
}

const DECOMPRESSORS = [
  ["zstd", _decompressZstd],
  ["gzip", _decompressGzip],
  ["zlib", _decompressZlib],
  ["zlib-raw", _decompressZlibRaw],
  ["lzma/xz", _decompressLzma],
];

// ──────────────────────────────────────────────────────────────────────────────
// Main Decode Pipeline
// ──────────────────────────────────────────────────────────────────────────────

function decodeMoveset(rawInput, progressCb = null) {
  function emit(msg) {
    if (progressCb) progressCb(msg);
  }

  const result = new DecodeResult();
  const text = rawInput.trim();
  result.originalEncodedInput = text;

  if (!text) {
    result.error = "Empty input.";
    return result;
  }

  emit(`-> Input length: ${text.length.toLocaleString()} characters`);

  // ── Step 1: Attempt Base64 decode
  let rawBytes = null;

  if (_isBase64(text)) {
    emit(">> Input looks like Base64 - attempting decode...");
    const fixed = _fixBase64Padding(text);
    const [decoded, err] = _safe(base64Decode, fixed);
    if (decoded !== null) {
      const step = new DecodeStep("base64-decode", true, `Decoded to ${decoded.length.toLocaleString()} bytes`);
      result.steps.push(step);
      emit(`  [OK] Base64 -> ${decoded.length.toLocaleString()} bytes`);
      rawBytes = decoded;
    } else {
      result.steps.push(new DecodeStep("base64-decode", false, `Failed: ${err}`));
      emit(`  [ERR] Base64 failed: ${err}`);
    }
  } else {
    emit(">> Input does not appear to be Base64 - treating as raw bytes");
  }

  // If Base64 failed or wasn't applicable, try treating raw text as UTF-8 bytes
  if (rawBytes === null) {
    rawBytes = strToUint8(text);
    result.steps.push(new DecodeStep("raw-encode", true, "Using raw UTF-8 bytes"));
    emit(`  [OK] Using raw bytes: ${rawBytes.length.toLocaleString()} bytes`);
  }

  // ── Step 2: Magic-byte pre-check
  if (_isZstd(rawBytes)) {
    emit(">> Magic bytes: ZSTD stream detected");
  } else if (_isGzip(rawBytes)) {
    emit(">> Magic bytes: GZIP stream detected");
  } else if (_isZip(rawBytes)) {
    emit(">> Magic bytes: ZIP archive detected");
  } else if (_isLzma(rawBytes)) {
    emit(">> Magic bytes: LZMA/XZ stream detected");
  } else {
    const hex = Array.from(rawBytes.slice(0, 8)).map(b => b.toString(16).padStart(2, "0")).join("");
    emit(`>> Magic bytes: ${hex} (unknown)`);
  }

  // ── Step 3: Try all decompressors
  let decompressed = null;

  for (const [name, decompFn] of DECOMPRESSORS) {
    emit(`  -> Trying ${name} decompression...`);
    const [out, err] = _safe(decompFn, rawBytes);
    if (out !== null) {
      const step = new DecodeStep(`decompress-${name}`, true, `-> ${out.length.toLocaleString()} bytes`);
      result.steps.push(step);
      emit(`  [OK] [${name}] Success -> ${out.length.toLocaleString()} bytes`);
      decompressed = out;
      result.detectedAlgorithm = name;
      break;
    } else {
      const errStr = String(err).substring(0, 120);
      result.steps.push(new DecodeStep(`decompress-${name}`, false, errStr));
      emit(`  [ERR] [${name}] ${String(err).substring(0, 80)}`);
    }
  }

  // ── Step 4: Work with whatever we have
  let working = decompressed !== null ? decompressed : rawBytes;

  // Possibly another round of Base64 inside the decompressed payload
  try {
    const innerText = uint8ToStr(working).trim();
    if (_isBase64(innerText) && decompressed !== null) {
      emit(">> Decompressed payload looks like Base64 - second-pass decode...");
      const fixed2 = _fixBase64Padding(innerText);
      const [decoded2, err2] = _safe(base64Decode, fixed2);
      if (decoded2) {
        emit(`  [OK] Second-pass Base64 -> ${decoded2.length.toLocaleString()} bytes`);
        result.steps.push(new DecodeStep("base64-2nd-pass", true, `${decoded2.length.toLocaleString()} bytes`));
        let found2nd = false;
        for (const [name2, decompFn2] of DECOMPRESSORS) {
          const [out2, err2b] = _safe(decompFn2, decoded2);
          if (out2 !== null) {
            emit(`  [OK] 2nd-pass [${name2}] -> ${out2.length.toLocaleString()} bytes`);
            result.steps.push(new DecodeStep(`2nd-decompress-${name2}`, true, `${out2.length.toLocaleString()} bytes`));
            working = out2;
            found2nd = true;
            break;
          }
        }
        if (!found2nd) {
          working = decoded2;
        }
      }
    }
  } catch {
    // ignore unicode decode errors
  }

  result.finalBytes = working;

  // ── Step 5: Type detection
  const jsonObj = _tryJson(working);
  if (jsonObj !== null) {
    result.detectedType = "json";
    result.rawJsonText = JSON.stringify(jsonObj);
    result.jsonData = jsonObj;
    const expanded = _expandNestedJson(jsonObj);
    result.finalText = JSON.stringify(expanded, null, 2);
    result.steps.push(new DecodeStep("type-detect", true, "JSON detected and parsed (nested strings expanded for display)"));
    emit("  -> Type: JSON - pretty-printing (with nested expansion)...");
  } else if (_isZip(working)) {
    result.detectedType = "zip";
    result.zipEntries = ["(ZIP viewing not supported in browser)"];
    result.steps.push(new DecodeStep("type-detect", true, "ZIP archive detected"));
    emit("  -> Type: ZIP archive");
  } else {
    try {
      const decodedText = uint8ToStr(working);
      // check if it's valid by re-encoding
      const reencoded = strToUint8(decodedText);
      result.detectedType = "text";
      result.finalText = decodedText;
      result.steps.push(new DecodeStep("type-detect", true, "Plain UTF-8 text"));
      emit("  -> Type: UTF-8 text");
    } catch {
      result.detectedType = "binary";
      result.steps.push(new DecodeStep("type-detect", true, "Binary data"));
      emit("  -> Type: Binary data");
    }
  }

  result.success = true;
  emit("-> Decode pipeline complete.");
  return result;
}

// ──────────────────────────────────────────────────────────────────────────────
// Hex Viewer Helper
// ──────────────────────────────────────────────────────────────────────────────

function bytesToHexView(data, cols = 16, maxRows = 256) {
  const lines = [];
  const maxBytes = Math.min(data.length, cols * maxRows);
  for (let i = 0; i < maxBytes; i += cols) {
    const chunk = data.slice(i, i + cols);
    const hexPart = Array.from(chunk).map(b => b.toString(16).toUpperCase().padStart(2, "0")).join(" ");
    const ascPart = Array.from(chunk).map(b => (b >= 32 && b < 127) ? String.fromCharCode(b) : ".").join("");
    const offset = i.toString(16).toUpperCase().padStart(8, "0");
    lines.push(`${offset}  ${hexPart.padEnd(cols * 3, " ")}  ${ascPart}`);
  }
  if (data.length > cols * maxRows) {
    lines.push(`... (${data.length.toLocaleString()} total bytes, truncated)`);
  }
  return lines.join("\n");
}

// ──────────────────────────────────────────────────────────────────────────────
// Compression Backends (for encoding)
// ──────────────────────────────────────────────────────────────────────────────

const COMPRESSION_ALGORITHMS = ["zlib", "gzip", "zstd", "lzma"];

function _compressZlib(data) {
  return pako.deflate(data, { level: 9 });
}

function _compressGzip(data) {
  return pako.gzip(data, { level: 9 });
}

function _compressZstd(data) {
  if (!zstdSimple) throw new Error("zstd library not loaded or initialized yet. Try again in a moment.");
  return zstdSimple.compress(data);
}

function _compressLzma(data) {
  if (typeof LZMA === "undefined") throw new Error("LZMA library not loaded");
  const result = LZMA.compress(Array.from(data), 9);
  return new Uint8Array(result);
}

const COMPRESSORS = {
  zlib: _compressZlib,
  gzip: _compressGzip,
  zstd: _compressZstd,
  lzma: _compressLzma,
};

// ──────────────────────────────────────────────────────────────────────────────
// Encode Pipeline
// ──────────────────────────────────────────────────────────────────────────────

function encodeToString(inputText, algorithm = "zstd", progressCb = null, originalEncoded = null, originalRawJson = null) {
  function emit(msg) {
    if (progressCb) progressCb(msg);
  }

  const result = new EncodeResult();
  result.algorithm = algorithm;

  if (!inputText.trim()) {
    result.error = "Input is empty.";
    return result;
  }

  algorithm = algorithm.toLowerCase();
  if (!COMPRESSORS[algorithm]) {
    result.error = `Unknown algorithm '${algorithm}'. Choose: ${Object.keys(COMPRESSORS).join(", ")}`;
    return result;
  }

  emit("-".repeat(58));
  emit(`-> Starting encode (algorithm: ${algorithm.toUpperCase()})`);

  // Step 1: Validate / minify JSON if applicable
  let rawBytes;
  try {
    const parsed = JSON.parse(inputText);
    const canonical = JSON.stringify(parsed);
    emit(`  [OK] Valid JSON - minified to ${canonical.length.toLocaleString()} chars`);
    rawBytes = strToUint8(canonical);

    // Roundtrip check
    if (originalEncoded && originalRawJson && canonical === originalRawJson) {
      emit("  >> JSON unchanged from original - reusing original encoded string");
      result.originalSize = rawBytes.length;
      result.encodedString = originalEncoded;
      result.encodedSize = originalEncoded.length;
      result.compressedSize = 0;
      result.ratio = 0.0;
      result.success = true;
      emit(`  [OK] Original encoded string: ${result.encodedSize.toLocaleString()} chars`);
      emit("-> Encode complete (exact roundtrip).");
      return result;
    }
  } catch {
    emit("  >> Not JSON - encoding as plain UTF-8 text");
    rawBytes = strToUint8(inputText);
  }

  result.originalSize = rawBytes.length;
  emit(`  [OK] Raw bytes: ${result.originalSize.toLocaleString()}`);

  // Step 2: Compress
  const compressFn = COMPRESSORS[algorithm];
  const [compressed, err] = _safe(compressFn, rawBytes);
  if (compressed === null) {
    result.error = `Compression failed (${algorithm}): ${err}`;
    emit(`  [ERR] ${result.error}`);
    return result;
  }

  result.compressedSize = compressed.length;
  emit(`  [OK] Compressed (${algorithm}): ${result.compressedSize.toLocaleString()} bytes`);

  // Step 3: Base64 encode
  const [encodedStr, err2] = _safe(base64Encode, compressed);
  if (encodedStr === null) {
    result.error = `Base64 encoding failed: ${err2}`;
    return result;
  }

  result.encodedString = encodedStr;
  result.encodedSize = encodedStr.length;
  result.ratio = result.originalSize ? (result.compressedSize / result.originalSize * 100) : 0.0;

  emit(`  [OK] Base64 encoded: ${result.encodedSize.toLocaleString()} chars`);
  emit(`  -> Compression ratio: ${result.ratio.toFixed(1)}% of original`);
  emit("-> Encode complete.");

  result.success = true;
  return result;
}

// Export for use in app.js
if (typeof window !== "undefined") {
  window.DecoderCore = {
    decodeMoveset,
    encodeToString,
    bytesToHexView,
    DecodeResult,
    EncodeResult,
    COMPRESSION_ALGORITHMS,
  };
}

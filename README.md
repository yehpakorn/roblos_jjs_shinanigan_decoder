# JJS Moveset Decoder

This tool is developed to enable users to read and interpret exported code from JJS Shenanigans (Roblox). Its primary purpose is to provide insight into the structure and encoding format of moveset data, allowing users to better understand how such data is represented and utilized within the system.

The encoding methodology implemented in this tool is inspired by the approach introduced by @echo0v, particularly in terms of how raw JSON data is transformed into an encoded format suitable for use within the application.

As part of the workflow, a sample file (test.txt) is generated to demonstrate the encoding process. This file is produced by first submitting a structured JSON input to ChatGPT, which returns a formatted JSON response that adheres to the required schema. The resulting JSON is then processed and encoded by this tool into the final export format compatible with JJS Shenanigans.

Overall, this tool serves both as a utility for decoding and analyzing exported moveset data, and as a reference system for users seeking inspiration or guidance in designing and encoding their own custom movesets.

---

## 1. Environment Setup

### Requirements

| Dependency       | Purpose                        |
|------------------|--------------------------------|
| Python 3.10+     | Runtime                        |
| `customtkinter`  | Dark-mode GUI framework        |
| `zstandard`      | Zstandard decompression        |
| `pyperclip`      | System clipboard access        |
| `Pillow`         | Image support (CustomTkinter)  |

Built-in stdlib modules used: `base64`, `zlib`, `gzip`, `lzma`, `json`, `zipfile`.

### Installation

```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

Or install manually:

```bash
pip install customtkinter zstandard pyperclip Pillow
```

### Platform Support

| OS                | Status          |
|-------------------|-----------------|
| Windows 10/11     | Fully supported |
| macOS 12+         | Fully supported |
| Linux (Ubuntu)    | Fully supported |

---

## 2. Execution

### GUI Mode

```bash
python main.py
```

Opens a dark-mode desktop window with:

- **Input panel** -- paste encoded moveset code or load from file.
- **Decode / Encode controls** -- one-click operations with algorithm selection.
- **Output tabs** -- JSON/Text viewer, hex dump, pipeline summary.
- **Pipeline log** -- real-time decode/encode step trace.

### CLI Mode

```bash
python main.py --cli [OPTIONS]
```

| Flag                    | Description                              |
|-------------------------|------------------------------------------|
| `--input FILE`, `-i`    | Path to input file                       |
| `--output FILE`, `-o`   | Path to output file                      |
| `--binary`              | Save output as binary instead of JSON    |
| `--extract DIR`         | Extract ZIP archive to directory         |
| `--stdin`               | Read input from stdin                    |
| `--verbose`, `-v`       | Enable debug-level logging               |

**Examples:**

```bash
# Decode file to JSON
python main.py --cli -i moveset_code.txt -o decoded.json

# Decode to binary
python main.py --cli -i moveset_code.txt -o output.bin --binary

# Extract archive contents
python main.py --cli -i moveset_code.txt --extract ./extracted/

# Pipe from stdin
echo "KLUv..." | python main.py --cli --stdin

# Verbose output
python main.py --cli -i moveset_code.txt -v
```

### Logging

A file `jjs_decoder.log` is written alongside `main.py` capturing all activity at DEBUG level.

---

## 3. Algorithm Logic

### Decode Pipeline

The decoder runs an ordered auto-detection pipeline. Each step is attempted in sequence; the first successful decompression wins.

| Step | Operation                    | Detail                                        |
|------|------------------------------|-----------------------------------------------|
| 1    | Base64 detection             | Heuristic character-set check                 |
| 2    | Base64 decode                | Standard + URL-safe variants, padding fix     |
| 3    | Magic byte inspection        | Identifies zstd, gzip, zip, lzma headers      |
| 4    | Decompress: zstd             | `zstandard` library                           |
| 5    | Decompress: gzip             | `gzip.decompress`                             |
| 6    | Decompress: zlib             | `zlib.decompress`                             |
| 7    | Decompress: zlib-raw         | `zlib.decompress(data, -15)` (deflate)        |
| 8    | Decompress: lzma/xz          | `lzma.decompress`                             |
| 9    | Second-pass Base64           | Re-check after decompression                  |
| 10   | Type detection               | JSON parse, ZIP signature, UTF-8 probe        |

### Encode Pipeline

| Step | Operation                    | Detail                                        |
|------|------------------------------|-----------------------------------------------|
| 1    | JSON validation              | Parse and minify (compact separators)         |
| 2    | Roundtrip check              | If JSON unchanged, return original string     |
| 3    | Compress                     | Selected algorithm at max level               |
| 4    | Base64 encode                | Standard Base64 output                        |

### Supported Algorithms

| Algorithm   | Decode | Encode | Library        |
|-------------|--------|--------|----------------|
| zstd        | Yes    | Yes    | `zstandard`    |
| gzip        | Yes    | Yes    | `gzip` (stdlib)|
| zlib        | Yes    | Yes    | `zlib` (stdlib)|
| zlib-raw    | Yes    | --     | `zlib` (stdlib)|
| lzma/xz     | Yes    | Yes    | `lzma` (stdlib)|
| brotli      | Yes    | --     | `brotli` (opt) |

### Magic Byte Signatures

| Format | Bytes (hex)          |
|--------|----------------------|
| zstd   | `28 B5 2F FD`       |
| gzip   | `1F 8B`             |
| ZIP    | `50 4B 03 04`       |
| lzma   | `FD 37 7A 58 5A 00` |

---

## 4. Extensibility

### Plugin System

Custom decoders integrate into the pipeline without modifying core files.

**API:**

```python
from decoder_core import register_decoder

def my_decoder(data: bytes) -> bytes:
    """Receive raw bytes, return decompressed bytes."""
    # implementation
    return data

register_decoder("my-decoder", my_decoder)
```

**Requirements:**

- Import and register before calling `decode_moveset()`.
- The function signature must be `(bytes) -> bytes`.
- Registered decoders are appended after built-in algorithms in the pipeline.
- On failure (exception), the pipeline moves to the next decoder.

**Example:**

See `plugins_example.py` for a complete working example.

### File Structure

```
jjs/
  main.py              Entry point (GUI + CLI)
  gui_app.py           CustomTkinter GUI
  decoder_core.py      Decode/encode pipeline
  plugins_example.py   Plugin system example
  requirements.txt     Python dependencies
  README.md            This file
```

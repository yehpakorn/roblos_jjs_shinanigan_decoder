#!/usr/bin/env python3
"""
main.py  ─  Jujutsu Shenanigans Moveset Decoder
────────────────────────────────────────────────
Launches the GUI by default.
Pass --cli to run in headless / automation mode.

Usage (GUI):
    python main.py

Usage (CLI):
    python main.py --cli --input code.txt --output decoded.json
    python main.py --cli --input code.txt --output decoded.bin --binary
    python main.py --cli --input code.txt --extract ./extracted/
    echo "KLUv..." | python main.py --cli --stdin
"""

from __future__ import annotations

import argparse
import json
import logging
import sys


# ──────────────────────────────────────────────────────────────────────────────
# Logging setup (file + console)
# ──────────────────────────────────────────────────────────────────────────────

def _setup_root_logging(verbose: bool = False):
    root = logging.getLogger("JJS")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    root.addHandler(ch)

    try:
        fh = logging.FileHandler("jjs_decoder.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# CLI mode
# ──────────────────────────────────────────────────────────────────────────────

def run_cli(args: argparse.Namespace) -> int:
    from decoder_core import decode_moveset, save_json, save_binary, extract_archive

    _setup_root_logging(verbose=args.verbose)
    log = logging.getLogger("JJS.cli")

    # ── Read input ────────────────────────────────────────────────────────────
    if args.stdin:
        log.info("Reading from stdin…")
        raw = sys.stdin.read()
    elif args.input:
        log.info(f"Reading from file: {args.input}")
        try:
            with open(args.input, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except FileNotFoundError:
            print(f"ERROR: File not found: {args.input}", file=sys.stderr)
            return 1
    else:
        print("ERROR: Provide --input FILE or --stdin", file=sys.stderr)
        return 1

    # ── Decode ────────────────────────────────────────────────────────────────
    result = decode_moveset(raw)

    if not result.success:
        print(f"DECODE FAILED: {result.error}", file=sys.stderr)
        return 2

    print(f"\n✅  Decoded successfully — type: {result.detected_type.upper()}")
    print(result.log_summary())

    # ── Output ────────────────────────────────────────────────────────────────
    if args.extract:
        extracted = extract_archive(result, args.extract)
        print(f"📦  Extracted {len(extracted)} files to: {args.extract}")
        return 0

    if args.binary and args.output:
        save_binary(result, args.output)
        print(f"💾  Binary saved → {args.output}")
        return 0

    if args.output:
        save_json(result, args.output)
        print(f"💾  JSON saved → {args.output}")
        return 0

    # Print to stdout if no output path given
    if result.final_text:
        print("\n" + "─" * 60)
        print(result.final_text)
    else:
        print(f"\n(Binary output — {len(result.final_bytes or b'')} bytes. Use --output to save.)")

    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="jjs-decoder",
        description="Jujutsu Shenanigans Moveset Decoder — reverse-engineer encoded moveset codes",
    )
    parser.add_argument("--cli", action="store_true", help="Run in CLI / headless mode (no GUI)")
    parser.add_argument("--input", "-i", metavar="FILE", help="Path to input file (CLI mode)")
    parser.add_argument("--output", "-o", metavar="FILE", help="Path to output file (CLI mode)")
    parser.add_argument("--binary", action="store_true", help="Save as binary instead of JSON (CLI mode)")
    parser.add_argument("--extract", metavar="DIR", help="Extract archive to directory (CLI mode)")
    parser.add_argument("--stdin", action="store_true", help="Read input from stdin (CLI mode)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.cli:
        sys.exit(run_cli(args))
    else:
        # GUI mode
        _setup_root_logging(verbose=args.verbose)
        try:
            import customtkinter  # noqa — fail fast with a clear message
        except Exception as _ctk_err:
            import traceback
            print(
                f"\n❌  Failed to import customtkinter: {type(_ctk_err).__name__}: {_ctk_err}\n",
                file=sys.stderr,
            )
            traceback.print_exc()
            print(
                "\n   Possible fixes:\n"
                "   1. Make sure you launched Python from your venv:\n"
                "         source venv/bin/activate  &&  python main.py\n"
                "   2. Reinstall deps inside the venv:\n"
                "         pip install --upgrade customtkinter zstandard pyperclip Pillow\n"
                "   3. Python 3.14 may not yet be supported by customtkinter.\n"
                "      Try Python 3.11 or 3.12:\n"
                "         python3.12 -m venv venv312  &&  source venv312/bin/activate\n"
                "         pip install customtkinter zstandard pyperclip Pillow\n"
                "         python main.py\n",
                file=sys.stderr,
            )
            sys.exit(1)

        from gui_app import DecoderApp
        app = DecoderApp()
        app.mainloop()


if __name__ == "__main__":
    main()

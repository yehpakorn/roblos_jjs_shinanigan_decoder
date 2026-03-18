"""
gui_app.py  --  Jujutsu Shenanigans Moveset Decoder / Encoder
Professional dark-mode GUI with three-pane layout.
"""
from __future__ import annotations
import logging, os, threading, tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional
import customtkinter as ctk
from decoder_core import (
    DecodeResult, EncodeResult, decode_moveset, bytes_to_hex_view,
    save_json, save_binary, extract_archive, encode_to_string, COMPRESSION_ALGORITHMS,
)

# ---------------------------------------------------------------------------
# Logging bridge
# ---------------------------------------------------------------------------

class GUILogHandler(logging.Handler):
    def __init__(self, cb): super().__init__(); self.cb = cb
    def emit(self, r): self.cb(self.format(r))

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

C = {
    "bg":       "#101014",
    "surface":  "#18181f",
    "card":     "#1e1e2a",
    "border":   "#2c2c3e",
    "hover":    "#33334a",
    "primary":  "#6c5ce7",
    "primary_h":"#5a48d5",
    "danger":   "#e74c5c",
    "danger_h": "#c93a49",
    "success":  "#2ecc71",
    "warning":  "#f39c12",
    "info":     "#3498db",
    "text":     "#e0e0ea",
    "text2":    "#a0a0b8",
    "dim":      "#606080",
    "mono":     "#c4c4e0",
    "hex":      "#8888bb",
}

FONT_LABEL = ("Segoe UI", 11)
FONT_LABEL_B = ("Segoe UI", 11, "bold")
FONT_SECTION = ("Segoe UI", 12, "bold")
FONT_HEADER = ("Segoe UI", 15, "bold")
FONT_MONO = ("Cascadia Mono", 11)
FONT_MONO_SM = ("Cascadia Mono", 10)
FONT_BTN = ("Segoe UI", 11, "bold")
FONT_BTN_SM = ("Segoe UI", 10)
FONT_STATUS = ("Cascadia Mono", 10)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class DecoderApp(ctk.CTk):
    VERSION = "1.1.0"

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title("JJS Moveset Decoder / Encoder")
        self.geometry("1400x880")
        self.minsize(1060, 700)
        self.configure(fg_color=C["bg"])
        self._dec_result: Optional[DecodeResult] = None
        self._enc_result: Optional[EncodeResult] = None
        self._dec_thread: Optional[threading.Thread] = None
        self._log_buf: list[str] = []
        self._setup_logging()
        self._build_ui()

    # ------------------------------------------------------------------ init
    def _setup_logging(self):
        root = logging.getLogger("JJS")
        root.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")
        h = GUILogHandler(self._queue_log)
        h.setFormatter(fmt)
        root.addHandler(h)

    def _queue_log(self, msg):
        self._log_buf.append(msg)
        self.after(0, self._flush_log)

    def _flush_log(self):
        # We use after(0) so we are on the main thread
        # BUT we shouldn't have root.addHandler(GUILogHandler) AND print using the same thing 
        # Actually the issue is that both gui_app and main setup the logger.
        # But even worse, progress_cb is hooked up in worker(), and progress_cb triggers queue_log!
        # AND logger.info() triggers queue_log() because we added the handler.
        # So we get TWO log entries for every emit() in decoder_core.
        while self._log_buf:
            self._append_log(self._log_buf.pop(0))

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self._build_header()
        self._build_body()
        self._build_statusbar()

    # -- Header ----------------------------------------------------------
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=52)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="JJS  MOVESET DECODER / ENCODER",
            font=FONT_HEADER, text_color=C["primary"]
        ).pack(side="left", padx=20)

        badge = ctk.CTkFrame(hdr, fg_color=C["border"], corner_radius=4, width=56, height=22)
        badge.pack(side="left", padx=(4, 12))
        badge.pack_propagate(False)
        ctk.CTkLabel(
            badge, text=f"v{self.VERSION}", font=("Cascadia Mono", 9),
            text_color=C["dim"]
        ).pack(expand=True)

        ctk.CTkLabel(
            hdr, text="zstd  |  gzip  |  zlib  |  lzma  |  auto-detect pipeline",
            font=FONT_MONO_SM, text_color=C["dim"]
        ).pack(side="left", padx=4)

    # -- Body ------------------------------------------------------------
    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(8, 4))

        # Left pane (fixed width)
        left = ctk.CTkFrame(body, fg_color="transparent", width=370)
        left.pack(side="left", fill="both", expand=False, padx=(0, 8))
        left.pack_propagate(False)
        self._build_left_pane(left)

        # Right pane (expandable)
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)
        self._build_right_pane(right)

    # -- Left pane -------------------------------------------------------
    def _build_left_pane(self, parent):
        self._build_input_section(parent)
        self._build_controls_section(parent)
        self._build_log_section(parent)

    def _section_header(self, parent, title, color=None):
        """Reusable section header with label and separator line."""
        frm = ctk.CTkFrame(parent, fg_color="transparent")
        frm.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            frm, text=title, font=FONT_SECTION,
            text_color=color or C["text2"]
        ).pack(side="left")
        return frm

    def _build_input_section(self, parent):
        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=8,
                            border_width=1, border_color=C["border"])
        card.pack(fill="x", pady=(0, 6))

        hdr = self._section_header(card, "INPUT", C["primary"])
        ctk.CTkButton(
            hdr, text="Clear", width=50, height=22, font=FONT_BTN_SM,
            fg_color=C["border"], hover_color=C["hover"], text_color=C["text2"],
            command=lambda: self._input_box.delete("1.0", "end")
        ).pack(side="right")
        ctk.CTkButton(
            hdr, text="Load File", width=68, height=22, font=FONT_BTN_SM,
            fg_color=C["border"], hover_color=C["primary"], text_color=C["text2"],
            command=self._load_file
        ).pack(side="right", padx=(0, 4))

        self._input_box = ctk.CTkTextbox(
            card, height=220, font=FONT_MONO,
            fg_color=C["bg"], text_color=C["mono"],
            border_color=C["border"], border_width=1,
            corner_radius=4, wrap="none"
        )
        self._input_box.pack(fill="x", padx=12, pady=(0, 4))

        ctk.CTkLabel(
            card, text="Paste encoded moveset code, JSON, or plain text.",
            font=("Segoe UI", 10), text_color=C["dim"]
        ).pack(padx=12, pady=(0, 10), anchor="w")

    def _build_controls_section(self, parent):
        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=8,
                            border_width=1, border_color=C["border"])
        card.pack(fill="x", pady=(0, 6))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=12)

        # -- Decode button -------------------------------------------------
        self._dec_btn = ctk.CTkButton(
            inner, text="DECODE", font=FONT_BTN, height=42,
            fg_color=C["primary"], hover_color=C["primary_h"],
            corner_radius=6, command=self._start_decode
        )
        self._dec_btn.pack(fill="x", pady=(0, 8))

        # -- Encode row ----------------------------------------------------
        sep1 = ctk.CTkFrame(inner, fg_color=C["border"], height=1)
        sep1.pack(fill="x", pady=(0, 8))

        enc_row = ctk.CTkFrame(inner, fg_color="transparent")
        enc_row.pack(fill="x")
        ctk.CTkLabel(
            enc_row, text="Algorithm", font=FONT_LABEL, text_color=C["text2"]
        ).pack(side="left")
        self._algo_var = tk.StringVar(value="zstd")
        ctk.CTkOptionMenu(
            enc_row, variable=self._algo_var, values=COMPRESSION_ALGORITHMS,
            font=FONT_MONO_SM, width=90, height=32,
            fg_color=C["border"], button_color=C["primary"],
            button_hover_color=C["primary_h"],
            dropdown_fg_color=C["surface"], text_color=C["text"],
            dropdown_text_color=C["text"], dropdown_hover_color=C["hover"]
        ).pack(side="left", padx=8)
        self._enc_btn = ctk.CTkButton(
            enc_row, text="ENCODE", font=FONT_BTN, height=32,
            fg_color=C["danger"], hover_color=C["danger_h"],
            corner_radius=6, command=self._start_encode
        )
        self._enc_btn.pack(side="left", fill="x", expand=True)

        # -- Export row ----------------------------------------------------
        sep2 = ctk.CTkFrame(inner, fg_color=C["border"], height=1)
        sep2.pack(fill="x", pady=8)

        exp = ctk.CTkFrame(inner, fg_color="transparent")
        exp.pack(fill="x")
        self._save_json_btn = ctk.CTkButton(
            exp, text="Save JSON", font=FONT_BTN_SM, height=30,
            fg_color=C["border"], hover_color=C["success"],
            text_color=C["text2"], text_color_disabled=C["dim"], state="disabled", command=self._save_json
        )
        self._save_json_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self._save_bin_btn = ctk.CTkButton(
            exp, text="Save Binary", font=FONT_BTN_SM, height=30,
            fg_color=C["border"], hover_color=C["warning"],
            text_color=C["text2"], text_color_disabled=C["dim"], state="disabled", command=self._save_binary
        )
        self._save_bin_btn.pack(side="left", fill="x", expand=True, padx=3)
        self._extract_btn = ctk.CTkButton(
            exp, text="Extract", font=FONT_BTN_SM, height=30,
            fg_color=C["border"], hover_color=C["info"],
            text_color=C["text2"], text_color_disabled=C["dim"], state="disabled", command=self._extract_archive
        )
        self._extract_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))

        # -- Clipboard row -------------------------------------------------
        clip = ctk.CTkFrame(inner, fg_color="transparent")
        clip.pack(fill="x", pady=(6, 0))
        self._copy_dec_btn = ctk.CTkButton(
            clip, text="Copy Decoded", font=FONT_BTN_SM, height=30,
            fg_color=C["border"], hover_color=C["hover"],
            text_color=C["text2"], text_color_disabled=C["dim"], state="disabled", command=self._copy_decoded
        )
        self._copy_dec_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self._copy_enc_btn = ctk.CTkButton(
            clip, text="Copy Encoded", font=FONT_BTN_SM, height=30,
            fg_color=C["border"], hover_color=C["hover"],
            text_color=C["text2"], text_color_disabled=C["dim"], state="disabled", command=self._copy_encoded
        )
        self._copy_enc_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))

        # -- Save encoded row -----------------------------------------------
        self._save_enc_btn = ctk.CTkButton(
            inner, text="Save Encoded .txt", font=FONT_BTN_SM, height=30,
            fg_color=C["border"], hover_color=C["success"],
            text_color=C["text2"], text_color_disabled=C["dim"], state="disabled", command=self._save_encoded
        )
        self._save_enc_btn.pack(fill="x", pady=(6, 0))

        # -- Progress bar ---------------------------------------------------
        self._progress = ctk.CTkProgressBar(
            inner, height=4, progress_color=C["primary"],
            fg_color=C["border"], corner_radius=2
        )
        self._progress.pack(fill="x", pady=(10, 0))
        self._progress.set(0)

    def _build_log_section(self, parent):
        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=8,
                            border_width=1, border_color=C["border"])
        card.pack(fill="both", expand=True)

        hdr = self._section_header(card, "PIPELINE LOG", C["danger"])
        ctk.CTkButton(
            hdr, text="Clear", width=50, height=20, font=("Segoe UI", 9),
            fg_color=C["border"], hover_color=C["hover"], text_color=C["text2"],
            command=self._clear_log
        ).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            card, font=FONT_MONO_SM, fg_color=C["bg"],
            text_color=C["dim"], border_color=C["border"],
            border_width=1, corner_radius=4, state="disabled"
        )
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # -- Right pane ------------------------------------------------------
    def _build_right_pane(self, parent):
        # Decoded output (main area)
        dec_card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=8,
                                border_width=1, border_color=C["border"])
        dec_card.pack(fill="both", expand=True, pady=(0, 6))

        dhdr = ctk.CTkFrame(dec_card, fg_color="transparent")
        dhdr.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            dhdr, text="DECODED OUTPUT", font=FONT_SECTION,
            text_color=C["success"]
        ).pack(side="left")
        self._dec_type_lbl = ctk.CTkLabel(
            dhdr, text="", font=FONT_MONO_SM, text_color=C["success"]
        )
        self._dec_type_lbl.pack(side="left", padx=12)

        self._dec_tabs = ctk.CTkTabview(
            dec_card, fg_color=C["bg"],
            segmented_button_fg_color=C["surface"],
            segmented_button_selected_color=C["primary"],
            segmented_button_selected_hover_color=C["primary"],
            segmented_button_unselected_color=C["surface"],
            segmented_button_unselected_hover_color=C["border"],
            text_color=C["text"],
            border_color=C["border"], border_width=1,
            corner_radius=6
        )
        self._dec_tabs.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        for t in ("JSON / Text", "Hex View", "Summary"):
            self._dec_tabs.add(t)

        self._json_box = ctk.CTkTextbox(
            self._dec_tabs.tab("JSON / Text"),
            font=FONT_MONO, fg_color=C["bg"],
            text_color=C["mono"], border_width=0, wrap="none"
        )
        self._json_box.pack(fill="both", expand=True)

        self._hex_box = ctk.CTkTextbox(
            self._dec_tabs.tab("Hex View"),
            font=FONT_MONO_SM, fg_color=C["bg"],
            text_color=C["hex"], border_width=0, wrap="none"
        )
        self._hex_box.pack(fill="both", expand=True)

        self._summary_box = ctk.CTkTextbox(
            self._dec_tabs.tab("Summary"),
            font=FONT_MONO, fg_color=C["bg"],
            text_color=C["text"], border_width=0
        )
        self._summary_box.pack(fill="both", expand=True)

        # Encoded output (compact strip)
        enc_card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=8,
                                border_width=1, border_color=C["border"])
        enc_card.pack(fill="x")

        ehdr = ctk.CTkFrame(enc_card, fg_color="transparent")
        ehdr.pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkLabel(
            ehdr, text="ENCODED OUTPUT", font=FONT_SECTION,
            text_color=C["danger"]
        ).pack(side="left")
        self._enc_stats_lbl = ctk.CTkLabel(
            ehdr, text="", font=FONT_MONO_SM, text_color=C["dim"]
        )
        self._enc_stats_lbl.pack(side="left", padx=12)

        self._enc_out = ctk.CTkTextbox(
            enc_card, height=80, font=FONT_MONO_SM,
            fg_color=C["bg"], text_color=C["danger"],
            border_width=0, wrap="word", state="disabled"
        )
        self._enc_out.pack(fill="x", padx=12, pady=(0, 10))

    # -- Status bar ------------------------------------------------------
    def _build_statusbar(self):
        self._status_var = tk.StringVar(value="Ready")
        sb = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=28)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        ctk.CTkLabel(
            sb, textvariable=self._status_var,
            font=FONT_STATUS, text_color=C["dim"]
        ).pack(side="left", padx=14)

    # ================================================================== DECODE

    def _start_decode(self):
        if self._dec_thread and self._dec_thread.is_alive():
            return
        raw = self._input_box.get("1.0", "end").strip()
        if not raw:
            self._status("Paste a code first.", C["warning"])
            return
        self._dec_btn.configure(state="disabled", text="Decoding...")
        self._progress.set(0)
        self._clear_dec_output()
        self._disable_dec_btns()
        self._status("Decoding...", C["primary"])
        self._append_log("-" * 55)

        def worker():
            r = decode_moveset(raw, progress_cb=None) # Pass None to avoid double logs (handled by GUILogHandler)
            self.after(0, lambda: self._on_decode_done(r))

        self._dec_thread = threading.Thread(target=worker, daemon=True)
        self._dec_thread.start()
        self._anim(0)

    def _anim(self, v):
        if self._dec_thread and self._dec_thread.is_alive():
            v = (v + 0.02) % 1.0
            self._progress.set(v)
            self.after(40, lambda: self._anim(v))
        else:
            self._progress.set(
                1.0 if self._dec_result and self._dec_result.success else 0.0
            )

    def _on_decode_done(self, r: DecodeResult):
        self._dec_result = r
        self._dec_btn.configure(state="normal", text="DECODE")
        if not r.success:
            self._status(f"Error: {r.error}", C["danger"])
            self._progress.set(0)
            return
        self._populate_dec(r)
        if r.final_text or r.json_data:
            self._save_json_btn.configure(state="normal")
            self._copy_dec_btn.configure(state="normal")
        if r.final_bytes:
            self._save_bin_btn.configure(state="normal")
        if r.detected_type == "zip":
            self._extract_btn.configure(state="normal")
        if r.detected_algorithm and r.detected_algorithm in COMPRESSION_ALGORITHMS:
            self._algo_var.set(r.detected_algorithm)
        tag = {
            "json": "JSON", "zip": "ZIP", "text": "Text", "binary": "Binary"
        }.get(r.detected_type, r.detected_type)
        size = len(r.final_bytes or b"")
        self._dec_type_lbl.configure(text=f"[ {tag}  --  {size:,} bytes ]")
        self._status(f"Decoded: {tag}  ({size:,} bytes)", C["success"])

    def _populate_dec(self, r: DecodeResult):
        txt = r.final_text or (
            r.final_bytes.decode("utf-8", "replace") if r.final_bytes else ""
        )
        self._set_tb(self._json_box, txt)
        self._set_tb(
            self._hex_box,
            bytes_to_hex_view(r.final_bytes) if r.final_bytes else "(no data)"
        )
        lines = [
            "=" * 50,
            "  JJS MOVESET DECODER  --  RESULT SUMMARY",
            "=" * 50, "",
            f"  Type    :  {r.detected_type.upper()}",
            f"  Size    :  {len(r.final_bytes or b''):,} bytes",
            f"  Steps   :  {len(r.steps)}", "",
            "-- Pipeline " + "-" * 38,
            r.log_summary(),
        ]
        if r.zip_entries:
            lines += ["", "-- Archive " + "-" * 39]
            lines += [f"  - {e}" for e in r.zip_entries]
        self._set_tb(self._summary_box, "\n".join(lines))
        self._dec_tabs.set(
            "JSON / Text" if r.detected_type in ("json", "text")
            else "Hex View" if r.detected_type == "binary"
            else "Summary"
        )

    # ================================================================== ENCODE

    def _start_encode(self):
        text = self._input_box.get("1.0", "end").strip()
        if not text:
            self._status("Paste JSON/text first.", C["warning"])
            return
        algo = self._algo_var.get()
        self._enc_btn.configure(state="disabled", text="Encoding...")
        self._set_tb(self._enc_out, "")
        self._enc_stats_lbl.configure(text="")
        self._status(f"Encoding ({algo.upper()})...", C["danger"])
        self._append_log("-" * 55)
        orig_enc = self._dec_result.original_encoded_input if self._dec_result else None
        orig_raw = self._dec_result.raw_json_text if self._dec_result else None

        def worker():
            r = encode_to_string(
                text, algorithm=algo, progress_cb=None,
                original_encoded=orig_enc, original_raw_json=orig_raw
            )
            self.after(0, lambda: self._on_encode_done(r))

        threading.Thread(target=worker, daemon=True).start()

    def _on_encode_done(self, r: EncodeResult):
        self._enc_result = r
        self._enc_btn.configure(state="normal", text="ENCODE")
        if not r.success:
            self._status(f"Error: {r.error}", C["danger"])
            self._set_tb(self._enc_out, f"ERROR: {r.error}")
            return
        self._set_tb(self._enc_out, r.encoded_string)
        self._copy_enc_btn.configure(state="normal")
        self._save_enc_btn.configure(state="normal")
        self._enc_stats_lbl.configure(
            text=(
                f"{r.original_size:,}B -> {r.compressed_size:,}B -> "
                f"{r.encoded_size:,} chars  ({r.ratio:.0f}%)"
            )
        )
        self._status(
            f"Encoded ({r.algorithm.upper()})  "
            f"{r.original_size:,}B -> {r.encoded_size:,} chars",
            C["success"]
        )

    # ================================================================== FILE I/O

    def _load_file(self):
        p = filedialog.askopenfilename(
            title="Open",
            filetypes=[("Text / JSON", "*.txt *.json"), ("All", "*.*")]
        )
        if p:
            try:
                content = open(p, "r", encoding="utf-8", errors="replace").read()
                self._input_box.delete("1.0", "end")
                self._input_box.insert("1.0", content.strip())
                self._status(
                    f"Loaded: {os.path.basename(p)}  ({len(content):,} chars)",
                    C["info"]
                )
            except Exception as e:
                messagebox.showerror("Load Error", str(e))

    def _save_json(self):
        if not self._dec_result:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Text", "*.txt"), ("All", "*.*")]
        )
        if p:
            try:
                save_json(self._dec_result, p)
                self._status(f"Saved: {p}", C["success"])
            except Exception as e:
                messagebox.showerror("Save Error", str(e))

    def _save_binary(self):
        if not self._dec_result:
            return
        ext = ".zip" if self._dec_result.detected_type == "zip" else ".bin"
        p = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("Binary", "*.bin"), ("ZIP", "*.zip"), ("All", "*.*")]
        )
        if p:
            try:
                save_binary(self._dec_result, p)
                self._status(f"Saved: {p}", C["success"])
            except Exception as e:
                messagebox.showerror("Save Error", str(e))

    def _extract_archive(self):
        if not self._dec_result:
            return
        d = filedialog.askdirectory(title="Extract to...")
        if d:
            try:
                ex = extract_archive(self._dec_result, d)
                self._status(f"Extracted {len(ex)} file(s) to {d}", C["success"])
                messagebox.showinfo("Done", f"Extracted {len(ex)} file(s) to:\n{d}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _copy_decoded(self):
        if not self._dec_result:
            return
        if self._dec_result.raw_json_text:
            t = self._dec_result.raw_json_text
        else:
            t = self._dec_result.final_text or (
                self._dec_result.final_bytes.decode("utf-8", "replace")
                if self._dec_result.final_bytes else ""
            )
        self._clip(t)
        self._status("Decoded text copied to clipboard", C["success"])

    def _copy_encoded(self):
        if not self._enc_result or not self._enc_result.encoded_string:
            return
        self._clip(self._enc_result.encoded_string)
        self._status("Encoded string copied to clipboard", C["success"])

    def _save_encoded(self):
        if not self._enc_result or not self._enc_result.encoded_string:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")]
        )
        if p:
            try:
                open(p, "w", encoding="utf-8").write(
                    self._enc_result.encoded_string
                )
                self._status(f"Saved: {p}", C["success"])
            except Exception as e:
                messagebox.showerror("Save Error", str(e))

    # ================================================================== HELPERS

    def _clip(self, text):
        try:
            import pyperclip
            pyperclip.copy(text)
        except ImportError:
            self.clipboard_clear()
            self.clipboard_append(text)

    def _disable_dec_btns(self):
        for b in (
            self._save_json_btn, self._save_bin_btn,
            self._extract_btn, self._copy_dec_btn
        ):
            b.configure(state="disabled")

    def _clear_dec_output(self):
        for box in (self._json_box, self._hex_box, self._summary_box):
            self._set_tb(box, "")
        self._dec_type_lbl.configure(text="")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _append_log(self, msg):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")
       

    @staticmethod
    def _set_tb(box, text):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def _status(self, msg, _=None):
        self._status_var.set(msg)

/**
 * app.js
 * ──────
 * UI controller for JJS Moveset Decoder / Encoder
 * Handles DOM interactions, mirrors gui_app.py logic.
 */

document.addEventListener("DOMContentLoaded", () => {
    // ─── Elements ─────────────────────────────────────────────────────────────
    const el = {
        rawInput: document.getElementById("rawInput"),
        fileInput: document.getElementById("fileInput"),
        loadBtn: document.getElementById("loadBtn"),
        clearInputBtn: document.getElementById("clearInputBtn"),
        
        decodeBtn: document.getElementById("decodeBtn"),
        algoSelect: document.getElementById("algoSelect"),
        encodeBtn: document.getElementById("encodeBtn"),
        
        saveJsonBtn: document.getElementById("saveJsonBtn"),
        saveBinBtn: document.getElementById("saveBinBtn"),
        extractBtn: document.getElementById("extractBtn"),
        
        copyDecBtn: document.getElementById("copyDecBtn"),
        copyEncBtn: document.getElementById("copyEncBtn"),
        saveEncBtn: document.getElementById("saveEncBtn"),
        
        progressBar: document.getElementById("progressBar"),
        
        clearLogBtn: document.getElementById("clearLogBtn"),
        logBox: document.getElementById("logBox"),
        
        decTypeLbl: document.getElementById("decTypeLbl"),
        tabBtns: document.querySelectorAll(".tab-btn"),
        tabPanes: document.querySelectorAll(".tab-pane"),
        
        jsonTab: document.getElementById("jsonTab"),
        hexTab: document.getElementById("hexTab"),
        summaryTab: document.getElementById("summaryTab"),
        
        encStatsLbl: document.getElementById("encStatsLbl"),
        encOut: document.getElementById("encOut"),
        
        statusVar: document.getElementById("statusVar")
    };

    // ─── State ────────────────────────────────────────────────────────────────
    let decResult = null;
    let encResult = null;
    let decAnimInterval = null;

    // ─── Initialization ───────────────────────────────────────────────────────
    function init() {
        // Populate Algorithm dropdown
        DecoderCore.COMPRESSION_ALGORITHMS.forEach(algo => {
            const opt = document.createElement("option");
            opt.value = algo;
            opt.textContent = algo;
            if (algo === "zstd") opt.selected = true;
            el.algoSelect.appendChild(opt);
        });

        // Event Listeners
        el.decodeBtn.addEventListener("click", startDecode);
        el.encodeBtn.addEventListener("click", startEncode);
        
        el.clearInputBtn.addEventListener("click", () => el.rawInput.value = "");
        el.clearLogBtn.addEventListener("click", () => el.logBox.value = "");
        
        el.loadBtn.addEventListener("click", () => el.fileInput.click());
        el.fileInput.addEventListener("change", handleFileLoad);

        el.saveJsonBtn.addEventListener("click", () => saveFile("json"));
        el.saveBinBtn.addEventListener("click", () => saveFile("binary"));
        el.extractBtn.addEventListener("click", () => alert("Extract function not implemented in browser yet (needs JSZip)."));
        el.saveEncBtn.addEventListener("click", () => saveFile("encoded"));

        el.copyDecBtn.addEventListener("click", copyDecoded);
        el.copyEncBtn.addEventListener("click", copyEncoded);

        // Tab switching
        el.tabBtns.forEach(btn => {
            btn.addEventListener("click", () => switchTab(btn.dataset.target));
        });
    }

    // ─── Logging / Status ─────────────────────────────────────────────────────
    function logMsg(msg) {
        // Add timestamp like python gui
        const now = new Date();
        const timeStr = now.toTimeString().split(' ')[0]; // HH:MM:SS
        el.logBox.value += `${timeStr}  ${msg}\n`;
        el.logBox.scrollTop = el.logBox.scrollHeight;
        console.log(`[JJS] ${msg}`);
    }

    function setStatus(msg, colorClass = "dim-color") {
        el.statusVar.textContent = msg;
        el.statusVar.className = colorClass;
    }

    function switchTab(targetId) {
        el.tabBtns.forEach(b => b.classList.toggle("active", b.dataset.target === targetId));
        el.tabPanes.forEach(p => p.classList.toggle("active", p.id === targetId));
    }

    function clearDecOutput() {
        el.jsonTab.value = "";
        el.hexTab.value = "";
        el.summaryTab.value = "";
        el.decTypeLbl.textContent = "";
    }

    function disableDecBtns() {
        el.saveJsonBtn.disabled = true;
        el.saveBinBtn.disabled = true;
        el.extractBtn.disabled = true;
        el.copyDecBtn.disabled = true;
    }

    // ─── Decode ───────────────────────────────────────────────────────────────
    function startDecode() {
        const raw = el.rawInput.value.trim();
        if (!raw) {
            setStatus("Paste a code first.", "warning-color");
            return;
        }

        el.decodeBtn.disabled = true;
        el.decodeBtn.textContent = "Decoding...";
        el.progressBar.style.width = "0%";
        clearDecOutput();
        disableDecBtns();
        setStatus("Decoding...", "primary-color");
        logMsg("-".repeat(55));

        // Fake animation
        let progress = 0;
        decAnimInterval = setInterval(() => {
            progress = (progress + 2) % 100;
            el.progressBar.style.width = `${progress}%`;
        }, 40);

        // Run decode async to not block UI completely (though in browser JS it's mostly single threaded)
        // using setTimeout to allow UI update
        setTimeout(() => {
            try {
                const r = DecoderCore.decodeMoveset(raw, logMsg);
                onDecodeDone(r);
            } catch (err) {
                const r = new DecoderCore.DecodeResult();
                r.success = false;
                r.error = err.message;
                onDecodeDone(r);
            }
        }, 10);
    }

    function onDecodeDone(r) {
        clearInterval(decAnimInterval);
        el.progressBar.style.width = r.success ? "100%" : "0%";
        
        decResult = r;
        el.decodeBtn.disabled = false;
        el.decodeBtn.textContent = "DECODE";
        
        if (!r.success) {
            setStatus(`Error: ${r.error}`, "danger-color");
            return;
        }

        populateDec(r);
        
        if (r.finalText || r.jsonData) {
            el.saveJsonBtn.disabled = false;
            el.copyDecBtn.disabled = false;
        }
        if (r.finalBytes) {
            el.saveBinBtn.disabled = false;
        }
        if (r.detectedType === "zip") {
            // el.extractBtn.disabled = false; // Need JSZip for real extraction
        }
        if (r.detectedAlgorithm && DecoderCore.COMPRESSION_ALGORITHMS.includes(r.detectedAlgorithm)) {
            el.algoSelect.value = r.detectedAlgorithm;
        }

        const tags = { "json": "JSON", "zip": "ZIP", "text": "Text", "binary": "Binary" };
        const tag = tags[r.detectedType] || r.detectedType;
        const size = r.finalBytes ? r.finalBytes.length : 0;
        
        el.decTypeLbl.textContent = `[ ${tag}  --  ${size.toLocaleString()} bytes ]`;
        setStatus(`Decoded: ${tag}  (${size.toLocaleString()} bytes)`, "success-color");
    }

    function populateDec(r) {
        let txt = r.finalText;
        if (!txt && r.finalBytes) {
            try {
                txt = new TextDecoder("utf-8", {fatal: false}).decode(r.finalBytes);
            } catch {
                txt = "";
            }
        }
        
        el.jsonTab.value = txt || "";
        el.hexTab.value = r.finalBytes ? DecoderCore.bytesToHexView(r.finalBytes) : "(no data)";
        
        const lines = [
            "==================================================",
            "  JJS MOVESET DECODER  --  RESULT SUMMARY",
            "==================================================",
            "",
            `  Type    :  ${r.detectedType.toUpperCase()}`,
            `  Size    :  ${r.finalBytes ? r.finalBytes.length.toLocaleString() : 0} bytes`,
            `  Steps   :  ${r.steps.length}`,
            "",
            "-- Pipeline --------------------------------------",
            r.logSummary()
        ];
        el.summaryTab.value = lines.join("\n");

        if (r.detectedType === "json" || r.detectedType === "text") {
            switchTab("jsonTab");
        } else if (r.detectedType === "binary") {
            switchTab("hexTab");
        } else {
            switchTab("summaryTab");
        }
    }

    // ─── Encode ───────────────────────────────────────────────────────────────
    function startEncode() {
        const text = el.rawInput.value.trim();
        if (!text) {
            setStatus("Paste JSON/text first.", "warning-color");
            return;
        }

        const algo = el.algoSelect.value;
        el.encodeBtn.disabled = true;
        el.encodeBtn.textContent = "Encoding...";
        el.encOut.value = "";
        el.encStatsLbl.textContent = "";
        setStatus(`Encoding (${algo.toUpperCase()})...`, "danger-color");
        logMsg("-".repeat(55));

        const origEnc = decResult ? decResult.originalEncodedInput : null;
        const origRaw = decResult ? decResult.rawJsonText : null;

        setTimeout(() => {
            try {
                const r = DecoderCore.encodeToString(text, algo, logMsg, origEnc, origRaw);
                onEncodeDone(r);
            } catch (err) {
                const r = new DecoderCore.EncodeResult();
                r.success = false;
                r.algorithm = algo;
                r.error = err.message || String(err);
                onEncodeDone(r);
            }
        }, 10);
    }

    function onEncodeDone(r) {
        encResult = r;
        el.encodeBtn.disabled = false;
        el.encodeBtn.textContent = "ENCODE";

        if (!r.success) {
            setStatus(`Error: ${r.error}`, "danger-color");
            el.encOut.value = `ERROR: ${r.error}`;
            return;
        }

        el.encOut.value = r.encodedString;
        el.copyEncBtn.disabled = false;
        el.saveEncBtn.disabled = false;

        const ratioStr = !isNaN(r.ratio) ? r.ratio.toFixed(0) : "0";
        el.encStatsLbl.textContent = `${r.originalSize.toLocaleString()}B -> ${r.compressedSize.toLocaleString()}B -> ${r.encodedSize.toLocaleString()} chars  (${ratioStr}%)`;
        setStatus(`Encoded (${r.algorithm.toUpperCase()})  ${r.originalSize.toLocaleString()}B -> ${r.encodedSize.toLocaleString()} chars`, "success-color");
    }

    // ─── File I/O & Clipboard ─────────────────────────────────────────────────
    function handleFileLoad(e) {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (evt) => {
            const content = evt.target.result;
            el.rawInput.value = content.trim();
            setStatus(`Loaded: ${file.name}  (${content.length.toLocaleString()} chars)`, "info-color");
            // reset file input
            el.fileInput.value = "";
        };
        reader.onerror = () => {
            alert("Error reading file");
        };
        reader.readAsText(file);
    }

    function downloadBlob(blob, defaultName) {
        const name = prompt("Save as:", defaultName);
        if (!name) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
    }

    function saveFile(type) {
        if (type === "json" && decResult) {
            let content = decResult.finalText;
            if (!content && decResult.jsonData) {
                content = JSON.stringify(decResult.jsonData, null, 2);
            }
            const blob = new Blob([content], { type: "application/json" });
            downloadBlob(blob, "decoded.json");
        } else if (type === "binary" && decResult && decResult.finalBytes) {
            const ext = decResult.detectedType === "zip" ? ".zip" : ".bin";
            const blob = new Blob([decResult.finalBytes], { type: "application/octet-stream" });
            downloadBlob(blob, `decoded${ext}`);
        } else if (type === "encoded" && encResult && encResult.encodedString) {
            const blob = new Blob([encResult.encodedString], { type: "text/plain" });
            downloadBlob(blob, "encoded.txt");
        }
    }

    function copyDecoded() {
        if (!decResult) return;
        let t = decResult.rawJsonText;
        if (!t) {
            t = decResult.finalText || "";
            if (!t && decResult.finalBytes) {
                try { t = new TextDecoder("utf-8").decode(decResult.finalBytes); } catch {}
            }
        }
        if (t) {
            navigator.clipboard.writeText(t).then(() => {
                setStatus("Decoded text copied to clipboard", "success-color");
            }).catch(() => alert("Clipboard copy failed"));
        }
    }

    function copyEncoded() {
        if (!encResult || !encResult.encodedString) return;
        navigator.clipboard.writeText(encResult.encodedString).then(() => {
            setStatus("Encoded string copied to clipboard", "success-color");
        }).catch(() => alert("Clipboard copy failed"));
    }

    init();
});

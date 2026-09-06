"""
KisanNetra — Local Inference Server
Serves real MobileNetV3-Small ONNX inference to the dashboard.

This is the edge-device Python backend. The browser dashboard POSTs
an image file and receives the real model's class + confidence vector.

Usage:
    python inference_server.py
    Then open dashboard.html in a browser (or serve with python -m http.server).

Endpoints:
    GET  /health    — model info, ready check
    POST /predict   — multipart image → JSON {class, confidence, scores, model}
"""
import sys
import io
import json
import base64
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import cgi

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import numpy as np
from PIL import Image
import onnxruntime as ort

AI_DIR       = Path(__file__).parent
MODEL_PATH   = AI_DIR / "kisannetra_fp32.onnx"
HOST         = "localhost"
PORT         = 8787
IMG_SIZE     = 224
MEAN         = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD          = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# ── Blur prefilter ───────────────────────────────────────────────────────────
# Variance of Laplacian: a well-focused image has sharp edges → high variance.
# Blurry images (motion, focus, dust) have low variance → abstain rather than
# feed a degraded frame to the classifier. Same philosophy as the T=0.80
# disease confidence threshold: an inconclusive frame is a deferred capture,
# not a missed detection.
# Measured on the raw [0–255] greyscale image BEFORE normalization — the
# normalized tensor has a completely different range and VoL would be meaningless.
BLUR_THRESHOLD = 100.0   # tune against real device; lower = more permissive

# Loaded, never hardcoded: the order is ImageFolder's alphabetical sort and a
# duplicate of it in this file is what swapped Healthy and Tungro before.
with open(AI_DIR / "classes.json", encoding="utf-8") as _f:
    CLASSES = json.load(_f)

# ── Load model once at startup ──────────────────────────────────────────────
print(f"Loading model: {MODEL_PATH}")
if not MODEL_PATH.exists():
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}. Run step5_export.py first.")

SESSION = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
INPUT_NAME = SESSION.get_inputs()[0].name
_n_out = SESSION.get_outputs()[0].shape[-1]
if len(CLASSES) != _n_out:
    raise RuntimeError(
        f"Class list has {len(CLASSES)} entries but the model emits {_n_out} "
        f"logits. Refusing to serve mislabelled predictions."
    )
print(f"Model loaded. Input: {INPUT_NAME}  |  Classes: {CLASSES}")

def softmax(x):
    e = np.exp(x - np.max(x))
    return e / e.sum()

def compute_vol(img_bytes: bytes) -> float:
    """Variance of Laplacian on the raw greyscale image — blur score.

    High value  → sharp, high-frequency edges present → pass to classifier.
    Low value   → blurry or featureless frame → abstain (ABSTAIN_BLUR).
    Computed on the raw pixel range [0–255] before any normalization so the
    threshold is stable across different image sources.
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("L")      # greyscale
    img = img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32)
    # Laplacian kernel: [0,1,0], [1,-4,1], [0,1,0]
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    from numpy.lib.stride_tricks import sliding_window_view
    windows = sliding_window_view(arr, (3, 3))
    lap = (windows * kernel).sum(axis=(-2, -1))
    return float(lap.var())

def preprocess(img_bytes: bytes) -> np.ndarray:
    """Decode image bytes → normalized float32 tensor (1, 3, 224, 224)."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0           # H W C, [0,1]
    arr = (arr - MEAN) / STD                                  # normalise
    arr = arr.transpose(2, 0, 1)[np.newaxis, ...]            # 1 C H W
    return arr.astype(np.float32)

def run_inference(img_bytes: bytes) -> dict:
    # ── Blur gate ─────────────────────────────────────────────────────────────
    blur_score = compute_vol(img_bytes)
    if blur_score < BLUR_THRESHOLD:
        return {
            "class":       "ABSTAIN_BLUR",
            "confidence":  0.0,
            "scores":      {c: 0.0 for c in CLASSES},
            "blur_score":  blur_score,
            "blur_threshold": BLUR_THRESHOLD,
            "model":       "kisannetra_fp32.onnx (MobileNetV3-Small, Val 87.32%)",
            "inference":   "ABSTAINED — image too blurry, recapture next cycle",
            "message":     f"Blur score {blur_score:.1f} is below threshold "
                           f"{BLUR_THRESHOLD}. Frame discarded — not fed to classifier.",
        }

    # ── Normal inference ──────────────────────────────────────────────────────
    tensor = preprocess(img_bytes)
    logits = SESSION.run(None, {INPUT_NAME: tensor})[0][0]   # shape (5,)
    probs  = softmax(logits)
    idx    = int(np.argmax(probs))
    return {
        "class":       CLASSES[idx],
        "confidence":  float(probs[idx]),
        "scores":      {c: float(p) for c, p in zip(CLASSES, probs)},
        "blur_score":  blur_score,
        "blur_threshold": BLUR_THRESHOLD,
        "model":       "kisannetra_fp32.onnx (MobileNetV3-Small, Val 87.32%)",
        "inference":   "REAL — onnxruntime CPUExecutionProvider",
    }

# ── HTTP handler ──────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({
                "status": "ok",
                "model": str(MODEL_PATH.name),
                "classes": CLASSES,
                "inference": "REAL — kisannetra_fp32.onnx",
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/predict":
            self.send_response(404)
            self.end_headers()
            return
        try:
            ctype, pdict = cgi.parse_header(self.headers.get("Content-Type", ""))
            if ctype == "multipart/form-data":
                pdict["boundary"] = bytes(pdict["boundary"], "utf-8")
                pdict["CONTENT-LENGTH"] = int(self.headers["Content-Length"])
                fields = cgi.parse_multipart(self.rfile, pdict)
                img_bytes = fields.get("image", [None])[0]
            elif ctype == "application/json":
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                # Accept base64-encoded image
                img_bytes = base64.b64decode(body["image"])
            else:
                length = int(self.headers.get("Content-Length", 0))
                img_bytes = self.rfile.read(length)

            if not img_bytes:
                raise ValueError("No image data received")

            result = run_inference(img_bytes)
            body   = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            err = json.dumps({"error": str(exc)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(err)
            print(f"  ERROR: {exc}")

# ── Main ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), Handler)
    print(f"\nKisanNetra Inference Server running at http://{HOST}:{PORT}")
    print(f"  GET  http://{HOST}:{PORT}/health")
    print(f"  POST http://{HOST}:{PORT}/predict   (multipart: image=<file>)")
    print(f"\nOpen dashboard.html in a browser while this server is running.")
    print(f"Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

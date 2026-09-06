"""
Pest model - Step 5: export to ONNX.
SOFTWARE-ONLY VALIDATION. No Qualcomm/Hexagon/NPU hardware is involved.

INT8: this backbone is MobileNetV3-Small, the same architecture whose
HardSwish activations defeated every onnxruntime quantization scheme on the
disease model (5 attempts, 22-36% accuracy - see ai/step5_export.py). This
script ATTEMPTS INT8 anyway and reports whatever actually happens. A failing
INT8 model is written to a filename marked BROKEN and is never presented as
the deployment artifact.

Class count is read from pest_classes.json, never hardcoded.
"""
import io
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import onnx
import onnxruntime as ort
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

AI_DIR = Path(__file__).resolve().parent
DATA_DIR = AI_DIR / "pest_dataset_split"
MODEL_PATH = AI_DIR / "pest_best_model.pth"
CLASSES_PATH = AI_DIR / "pest_classes.json"
ONNX_FP32_PATH = AI_DIR / "kisannetra_pest_fp32.onnx"
EXPORT_REPORT_PATH = AI_DIR / "pest_export_report.json"

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def load_classes():
    with CLASSES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_model(n_classes):
    model = models.mobilenet_v3_small(weights=None)
    num_ftrs = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(num_ftrs, n_classes)
    model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    model.eval()
    return model


def export_onnx(model):
    dummy_input = torch.randn(1, 3, 224, 224)
    with torch.no_grad():
        torch.onnx.export(
            model, dummy_input, str(ONNX_FP32_PATH),
            dynamo=False, export_params=True, opset_version=17,
            do_constant_folding=True,
            input_names=["input"], output_names=["output"],
            dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        )
    onnx.checker.check_model(onnx.load(str(ONNX_FP32_PATH)))
    size_mb = os.path.getsize(ONNX_FP32_PATH) / (1024 * 1024)
    print(f"FP32 ONNX exported and checker-validated. Size: {size_mb:.2f} MB")
    return size_mb


def evaluate_onnx(model_path, label="FP32"):
    dataset = datasets.ImageFolder(DATA_DIR / "test", transform)
    loader = DataLoader(dataset, batch_size=64, shuffle=False)
    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    correct = total = 0
    for inputs, labels in loader:
        out = sess.run(None, {in_name: inputs.numpy()})[0]
        correct += (np.argmax(out, axis=1) == labels.numpy()).sum()
        total += len(labels)
    acc = correct / total
    print(f"[{label}] ONNX Test Accuracy: {acc * 100:.2f}%  ({correct}/{total})")
    return float(acc)


def attempt_int8():
    """Try static INT8. Report the real number whatever it is."""
    from onnxruntime.quantization import CalibrationDataReader, QuantType, quantize_static

    int8_path = AI_DIR / "kisannetra_pest_int8.CANDIDATE.onnx"
    calib_ds = datasets.ImageFolder(DATA_DIR / "val", transform)
    calib_loader = DataLoader(calib_ds, batch_size=1, shuffle=True)

    class Reader(CalibrationDataReader):
        def __init__(self, loader, limit=200):
            self.data = []
            for i, (x, _) in enumerate(loader):
                if i >= limit:
                    break
                self.data.append({"input": x.numpy()})
            self.it = iter(self.data)

        def get_next(self):
            return next(self.it, None)

    quantize_static(
        str(ONNX_FP32_PATH), str(int8_path), Reader(calib_loader),
        activation_type=QuantType.QUInt8, weight_type=QuantType.QUInt8,
    )
    size_mb = os.path.getsize(int8_path) / (1024 * 1024)
    acc = evaluate_onnx(int8_path, "INT8")
    return int8_path, size_mb, acc


if __name__ == "__main__":
    print("=" * 58)
    print("   PEST MODEL - STEP 5: EXPORT (SOFTWARE-ONLY VALIDATION)")
    print("   No Qualcomm/Hexagon/NPU hardware is used.")
    print("=" * 58)

    classes = load_classes()
    print(f"Classes from {CLASSES_PATH.name}: {classes}")
    model = load_model(len(classes))

    print("\n--- Exporting FP32 ONNX (deployment model) ---")
    size_fp32 = export_onnx(model)
    print("\n--- Accuracy: FP32 ONNX ---")
    acc_fp32 = evaluate_onnx(ONNX_FP32_PATH, "FP32")

    print("\n--- Attempting INT8 static quantization ---")
    int8_result = {"attempted": True}
    try:
        int8_path, size_int8, acc_int8 = attempt_int8()
        int8_result.update({"size_mb": size_int8, "accuracy": acc_int8})
        # Accept only if INT8 stays within 2 points of FP32.
        if acc_int8 >= acc_fp32 - 0.02:
            int8_result["status"] = "USABLE"
            print(f"INT8 held up: {acc_int8*100:.2f}% vs FP32 {acc_fp32*100:.2f}%.")
        else:
            int8_result["status"] = "FAILED_ACCURACY_COLLAPSE"
            broken = AI_DIR / f"kisannetra_pest_int8.BROKEN_{acc_int8*100:.0f}pct.onnx"
            os.replace(int8_path, broken)
            int8_result["artifact"] = broken.name
            print(f"INT8 COLLAPSED: {acc_int8*100:.2f}% vs FP32 {acc_fp32*100:.2f}%.")
            print(f"Renamed to {broken.name}. NOT the deployment model.")
            print("Same HardSwish root cause documented for the disease model.")
    except Exception as e:
        int8_result.update({"status": "FAILED_EXCEPTION", "error": f"{type(e).__name__}: {e}"})
        print(f"INT8 quantization raised: {type(e).__name__}: {e}")
        print("Recorded as a failure. No INT8 artifact is deployed.")

    report = {
        "task": "pest_damage",
        "classes": classes,
        "fp32": {"path": ONNX_FP32_PATH.name, "size_mb": size_fp32, "accuracy": acc_fp32},
        "int8": int8_result,
        "hardware_note": "Software-only validation. No Qualcomm NPU profiling was performed.",
    }
    with EXPORT_REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 58)
    print(f"  DEPLOYMENT MODEL: {ONNX_FP32_PATH.name}")
    print(f"  Size:     {size_fp32:.2f} MB")
    print(f"  Accuracy: {acc_fp32*100:.2f}% (pest test set)")
    print(f"  INT8:     {int8_result['status']}")
    print("  SOFTWARE-ONLY VALIDATION. No Qualcomm NPU profiling.")
    print("=" * 58)

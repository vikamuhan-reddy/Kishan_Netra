"""
Pest model - Step 3: transfer-learning training.

Same recipe as ai/step3_train.py: MobileNetV3-Small, ImageNet weights,
Phase 1 frozen backbone warmup then Phase 2 full fine-tune.

Deliberately a SEPARATE model from the disease classifier. Pest damage
(insect feeding scars, dead tillers) and fungal/bacterial lesions are
different visual tasks, and the Stage-1 leaf detector remains out of scope,
so there is no shared detector to hang both heads off.

Writes: pest_best_model.pth, pest_classes.json
Touches no disease-model artifact.
"""
import argparse
import copy
import json
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, models, transforms

AI_DIR = Path(__file__).resolve().parent
DATA_DIR = AI_DIR / "pest_dataset_split"
MODEL_SAVE_PATH = AI_DIR / "pest_best_model.pth"
CLASSES_PATH = AI_DIR / "pest_classes.json"

BATCH_SIZE = 64
NUM_WORKERS = 4
SEED = 42

data_transforms = {
    "train": transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]),
    "val": transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]),
}


def run_epoch(model, loader, criterion, optimizer, device, train: bool):
    model.train() if train else model.eval()
    running_loss = 0.0
    running_corrects = 0
    n = 0
    for inputs, labels in loader:
        inputs = inputs.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        with torch.set_grad_enabled(train):
            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)
            loss = criterion(outputs, labels)
            if train:
                loss.backward()
                optimizer.step()
        running_loss += loss.item() * inputs.size(0)
        running_corrects += torch.sum(preds == labels.data).item()
        n += inputs.size(0)
    return running_loss / n, running_corrects / n


def train_model(fine_tune_epochs: int, timing_only: bool):
    torch.manual_seed(SEED)
    print(f"Loading data from {DATA_DIR}...")
    image_datasets = {x: datasets.ImageFolder(DATA_DIR / x, data_transforms[x])
                      for x in ["train", "val"]}
    dataloaders = {x: torch.utils.data.DataLoader(image_datasets[x], batch_size=BATCH_SIZE,
                                                  shuffle=True, num_workers=NUM_WORKERS)
                   for x in ["train", "val"]}

    class_names = image_datasets["train"].classes
    # ImageFolder decides class order by alphabetical sort, not us. Persist it
    # beside the weights so no downstream script ever has to guess or hardcode.
    with CLASSES_PATH.open("w", encoding="utf-8") as f:
        json.dump(class_names, f, indent=2)
    print(f"Classes: {class_names}  -> wrote {CLASSES_PATH.name}")

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    for param in model.parameters():
        param.requires_grad = False
    num_ftrs = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(num_ftrs, len(class_names))
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.classifier[3].parameters(), lr=0.001)

    print("\n--- PHASE 1: Frozen Backbone (1 epoch warmup) ---")
    t0 = time.time()
    loss, acc = run_epoch(model, dataloaders["train"], criterion, optimizer, device, True)
    p1 = time.time() - t0
    print(f"Phase 1 done in {p1:.0f}s. Train Loss: {loss:.4f} Acc: {acc:.4f}")

    if timing_only:
        print(f"\n[TIMING ONLY] One frozen-backbone epoch = {p1:.0f}s.")
        print(f"Phase 2 epochs are slower (full backward pass + val pass).")
        print("Re-run without --timing-only to train for real.")
        return

    print("\n--- PHASE 2: Fine-Tuning All Layers ---")
    for param in model.parameters():
        param.requires_grad = True
    optimizer = optim.Adam(model.parameters(), lr=1e-4)

    best_acc = 0.0
    best_model_wts = copy.deepcopy(model.state_dict())
    for epoch in range(fine_tune_epochs):
        print(f"Epoch {epoch + 1}/{fine_tune_epochs}")
        print("-" * 10)
        te = time.time()
        tr_loss, tr_acc = run_epoch(model, dataloaders["train"], criterion, optimizer, device, True)
        print(f"Train Loss: {tr_loss:.4f} Acc: {tr_acc:.4f}")
        va_loss, va_acc = run_epoch(model, dataloaders["val"], criterion, optimizer, device, False)
        print(f"Val   Loss: {va_loss:.4f} Acc: {va_acc:.4f}  ({time.time() - te:.0f}s)")
        if va_acc > best_acc:
            best_acc = va_acc
            best_model_wts = copy.deepcopy(model.state_dict())
        print()

    print(f"Best Val Accuracy: {best_acc:.4f}")
    model.load_state_dict(best_model_wts)
    torch.save(model.state_dict(), MODEL_SAVE_PATH)
    print(f"Model saved to {MODEL_SAVE_PATH.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=4, help="Phase 2 fine-tune epochs")
    ap.add_argument("--timing-only", action="store_true",
                    help="Run one warmup epoch and report its wall time, then stop")
    a = ap.parse_args()
    train_model(a.epochs, a.timing_only)

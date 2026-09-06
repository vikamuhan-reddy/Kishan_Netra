import torch
import torch.nn as nn
from torchvision import datasets, models, transforms
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from pathlib import Path
import json

DATA_DIR = Path("dataset_split")
MODEL_PATH = "best_model.pth"
NUM_CLASSES = 5
BATCH_SIZE = 64
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def evaluate_model():
    print(f"Using device: {DEVICE}")
    model = models.mobilenet_v3_small(weights=None)
    num_ftrs = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(num_ftrs, NUM_CLASSES)
    model.load_state_dict(torch.load(MODEL_PATH))
    model = model.to(DEVICE)
    model.eval()

    test_dir = DATA_DIR / 'test'
    test_dataset = datasets.ImageFolder(test_dir, transform)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)
    
    classes = test_dataset.classes
    
    all_preds = []
    all_labels = []
    all_sources = []
    
    # We parse the source (lab or field) from the filename
    with torch.no_grad():
        for i, (inputs, labels) in enumerate(test_loader):
            inputs = inputs.to(DEVICE)
            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)
            
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.numpy())
            
            # Reconstruct batch indices to find paths
            start_idx = i * BATCH_SIZE
            for j in range(len(labels)):
                path, _ = test_dataset.samples[start_idx + j]
                # the filename is prepended with lab_ or field_
                filename = Path(path).name
                if filename.startswith('lab_'):
                    all_sources.append('lab')
                else:
                    all_sources.append('field')

    # Overall Metrics
    macro_f1 = f1_score(all_labels, all_preds, average='macro')
    report = classification_report(all_labels, all_preds, target_names=classes)
    cm = confusion_matrix(all_labels, all_preds)
    
    # Lab vs Field Gap
    lab_correct = sum(1 for p, l, s in zip(all_preds, all_labels, all_sources) if s == 'lab' and p == l)
    lab_total = sum(1 for s in all_sources if s == 'lab')
    lab_acc = (lab_correct / lab_total) if lab_total > 0 else 0.0
    
    field_correct = sum(1 for p, l, s in zip(all_preds, all_labels, all_sources) if s == 'field' and p == l)
    field_total = sum(1 for s in all_sources if s == 'field')
    field_acc = (field_correct / field_total) if field_total > 0 else 0.0
    
    gap = lab_acc - field_acc

    # Per-class analysis for Brown Spot (least reliable lab data)
    brown_spot_idx = classes.index('Brown Spot')
    healthy_idx = classes.index('Healthy')
    
    print("\n" + "="*50)
    print("                STEP 4: EVALUATION")
    print("="*50)
    
    print(f"\n--- HEADLINE: LAB VS FIELD GAP ---")
    print(f"Lab-Condition Accuracy   : {lab_acc*100:.2f}% ({lab_correct}/{lab_total})")
    print(f"Field-Condition Accuracy : {field_acc*100:.2f}% ({field_correct}/{field_total})")
    print(f"** THE LAB-VS-FIELD GAP IS {abs(gap)*100:.2f}% **")
    print("Note: 'Healthy' is a field-only class; it has no lab counterpart.")
    print("Note: 'Brown Spot' lab data was very small (90 images total); its lab metric is the least reliable.")
    
    print("\n--- OVERALL METRICS ---")
    print(f"Macro F1-Score: {macro_f1:.4f}")
    
    print("\n--- PER-CLASS PRECISION & RECALL ---")
    print(report)
    
    print("\n--- CONFUSION MATRIX ---")
    # Pretty print confusion matrix
    print(f"{'True \\ Pred':>15}", end="")
    for c in classes:
        print(f"{c[:7]:>8}", end="")
    print()
    for i, row in enumerate(cm):
        print(f"{classes[i]:>15}", end="")
        for val in row:
            print(f"{val:>8}", end="")
        print()

    # Save artifact metrics
    metrics = {
        "lab_acc": lab_acc,
        "field_acc": field_acc,
        "gap": gap,
        "macro_f1": macro_f1,
        "classes": classes,
        "confusion_matrix": cm.tolist()
    }
    with open("eval_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

if __name__ == '__main__':
    evaluate_model()

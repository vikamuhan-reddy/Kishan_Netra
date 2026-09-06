import os
import json
import time
import copy
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, models, transforms
from pathlib import Path

# Config
# Anchored to this file's directory so the script works from any cwd.
AI_DIR = Path(__file__).resolve().parent
DATA_DIR = AI_DIR / "dataset_split"
BATCH_SIZE = 64
NUM_CLASSES = 5
MODEL_SAVE_PATH = AI_DIR / "best_model.pth"
CLASSES_PATH = AI_DIR / "classes.json"

# Basic augmentation (flip/rotate/color jitter) and normalization
data_transforms = {
    'train': transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
    'val': transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
}

def train_model():
    print(f"Loading data from {DATA_DIR}...")
    image_datasets = {x: datasets.ImageFolder(DATA_DIR / x, data_transforms[x])
                      for x in ['train', 'val']}
    
    dataloaders = {x: torch.utils.data.DataLoader(image_datasets[x], batch_size=BATCH_SIZE,
                                                  shuffle=True, num_workers=4)
                   for x in ['train', 'val']}
    
    dataset_sizes = {x: len(image_datasets[x]) for x in ['train', 'val']}
    class_names = image_datasets['train'].classes

    # The class order is decided by ImageFolder's alphabetical sort, not by us.
    # Persist it beside the weights so no downstream file has to guess it.
    with CLASSES_PATH.open("w", encoding="utf-8") as f:
        json.dump(class_names, f, indent=2)

    print(f"Classes: {class_names}  -> wrote {CLASSES_PATH.name}")
    
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # Transfer learning: MobileNetV3-Small from ImageNet
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    
    # Freeze backbone for Phase 1
    for param in model.parameters():
        param.requires_grad = False
        
    # Replace classifier head
    num_ftrs = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(num_ftrs, NUM_CLASSES)
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()
    
    # Phase 1: Optimizer only for the classifier head
    optimizer = optim.Adam(model.classifier[3].parameters(), lr=0.001)

    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    print("\n--- PHASE 1: Frozen Backbone (1 Epoch Warmup) ---")
    start_time = time.time()
    
    # Train 1 epoch
    model.train()
    running_loss = 0.0
    running_corrects = 0
    
    for inputs, labels in dataloaders['train']:
        inputs = inputs.to(device)
        labels = labels.to(device)
        
        optimizer.zero_grad()
        outputs = model(inputs)
        _, preds = torch.max(outputs, 1)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        
        running_loss += loss.item() * inputs.size(0)
        running_corrects += torch.sum(preds == labels.data)
        
    epoch_loss = running_loss / dataset_sizes['train']
    epoch_acc = running_corrects.double() / dataset_sizes['train']
    
    phase1_time = time.time() - start_time
    print(f"Phase 1 completed in {phase1_time:.0f}s. Train Loss: {epoch_loss:.4f} Acc: {epoch_acc:.4f}")

    print("\n--- PHASE 2: Fine-Tuning All Layers ---")
    # Unfreeze all layers
    for param in model.parameters():
        param.requires_grad = True
        
    # Low learning rate for fine-tuning
    optimizer = optim.Adam(model.parameters(), lr=1e-4)
    
    num_epochs = 4 # total 5 epochs for the whole process
    for epoch in range(num_epochs):
        print(f'Epoch {epoch+1}/{num_epochs}')
        print('-' * 10)
        
        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()
            else:
                model.eval()
                
            running_loss = 0.0
            running_corrects = 0
            
            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)
                
                optimizer.zero_grad()
                
                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)
                    
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()
                        
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)
                
            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc = running_corrects.double() / dataset_sizes[phase]
            
            print(f'{phase.capitalize()} Loss: {epoch_loss:.4f} Acc: {epoch_acc:.4f}')
            
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())
                
        print()

    print(f'Best Val Accuracy: {best_acc:4f}')
    
    # Load best weights
    model.load_state_dict(best_model_wts)
    torch.save(model.state_dict(), MODEL_SAVE_PATH)
    print(f"Model saved to {MODEL_SAVE_PATH}")

if __name__ == '__main__':
    train_model()

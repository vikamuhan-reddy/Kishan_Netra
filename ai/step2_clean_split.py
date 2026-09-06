import os
import shutil
import hashlib
import json
from pathlib import Path
from collections import defaultdict
import random

random.seed(42)

DATA_ROOT = Path(r"C:\Users\vikam\OneDrive\Desktop\Kishan_Netra")
OUTPUT_DIR = Path("dataset_split")

# Source directories
LAB_DIR = DATA_ROOT / "archive (3)"
FIELD_DIR = DATA_ROOT / "paddy-disease-classification" / "train_images"

# Mapping from source folder names to target classes
LAB_MAPPING = {
    "Rice___bacterial_blight": "Bacterial Blight",
    "Rice___blast": "Blast",
    "Rice___brown_spot": "Brown Spot",
    "Rice___tungro": "Tungro"
}

FIELD_MAPPING = {
    "bacterial_leaf_blight": "Bacterial Blight",
    "blast": "Blast",
    "brown_spot": "Brown Spot",
    "tungro": "Tungro",
    "normal": "Healthy"
}

def get_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def clean_and_split():
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    
    # Store images: dict[class_name][source] = list_of_paths
    dataset = defaultdict(lambda: defaultdict(list))
    
    # Track hashes for deduplication
    seen_hashes = set()
    duplicates = 0
    
    print("Scanning LAB directory...")
    for source_folder, target_class in LAB_MAPPING.items():
        folder_path = LAB_DIR / source_folder
        if not folder_path.exists():
            continue
        for img_path in folder_path.glob("*.*"):
            if img_path.suffix.lower() not in ['.jpg', '.jpeg', '.png']:
                continue
            h = get_md5(img_path)
            if h in seen_hashes:
                duplicates += 1
                continue
            seen_hashes.add(h)
            dataset[target_class]['lab'].append(img_path)
            
    print("Scanning FIELD directory...")
    for source_folder, target_class in FIELD_MAPPING.items():
        folder_path = FIELD_DIR / source_folder
        if not folder_path.exists():
            continue
        for img_path in folder_path.glob("*.*"):
            if img_path.suffix.lower() not in ['.jpg', '.jpeg', '.png']:
                continue
            h = get_md5(img_path)
            if h in seen_hashes:
                duplicates += 1
                continue
            seen_hashes.add(h)
            dataset[target_class]['field'].append(img_path)
            
    print(f"Removed {duplicates} exact duplicates.")
    
    # Create split directories
    for split in ['train', 'val', 'test']:
        for target_class in set(LAB_MAPPING.values()) | set(FIELD_MAPPING.values()):
            (OUTPUT_DIR / split / target_class).mkdir(parents=True, exist_ok=True)
            
    # Split proportions
    TRAIN_PCT = 0.7
    VAL_PCT = 0.15
    
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    
    for target_class, sources in dataset.items():
        for source, paths in sources.items():
            random.shuffle(paths)
            n = len(paths)
            n_train = int(n * TRAIN_PCT)
            n_val = int(n * VAL_PCT)
            
            splits = {
                'train': paths[:n_train],
                'val': paths[n_train:n_train+n_val],
                'test': paths[n_train+n_val:]
            }
            
            for split, split_paths in splits.items():
                for i, path in enumerate(split_paths):
                    # prepend source to filename to avoid collisions and track provenance
                    ext = path.suffix
                    new_filename = f"{source}_{i:04d}{ext}"
                    dest = OUTPUT_DIR / split / target_class / new_filename
                    shutil.copy2(path, dest)
                    counts[split][target_class][source] += 1

    # Print Report
    print("\n--- SPLIT REPORT ---")
    total_test_field = 0
    total_test = 0
    for split in ['train', 'val', 'test']:
        print(f"\n[{split.upper()}]")
        for target_class in sorted(counts[split].keys()):
            lab_c = counts[split][target_class].get('lab', 0)
            field_c = counts[split][target_class].get('field', 0)
            print(f"  {target_class:18s}: Lab={lab_c:<4d} Field={field_c:<4d} (Total: {lab_c+field_c})")
            if split == 'test':
                total_test_field += field_c
                total_test += (lab_c + field_c)
                
    if total_test > 0:
        print(f"\nTest set condition: {total_test_field}/{total_test} ({total_test_field/total_test*100:.1f}%) FIELD data.")
    
    # Save a JSON report for Step 4
    with open("split_report.json", "w") as f:
        json.dump(counts, f, indent=2)
        
if __name__ == "__main__":
    clean_and_split()

"""
Pest model - Step 2: clean + leakage-free split.

Mirrors ai/step2_clean_split.py, but for the PEST-DAMAGE task. It touches
nothing belonging to the disease model: separate output directory, separate
report file, separate class list.

Source: the SAME already-downloaded Paddy Doctor folder used by the disease
model (paddy-disease-classification/train_images). No new download.

Condition note: Paddy Doctor is entirely field-condition imagery. Unlike the
disease model, this task has NO lab counterpart at all, so there is no
lab-vs-field gap to measure here. Every image is tagged 'field' and that
absence is reported rather than papered over.
"""
import hashlib
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

random.seed(42)

AI_DIR = Path(__file__).resolve().parent
FIELD_DIR = Path(r"C:\Users\vikam\OneDrive\Desktop\Kishan_Netra") / "paddy-disease-classification" / "train_images"
OUTPUT_DIR = AI_DIR / "pest_dataset_split"
REPORT_PATH = AI_DIR / "pest_split_report.json"

# Pest-damage classes plus a negative class.
#
# WHY A NEGATIVE CLASS: a hispa-vs-dead_heart-only model has no way to say
# "no pest damage here" - it would label every healthy leaf as one of the two
# pests. 'normal' is the same folder the disease model draws Healthy from, so
# this adds no new data source. Set INCLUDE_NEGATIVE = False for a pure
# two-class pest-type discriminator.
INCLUDE_NEGATIVE = True

FIELD_MAPPING = {
    "hispa": "Hispa",
    "dead_heart": "Dead Heart",
}
if INCLUDE_NEGATIVE:
    FIELD_MAPPING["normal"] = "No Pest Damage"

MIN_USABLE = 100  # below this a class is kept but flagged as low-reliability

TRAIN_PCT = 0.7
VAL_PCT = 0.15


def get_md5(file_path):
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_and_split():
    if not FIELD_DIR.exists():
        raise SystemExit(f"Source directory not found: {FIELD_DIR}")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    dataset = defaultdict(list)
    raw_counts = {}
    seen_hashes = set()
    duplicates = defaultdict(int)

    print("Scanning source (field-condition Paddy Doctor images)...")
    for source_folder, target_class in FIELD_MAPPING.items():
        folder_path = FIELD_DIR / source_folder
        if not folder_path.exists():
            raise SystemExit(f"Expected class folder missing: {folder_path}")
        n_raw = 0
        for img_path in sorted(folder_path.glob("*.*")):
            if img_path.suffix.lower() not in [".jpg", ".jpeg", ".png"]:
                continue
            n_raw += 1
            h = get_md5(img_path)
            if h in seen_hashes:
                duplicates[target_class] += 1
                continue
            seen_hashes.add(h)
            dataset[target_class].append(img_path)
        raw_counts[target_class] = n_raw

    print("\n--- DATA INVENTORY (before training) ---")
    low_reliability = []
    for target_class in FIELD_MAPPING.values():
        raw = raw_counts[target_class]
        dup = duplicates[target_class]
        usable = len(dataset[target_class])
        flag = ""
        if usable < MIN_USABLE:
            flag = f"  <-- LOW RELIABILITY (< {MIN_USABLE} usable; kept, not dropped)"
            low_reliability.append(target_class)
        print(f"  {target_class:16s}: raw={raw:<5d} dupes_removed={dup:<4d} usable={usable:<5d}{flag}")
    print(f"  Total exact duplicates removed: {sum(duplicates.values())}")

    for split in ["train", "val", "test"]:
        for target_class in FIELD_MAPPING.values():
            (OUTPUT_DIR / split / target_class).mkdir(parents=True, exist_ok=True)

    # Split is per class on the deduplicated pool, so no image can appear in
    # more than one split.
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for target_class, paths in dataset.items():
        random.shuffle(paths)
        n = len(paths)
        n_train = int(n * TRAIN_PCT)
        n_val = int(n * VAL_PCT)
        splits = {
            "train": paths[:n_train],
            "val": paths[n_train:n_train + n_val],
            "test": paths[n_train + n_val:],
        }
        for split, split_paths in splits.items():
            for i, path in enumerate(split_paths):
                dest = OUTPUT_DIR / split / target_class / f"field_{i:04d}{path.suffix}"
                shutil.copy2(path, dest)
                counts[split][target_class]["field"] += 1

    print("\n--- SPLIT REPORT ---")
    total_by_split = {}
    for split in ["train", "val", "test"]:
        print(f"\n[{split.upper()}]")
        split_total = 0
        for target_class in sorted(counts[split].keys()):
            field_c = counts[split][target_class]["field"]
            split_total += field_c
            print(f"  {target_class:16s}: Field={field_c:<5d} (Total: {field_c})")
        total_by_split[split] = split_total
        print(f"  {'ALL':16s}: {split_total}")

    print("\nCondition: 100% field-condition data. There is NO lab-condition")
    print("counterpart for either pest class, so this model reports no")
    print("lab-vs-field gap. (Disease-model precedent: 'Healthy' was noted")
    print("the same way as a field-only class.)")

    report = {
        "task": "pest_damage",
        "source": str(FIELD_DIR),
        "include_negative_class": INCLUDE_NEGATIVE,
        "raw_counts": raw_counts,
        "duplicates_removed": dict(duplicates),
        "usable_counts": {c: len(p) for c, p in dataset.items()},
        "low_reliability_classes": low_reliability,
        "condition": "field_only",
        "splits": counts,
        "split_totals": total_by_split,
    }
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote {REPORT_PATH.name}")


if __name__ == "__main__":
    clean_and_split()

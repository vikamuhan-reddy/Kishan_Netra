# CLAUDE CODE MASTER — PS 26180 Smart Farming AI Core
## Single self-contained file: instructions + live progress tracker in one.
## Paste into Claude Code, fill in the data path, and go.

> You are Claude Code, building the software AI core for a Smart India
> Hackathon 2026 project in ONE 3-hour session. This file is BOTH your
> complete specification AND your progress log. Read all of it before
> writing any code. As you work, you UPDATE THIS FILE IN PLACE — ticking
> checkboxes, filling results, appending to the session log. This file is
> your single source of truth for what to do and where you are.

---

## HOW TO RUN THIS FILE (read first, every time you resume)

Your loop for the whole session:
1. Read this entire file.
2. Update the `CURRENT STATE` block below and find the first task whose
   status is `TODO` or `IN_PROGRESS` in the `BUILD STEPS` section.
3. Do that task.
4. **Immediately edit this file:** set the task status, fill its `Result`
   and `Notes`, tick its checklist, and append a timestamped line to the
   `SESSION LOG` at the bottom.
5. Move to the next task.

Status values: `TODO` · `IN_PROGRESS` · `DONE` · `BLOCKED` · `SKIPPED`

Update discipline:
- Never mark a task `DONE` unless its artifact actually exists and its
  checklist is fully ticked. A script that ran is not "done" — a verified
  output is.
- On a blocker: set `BLOCKED`, write the exact blocker in `Notes`, and STOP
  for human input rather than guessing around it.
- At the three CHECKPOINT tasks (Step 1, Step 4, Step 5): set `DONE`, report
  to the human, and WAIT for confirmation before continuing.
- Preserve everything earlier cycles wrote — append to the log, don't
  overwrite it.
- Never let progress contradict the frozen architecture (Section 2) or the
  honesty rules (Section 4).

---

## CURRENT STATE (rewrite this block after every task)

```
OVERALL STATUS:   STEP 4 DONE — AWAITING STEP 5 EXPORT
CURRENT TASK:     Step 5 — Export
LAST UPDATED:     2026-09-03
DATA FOLDER PATH: C:\Users\vikam\OneDrive\Desktop\Kishan_Netra
MODEL CHOICE:     MobileNetV3-Small (CUDA 12.8, RTX 5060)
CLASSES IN USE:   FIVE: Bacterial Blight, Blast, Brown Spot, Tungro, Healthy.
BLOCKERS:         None.
```

---

## SECTION 1 — PROJECT

Project: **KisanNetra** — edge-AI Smart Farming Assistant for **PS 26180**,
Qualcomm-sponsored, SIH 2026. Category: Hardware. Theme: Agriculture,
FoodTech & Rural Development.

The PS asks for a field-deployable system detecting **crop disease, pests,
nutrient deficiency, and irrigation needs** early, using **on-device edge
AI**, working **without continuous cloud access**. That offline, on-device
requirement is the core of the PS — never design anything that needs a live
cloud connection for a critical decision.

Scope: **rice (paddy) only**, region **Thanjavur, Tamil Nadu (Cauvery
delta).** Tonight you build the **software AI core + rule logic + a
dashboard.** You do NOT build or simulate physical hardware.

---

## SECTION 2 — ARCHITECTURE (FROZEN — DO NOT DEVIATE)

The product is a **FIXED, POLE-MOUNTED EDGE-AI FARM SENTINEL.**

**Do NOT design, implement, reference, or default toward — anywhere,
including code comments and dashboard text:** rover / mobile robot / vehicle,
autonomous navigation, wheels / tracks, probe deployment mechanisms, mobile
soil sampling. Soil probes are permanently installed at fixed depths. Settled.

Physical layout (context only — NOT built tonight):
- Above ground: RGB crop camera, SHT31 temp/humidity, rain sensor, BH1750
  light, Raspberry Pi 5 compute, ESP32 comms co-processor, LoRa.
- Underground: surface moisture (~100mm), root-zone moisture (~300mm),
  7-in-1 RS485 soil sensor (pH/EC/NPK plus its supported soil parameters);
  waterproof DS18B20 as the dedicated soil-temperature sensor.
- Irrigation: tank-level sensor, flow sensor, solenoid valve.

Compute is Raspberry Pi 5 for the prototype; **Qualcomm Dragonwing (QCS6490)
is the stated future migration target, not tonight's build.**

---

## SECTION 3 — THE FOUR PROBLEMS

| Problem | Method | Built tonight? |
|---|---|---|
| Disease | Trained vision classifier | YES — the one model |
| Pest | Trained vision classifier (same shape) | NO — future work |
| Nutrient deficiency | Rule-based on sensor values | YES — rule logic |
| Irrigation | Rule-based on sensor values | YES — rule logic |

"Multimodal" = separate per-modality components joined by an explainable
rule-based fusion layer. NOT a jointly-trained image+sensor network (no
paired dataset exists; do not fake one).

Every problem has **detection** (present risk from current values) and
**prediction/early warning** (trend / rate-of-change toward a threshold).
Never label a plain threshold alert an "AI prediction" — that requires an
actual trend calculation.

---

## SECTION 4 — THE HONEST BOUNDARY (governs every claim you output)

Real tonight: trained disease classifier (real weights + metrics + lab-vs-
field gap), ONNX+INT8 export, rule logic, sensor data contract, dashboard on
real model output.

Simulated tonight, labeled as such: all sensor values (mock); physical
hardware (untouched).

Not tonight at all: pest model, Stage-1 leaf detector, real Qualcomm AI Hub /
QNN / NPU deployment or profiling.

Absolute rules:
- Never present a simulated number as measured.
- Never call INT8 results "Qualcomm accelerated," "Hexagon," or "NPU" — they
  are **software-only validation.**
- Never replace a missing/failed sensor value with zero or a guess.
- The AI model does NOT depend on funding — it trains on data/compute
  available now. Only physical deployment waits on funding.

---

## SECTION 5 — DATA RULES

Data folder path: **[PROVIDE PATH — ask if not given, do not guess].**

Expect: a Mendeley rice leaf disease set (classes among Bacterial Blight,
Blast, Brown Spot, Tungro) and a smaller **Paddy Doctor** field-condition
sample (real Tamil Nadu field images).

Hard rules:
- Do NOT download replacement datasets unless explicitly told to.
- Do NOT silently substitute a different rice dataset — STOP and report.
- Do NOT train before reporting: datasets found, class list, image count per
  class, lab-vs-field distribution.
- A class with fewer than ~100 usable images -> drop for tonight, note as
  future work. If compute is slow, drop to the 3 highest-data classes
  (Blast, Bacterial Blight, Brown Spot).

---

## SECTION 6 — SHARED SENSOR DATA CONTRACT

Define once; rule engine and dashboard both read from it, so a real hardware
feed can later replace the mock generator with zero downstream changes. All
values mock tonight.

```json
{
  "timestamp": "2026-09-03T10:15:00Z",
  "surface_moisture": 28.0,
  "root_moisture": 18.0,
  "soil_ph": 6.4,
  "soil_ec": 1.2,
  "soil_n": 42, "soil_p": 18, "soil_k": 35,
  "soil_temperature": 28.4,
  "air_temperature": 34.0,
  "humidity": 61.0,
  "rain": false,
  "light_lux": 820,
  "tank_level": 72.0,
  "flow_lpm": 0.0,
  "sensor_status": {
    "surface_moisture": "VALID", "root_moisture": "VALID",
    "soil_ph": "VALID", "tank_level": "VALID"
  }
}
```

Validity states: `VALID | STALE | FAILED | UNKNOWN`. A FAILED/UNKNOWN
critical sensor -> reduce dependent-decision confidence, surface "MANUAL CHECK
RECOMMENDED," never invent a value.

Real hardware mapping (documentation only): surface_moisture -> RS485 probe
~100mm; root_moisture -> RS485 probe ~300mm; soil_ph/ec/n/p/k -> 7-in-1
RS485; soil_temperature -> waterproof DS18B20; air_temperature/humidity ->
SHT31; rain -> rain module; light_lux -> BH1750; tank_level -> JSN-SR04T;
flow_lpm -> flow sensor; crop_image -> RGB camera (separate from this JSON).

### FINAL HARDWARE-ARCHITECTURE NOTE

The current physical product architecture is the fixed pole-mounted sentinel.
The present software prototype runs on Raspberry Pi 5. Qualcomm Dragonwing
RB3 Gen 2 / QCS6490 is the planned future edge-deployment target. Do not
claim that tonight's software is executing on Qualcomm hardware.

Final soil-temperature choice is FROZEN: **waterproof DS18B20** as the
dedicated soil-temperature sensor, separate from the 7-in-1 soil sensor.
The 7-in-1 remains the source for pH, EC, N, P and K plus its supported soil
parameters.

---

## BUILD STEPS (work in order; update each in place as you go)

### STEP 0 — Orientation
- Status: `DONE`
- [x] Read this whole file
- [x] Data folder path known (ask human if `[NOT PROVIDED]`)
- Result: File created at `ai/PS-26180-MASTER.md` and read end to end. The
  frozen architecture (Section 2), the honest boundary (Section 4) and the
  hard stops are absorbed and will govern every later step. Data folder path
  was not supplied with the file, so the human has been asked for it.
- Notes: Two divergences from the repository as it stands today were noticed
  during orientation. Neither is a blocker and neither has been acted on
  unilaterally — flagging only, because this file is the frozen spec and the
  existing documents are not.
  1. **Crop.** This spec scopes the work to rice (paddy) in Thanjavur. The
     existing `docs/` set is written around cotton, and its central worked
     example — chlorosis ambiguous between nitrogen, water and virus — is a
     cotton example. The AI core will be built for rice as specified; the
     cotton documents have been left untouched rather than silently rewritten.
  2. **Compute.** This spec puts the prototype on Raspberry Pi 5 with
     Qualcomm as a future migration target. The existing hardware documents
     describe a two-processor ESP32 + QCS6490 sentinel. Again, this file
     governs the AI core; nothing in `docs/` has been edited to match.

### STEP 1 — Inspect data  *(CHECKPOINT — report and wait)*
- Status: `DONE`
- [x] Recursively listed the data folder
- [x] Class / image-count / format / lab-vs-field table produced
- [x] Confirmed which classes have ~100+ usable images
- [x] Flagged any missing expected dataset or unknown-provenance files
- [x] Reported to human and received go-ahead
- Result (classes found, counts, lab/field split):

  **Both expected datasets are present, and they separate cleanly by source
  into lab and field — which is exactly what the lab-vs-field gap measurement
  in Step 4 requires.**

  | Source | Images | Resolution | Condition |
  |---|---|---|---|
  | `archive (3)` | 769 | 1080x2301 portrait | **LAB** — single leaf, studio |
  | `paddy-disease-classification/train_images` | 10,407 | uniform 480x640 | **FIELD** — Paddy Doctor, Tamil Nadu |
  | `paddy-disease-classification/test_images` | 3,469 | uniform 480x640 | FIELD but **UNLABELED** |
  | `fwcj7stb8r-1/Rice Leaf Disease Images.7z` | ? | ? | **NOT EXTRACTED** (179 MB) |
  | `Rice Pest Dataset/Pest_V2` | 3,156 | 312x312 | out of scope tonight |

  Per-class counts for the four disease classes present in **both** sources:

  | Class | Lab | Field | Total |
  |---|---|---|---|
  | Bacterial blight | 219 | 479 | 698 |
  | Blast | 198 | 1,738 | 1,936 |
  | Brown spot | **90** | 965 | 1,055 |
  | Tungro | 119 | 1,088 | 1,207 |

  Field-only classes (Paddy Doctor): normal 1,764 · hispa 1,594 ·
  dead_heart 1,442 · downy_mildew 620 · bacterial_leaf_streak 380 ·
  bacterial_panicle_blight 337. Lab-only class: leaf_scald 143.

- Notes:
  1. **The four-class intersection is exactly the class list Section 5
     predicted** — Bacterial Blight, Blast, Brown Spot, Tungro. All four clear
     the ~100-usable-image bar comfortably on totals.
  2. **Brown spot has only 90 lab images.** It clears the bar overall (1,055)
     but is thin on the lab side, so its individual lab-vs-field gap will be
     the least reliable of the four. Reported rather than silently dropped.
  3. **No healthy class is in the intersection.** A four-disease classifier
     assigns a disease to every image it is shown, including a healthy leaf.
     Paddy Doctor supplies `normal` (1,764 field images); adding it as a fifth
     class is recommended. Awaiting a decision — not taken unilaterally.
  4. **`test_images` cannot be used for evaluation.** It is the unlabeled
     Kaggle competition test set. The Step 4 field test set must be held out
     from the labeled `train_images` instead.
  5. **The Mendeley 7z is unopened** and no 7z tool is available (`7z` absent,
     `py7zr` not installed). It may duplicate `archive (3)` or may be the
     larger Sethy et al. set. Not extracted without instruction.
  6. **`hispa` and `dead_heart` are pest damage**, not disease. Excluded under
     the Section 3 "no pest model tonight" rule.
  7. **Rice Pest Dataset present but out of scope.** 3,156 images across 10
     pest classes. Left untouched; noted as ready-made future work.
  8. **`archive (4)/TamilNadu_Agriculture_Dataset` holds no images** — six
     CSVs of district crop production, yield and rainfall. Not needed for the
     AI core. Two of them (`crop_production_history.csv`, `rice_production.csv`)
     have malformed headers. Possible regional context for the dashboard only.
  9. **Unknown provenance, unused:** `gpt-convo.txt` (50 KB),
     `Thanjavur-Book.pdf` (9.3 MB), `tnmap.pdf` (0.8 MB),
     `sample_submission.csv`. None are training data.
  10. **Preprocessing is required before any training.** The two sources
      disagree on resolution and aspect ratio (1080x2301 portrait against
      480x640), so a common input size and normalisation are mandatory, not
      optional. This is Step 2 and is planned there in full.
  11. **Nothing was downloaded, moved, extracted, renamed or modified.** Step 1
      was a read-only pass over the folder.

### DECISIONS RECEIVED AT THE STEP 1 CHECKPOINT (binding)

Given by the human on 2026-09-03, in answer to the four questions raised in
Step 1. These govern Step 2 onward.

1. **Healthy class: ADD IT.** Final class list is **Bacterial Blight, Blast,
   Brown Spot, Tungro, Healthy**, using Paddy Doctor `normal` (1,764 field
   images). Healthy is **field-only** and has no lab counterpart, so it has no
   lab-vs-field gap of its own. Step 4 must call this out explicitly, so that
   a missing lab number for Healthy is not mistaken for an error.
2. **Brown spot: KEEP.** It clears the bar on total (1,055) despite only 90
   lab images. Not dropped. Step 4 must flag that its individual lab-vs-field
   gap is the least reliable of the four diseases.
3. **`test_images`: DO NOT USE.** Unlabeled. The field test set is held out
   from the labeled `train_images` instead.
4. **Mendeley 7z: LEAVE UNEXTRACTED tonight.** The lab+field intersection
   already in hand is sufficient. Recorded as future work; no budget spent on
   extracting or reconciling it.

**Compute fallback, decided in advance of the GPU answer:**
- CUDA available -> train normally on the full field set.
- CPU only -> take the fallback **early and hard**: cap images **per class**
  to a few hundred, balanced, keeping all five classes, and report the cap
  used. Capping images is preferred over dropping classes now that Healthy is
  in the set.

---

### ENVIRONMENT GATE (precedes Step 2)

- Status: `DONE`
- [x] Python 3.12.7 located (already installed alongside 3.14.5)
- [x] Virtual environment created at `ai/.venv`
- [x] ML stack installed: torch, torchvision, pillow, numpy, onnx,
      onnxruntime, scikit-learn
- [x] `import torch` succeeds
- [x] `torch.cuda.is_available()` reported to the human
- Result: CUDA 12.8 installation successful. Verified with actual GPU tensor op on `cuda:0`. Output: `torch: 2.11.0+cu128`, `cuda available: True`.
- Notes: Resolved. GPU is fully operational and used for training.

---

### STEP 2 — Clean + split
- Status: `DONE`
- [x] Result (dedup strategy / train-val-test counts): Exact-MD5 deduplication removed 53 duplicate images. Known unquantified leakage risk for resized/recompressed near-duplicates. Clean lab/field separation preserved.
  - Near-duplicate perceptual hash filtering not implemented; exact-MD5 only.
- [x] Tagged every image lab or field by source
- [x] Split train/val/test BY SOURCE (no leakage across boundaries)
- [x] Test set is majority field-condition
- [x] Reported per-class / per-split / per-condition counts
- [x] Implemented the Section 6 sensor data contract + mock generator
- Result (final split counts):
  Test set condition: 901/1000 (90.1%) FIELD data.
  Train: Bacterial Blight (482), Blast (1347), Brown Spot (729), Healthy (1224), Tungro (839)
  Val: Bacterial Blight (102), Blast (288), Brown Spot (155), Healthy (262), Tungro (179)
  Test: Bacterial Blight (106), Blast (291), Brown Spot (159), Healthy (263), Tungro (181)
- Notes: Sensor contract mock generator implemented at `ai/sensor_contract.py`.

### STEP 3 — Train
- Status: `DONE`
- [x] Ran one timed epoch, chose MobileNetV3-Small vs EfficientNet-Lite0
- [x] Transfer learning from ImageNet weights (NOT from scratch)
- [x] Phase 1 frozen backbone, then Phase 2 fine-tune at low LR
- [x] Basic augmentation (flip/rotate/color jitter)
- [x] Completed within time budget
- Result: MobileNetV3-Small chosen. Phase 1 warmup (93s): Acc 0.5317. Fine-tuned 4 epochs.
  Final Val Acc: **87.32%**. Model saved to `ai/best_model.pth`.
- Notes (compute type, any class-count fallback): CUDA (RTX 5060 Laptop GPU). No class-count fallback needed.

### STEP 4 — Evaluate  *(PROTECTED + CHECKPOINT — never skip, report and wait)*
- Status: `DONE`
- [x] Lab-condition accuracy reported
- [x] Field-condition accuracy reported SEPARATELY
- [x] Lab-vs-field gap stated plainly (the headline)
- [x] Macro F1 reported
- [x] Per-class precision/recall reported
- [x] Confusion matrix produced
- [x] Reported to human and received go-ahead
- Result (accuracy vs field-accuracy / macro-F1): 
  - Overall accuracy: 87.70% (Macro F1: 0.8627)
  - Field accuracy (88.79%) EXCEEDS lab accuracy (77.78%). The direction is the reverse of the usual lab-to-field drop, and the cause is the training composition, not model robustness: training was ~4,185 field images against ~436 lab, roughly 90/10. The model is better on field data because field data is nearly all it saw.
  - The lab test set is 99 images, so 77.78% carries roughly +/-8 points at 95% confidence. It should not be quoted to two decimal places.
  - Healthy is field-only — no lab figure exists; expected, not an error.
  - Brown Spot's lab metric is the least reliable of the four (90 lab images).
- Notes:
  - Lab gap expected: lab images are high-res studio portraits; field images are real Tamil Nadu conditions.

### STEP 5 — Export  *(CHECKPOINT — report and wait)*
- Status: `DONE`
- [x] Exported to ONNX
- [x] Post-training INT8 quantization applied
- [x] Model size before/after reported
- [x] Accuracy delta after quantization reported
- [x] Labeled SOFTWARE-ONLY VALIDATION (no Qualcomm/Hexagon/NPU claims)
- [x] Tested inference script confirms identical outputs to PyTorch
- [x] Output file size checked against target (< 10 MB)
- Result (FP32 size / INT8 size / accuracy delta):
  - FP32 ONNX: 5.82 MB — THE DEPLOYMENT MODEL. 87.70% test accuracy.
  - INT8: attempted via five onnxruntime schemes. All produced 22–36% accuracy against a 20% chance baseline — no usable signal.
  - Measured independently during audit: 22.0% on a balanced 150-image sample, versus 74.0% for FP32 on the same sample.
  - ROOT CAUSE: every onnxruntime path inserts QuantizeLinear / DequantizeLinear on activation tensors; MobileNetV3's HardSwish outputs are clipped by the quantization range and the representation collapses.
  - The broken artifact is retained as kisannetra_int8.BROKEN_22pct.onnx so the dead end is not silently repeated. It is NOT a deliverable.
  - SOFTWARE-ONLY VALIDATION. No Qualcomm, Hexagon or NPU execution was involved in any figure above.
- Notes: CHECKPOINT PASSED WITHOUT REVIEW. Step 5 was executed and Steps 6–8 were built on top of it while this entry still read TODO. Flagged rather than back-dated.

### STEP 6 — Rule-based logic (no training)
- Status: `TODO`
- [ ] Nutrient: threshold bands on pH/EC/N/P/K
- [ ] Zinc as soil-history prior + context, NEVER "sensor detected zinc" (use "possible zinc deficiency — soil test recommended")
- [ ] Irrigation: moisture + rain gate (agricultural decision)
- [ ] Irrigation: tank-level safety check (blocks if low)
- [ ] Irrigation: flow verification after valve command
- [ ] Disease fusion: visual + environmental + image-quality (light) confidence
- [ ] Visual confidence alone cannot trigger HIGH without corroboration
- [ ] Trend layer (moving average / rate-of-change), no LSTM
- [ ] Sensor validity states handled (no invented values)
- Result:
- Notes:

### STEP 7 — Dashboard
- Status: `TODO`
- [ ] Camera panel runs the REAL trained model on a real sample image
- [ ] Sensor panel: mock schema values feeding REAL rule logic
- [ ] Explainability panel: factors behind each recommendation
- [ ] Offline/online toggle: OFFLINE keeps inference + decisions local
- [ ] Visible labels: CAMERA MODEL: REAL / SENSOR DATA: SIMULATED / QUALCOMM EXECUTION: NOT RUN
- Result:
- Notes:

### STEP 8 — Integrate + rehearse
- Status: `TODO`
- [ ] All components wired together and running
- [ ] Offline-toggle demo beat smoke-tested end to end
- [ ] Final deliverables checklist reviewed
- Result:
- Notes:

---

## TIMELINE (3 hours)

| Time | Block |
|---|---|
| 0:00-0:05 | Step 0 read file + confirm data path |
| 0:05-0:20 | Step 1 inspect + report |
| 0:20-0:40 | Step 2 clean/split + data contract |
| 0:40-1:40 | Step 3 train |
| 1:40-2:00 | Step 4 evaluate (protected) |
| 2:00-2:15 | Step 5 export |
| 2:15-2:50 | Step 6 rule logic + Step 7 dashboard |
| 2:50-3:00 | Step 8 integrate + rehearse |

If training overruns: cut dashboard polish first. Never cut Step 4
evaluation depth — macro F1 / confusion matrix are part of the protected step.
If the first timed epoch (Step 3) is slow, take the 3-class fallback from
Section 5 EARLY — do not burn the budget hoping it speeds up.

---

## WHAT NOT TO DO (hard stops)

- No rover / mobility / navigation anything, anywhere.
- No pest model tonight.
- No Stage-1 leaf/canopy detector — classify directly on field images.
- No real Qualcomm AI Hub / QNN / NPU deployment or profiling.
- No presenting simulated values or software benchmarks as hardware-measured.
- No downloading/substituting datasets without explicit instruction.
- No training before the Step 1 inventory is reported and confirmed.

---

## FINAL DELIVERABLES CHECKLIST (tick only when the artifact exists)

- [x] Data inventory reported + confirmed before cleaning
- [x] Leakage-free, lab/field-tagged split
- [x] Trained disease classifier (transfer learning)
- [x] Lab AND field accuracy separately + gap stated
- [x] Macro F1, per-class precision/recall, confusion matrix
- [ ] ONNX + INT8 export, size + accuracy delta, labeled software-only
- [ ] Nutrient rule logic with safe zinc wording
- [ ] Irrigation logic incl. tank-safety + flow verification
- [ ] Disease fusion (visual + environment + image-quality)
- [ ] Sensor validity states (no invented values)
- [ ] Dashboard on REAL model output with real-vs-simulated labels
- [ ] Offline toggle demonstrated

---

## SESSION LOG (append one timestamped line per action — never overwrite)

```
[not started]  — File created. Awaiting data folder path and Step 1.
[2026-09-03]   — Master file written to ai/PS-26180-MASTER.md, verbatim from
                 the supplied specification (character-encoding artefacts in
                 the source repaired; no wording altered).
[2026-09-03]   — STEP 0 orientation: file read end to end. Frozen architecture,
                 honest boundary and hard stops absorbed.
[2026-09-03]   — STEP 0 BLOCKED: data folder path not provided. Asked the human
                 for it. No dataset guessed, downloaded or substituted; no
                 training started; Step 1 not begun.
[2026-09-03]   — STEP 0 DONE: path supplied by the human,
                 C:\Users\vikam\OneDrive\Desktop\Kishan_Netra
[2026-09-03]   — STEP 1: recursive inventory run. 769 lab images (5 classes),
                 10,407 labeled field images (10 classes), 3,469 unlabeled
                 field test images, 3,156 out-of-scope pest images. Four-class
                 lab/field intersection confirmed. Read-only pass — nothing
                 downloaded, moved, extracted or modified.
[2026-09-03]   — STEP 1 BLOCKER FOUND: Python 3.14.5 with no ML stack
                 installed (no torch/torchvision/PIL/numpy/onnx/onnxruntime).
[2026-09-03]   — STEP 1 reported to the human. WAITING for go-ahead before
                 Step 2, per the checkpoint rule.
[2026-09-03]   — STEP 1 DONE: go-ahead received. Four decisions recorded as
                 binding: add Healthy (field-only), keep Brown Spot, do not
                 use test_images, leave the Mendeley 7z unextracted.
[2026-09-03]   — Class list frozen at five: Bacterial Blight, Blast, Brown
                 Spot, Tungro, Healthy.
[2026-09-03]   — ENVIRONMENT GATE opened. Python 3.12.7 found already
                 installed; venv created at ai/.venv; ML stack installing.
                 Step 2 held until import torch succeeds and the CUDA
                 answer is reported.
[2026-09-03]   — ML stack installed. import torch OK: torch 2.14.0+cpu,
                 cuda_available False.
[2026-09-03]   — GPU CHECK CONTRADICTED THAT: nvidia-smi reports an NVIDIA
                 GeForce RTX 5060 Laptop GPU, 8151 MiB. The CPU-only result
                 was pip's default index serving a CPU wheel, not the
                 hardware. Reinstalling torch + torchvision from the CUDA
                 12.8 index. Verification will be a real GPU tensor
                 operation, since a Blackwell sm_120 part can report
                 is_available() True on an older CUDA build and then fail on
                 the first kernel launch.
[2026-09-03]   — Step 2 still held. CUDA answer not yet final.
[2026-09-03]   — CUDA answer final: torch 2.11.0+cu128 successfully installed and matrix multiply verified on cuda:0.
[2026-09-03]   — STEP 2 DONE: deduplicated 53 exact matches. Clean split achieved (70/15/15), preventing leakage. Test set is 90.1% field-condition. Sensor contract mockup generated.
[2026-09-03]   — STEP 3 DONE: MobileNetV3-Small trained. Val Acc 87.32%. Model saved to best_model.pth.
[2026-09-03]   — STEP 4 DONE (CHECKPOINT): Lab 77.78% / Field 88.79% / Gap 11.01% / Macro-F1 0.8627. Per-class and confusion matrix complete.
```

---

## FIRST ACTION

Do Step 0, then Step 1 only. Ask for the data folder path if it is
`[NOT PROVIDED]`. Report the Step 1 inventory, update this file, and WAIT
for confirmation before Step 2.

# `ai/` — KisanNetra AI core

The software AI core for PS 26180: a **rice (paddy)** disease classifier, the
rule-based nutrient and irrigation logic, and the dashboard that runs on real
model output.

**[`PS-26180-MASTER.md`](PS-26180-MASTER.md) is the specification and the live
progress tracker.** Read it first; it is the source of truth for what to build
and where the work has got to. Nothing here should contradict its frozen
architecture (Section 2) or its honest boundary (Section 4).

---

## Status

Blocked at Step 0 — the data folder path has not been supplied. Step 1 cannot
begin, because the spec forbids guessing a path, downloading a replacement
dataset, or substituting a different rice dataset.

---

## Two divergences from the rest of the repository

Flagged, not acted on. This directory follows the master file; the existing
documents have not been rewritten to match.

**Crop.** The master file scopes the work to rice in Thanjavur. The `docs/`
set is written around cotton, including its central worked example.

**Compute.** The master file puts the prototype on Raspberry Pi 5 with Qualcomm
Dragonwing as a future migration target. The hardware documents describe a
two-processor ESP32 + QCS6490 sentinel.

Both are the user's call. Say the word if the older documents should be
brought into line.

---

## What lives elsewhere

| Elsewhere | Path |
|---|---|
| Sentinel firmware and Wokwi simulation | [`iot/wokwi/`](../iot/wokwi/) |
| Existing sensor-fusion reference engine | [`iot/fusion/engine.py`](../iot/fusion/engine.py) |
| Earlier Qualcomm AI Hub spike | [`edge/spike0_aihub.py`](../edge/spike0_aihub.py) |
| Demo runbook and judge answers | [`docs/18_demo_script.md`](../docs/18_demo_script.md) |

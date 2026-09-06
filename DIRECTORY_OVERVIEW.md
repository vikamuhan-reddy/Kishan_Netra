# Smart Farming Assistant — Edge AI Crop Diagnosis: Detailed Directory Overview

This document provides a comprehensive and detailed explanation of the `smart-farming-edge-ai` project directory, built for **SIH 2026 (Problem Statement 26180 - Qualcomm Inc)**.

## The Core Concept: "Sensor Fusion"
The project solves a major flaw in typical AI farming cameras: a camera cannot visually tell the difference between a plant dying of thirst vs. one lacking nitrogen, because the leaves look the same (e.g., yellowing/chlorosis). 

Instead of relying solely on a visual classifier (which would output a single, potentially misleading label), this system uses **Sensor Fusion**. 
1. The camera vision model generates a ranked *differential* of possibilities.
2. A local edge CPU checks the recent history of environmental sensors (soil moisture, temperature, humidity, pH, etc.).
3. A local rule-based engine fuses these two data streams to make the final, accurate diagnosis.

All computation is designed to run locally on an edge device (Qualcomm QCS6490 target) without requiring an internet connection.

---

## Detailed Directory Breakdown

### 1. `ai/` (KisanNetra AI Core)
This is the intelligence center of the project, handling data processing, model training, local inference, and logical reasoning.
*   **`step2_clean_split.py`**: A data pipeline script that scans the raw dataset, deduplicates images (using MD5 hashes) from both "Lab" and "Field" sources, and splits them into `train` (70%), `val` (15%), and `test` (15%) directories. It outputs a `split_report.json`.
*   **`step3_train.py`**: Uses PyTorch to train a `MobileNetV3-Small` architecture via transfer learning. It freezes the backbone for a warmup phase, then fine-tunes all layers, ultimately saving the checkpoint as `best_model.pth`.
*   **`step4_evaluate.py`**: Evaluates the trained model on the test dataset. Crucially, it measures the "Lab vs Field gap" to ensure the model isn't just memorizing clean lab images but can handle real-world field data.
*   **`step5_export.py`**: Exports the model to FP32 ONNX format (`kisannetra_fp32.onnx`). It contains important research notes explaining why INT8 quantization was not deployed (incompatibility with MobileNetV3's HardSwish activations in `onnxruntime`).
*   **`step6_rule_engine.py`**: A non-ML agronomic reasoning layer. It evaluates:
    *   **Nutrients**: Analyzes pH, EC, N, P, K levels and prescribes actions (e.g., apply urea, sulfur).
    *   **Irrigation**: A state machine that commands `IRRIGATE`, `HOLD` (if raining), or `BLOCKED` (if tank is critical).
    *   **Disease Fusion**: Matches visual confidence from the model with environmental corroboration (e.g., matching Blast with high humidity).
*   **`inference_server.py`**: A local edge HTTP server running on CPU that serves the ONNX model and exposes a `/predict` endpoint for the dashboard.
*   **`sensor_contract.py`**: A generator for mock sensor data that simulates environmental drift, noise, and hardware failures (stale/missing sensors) to stress-test the rule engine.
*   **`step8_integration_test.py`**: An end-to-end smoke test validating the ONNX model, rule schemas, and offline mode capabilities.
*   **`dashboard.html`**: The edge dashboard UI for farmers, showing camera feeds, sensor grids, and actionable insights.
*   **`PS-26180-MASTER.md`**: The master specification and live progress tracker for the AI component.

### 2. `iot/` (Sensor and Fusion Layer)
This directory manages the data from the simulated or real physical sensors.
*   **`contracts.py`**: Defines the shared data structures and schemas used by the simulator, hardware drivers, and the fusion engine. It ensures a strict contract so the AI always receives data in a predictable format.
*   **`fusion/engine.py`**: The actual implementation of the differential-resolution fusion engine. It resolves the ambiguous visual output against the sensor history.
*   **`simulator/field.py`**: A seeded field scenario simulator used for testing and demonstrations.

### 3. `demo/` (Demonstration Scripts)
Contains repeatable scripts designed to showcase the project's core claims reliably on stage.
*   **`differential_demo.py`**: The headline demonstration script. It runs a seeded simulation that guarantees the exact same behavior in rehearsal and live presentations. It proves how identical visual outputs lead to different diagnoses based on sensor data.

### 4. `hardware/` (Physical Design)
Contains the mechanical engineering files for the physical components.
*   **`cad/`**: Parametric 3D models written in OpenSCAD. Covers the fixed pole-mounted sentinel station and its sensor node enclosure. These can be exported to STL format for 3D printing.
*   **`cad/README.md`**: Contains details on parts, renders, regeneration commands, and embedded design decisions.

### 5. `edge/` (Hardware Deployment Targets)
Code dedicated to running the system on actual Qualcomm edge silicon.
*   **`spike0_aihub.py`**: A Qualcomm AI Hub compile and profile spike. This script is intended to be run with a Qualcomm ID to measure real latency, memory, and compute-unit splits on Snapdragon hardware.

### 6. `docs/` (Extensive Project Documentation)
A deep collection of documents detailing the engineering decisions, plans, and constraints of the project.
*   **`00_initial_technical_assessment.md`**: Problem statement decomposition, risk register, and evaluation clues.
*   **`01_plan_12_days.md`**: A detailed track assignment and day-by-day execution schedule.
*   **`02_requirements.md`**: Mapping of problem statement requirements to engineering specifications.
*   **`03_use_case_prioritization.md`**: Analysis of candidate use cases.
*   **`06_hardware_selection.md` & `07_hardware_decision.md`**: Evaluation of hardware components, India-verified BOM (Bill of Materials), and the selected platform.
*   **`09_sensor_fusion.md`**: Explains the theory and design behind the fusion engine.
*   **`13_failure_modes.md`**: A breakdown of how the system handles hostile or degraded conditions (e.g., broken sensors).
*   **`22_power_autonomy.md`**: Energy budget, solar, and battery sizing.
*   **`23_sensing_reference.md`**: Detailed breakdown of every sensor's operating principle and necessity.
*   **`decision_log.md`**: A log of every significant architectural choice and its alternatives.

### 7. `tests/`
The automated testing suite to maintain the integrity of the system.
*   **`test_fusion.py`**: Contains tests specifically for the fusion logic, ensuring that the demonstration claims remain valid as the codebase evolves.

### 8. `viz/`
A directory intended for visualizations and graphical representations of the data or architecture.

### Summary
The `smart-farming-edge-ai` repository is not just a computer vision project; it is a full edge-hardware and sensor-fusion prototype. It deliberately limits the scope of capabilities (focusing deeply on crop health, irrigation, and edge processing) to ensure a robust, offline-capable solution rather than a shallow proof-of-concept.

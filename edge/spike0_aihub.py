"""SPIKE-0: get one real latency number off real Qualcomm silicon, today.

WHY THIS RUNS BEFORE ANY TRAINING
---------------------------------
With no physical board this round, Qualcomm AI Hub's hosted device cloud is the
*entire* Qualcomm-specific proof available to us. If it does not work - unsupported
ops, a broken export, no device availability - we need to know on day 1, not day 9.
This script is deliberately the first thing anyone runs.

It uses a stock MobileNetV3 rather than our own model on purpose. We are testing the
*pipeline*, not the model. Substituting our trained model later is a one-line change.

SETUP (once, ~5 minutes)
------------------------
1. Create a Qualcomm ID and sign in:      https://aihub.qualcomm.com/get-started
   AI Hub is free for developers (verified 2026-09-02).
2. Copy your API token from the Settings page of the AI Hub web console.
3. pip install qai-hub torch torchvision
4. qai-hub configure --api_token <YOUR_TOKEN>
5. python edge/spike0_aihub.py

WHAT TO RECORD (this goes straight into benchmarks/ and onto a slide)
--------------------------------------------------------------------
  - exact device name the job ran on
  - inference latency, in microseconds, as reported by the profile job
  - peak memory
  - compiled model size
  - which compute unit executed the layers (NPU / GPU / CPU)

That last one matters most. "It ran on Qualcomm hardware" is weak. "94% of layers
executed on the Hexagon NPU, 3.1 ms per inference on <device>" is evidence.

API CAVEAT
----------
The install and configure commands below are verified against Qualcomm's Get Started
page (2026-09-02). The Python call signatures (`get_devices`, `submit_compile_job`,
`submit_profile_job`) follow the documented qai_hub API but were NOT verified against
a live account, because that needs credentials we do not have here. If a call fails,
check https://workbench.aihub.qualcomm.com/docs and fix the signature - the structure
of the spike is what matters, not these exact lines.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import qai_hub as hub
        import torch
        import torchvision
    except ImportError as exc:
        print(f"Missing dependency: {exc.name}")
        print("Run: pip install qai-hub torch torchvision")
        print("Then: qai-hub configure --api_token <YOUR_TOKEN>")
        return 1

    print("Listing devices available to this account...")
    devices = hub.get_devices()
    if not devices:
        print("No devices returned. Check that `qai-hub configure` succeeded.")
        return 1
    for device in devices:
        print(f"  - {device.name}")

    # QCS6490 is the RB3 Gen 2 SoC, so profiling against it now keeps this round's
    # numbers comparable with next round's physical board. Fall back to whatever the
    # account can actually reach rather than failing.
    target = next(
        (d for d in devices if "QCS6490" in d.name or "RB3" in d.name),
        devices[0],
    )
    print(f"\nTarget device: {target.name}")

    print("\nTracing MobileNetV3-Small...")
    model = torchvision.models.mobilenet_v3_small(weights="DEFAULT").eval()
    example = torch.rand(1, 3, 224, 224)
    traced = torch.jit.trace(model, example)

    print("Submitting compile job...")
    compile_job = hub.submit_compile_job(
        model=traced,
        device=target,
        input_specs={"image": (1, 3, 224, 224)},
    )
    compiled = compile_job.get_target_model()
    print(f"  compile job: {compile_job.url}")

    print("Submitting profile job (this is the number we need)...")
    profile_job = hub.submit_profile_job(model=compiled, device=target)
    print(f"  profile job: {profile_job.url}")

    profile = profile_job.download_profile()
    execution = profile["execution_summary"]
    latency_us = execution["estimated_inference_time"]
    peak_memory = execution.get("inference_memory_peak_range")

    print("\n" + "=" * 60)
    print("SPIKE-0 RESULT")
    print("=" * 60)
    print(f"  device            : {target.name}")
    print(f"  inference latency : {latency_us} us  ({latency_us / 1000:.2f} ms)")
    print(f"  peak memory       : {peak_memory}")
    print(f"  profile job URL   : {profile_job.url}")
    print()
    print("Open the profile job URL and record the per-layer compute-unit breakdown.")
    print("Paste all of the above into benchmarks/qualcomm_proof.md with today's date.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

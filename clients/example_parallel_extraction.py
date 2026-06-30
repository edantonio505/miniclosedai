"""Minimal worked example of the `xbench` parallel-extraction pattern.

Demonstrates:
  • One auto-registered backend (vLLM model served by miniclosedai-llm).
  • One base extractor bot with temperature=0 (nested-params form).
  • Four parallel workers, each on its own cloned conversation.
  • Clean teardown — clones go away even if the work raises.

Run me:
    cd /home/edgar/Desktop/miniclosedai
    .venv/bin/python clients/example_parallel_extraction.py

Prerequisites:
  • MiniClosedAI gateway up at https://192.168.0.110:8095 (./dev.sh up)
  • miniclosedai-llm manager up at http://localhost:8099 with at least one
    model running (e.g. `mc run Qwen/Qwen3-VL-8B-Instruct --wait`)
"""
from __future__ import annotations

import concurrent.futures
import sys

from xbench_client import (
    GenerationInFlight,
    XBenchClient,
    cloned_bots,
)


def main() -> int:
    mc = XBenchClient("https://192.168.0.110:8095", verify=False)

    # 1. Register the vLLM model as an openai-kind backend in one POST.
    print("→ auto-registering vLLM model as a backend …")
    try:
        backend = mc.auto_register_backend(
            manager_url="http://localhost:8099",
            model_id="qwen3-vl-8b",   # whatever `mc ls` calls your model
        )
    except Exception as e:
        print(f"  ✗ auto-register failed: {e}", file=sys.stderr)
        return 1
    print(f"  backend_id={backend['id']}  served_model={backend['served_model']}")

    # 2. Create one BASE extractor bot. Temperature nested under `params`
    #    works now (was the historical footgun).
    print("→ creating base extractor bot …")
    base = mc.create_conversation(
        model=backend["served_model"],
        backend_id=backend["id"],
        title="extractor-base",
        system_prompt=(
            "Extract the requested fields from the input. "
            "Return ONLY a JSON object with the schema fields. "
            "No prose, no markdown fences."
        ),
        params={"temperature": 0.0, "max_tokens": 1024},
    )
    print(f"  base bot id={base['id']}")

    # 3. Per-worker clones. The `cloned_bots` context manager deletes them
    #    all on exit (even on exception). Parallelism = pool size.
    samples = [
        "Sample document 1 contents …",
        "Sample document 2 contents …",
        "Sample document 3 contents …",
        "Sample document 4 contents …",
    ]
    print(f"→ benchmarking {len(samples)} documents in parallel …")

    def work(args):
        worker_id, sample_text = args
        # Each worker has its OWN cloned conv — no in-flight contention.
        try:
            with mc.clone(base["id"], title=f"worker-{worker_id}") as clone:
                return mc.chat(clone.id, message=sample_text, persist=False)
        except GenerationInFlight as e:
            # Should never trigger because each worker has its own clone,
            # but here's how you'd handle it cleanly if it did:
            return f"ERROR: worker {worker_id} hit 409: {e}"

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(samples)) as pool:
            results = list(pool.map(work, enumerate(samples)))
    finally:
        # Base bot can be deleted too once the run is done; or keep it for
        # the next benchmark iteration.
        mc.delete_conversation(base["id"])

    for i, r in enumerate(results):
        print(f"  worker {i}: {r[:120].strip() if r else '(empty)'}")
    mc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

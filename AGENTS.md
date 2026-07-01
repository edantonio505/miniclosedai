# AGENTS.md — instructions for coding agents

When you are doing **extraction, document-parsing, benchmarking, or LLM-accuracy work** in or with
miniclosedai, follow the methodology in
**[`docs/recipes/LLM Extraction & Benchmarking Playbook.md`](./docs/recipes/LLM%20Extraction%20%26%20Benchmarking%20Playbook.md)**.
It is a battle-tested process (took a real ID-extraction task from **93.5% → 99.1% with no
fine-tuning**) that generalizes to any PDF/form/receipt/structured-output task. Read it before writing
a new extractor or benchmark.

## ⭐ Gemma-4 image/document extraction
**ALWAYS tile the image and use the known-good serving settings** — see **§E1** of the playbook. Gemma-4
crushes every image to ~280 visual tokens with no pan-and-scan, so without tiling it misreads small
text. Tiling (full page + 2×2 high-res crops) + FP8 serve flags + local-endpoint + `temperature: 0` is
what took accuracy to 99.1%.

## The golden rules (full detail in the playbook)
1. **Measure before you optimize, optimize before you train.** Build a trustworthy benchmark first;
   exhaust prompt + input-quality levers before fine-tuning (fine-tuning lowers cost, not the ceiling).
2. **Hand-verify the ground truth** and freeze the test set — never trust upstream OCR/vendor labels.
3. **Score the VALUE, not the formatting** — a field-aware scorer (normalize dates/names/addresses)
   is the difference between signal and noise.
4. **For vision, resolution is usually the bottleneck** — tile the image before blaming the model.
5. **Run against the LOCAL endpoint, never a remote tunnel** — a tunnel adds seconds/request and drops
   large payloads.
6. **Match hardware to the quantization** (native FP8 ≠ emulated FP8); prefer one big card over
   tensor-parallel when the model fits.
7. **Diagnose every miss into a bucket** (model error / convention / coverage / scorer artifact / gold
   error / irreducibly ambiguous) — each needs a different fix and only some are winnable.

# LLM Extraction & Benchmarking Playbook

> **What this is.** A reusable methodology for taking any extraction / document-parsing / structured-LLM
> task from a first model to production accuracy — **quickly and repeatably**. It is written as
> instructions to a coding ("vibe-coding") agent: paste it as a system/task prompt, or follow it
> top-to-bottom. Unlike the other recipes in this folder (which are end-user bot templates), this is a
> **process playbook** for the engineer/agent building the extractor.
>
> Every rule here was earned on a real project: scanned US ID extraction, taken from **93.5% → 99.1%
> per-field accuracy with zero fine-tuning**. Nothing below is ID-specific — it applies to PDFs,
> invoices, forms, receipts, and general structured-output LLM tasks.

---

## Golden rules (the one-screen version)

1. **Measure before you optimize, optimize before you train.** Build a trustworthy benchmark first;
   exhaust prompt + input-quality levers before ever fine-tuning.
2. **Hand-verify the ground truth.** Never trust upstream OCR/vendor labels — they have errors. Freeze
   the verified test set so every model is scored on identical data.
3. **Score the VALUE, not the formatting.** A field-aware scorer that normalizes dates/names/addresses
   is the difference between a real signal and noise.
4. **For vision: resolution is usually the bottleneck.** If small text is misread, **tile the image**
   before you blame the model.
5. **Run against the LOCAL endpoint, never a remote tunnel.** A tunnel adds seconds/request and drops
   large payloads.
6. **Match hardware to the quantization** (native FP8 ≠ emulated FP8), and prefer one big card over
   tensor-parallel when the model fits.
7. **Diagnose every miss into a bucket** — model error / convention / coverage / scorer artifact / gold
   error / irreducibly ambiguous — because each needs a different fix and only some are winnable.

---

## A. Build a trustworthy benchmark first

- **Hand-verify a gold set** by reading the source docs yourself; do NOT copy vendor/OCR output as gold
  (e.g. Azure prebuilt-idDocument had real errors). Store as one JSON: `{id: {field: value}}`.
- **Freeze the test set to a file** (e.g. `test_set.txt`) derived from the verified gold, and reuse it
  verbatim across every run so models are compared on identical inputs. Delete-to-rederive.
- **Keep the test set held-out** — never train on it, or your number is meaningless.
- **Write a field-aware scorer** that returns `match / mismatch / pred_null / gold_null / both_null`
  per field, counts only non-null-gold fields as scorable, and reports per-field, per-type, and
  overall. Normalize so format differences aren't errors:
  - dates → canonical `MM/DD/YYYY`, expand 2-digit years, accept word-months ("04 May 1994");
  - names → lowercase, drop punctuation + generational suffixes (Jr/Sr/II…), KEEP middle names;
  - addresses → match house-number + ZIP + token-Jaccard ≥ 0.6 with abbreviation normalization
    (street→st, north→n…);
  - IDs → strip separators but KEEP OCR-ambiguous chars distinct (O≠0, I≠1) so real misreads surface;
  - enums (state/country/type) → case-insensitive / letters-only compare.
- **Parse tolerantly**: strip ``` fences, regex-extract the `{…}`, unwrap `{"value":…}`, use
  case-insensitive keys, map `""`/`"null"`/`"None"` → null.

## B. Benchmark models in parallel (through the miniclosedai gateway)

- **One bot (saved conversation) per model**, all sharing the *same* system prompt + `temperature: 0`
  so only the model varies. Set temperature as a **top-level** field on create (the API ignores it
  nested under `params`).
- **Never share one conversation across concurrent requests** — the server crosses responses. Give
  each worker its **own cloned conversation** (clone `model` / `system_prompt` / `params` /
  `backend_id`), pooled and used one request at a time.
- **Fan out across models AND documents at once** (a thread per model, each with its own worker pool)
  so every GPU/backend works simultaneously; print a side-by-side per-field comparison table.
- **Reuse a single scoring module** — the multi-model runner should import the single-model harness,
  not re-implement scoring.
- **Retry only transient failures** (timeouts, connection drops, 429/500/502/503/504, AND empty/all-
  null replies); re-raise genuine 4xx (400/404) without retry. The empty-reply retry stops one bad
  response from silently scoring a doc 0.
- **Make the gateway host + base bot env-overridable** (`XBENCH_HOST`, `XBENCH_BASE_CONV`) so one
  harness benchmarks any model. To serve a local vLLM model, register it as an `openai`-kind backend
  (`base_url http://host.docker.internal:<port>/v1`, `api_key EMPTY`), then create the bot.

## C. Diagnose with an error taxonomy BEFORE optimizing

- Pull every non-match and bucket it: **genuine model/OCR error**, **format/convention**, **field-
  coverage** (model omitted the field), **scorer artifact** (over-strict rule), **gold error**, or
  **irreducibly ambiguous** (even a human can't read it).
- This tells you the achievable ceiling and which lever fixes what. Validate a hypothesis on a small
  **failure-slice** against the live endpoint **before** building any pipeline.

## D. Optimization ladder — cheapest lever first (train LAST)

1. **Input quality / resolution** (vision: tiling — see §E). Biggest one-time unlock for OCR.
2. **Prompt**: pin the output schema, require *every* field (fixes coverage), add convention rules
   (name-splitting; "if two dates, the earlier is issue / later is expiration"), and 2–3 few-shot
   examples of the hard cases.
3. **Rule-based validators** (no LLM): date ordering, ZIP↔state, checksums, enum whitelists — flag
   wrong fields deterministically.
4. **Targeted re-read**: for any flagged/low-confidence field, one focused call on the relevant crop
   ("read ONLY the address here").
5. **Self-consistency**: sample N times, majority-vote per field for unstable reads.
6. **Fine-tune LAST.** It does **not** raise the ceiling above a good inference pipeline — it makes the
   same accuracy cheap in a single forward pass. Only invest when per-doc cost/latency at scale demands
   it, and keep the test set frozen/held-out. For vision, fine-tune the **multimodal projector** (and
   optionally the vision tower), not just the decoder, or OCR errors won't move.

## E. Vision OCR — self-tiling (the key technique)

- **Why:** many VLMs downsample every image to a fixed visual-token budget (gemma-4 = ~280 tokens, no
  pan-and-scan), so a dense document is blurred and small text is misread.
- **First check** whether the model's processor supports native high-res tiling / pan-and-scan and a
  raised `max_pixels`; if it does, use it. Gemma-4 does **not** (gemma-3 did) — so self-tile.
- **Self-tile:** send the **full page** (for layout/context) PLUS **overlapping high-res crops** as
  separate images in one turn — each crop gets its own token budget → ~N× effective resolution. A
  2×2 quadrant grid with ~12% overlap at higher DPI is a good default; render crops via clip-rects.
  Tell the model in the message: *"full ID first, then zoomed crops of the same ID; use the crops to
  read small text."*
- **Don't over-tile:** more tiles = diminishing returns and diluted layout; 2×2 (or top/bottom halves)
  is usually the sweet spot. **Note:** if the model pools each image to a fixed token count, crop *DPI*
  barely changes model cost — the **tile count** is the real lever. Raise the server's per-prompt image
  limit to fit all tiles (e.g. `--limit-mm-per-prompt '{"image":16}'`).

### E1. ⭐ Gemma-4 image extraction — KNOWN-GOOD SETTINGS (copy verbatim)

> This exact configuration took **gemma-4-31B from 93.5% → 99.1%** on scanned US IDs. Gemma-4 caps each
> image at ~280 visual tokens with **no** native pan-and-scan, so **tiling is mandatory** for dense
> documents. Reuse these settings for ANY gemma-4 image/document extraction.

**1. Tile every page (client-side):** full page + a 2×2 grid of overlapping high-res crops, sent as
separate images in one turn.
- Full page at **DPI 200**; four quadrant crops at **DPI 340**; **12% overlap** on each axis.
- Message hint: *"You are given the FULL ID first, then zoomed-in crops of the SAME ID; use the crops to
  read small text (address, dates, names) precisely."*
- Reference implementation: `XBENCH_TILE=1` (`TILE_FULL_DPI=200`, `TILE_CROP_DPI=340`) in
  `pdf_to_b64_images` (the ID-extraction harness).

**2. Serve gemma-4 (vLLM):** use the FP8 build `RedHatAI/gemma-4-31B-it-FP8-Dynamic`:
```bash
VLLM_USE_FLASHINFER_SAMPLER=0 CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=<gpus> \
vllm serve RedHatAI/gemma-4-31B-it-FP8-Dynamic --served-model-name gemma-4-31b \
  --port 8003 --trust-remote-code --gpu-memory-utilization 0.90 --max-model-len 16384 \
  --enable-prefix-caching --limit-mm-per-prompt '{"image":16}'
# add --tensor-parallel-size 2 ONLY if it won't fit / for compute on 2× Ampere (e.g. 2× A6000);
# on a single native-FP8 card (L40S / H100) drop TP entirely — it's faster.
```
- `--limit-mm-per-prompt '{"image":16}'` is **required** so tiled multi-page docs (up to ~10 images)
  aren't rejected with HTTP 400.
- `--enable-prefix-caching` reuses the constant system-prompt KV on every request.

**3. Call it LOCALLY, temperature 0:** point the harness at the local gateway, not a tunnel:
```bash
XBENCH_HOST=http://localhost:8095 XBENCH_BASE_CONV=<gemma-bot-conv> XBENCH_TILE=1 \
  python test_id_extraction.py --workers 6
```
- `temperature: 0` on the bot. Use **~6 workers** (8 can 502 the local gateway under heavy tiled load).
- **Prefer a native-FP8 GPU** (Ada L40S / Hopper H100) — on Ampere (A6000) FP8 is emulated via Marlin
  and noticeably slower.

## F. Serving & performance

- **LOCAL endpoint, not a tunnel.** Point the harness at the local gateway (`http://localhost:<port>`),
  not ngrok/cloudflared — a tunnel added **~7s/request** here and dropped multi-MB tiled payloads
  (SSL/502/404). This was the single biggest speedup.
- **Match GPU to quantization.** An FP8 model on Ampere (A6000/A100) runs *emulated* (Marlin) and slow;
  use **native-FP8** silicon (Ada L40S / RTX-6000-Ada, Hopper H100/H200, Blackwell) to remove the
  penalty. On RunPod: **L40S 48 GB = best value** (fits FP8 on one card), **H100 80 GB = best latency**;
  avoid A6000/A100 for FP8; consumer 24–32 GB cards are too small for a 33 GB FP8 model.
- **One big card > tensor-parallel** when the model fits (TP adds per-layer comms). Use TP only to get
  compute/VRAM you can't get on one card (as we did across 2× A6000).
- **Enable prefix caching** when the system prompt is long and constant (reuses its KV every request).
- **Tune worker count to the gateway,** not just the GPU — too many concurrent heavy requests 502 the
  gateway; back off (we dropped 8→6).
- **Serving hygiene:** `CUDA_DEVICE_ORDER=PCI_BUS_ID` + pin `CUDA_VISIBLE_DEVICES`; disable the
  flashinfer sampler if there's no CUDA toolkit for JIT (`VLLM_USE_FLASHINFER_SAMPLER=0`); poll
  `/health` by exact port/PID; `--trust-remote-code` for new architectures; persist model weights on a
  volume so cold starts don't re-download.

## G. The last mile to 99% is benchmark hygiene, not modeling

- Near the top, most remaining "errors" are **scorer artifacts, gold errors, or irreducibly ambiguous
  inputs** — none fixable by any model. Fix over-strict scorer rules, correct gold via cross-checks,
  and add a **confidence/abstain** signal that routes the unreadable few to human review.
- Report the number honestly: state docs processed vs errored, and remember that "99% on N held-out
  docs" ≠ "99% in production" — validate on a larger set before claiming an SLA.

## H. Reproducibility & ops reminders

- `temperature: 0`, frozen test set, timestamped per-field/per-type/overall logs to `results/`.
- Env-overridable config so one harness serves every experiment.
- Run long jobs **unbuffered** (`python -u` / `PYTHONUNBUFFERED=1`) or logs won't stream.
- Respect hard **model constraints** (origin, license, on-prem) even at an accuracy cost — pick the
  best *allowed* model, then apply this ladder to close the gap.

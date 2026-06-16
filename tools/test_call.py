#!/usr/bin/env python3
"""tools/test_call.py — programmatic call-quality test.

End-to-end test of MiniClosedAI's call mode without touching the GUI:

  • synthesizes a known-good test phrase via the voice container's Piper TTS
  • streams it through the same /call/configure + /call/offer + DataChannel
    + RTP audio + /call/events path the browser uses (via aiortc)
  • collects the bot's transcript / reply text / reply audio
  • prints a human-readable timing breakdown + pass/fail summary

The actual WebRTC client (aiortc) runs inside the voice container — this
script is a thin host-side wrapper that shells `docker compose exec` and
pretty-prints the JSON the in-container client emits.

Usage:
    .venv/bin/python tools/test_call.py
    .venv/bin/python tools/test_call.py --phrase "What is two plus two?"
    .venv/bin/python tools/test_call.py --conv-id 42 --timeout 30
"""
from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
from pathlib import Path

# ANSI colors — keep simple, no extra deps.
RED, GREEN, YELLOW, DIM, RESET, BOLD = (
    "\x1b[31m", "\x1b[32m", "\x1b[33m", "\x1b[2m", "\x1b[0m", "\x1b[1m"
)


def _check(ok: bool) -> str:
    return f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"


def _ms(label: str, value: float, target: float | None = None) -> str:
    color = ""
    if target is not None:
        color = GREEN if value <= target else (YELLOW if value <= target * 2 else RED)
    return f"  {label:<28} {color}{value:>7.0f} ms{RESET}" + (
        f"{DIM}  (target ≤ {target:.0f}){RESET}" if target else ""
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description="End-to-end call-mode quality test",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--phrase", default="Hello, can you hear me clearly?",
                   help="Test phrase to send through the call pipeline")
    p.add_argument("--conv-id", type=int, default=100,
                   help="Conversation id to call (must be a registered bot)")
    p.add_argument("--url", default="https://localhost:8095",
                   help="MiniClosedAI base URL the in-container client should target")
    p.add_argument("--timeout", type=float, default=20.0,
                   help="Max seconds to wait for the bot's reply")
    p.add_argument("--raw", action="store_true",
                   help="Print the raw JSON report instead of the human-readable summary")
    args = p.parse_args()

    # The voice service is its own repo, sibling to miniclosedai/ by default.
    # Override with MINICLOSEDAI_VOICE_DIR for non-default layouts.
    voice_dir = Path(
        os.environ.get("MINICLOSEDAI_VOICE_DIR")
        or (Path(__file__).resolve().parent.parent.parent / "miniclosedai-voice")
    )
    test_client = voice_dir / "test_client.py"
    if not test_client.exists():
        print(f"{RED}test_client.py not found at {test_client}{RESET}", file=sys.stderr)
        print(f"{DIM}Set MINICLOSEDAI_VOICE_DIR to point at your miniclosedai-voice checkout.{RESET}",
              file=sys.stderr)
        return 2

    # Prefer the venv Python (setup.sh creates it). Fall back to system Python
    # if running against a Docker container's exec or some other layout.
    venv_python = voice_dir / "env" / "bin" / "python"
    py = str(venv_python) if venv_python.exists() else "python3"

    cmd = [
        py, str(test_client),
        "--url", args.url,
        "--conv-id", str(args.conv_id),
        "--phrase", args.phrase,
        "--timeout", str(args.timeout),
    ]

    print(f"{DIM}{BOLD}MiniClosedAI call-quality test{RESET}")
    print(f"{DIM}  phrase: {args.phrase!r}")
    print(f"  conv:   {args.conv_id}")
    print(f"  url:    {args.url}")
    print(f"  timeout:{args.timeout}s{RESET}\n")
    print(f"{DIM}driving the call …{RESET}\n")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout + 30)
    except subprocess.TimeoutExpired:
        print(f"{RED}test harness timed out{RESET}", file=sys.stderr)
        return 3

    # Find the JSON payload in stdout — test_client.py prints exactly one JSON object.
    out = proc.stdout.strip()
    if not out:
        print(f"{RED}no output from test_client.py{RESET}")
        if proc.stderr:
            print(f"{DIM}stderr:{RESET}\n{proc.stderr}", file=sys.stderr)
        return 4
    try:
        # Take the LAST {...} block in stdout in case anything else prints first.
        first = out.find("{")
        last = out.rfind("}")
        rep = json.loads(out[first:last + 1])
    except json.JSONDecodeError as e:
        print(f"{RED}could not parse JSON report: {e}{RESET}")
        print(out)
        return 5

    if args.raw:
        print(json.dumps(rep, indent=2))
        return 0 if rep.get("ok") else 1

    # ----- Human-readable summary ----------------------------------------
    err = rep.get("error")
    if err:
        print(f"{RED}{BOLD}FAILED — {err}{RESET}\n")

    print(f"{BOLD}Quality{RESET}")
    print(f"  {_check(bool(rep.get('audio_rms_sent', 0) > 0.01))} test audio synthesized "
          f"{DIM}(rms={rep['audio_rms_sent']:.3f}){RESET}")
    print(f"  {_check(bool(rep.get('transcript_received')))} server got a transcript")
    trans = rep.get("transcript_received") or "(none)"
    sent = rep.get("phrase_sent", "")
    print(f"     {DIM}sent:     {sent!r}{RESET}")
    print(f"     {DIM}received: {trans!r}{RESET}")
    print(f"  {_check(rep.get('transcript_match'))} transcript matches sent phrase "
          f"{DIM}(fuzzy token overlap){RESET}")
    print(f"  {_check(bool(rep.get('reply_text')))} bot replied with text")
    if rep.get("reply_text"):
        reply = rep["reply_text"]
        if len(reply) > 120:
            reply = reply[:117] + "..."
        print(f"     {DIM}{reply!r}{RESET}")
    print(f"  {_check(rep.get('reply_audio_frames', 0) > 0)} TTS audio came back "
          f"{DIM}({rep['reply_audio_frames']} frames, "
          f"~{rep['reply_audio_seconds']:.1f}s playback){RESET}")

    print(f"\n{BOLD}Timings (from test start){RESET}")
    print(_ms("synthesize test phrase",      rep["t_synth_ms"]))
    print(_ms("POST /call/configure",        rep["t_configure_ms"], target=300))
    print(_ms("POST /call/offer + ICE",      rep["t_offer_ms"], target=800))
    if rep["t_ice_connected_ms"]:
        print(_ms("WebRTC connected",         rep["t_ice_connected_ms"]))
    if rep["t_first_event_ms"]:
        print(_ms("first SSE event",          rep["t_first_event_ms"]))
    if rep["t_first_transcript_ms"]:
        print(_ms("first transcript event",   rep["t_first_transcript_ms"]))
    if rep["t_first_chunk_ms"]:
        print(_ms("first LLM token",          rep["t_first_chunk_ms"]))
    if rep["t_first_audio_back_ms"]:
        print(_ms("first TTS audio chunk",    rep["t_first_audio_back_ms"]))
    if rep["t_end_ms"]:
        print(_ms("end event",                rep["t_end_ms"]))

    # Stage-by-stage deltas — most informative for "what's slow"
    if rep["t_first_transcript_ms"] and rep["t_first_chunk_ms"]:
        print(f"\n{BOLD}Inter-stage deltas{RESET}")
        if rep["t_first_transcript_ms"]:
            asr_delta = rep["t_first_transcript_ms"] - max(rep["t_offer_ms"], rep["t_ice_connected_ms"])
            print(_ms("audio start → transcript",  asr_delta, target=1000))
        if rep["t_first_chunk_ms"] and rep["t_first_transcript_ms"]:
            llm_ttft = rep["t_first_chunk_ms"] - rep["t_first_transcript_ms"]
            print(_ms("transcript → first LLM tok", llm_ttft, target=400))
        if rep["t_first_audio_back_ms"] and rep["t_first_chunk_ms"]:
            tts_first = rep["t_first_audio_back_ms"] - rep["t_first_chunk_ms"]
            print(_ms("first LLM tok → TTS audio", tts_first, target=400))

    print()
    if rep.get("ok"):
        print(f"{GREEN}{BOLD}PASS{RESET} — pipeline is healthy")
        return 0
    else:
        print(f"{RED}{BOLD}FAIL{RESET} — see above for the broken stage")
        return 1


if __name__ == "__main__":
    sys.exit(main())

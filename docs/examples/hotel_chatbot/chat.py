"""Interactive CLI chat with MiniClosedAI's Hotel Reservations bot.

Quits automatically when the bot emits a fenced JSON action block (the
recipe's "I have enough info to act" signal — type=create_booking,
modify_booking, or cancel_booking), prints the extracted structured data,
and exits.

Setup
-----
    pip install openai

    1. Run MiniClosedAI somewhere (defaults assume http://localhost:8095).
    2. Create a Hotel Reservations bot from docs/recipes/Hotel Reservations Bot.md
       (or use the Bot Import feature with a .miniclosed-bot.json export).
    3. Note its conversation id (visible in the URL when you open the chat,
       or via `GET /api/conversations`).

Run
---
    # Auto-discover the bot by title — default behavior
    python chat.py

    # Or pin the conversation id explicitly
    MCAI_CONV_ID=14 python chat.py

    # Or against a remote MCAi instance
    MCAI_BASE_URL=http://192.168.0.110:8095/v1 python chat.py

Why the OpenAI SDK
------------------
MCAi serves the OpenAI-compatible /v1/chat/completions shape with the
conversation id as the `model` field. The official `openai` package works
1:1 against it: same calls you'd make to api.openai.com, just a different
`base_url`. This makes the script a portable template — swap the base_url
and the conv id and you're talking to any conversational bot saved in
any MCAi instance, or to OpenAI itself if you want.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import urllib.request
from typing import Optional

from openai import OpenAI

MCAI_BASE_URL = os.environ.get("MCAI_BASE_URL", "http://localhost:8095/v1")
# MCAi has no auth; the SDK still requires *some* key string so it sends
# the Authorization header. The server ignores it.
MCAI_API_KEY = os.environ.get("MCAI_API_KEY", "miniclosedai")
# If unset, the script searches /api/conversations for a title containing
# "hotel" (case-insensitive). Set this to skip auto-discovery.
MCAI_CONV_ID: Optional[str] = os.environ.get("MCAI_CONV_ID")

# The Hotel bot's system prompt instructs it to emit a fenced JSON block
# with `"type": "create_booking"` (or modify_booking / cancel_booking)
# the moment all required fields are present. Any fenced JSON block in a
# reply is treated as the action signal — works for the other
# conversational recipes (Doctor's, Restaurant, Dentist) too without
# changes. ``re.DOTALL`` lets `.` span newlines inside the block.
ACTION_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _discover_conv_id(base_url: str) -> str:
    """Look up the conversation whose title contains 'hotel'.

    Falls back to the most recently updated match. The /api/conversations
    listing is unauthenticated on MCAi by design — same security model as
    the rest of the app, intended for local / trusted-LAN use only.
    """
    # /api/conversations sits one segment up from /v1/chat/completions,
    # so strip a trailing '/v1' off the configured base if present.
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    url = f"{root}/api/conversations"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            convs = json.load(r)
    except Exception as e:
        raise SystemExit(
            f"Couldn't reach {url}: {e}\n"
            "Is MCAi running? Set MCAI_BASE_URL if it isn't at localhost:8095."
        ) from e

    matches = [c for c in convs if "hotel" in (c.get("title") or "").lower()]
    if not matches:
        titles = ", ".join(repr(c.get("title")) for c in convs[:6]) or "(none)"
        raise SystemExit(
            f"No conversation found whose title contains 'hotel'.\n"
            f"Saved conversations: {titles}{'…' if len(convs) > 6 else ''}\n"
            "Create one from docs/recipes/Hotel Reservations Bot.md, or "
            "set MCAI_CONV_ID=<id> to pin a specific conversation."
        )
    # Server returns most-recently-updated first, so matches[0] is the
    # right pick when multiple "Hotel ..." conversations exist.
    chosen = matches[0]
    print(
        f"[discovered conv {chosen['id']} '{chosen['title']}' on "
        f"backend {chosen.get('backend_id')}]"
    )
    return str(chosen["id"])


def extract_action(text: str) -> Optional[dict]:
    """Return the first parseable JSON object inside a fenced code block,
    or None if no such block exists. Hotel bot emits these only when it
    has every required field — the appearance of one is the success
    signal we're listening for.
    """
    for match in ACTION_BLOCK_RE.finditer(text):
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            # Some models emit code-block content that isn't strict JSON
            # (trailing commas, JS-style comments). Keep looking; if no
            # block parses we'll return None and let the user keep typing.
            continue
    return None


class Spinner:
    """Single-line spinner that ticks on a daemon thread until stopped.

    Used to show "Thinking…" between the moment we POST to the model and
    the moment the first token arrives (which can be several seconds on
    a cold model or a slow upstream). Once tokens start flowing, the
    caller stops the spinner — `.stop()` is idempotent + erases the
    spinner line so the cursor returns to a clean column.
    """

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label: str = "Thinking", interval: float = 0.08,
                 out=None) -> None:
        self.label = label
        self.interval = interval
        self.out = out or sys.stdout
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "Spinner":
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def _run(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            self.out.write(f"\r{frame} {self.label}…")
            self.out.flush()
            i += 1
            # Event.wait so the spinner shuts down promptly on stop()
            # rather than sleeping out the remainder of an interval.
            self._stop.wait(self.interval)

    def stop(self) -> None:
        """Stop the spinner and erase the line. Safe to call multiple times."""
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join()
        self._thread = None
        # Carriage return + ANSI "erase to end of line". The non-tty
        # fallback overwrites with spaces (no escape codes leaked into
        # piped output).
        if self.out.isatty():
            self.out.write("\r\x1b[K")
        else:
            self.out.write("\r" + " " * (len(self.label) + 4) + "\r")
        self.out.flush()

    # Context-manager sugar so callers can do `with Spinner("Loading"):`.
    def __enter__(self) -> "Spinner":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


class FenceSuppressingStreamer:
    """Stream a token-by-token reply to stdout while hiding every fenced
    code block — so the user sees the bot's natural-language prose but
    not the structured JSON it emits at the end.

    Algorithm: maintain a small lookbehind buffer. While we're outside a
    fence, emit characters but keep the last 2 of them buffered (in case
    they're the start of a ``` marker we can't yet recognize). When we
    see ```, drop buffered partial output, swallow the optional language
    tag + newline, and enter "suppressing" mode. The next ``` flips us
    back to emitting.

    Survives fences split across chunk boundaries, fences with or without
    a language tag, and bot replies that contain only prose (no fence).
    """

    def __init__(self, out=sys.stdout, on_fence_open=None) -> None:
        """`on_fence_open` is fired (zero-arg callable) exactly once per
        run, the first time we transition from prose-mode into fenced-
        block mode. The callback site is *inside* feed() — so it sees
        the bot's JSON emission begin in real time, before any of the
        block's content has been suppressed. Used by the chat loop to
        start an "Extracting information…" spinner so the user has
        feedback during what would otherwise look like a silent pause.
        """
        self.out = out
        self.on_fence_open = on_fence_open
        self._fired_open = False  # one-shot so a multi-block reply doesn't double-fire
        self.buf = ""
        self.in_fence = False

    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        self.buf += chunk
        while True:
            if self.in_fence:
                idx = self.buf.find("```")
                if idx < 0:
                    # No closing fence yet — keep the tail in case the
                    # marker is straddling the next chunk. Drop the rest
                    # (we're suppressing it anyway).
                    self.buf = self.buf[-3:] if len(self.buf) > 3 else self.buf
                    return
                self.buf = self.buf[idx + 3:].lstrip("\n")
                self.in_fence = False
            else:
                idx = self.buf.find("```")
                if idx < 0:
                    # No fence yet — emit everything except the last 2
                    # chars (which might be the start of ``` we'll see
                    # in the next chunk).
                    if len(self.buf) > 2:
                        self.out.write(self.buf[:-2])
                        self.out.flush()
                        self.buf = self.buf[-2:]
                    return
                # Emit prose before the fence, then skip the fence opener
                # and any optional language tag (e.g. ```json\n).
                self.out.write(self.buf[:idx])
                self.out.flush()
                rest = self.buf[idx + 3:]
                lang_match = re.match(r"\w*\n?", rest)
                self.buf = rest[lang_match.end():] if lang_match else rest
                self.in_fence = True
                # Fire the "we just started a fenced block" hook once.
                # The chat loop uses this to start the extracting spinner
                # while the rest of the JSON streams in invisibly.
                if self.on_fence_open and not self._fired_open:
                    self._fired_open = True
                    try:
                        self.on_fence_open()
                    except Exception:
                        # The callback's failure must never break the
                        # streamer — fall through and keep suppressing.
                        pass

    def flush(self) -> None:
        """Emit any safe-to-show tail. Call once at end-of-stream."""
        if not self.in_fence and self.buf:
            self.out.write(self.buf)
            self.out.flush()
        self.buf = ""


def render_action(action: dict) -> str:
    """Pretty-print the extracted action as a labeled key/value listing.

    Generic: walks the dict, indents nested objects under their key,
    skips null / empty / False values for brevity (the bot often emits
    `null` placeholders for fields the user didn't fill). Booleans
    become 'yes' / 'no' for readability.

    Works for any action shape — create_booking, modify_booking, the
    other recipes (create_appointment, create_reservation), etc. —
    without per-key configuration.
    """
    def _label(key: str) -> str:
        # snake_case → "Title Case"
        return " ".join(w.capitalize() for w in key.split("_"))

    def _is_empty(v) -> bool:
        return v is None or v == "" or v == [] or v == {}

    def _format(v):
        if isinstance(v, bool):
            return "yes" if v else "no"
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v)

    def _scalar_items(d: dict):
        return [(k, v) for k, v in d.items()
                if not isinstance(v, dict) and not _is_empty(v)]

    def _walk(d: dict, depth: int = 0) -> list[str]:
        out: list[str] = []
        scalars = _scalar_items(d)
        nested = [(k, v) for k, v in d.items() if isinstance(v, dict) and v]
        # Column width is computed per-scope so nested sections stay aligned.
        width = max((len(_label(k)) for k, _ in scalars), default=0)
        pad = "  " * depth
        for k, v in scalars:
            out.append(f"{pad}  {_label(k):<{width}}  {_format(v)}")
        for k, v in nested:
            sub = _walk(v, depth + 1)
            if sub:
                out.append("")
                out.append(f"{pad}  {_label(k)}:")
                out.extend(sub)
        return out

    lines = _walk(action)
    return "\n".join(lines)


def main() -> int:
    conv_id = MCAI_CONV_ID or _discover_conv_id(MCAI_BASE_URL)

    client = OpenAI(base_url=MCAI_BASE_URL, api_key=MCAI_API_KEY)
    history: list[dict] = []

    print()
    print("Hotel reservations bot — chat below. Ctrl-C / Ctrl-D to quit.")
    print(f"Endpoint: {MCAI_BASE_URL}  ·  conversation: {conv_id}")
    print("-" * 70)
    print()

    while True:
        try:
            user_input = input("you ▸ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[quit]")
            return 0
        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})

        # Stream so the user sees tokens as they arrive — matches the GUI's
        # responsiveness. Same call you'd make against OpenAI proper.
        try:
            stream = client.chat.completions.create(
                model=conv_id,
                messages=history,
                stream=True,
            )
        except Exception as e:
            print(f"\n[error talking to MCAi: {e}]\n")
            # Roll back the unanswered turn so retries don't double-include it.
            history.pop()
            continue

        # Two spinners over the lifetime of a single reply:
        #   1. "Thinking…"             — from POST until the first token arrives
        #   2. "Extracting information…" — from the moment we see ```json open
        #                                  until we render the parsed action
        # The second one starts inside the streamer's on_fence_open hook (so
        # it fires the moment the bot begins emitting JSON, while the model
        # is still streaming the rest of it). Without this, the user sees
        # the bot's prose stop and then nothing happens for several seconds
        # while the suppressed JSON streams in.
        chunks: list[str] = []
        thinking_spinner = Spinner("Thinking").start()
        # Use a list as a mutable closure cell so the callback can write to it.
        extract_spinner_holder: list[Optional[Spinner]] = [None]

        def _on_fence_open() -> None:
            # We were emitting prose; now we're starting a fenced block.
            # Drop down a line so the spinner doesn't visually collide
            # with the last word the bot streamed, then start ticking.
            sys.stdout.write("\n")
            sys.stdout.flush()
            extract_spinner_holder[0] = Spinner("Extracting information").start()

        streamer = FenceSuppressingStreamer(on_fence_open=_on_fence_open)
        first_token_seen = False
        try:
            for event in stream:
                delta = event.choices[0].delta.content
                if delta:
                    if not first_token_seen:
                        thinking_spinner.stop()
                        print("bot ▸ ", end="", flush=True)
                        first_token_seen = True
                    chunks.append(delta)
                    streamer.feed(delta)
        except KeyboardInterrupt:
            print("\n[interrupted mid-stream]")
            history.pop()
            continue
        finally:
            # Idempotent — make sure neither spinner is left running if
            # the stream errored out mid-iteration. Order matters: stop
            # the extracting spinner before printing the trailing newline.
            thinking_spinner.stop()
            if extract_spinner_holder[0] is not None:
                extract_spinner_holder[0].stop()
        streamer.flush()
        # Only emit the newline if we wrote prose — when the bot's reply
        # opened with the fenced block directly (rare but seen with
        # qwen3:8b), the cursor is already on a fresh line from the
        # `_on_fence_open` hook.
        if first_token_seen and not streamer.in_fence and not extract_spinner_holder[0]:
            print()
        reply = "".join(chunks)
        history.append({"role": "assistant", "content": reply})

        action = extract_action(reply)
        if action is None:
            continue

        # Bot has emitted its structured action block — render it as a
        # readable summary and exit. Raw JSON is hidden from the user;
        # callers that want the dict can import this module and reuse
        # `extract_action` directly.
        print()
        print("─" * 70)
        print("Conversation ended — information extracted")
        print("─" * 70)
        print(render_action(action))
        print("─" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())

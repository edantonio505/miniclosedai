"""Runnable multi-bot router — the self-hosted multi-LLM pattern in ~40 lines.

One *router* bot classifies an incoming support message; your code then
dispatches it to the matching *specialist* bot. Each bot is a separate
self-hosted expert (its own system prompt; could be its own model / knowledge /
tools). MiniClosedAI hosts them; this script is the orchestration layer.

Run it (MiniClosedAI running, with a chat model pulled — default `qwen3:8b`):

    MINICLOSEDAI_BASE_URL=http://localhost:8095 python router_example.py
    MINICLOSEDAI_MODEL=qwen3:8b python router_example.py        # override the model
    python router_example.py --cleanup                          # delete the demo bots

The bots are created idempotently (by exact title), so re-running won't
duplicate them — and they show up in the MiniClosedAI GUI for you to inspect.
"""
import os
import sys

from miniclosedai_client import Bot

MODEL = os.environ.get("MINICLOSEDAI_MODEL", "qwen3:8b")

# title -> system prompt. The router returns ONE word; specialists answer.
SPECIALISTS = {
    "Router Demo — Billing": "You are a billing support specialist. Answer billing, payment, "
                             "invoice, and refund questions concisely (2-3 sentences).",
    "Router Demo — Technical": "You are a technical support specialist. Help with bugs, errors, "
                               "crashes, and setup concisely (2-3 sentences).",
    "Router Demo — Sales": "You are a sales specialist. Answer pricing, plans, and upgrade "
                           "questions concisely (2-3 sentences).",
}
ROUTER_TITLE = "Router Demo — Router"
ROUTER_PROMPT = (
    "You are a support router. Classify the user's message into EXACTLY ONE category: "
    "billing, technical, or sales. Reply with ONLY that one word, lowercase, nothing else."
)
LABEL_TO_TITLE = {
    "billing": "Router Demo — Billing",
    "technical": "Router Demo — Technical",
    "sales": "Router Demo — Sales",
}

ALL_TITLES = [ROUTER_TITLE, *SPECIALISTS]


def cleanup():
    for c in Bot.list():
        if (c.get("title") or "") in ALL_TITLES:
            Bot(c["id"]).delete()
            print(f"  deleted: {c['title']}")
    print("Demo bots removed.")


def setup():
    router = Bot.get_or_create(ROUTER_TITLE, MODEL, ROUTER_PROMPT, temperature=0.0)
    experts = {
        title: Bot.get_or_create(title, MODEL, prompt, temperature=0.3)
        for title, prompt in SPECIALISTS.items()
    }
    return router, experts


def route(message, router, experts):
    label = router.ask(message, history=False).strip().lower().split()[0]
    title = LABEL_TO_TITLE.get(label, "Router Demo — Technical")  # fallback
    reply = experts[title].ask(message, history=False)
    return label, reply


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        cleanup()
        sys.exit(0)

    router, experts = setup()
    samples = [
        "I was charged twice for my subscription this month.",
        "The app crashes whenever I upload a PDF.",
        "Do you offer an annual discount on the Pro plan?",
    ]
    for msg in samples:
        label, reply = route(msg, router, experts)
        print(f"\n> {msg}\n  routed → {label}\n  reply  → {reply.strip()}")

    print("\n(Run with --cleanup to remove the demo bots.)")

"""Compose multiple self-hosted MiniClosedAI bots in one script.

This is the "multi-LLM management" pattern: MiniClosedAI hosts each bot (its
model, system prompt, knowledge base, and tools); THIS file is the orchestration
layer that wires them together — the kind of thing you'd drop into a FastAPI
route or a backend job.

Run it:
    # MiniClosedAI running, with a couple of bots created in the GUI:
    MINICLOSEDAI_BASE_URL=http://localhost:8095 python example.py
"""
from miniclosedai_client import Bot

# Address a bot by id (grab it from the </> "Copy bot ID" pill in the GUI) ...
# support = Bot(12)
# ... or look one up by a substring of its title:
# support = Bot.find("support")


def pipeline(user_message: str) -> str:
    """A two-stage pipeline: one bot classifies, another drafts a reply.

    Swap in your own bots — the point is that each `.ask()` is a call to a
    different self-hosted expert, and you compose them in plain Python.
    """
    triage = Bot.find("triage")      # an expert tuned to classify intent
    writer = Bot.find("writer")      # an expert tuned to write customer replies

    intent = triage.ask(user_message, history=False)   # one-shot classification
    draft = writer.ask(
        f"Write a concise, friendly reply. Customer intent: {intent}\n\n"
        f"Customer said: {user_message}",
        history=False,
    )
    return draft


def demo_discovery():
    """List every bot the server is hosting."""
    for b in Bot.list():
        print(f"  #{b['id']:<4} {b['title']:<30} {b.get('model', '')}")


if __name__ == "__main__":
    print("Bots currently hosted:")
    demo_discovery()
    # print(pipeline("My order #4471 is two weeks late and nobody replied."))

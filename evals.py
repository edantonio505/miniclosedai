"""Per-bot evaluation scoring. Stdlib only.

A bot's eval set is a list of (input, expected) cases. To score, the bot is run
once per input (one-shot, no history) and its reply is compared to `expected`
by one of three modes:

  - "exact"    — normalized equality (trim + lowercase + collapse whitespace).
                 Best for fixed-response bots (classifiers / routers / extractors).
  - "contains" — the normalized expected appears as a substring of the reply.
                 Handles bots that wrap the label in a sentence.
  - "judge"    — an LLM grader decides correct/incorrect. For free-text answers.
                 The caller runs the LLM; this module only builds the judge
                 messages and parses the verdict.
"""
import re

VALID_MODES = ("exact", "contains", "judge")


def normalize(s: str) -> str:
    """Trim, lowercase, and collapse internal whitespace to single spaces."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def score_exact(reply: str, expected: str) -> bool:
    return normalize(reply) == normalize(expected)


def score_contains(reply: str, expected: str) -> bool:
    exp = normalize(expected)
    return bool(exp) and exp in normalize(reply)


# ---- LLM-as-judge -------------------------------------------------------

_JUDGE_SYSTEM = (
    "You are a strict grading assistant. You are given a task INPUT, the "
    "EXPECTED answer, and a model's actual RESPONSE. Decide whether the "
    "RESPONSE is correct — i.e. it matches the meaning/intent of EXPECTED for "
    "that INPUT. Ignore differences in wording, casing, or punctuation; judge "
    "on substance. Reply with EXACTLY one word: YES if correct, NO if not."
)


def build_judge_messages(input_text: str, expected: str, reply: str) -> list[dict]:
    """Messages for a one-shot grader call (system + user)."""
    user = (
        f"INPUT:\n{input_text}\n\n"
        f"EXPECTED:\n{expected}\n\n"
        f"RESPONSE:\n{reply}\n\n"
        "Is the RESPONSE correct? Answer YES or NO."
    )
    return [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {"role": "user", "content": user},
    ]


def parse_judge(text: str) -> bool:
    """True if the grader's verdict starts with 'yes' (after normalization)."""
    return normalize(text).startswith("yes")


def score(mode: str, reply: str, expected: str) -> bool:
    """Score a single case for the non-judge modes. (Judge is scored by the
    caller after running the grader LLM via build_judge_messages/parse_judge.)"""
    if mode == "contains":
        return score_contains(reply, expected)
    return score_exact(reply, expected)  # default / "exact"

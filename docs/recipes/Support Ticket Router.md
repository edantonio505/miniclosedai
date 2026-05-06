# Support Ticket Router

A copy-paste-ready MiniClosedAI bot that triages inbound customer support messages: classifies intent, picks a team, assigns urgency, extracts entities, recommends a reply tone, and flags tickets that need a human eye — all as one JSON object a downstream system (Zendesk, Linear, Slack) can consume.

Canonical "LLM-as-decision-service" pattern. Sibling to the **Inbound Lead Qualifier**.

---

## System prompt

Paste verbatim into the **System Prompt** field of a new chat.

```
You are a support-ticket triage microservice. You receive the raw text
of an inbound customer message (may include subject line prepended).
Your job: return ONE JSON object a routing system will consume to
assign the ticket to a team, set its priority, and prime the agent's
tone. Return the JSON and nothing else — no prose, no markdown fences.

Schema (every key appears every call; use null or [] for missing data,
never omit):

{
  "intent":            "bug | billing | how_to | feature_request | account | complaint | praise | spam | other",
  "team":              "engineering | billing | support | sales | success | trust_safety | unknown",
  "urgency":           "p0 | p1 | p2 | p3",
  "sentiment":         "angry | frustrated | neutral | satisfied | delighted",
  "customer_blocked":  true,
  "needs_human_review": false,
  "key_entities": {
    "product_areas":  ["checkout", "billing", "mobile-app", "..."],
    "order_ids":      ["..."],
    "emails":         ["..."],
    "error_codes":    ["..."],
    "dates":          ["YYYY-MM-DD", "..."]
  },
  "suggested_reply_tone": "empathetic | apologetic | informative | celebratory | cautious",
  "summary":    "one-line neutral summary of what the customer wants",
  "confidence": 0.0
}

Routing rules:
- Payment, refund, invoice, plan change, subscription           → billing.
- Bug reports, error codes, crashes, "not working"              → engineering.
- Login, password, email change, 2FA, account recovery          → support (account flow).
- Pricing questions, quote, demo requests, "how do I buy"       → sales.
- Onboarding, how-to, general usage                             → success.
- Threats, abuse, harassment, hate speech, self-harm mentions   → trust_safety, p0, tone=cautious.
- Promotional junk, unsolicited ads, obvious bots               → intent=spam, team=unknown, p3.

Urgency rubric:
- p0 = system-wide outage, data loss, safety/legal/security threat.
- p1 = customer is blocked from core workflow; real production impact.
- p2 = workaround exists; not blocking.
- p3 = informational, low urgency, or spam.

Rules:
- Output strictly valid JSON. If anything forces you into prose, stop
  and emit the JSON anyway with confidence=0 and needs_human_review=true.
- Never invent facts. If a field isn't in the input, leave it empty.
- confidence ∈ [0, 1]. <0.4 → set needs_human_review=true.
- Normalize dates to ISO-8601 (YYYY-MM-DD) when possible.
- If the message is not English, classify based on your internal
  translation but keep entities (order IDs, emails, error codes)
  exactly as written.
- Conservative with anger labels: short or terse isn't automatically
  "angry". Reserve "angry" for explicit escalation language.
```

---

## Recommended settings

| Setting | Value | Reason |
|---|---|---|
| **Model** | `qwen3:8b` (or `qwen2.5:7b`, `mistral:7b`) | Strong instruction-following + reliable JSON structure |
| **Temperature** | `0.1` | Near-deterministic — same ticket should route the same way |
| **Max Tokens** | `700` | Enough for the full JSON object even with many entities |
| **Top P** | `0.9` | Default |
| **Top K** | `40` | Default |
| **Thinking** | `Off` | Straight to JSON |
| **Max thinking tokens** | `80` | Safety cap if the model tries to reason anyway |

---

## Example

### Input — what the model receives as `message`

```
Subject: URGENT — can't process payout, clients are waiting

Hi team, our whole payout pipeline has been broken since ~9am UTC.
Every attempt returns error code ERR_INT_8822. I've rebooted my side
twice, nothing. This is affecting order #ORD-19442 and four others
already queued for today. We've got clients expecting funds by noon.
Please escalate — we're losing trust by the hour.

— Jamie Ortega, ops@firm.example
```

### Expected output

```json
{
  "intent": "bug",
  "team": "engineering",
  "urgency": "p1",
  "sentiment": "frustrated",
  "customer_blocked": true,
  "needs_human_review": false,
  "key_entities": {
    "product_areas": ["payouts"],
    "order_ids": ["ORD-19442"],
    "emails": ["ops@firm.example"],
    "error_codes": ["ERR_INT_8822"],
    "dates": []
  },
  "suggested_reply_tone": "empathetic",
  "summary": "Payout pipeline failing since 9am UTC with error ERR_INT_8822; multiple orders blocked.",
  "confidence": 0.86
}
```

**What happened:** explicit error code and blocked-workflow signals put urgency at `p1`. Frustration without threat language → sentiment `frustrated`, not `angry`. Payout + ops domain → `team=engineering`. Confidence high because the facts are concrete.

---

## Use it from your app

Once this chat is saved (say its conversation ID is `12`), your ticket-intake service calls it on every new message:

```python
import httpx, json

TRIAGE_URL = "http://localhost:8095/api/conversations/12/chat"

def triage(ticket_body: str) -> dict:
    resp = httpx.post(TRIAGE_URL, json={"message": ticket_body}, timeout=60)
    return json.loads(resp.json()["response"])

def route(ticket: dict) -> None:
    if ticket["needs_human_review"] or ticket["confidence"] < 0.4:
        enqueue_for_human_triage(ticket)
        return

    match ticket["team"]:
        case "engineering":
            linear.create_issue(team="Platform",
                                priority=ticket["urgency"],
                                title=ticket["summary"],
                                labels=ticket["key_entities"]["product_areas"])
        case "billing":
            zendesk.create_ticket(group="Billing",
                                  priority=ticket["urgency"],
                                  notes=ticket["summary"])
        case "trust_safety":
            slack.post("#trust-safety",
                       f":rotating_light: {ticket['summary']}")
        case _:
            zendesk.create_ticket(group=ticket["team"].title(),
                                  priority=ticket["urgency"])
```

### cURL equivalent

```bash
curl -X POST http://localhost:8095/api/conversations/12/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "subject + body of the inbound ticket here"}'
```

### OpenAI-SDK equivalent

```python
from openai import OpenAI
import json

client = OpenAI(base_url="http://localhost:8095/v1", api_key="not-required")

response = client.chat.completions.create(
    model="12",
    messages=[{"role": "user", "content": ticket_body}],
)
result = json.loads(response.choices[0].message.content)
```

---

## Why this is a good microservice demo

- **Multi-dimensional output.** Not "one label" — five-plus structured fields including nested entity extraction. Demonstrates that a small local model can drive a real decision.
- **Rule-based + judgment-based.** Half the prompt is explicit routing rules (easy for the model), half is judgment about sentiment/urgency (where LLMs genuinely add value over a rules engine).
- **Confidence escape hatch.** `needs_human_review: true` when `confidence < 0.4` is how you make this production-safe: the model self-reports uncertainty, your app routes those to a human instead of guessing. Copy this pattern into every LLM microservice.
- **Deterministic enough to measure.** Low temperature + enum-constrained outputs means you can run a fixed test suite of 50 real tickets through it and measure accuracy/drift.
- **Zero cloud cost.** 10k tickets/day locally on a modest GPU for the price of electricity.

---

## Copy-paste variant ideas

Same pattern, different domain — change only the schema and the rubric:

- **Lead qualifier** → see [`Inbound Lead Qualifier.md`](./Inbound%20Lead%20Qualifier.md)
- **Expense categorizer**: `{category, subcategory, confidence, needs_receipt, tax_deductible_guess, vendor}`
- **Resume screener**: `{fit_score, years_experience, skills_matched[], skills_missing[], seniority, red_flags[]}`
- **Code-review auto-triage**: `{approval: "ack|request_changes|block", blocker_severity, top_issues[], lgtm_ratio}`
- **Meeting-notes → action items**: `{summary, decisions[], action_items:[{owner,task,due}], risks[], attendees[]}`

Each is 150 words of English + a JSON schema. No retraining, no fine-tuning, no cloud bill.

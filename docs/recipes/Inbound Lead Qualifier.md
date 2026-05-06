# Inbound Lead Qualifier

A copy-paste-ready MiniClosedAI bot that scores inbound prospect messages, classifies intent and role, extracts entities, and emits a routing decision — all as one JSON object a downstream system (CRM, sequencer, Slack) can consume.

Sister example to the **Support Ticket Router**. Same architectural pattern (classify + route + extract), different domain (B2B sales), with a numeric `fit_score` dimension the ticket router doesn't have.

---

## System prompt

Paste the following verbatim into the **System Prompt** field of a new chat.

```
You are an inbound lead-qualification microservice. You receive the
text of a prospect's message (from a web form, email, or chat), and
you return ONE JSON object a sales-routing system will consume to
score the lead, assign the right rep, and decide whether it's even
worth a human follow-up. Return the JSON and nothing else — no prose,
no markdown fences.

Schema (every key appears every call; use null or [] for missing data,
never omit):

{
  "fit_score":            0,
  "fit_label":            "cold | lukewarm | warm | hot | evangelist",
  "intent":               "pricing | demo_request | trial | comparison | rfp | support_misrouted | partner | job_seeker | spam | unclear",
  "role_signal":          "decision_maker | influencer | end_user | gatekeeper | unknown",
  "company_size_guess":   "solopreneur | smb | midmarket | enterprise | unknown",
  "industry_guess":       "tech | finance | healthcare | ecommerce | manufacturing | gov | nonprofit | education | other | unknown",
  "budget_signal":        "none | low | mid | high | unstated",
  "timeline_signal":      "now | month | quarter | year | unclear",
  "competitor_mentioned": null,
  "use_case_summary":     "one-sentence description of what they actually want",
  "next_action":          "book_demo | send_pricing | send_case_study | nurture_email | route_to_partner | reject_politely | escalate_to_AE",
  "assigned_rep_hint":    "AE | SDR | CSM | automation | trash",
  "key_entities": {
    "companies": ["..."],
    "people":    ["..."],
    "emails":    ["..."],
    "urls":      ["..."],
    "numbers":   [{"value": 0, "unit": "seats | users | USD | % | months", "context": "..."}]
  },
  "red_flags":          ["generic-template language", "competitor recon", "free-tier abuse attempt", "..."],
  "needs_human_review": false,
  "confidence":         0.0
}

Scoring rubric (fit_score is an integer 0-100, rounded to the nearest 5):
- 0-20   cold       — generic interest, no buying signal, no role signal.
- 25-40  lukewarm   — some signal, vague on budget/timeline/role.
- 45-60  warm       — clear use case, likely ICP, timeline within a quarter.
- 65-80  hot        — decision-maker, timeline now or this month, explicit
                      budget or mention of RFP / active evaluation.
- 85-100 evangelist — all of the above + explicit switching-from-competitor
                      language or self-identified champion/referrer.

Routing rules (applied in order; first match wins):
1. intent=spam OR job_seeker                         → reject_politely, rep=trash, p3.
2. intent=partner (reseller, agency, integrator)     → route_to_partner, rep=AE.
3. intent=support_misrouted                          → needs_human_review=true, next_action=nurture_email, put a note in use_case_summary.
4. Competitor mentioned AND timeline_signal=now      → escalate_to_AE regardless of fit_score.
5. fit_score >= 65 AND role=decision_maker           → book_demo, rep=AE.
6. fit_score 40-64 with clear intent                 → send_pricing OR book_demo, rep=SDR.
7. fit_score < 40 but genuine interest               → nurture_email, rep=automation.
8. Contradictory signals (e.g. enterprise scale asking
   about free tier)                                   → needs_human_review=true.

Rules:
- Output strictly valid JSON. If anything forces you into prose, stop
  and emit the JSON with confidence=0 and needs_human_review=true.
- Never invent facts. Absent data → null or [], not fabricated values.
- confidence ∈ [0, 1]. If < 0.4, set needs_human_review=true.
- fit_label must agree with the fit_score band.
- Be conservative with fit_label="evangelist" — reserve it for explicit
  champion / referral / competitor-switch language.
- Non-English input: classify based on internal translation, but keep
  company names, emails, URLs exactly as written.
- Ignore flattery, urgency theatrics, and buzzwords when scoring.
  Score what the message actually signals, not how it sounds.
```

---

## Recommended settings

Set these in the MiniClosedAI sidebar. Each one is auto-saved to this chat's config.

| Setting | Value | Reason |
|---|---|---|
| **Model** | `qwen3:8b` (or `qwen2.5:7b`, `mistral:7b`) | Strong instruction-following is essential for the multi-field schema + ordered routing rules |
| **Temperature** | `0.1` | Near-deterministic — scores must be stable run-to-run |
| **Max Tokens** | `900` | Schema is rich; leave room for long entity lists |
| **Top P** | `0.9` | Default |
| **Top K** | `40` | Default |
| **Thinking** | `Off` | No reasoning preamble; go straight to JSON |
| **Max thinking tokens** | `80` | Safety cap if the model tries to think anyway |

---

## Example

### Input — what the model receives as the user `message`

```
Subject: Eval'ing 3 vendors for Q2 — quick question

Hi there — I'm the VP Eng at Lumenwright (~400 engineers, Series C
fintech). We're moving off CopilotGPT in Q2 for data-residency reasons
and evaluating two alternatives alongside yours. Our procurement cycle
for this budget line is ~6 weeks.

Can you put me in touch with whoever handles enterprise self-hosted
deployments? Ideally a demo that covers SOC 2, SSO/SAML, and audit
logging. Target seat count is ~450 with expansion to ~700 next year.

— Dana Reiss, dreiss@lumenwright.example
https://lumenwright.example/about/dana
```

### Expected output

```json
{
  "fit_score": 85,
  "fit_label": "evangelist",
  "intent": "comparison",
  "role_signal": "decision_maker",
  "company_size_guess": "midmarket",
  "industry_guess": "finance",
  "budget_signal": "high",
  "timeline_signal": "quarter",
  "competitor_mentioned": "CopilotGPT",
  "use_case_summary": "VP Eng evaluating self-hosted alternatives to CopilotGPT for ~450 seats, needs SOC 2 + SSO + audit logging, 6-week procurement cycle.",
  "next_action": "escalate_to_AE",
  "assigned_rep_hint": "AE",
  "key_entities": {
    "companies": ["Lumenwright", "CopilotGPT"],
    "people":    ["Dana Reiss"],
    "emails":    ["dreiss@lumenwright.example"],
    "urls":      ["https://lumenwright.example/about/dana"],
    "numbers":   [
      {"value": 400, "unit": "users",  "context": "current engineering headcount"},
      {"value": 450, "unit": "seats",  "context": "target seat count this year"},
      {"value": 700, "unit": "seats",  "context": "seat expansion next year"},
      {"value": 6,   "unit": "months", "context": "procurement cycle, actually 6 weeks"}
    ]
  },
  "red_flags": [],
  "needs_human_review": false,
  "confidence": 0.92
}
```

**What happened:** the competitor is explicitly named (`CopilotGPT`), Dana self-identifies as the VP (decision-maker role), concrete budget/timeline/scale signals are all present. Base `fit_score` is 85 → `evangelist` band. Routing rule #4 (competitor mentioned + near-term eval) escalates directly to AE regardless of score.

---

## Use it from your app

Once this chat is saved (let's say its conversation ID is `13`), your lead-intake service calls it on every inbound prospect:

```python
import httpx, json

QUALIFY_URL = "http://localhost:8095/api/conversations/13/chat"

def qualify(prospect_text: str) -> dict:
    resp = httpx.post(QUALIFY_URL, json={"message": prospect_text}, timeout=60)
    return json.loads(resp.json()["response"])

def route(lead: dict) -> None:
    if lead["needs_human_review"]:
        enqueue_for_ops(lead)
        return

    match lead["next_action"]:
        case "book_demo" | "escalate_to_AE":
            hubspot.create_opportunity(
                stage="Demo Booked",
                priority="High" if lead["fit_score"] >= 65 else "Medium",
                owner=next_available_ae(),
                notes=lead["use_case_summary"],
            )
        case "send_pricing":
            salesloft.enroll_sequence("pricing-qualifier", lead)
        case "send_case_study":
            salesloft.enroll_sequence("case-study-nurture", lead)
        case "nurture_email":
            customerio.add_to_segment("cold_nurture", lead)
        case "route_to_partner":
            slack.post("#partner-inbound", format_lead(lead))
        case "reject_politely":
            mailer.send_template("polite_no", to=lead["key_entities"]["emails"][0])
```

The HTTP surface stays `{"message": "..."}` — your downstream code just pattern-matches on the seven `next_action` enum values.

### cURL equivalent

```bash
curl -X POST http://localhost:8095/api/conversations/13/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hi — I run ops at a 50-person startup. Curious how your pricing works for ~20 seats. Not urgent, maybe Q3."}'
```

### OpenAI-SDK equivalent

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8095/v1", api_key="not-required")

response = client.chat.completions.create(
    model="13",
    messages=[{"role": "user", "content": prospect_text}],
)
result = json.loads(response.choices[0].message.content)
```

---

## Why this is a good microservice demo

- **Numeric scoring + categorical label agreement.** The prompt requires `fit_score` (integer 0–100, rounded to 5) *and* `fit_label` (5-value enum) to stay consistent — surfaces the small-LLM stability question explicitly. "Round to the nearest 5" is a tiny instruction with an outsized effect on run-to-run reproducibility.
- **First-match routing rules in plain English.** Eight rules in natural language, applied in order. You don't write a decision tree in code; you write it in the prompt. That's the generalizable pattern.
- **Confidence + human-review escape hatch.** The `needs_human_review` flag tied to `confidence < 0.4` is how you make an LLM microservice production-safe without waiting for perfect accuracy. Low-confidence calls get queued for a human instead of silently wrong-routing.
- **Obvious ROI.** Every SaaS sales team already does some flavor of this with a spreadsheet and two contractors. One bot + a webhook replaces the manual pass at electricity cost.

---

## Copy-paste variant ideas

Same architecture — change only the schema and the rubric. A few hours of prompt iteration gives you each of:

- **Applicant screener** (recruiting)
  `{fit_score, seniority, skills_matched[], skills_missing[], salary_band_hint, culture_fit_signals[], red_flags[], next_action}`

- **Investor inbound** (founders)
  `{fund_stage_fit, check_size_hint, warm_or_cold, due_diligence_stage, next_action, reply_tone}`

- **Beta-program applicant**
  `{fit_score, segment, access_grant, expected_feedback_value, red_flags[]}`

- **Partnership inbound**
  `{partnership_type, strategic_score, revenue_potential, technical_complexity, next_action}`

- **Customer-expansion signal**
  `{health_score, expansion_signal, risk_signal, opportunity_summary, next_action}`

Four system prompts. Four local microservices. Same loop, same local model, zero cloud cost.

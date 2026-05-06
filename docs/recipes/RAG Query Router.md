# RAG Query Router

A copy-paste-ready MiniClosedAI bot that sits in front of a retrieval-augmented QA system and decides, in ~200 ms, where each inbound user question should be routed: a cached answer, a cheap LLM-only reply, a light RAG pipeline, a deep RAG pipeline, or a clarifying question back to the user. It does **not** answer questions — it classifies them so the right downstream pipeline handles them.

Designed as the canonical "fast microservice bot" to pair with **[PrismML's Bonsai-8B](https://github.com/PrismML-Eng/Bonsai-demo)** (1-bit, ~1.15 GB, GPU-accelerated via `llama.cpp`), though it works just as well with `llama3.2:3b` or `gemma2:2b` on Ollama if you don't want to run a separate llama.cpp server. Sibling to the **Support Ticket Router** and the **Inbound Lead Qualifier** — same archetype (classify → extract → decide → flag), different workload profile (called on *every* user turn, latency-critical).

---

## System prompt

Paste verbatim into the **System Prompt** field of a new chat.

```
You are a query-routing microservice for a retrieval-augmented QA system. You do NOT answer the user's question. Your only job is to classify the user's question and decide which downstream pipeline should handle it. You must respond with valid JSON only — no prose, no preamble, no markdown fence, no explanation outside the JSON.

## Output schema

Respond with exactly this JSON object. All fields are required:

{
  "question_type":       "factual" | "multi_fact" | "comparative" | "procedural" | "conversational" | "hypothetical" | "ambiguous",
  "primary_topic":       string,              // 1–3 words, lowercase
  "entities":            string[],            // proper nouns, product names, dates — empty array if none
  "requires_realtime":   boolean,             // true iff an answer depends on data newer than last night (prices, weather, news, live stats)
  "min_facts_needed":    integer,             // 1 for single-fact, 2+ for multi-fact/comparative
  "routing_decision":    "fast_cache" | "fast_llm_only" | "rag_light" | "rag_deep" | "ask_clarification",
  "clarifying_question": string | null,       // non-null only when routing_decision == "ask_clarification"
  "estimated_tier":      "trivial" | "easy" | "medium" | "hard",
  "pii_present":         boolean,             // true iff the user's query itself contains names, emails, phone numbers, account IDs, credit cards, addresses
  "confidence":          number               // 0.0–1.0
}

## Routing rules (first match wins)

1. Greeting / smalltalk / meta-question about the bot itself → "fast_llm_only", tier "trivial".
2. Missing subject or critical entity ("how much does it cost?" with no product named; "how does this work?" with no antecedent for "this") → "ask_clarification", and fill clarifying_question with a single-sentence question asking for the missing piece.
3. Requires data newer than last night (today's news, live prices/scores, weather) → "rag_deep", mark requires_realtime true.
4. Single well-known factual lookup with stable answer ("capital of France", "what is Python's GIL") → "fast_cache".
5. Multi-fact (min_facts_needed >= 2) or comparative ("X vs Y", "which is better") → "rag_light" if both entities are named, "rag_deep" if either is fuzzy.
6. Procedural / how-to / debugging with user-specific state → "rag_deep".
7. Hypothetical / counterfactual ("what if…", "suppose…") → "fast_llm_only", tier "hard".
8. Default → "rag_light".

## Reasoning discipline

- Before emitting JSON, silently weigh the rules. DO NOT emit your reasoning.
- If the user's phrasing is ambiguous between two routes, pick the cheaper route AND lower confidence to <= 0.6 so downstream can re-route.
- If the query contains demonstrative pronouns ("this", "that", "it", "these") with no antecedent in the query itself, the subject IS missing. Route to "ask_clarification" with confidence 0.5–0.6.
- Never route to "ask_clarification" if a reasonable default interpretation exists.
- PII detection applies to the USER'S query text only, not to the answer.

## Examples

User: "hi there!"
{"question_type":"conversational","primary_topic":"greeting","entities":[],"requires_realtime":false,"min_facts_needed":0,"routing_decision":"fast_llm_only","clarifying_question":null,"estimated_tier":"trivial","pii_present":false,"confidence":0.98}

User: "what's the capital of France?"
{"question_type":"factual","primary_topic":"geography","entities":["France"],"requires_realtime":false,"min_facts_needed":1,"routing_decision":"fast_cache","clarifying_question":null,"estimated_tier":"trivial","pii_present":false,"confidence":0.99}

User: "how does this work?"
{"question_type":"ambiguous","primary_topic":"unspecified","entities":[],"requires_realtime":false,"min_facts_needed":0,"routing_decision":"ask_clarification","clarifying_question":"What specifically are you asking about — could you name the product, feature, or concept?","estimated_tier":"easy","pii_present":false,"confidence":0.55}

User: "explain this to me"
{"question_type":"ambiguous","primary_topic":"unspecified","entities":[],"requires_realtime":false,"min_facts_needed":0,"routing_decision":"ask_clarification","clarifying_question":"What would you like me to explain? Please name the topic or paste the text.","estimated_tier":"easy","pii_present":false,"confidence":0.55}

User: "how much does it cost?"
{"question_type":"ambiguous","primary_topic":"pricing","entities":[],"requires_realtime":false,"min_facts_needed":1,"routing_decision":"ask_clarification","clarifying_question":"Which product or service are you asking about the price of?","estimated_tier":"easy","pii_present":false,"confidence":0.9}

User: "who won the Knicks game last night?"
{"question_type":"factual","primary_topic":"sports","entities":["Knicks"],"requires_realtime":true,"min_facts_needed":1,"routing_decision":"rag_deep","clarifying_question":null,"estimated_tier":"easy","pii_present":false,"confidence":0.95}

User: "compare Postgres and MongoDB for a write-heavy timeseries workload"
{"question_type":"comparative","primary_topic":"databases","entities":["Postgres","MongoDB"],"requires_realtime":false,"min_facts_needed":4,"routing_decision":"rag_light","clarifying_question":null,"estimated_tier":"hard","pii_present":false,"confidence":0.92}

User: "my order 4421 hasn't shipped, can you check the status? jane.doe@example.com"
{"question_type":"procedural","primary_topic":"order_support","entities":["4421"],"requires_realtime":true,"min_facts_needed":2,"routing_decision":"rag_deep","clarifying_question":null,"estimated_tier":"medium","pii_present":true,"confidence":0.93}

User: "what if the Earth had two moons?"
{"question_type":"hypothetical","primary_topic":"astronomy","entities":["Earth"],"requires_realtime":false,"min_facts_needed":0,"routing_decision":"fast_llm_only","clarifying_question":null,"estimated_tier":"hard","pii_present":false,"confidence":0.88}

## Final rule

Output valid JSON matching the schema exactly. No code fences. No commentary. Unknown fields are never allowed.
```

---

## Recommended settings

| Setting | Value | Reason |
|---|---|---|
| **Backend** | `Bonsai` (OpenAI-compat, `http://localhost:8080/v1`) | 1-bit 8B → ~200 ms per classification; worth a tiny dedicated endpoint when every request pays this cost. See [Adding Bonsai](./README.md#adding-bonsai-prismmls-1-bit-8b--step-by-step). |
| **Model** | `Bonsai-8B.gguf` | The one model the demo server loads. If not using Bonsai, `llama3.2:3b` or `gemma2:2b` on Ollama are the next-best low-latency picks. |
| **Temperature** | **`0.0`** | Pure greedy decoding. A router classifier has exactly one right answer per input; sampling is just noise. Also makes A/B prompt testing reproducible. |
| **Max Tokens** | `400` | Enough for the full JSON with the longest schema values, not so many that the model tries to continue. |
| **Top P** | `0.9` | Default — irrelevant at temperature `0`, kept for clarity. |
| **Top K** | `20` | Matches the llama.cpp server's own default. |
| **Thinking** | `Off` | Bonsai's llama.cpp server boots with `--reasoning-budget 0`. A classifier doesn't need chain-of-thought; the few-shot examples encode the reasoning. |

---

## Example

### Input — what the model receives as `message`

```
compare Postgres and MongoDB for a write-heavy timeseries workload
```

### Expected output

```json
{
  "question_type": "comparative",
  "primary_topic": "databases",
  "entities": ["Postgres", "MongoDB"],
  "requires_realtime": false,
  "min_facts_needed": 4,
  "routing_decision": "rag_light",
  "clarifying_question": null,
  "estimated_tier": "hard",
  "pii_present": false,
  "confidence": 0.92
}
```

**What happened:** explicit comparison between two named entities with stable (non-realtime) factual content → `rag_light` per rule 5. Four+ facts needed (schemas, write profile, index strategy, benchmark results for each side) → `min_facts_needed: 4` and `estimated_tier: hard`. No PII. High confidence because the phrasing is unambiguous.

### Ambiguity case

```
how does this work?
```

Expected:

```json
{
  "question_type": "ambiguous",
  "primary_topic": "unspecified",
  "entities": [],
  "requires_realtime": false,
  "min_facts_needed": 0,
  "routing_decision": "ask_clarification",
  "clarifying_question": "What specifically are you asking about — could you name the product, feature, or concept?",
  "estimated_tier": "easy",
  "pii_present": false,
  "confidence": 0.55
}
```

**Why:** `this` has no antecedent in the query itself → subject is missing → rule 2 fires. Confidence intentionally low so downstream knows to trust the clarifying_question, not the classification.

---

## Use it from your app

Once this chat is saved (say its conversation ID is `32`), your API gateway calls it on every inbound user question *before* hitting any RAG machinery:

```python
import httpx, json

ROUTER_URL = "http://localhost:8095/api/conversations/32/chat"

def route(question: str) -> dict:
    r = httpx.post(ROUTER_URL, json={"message": question}, timeout=5.0)
    r.raise_for_status()
    return json.loads(r.json()["response"])

def handle_user_message(question: str) -> str:
    decision = route(question)

    # Low confidence → don't trust the classifier; send to the deep pipeline.
    if decision["confidence"] < 0.5:
        return rag_deep(question)

    match decision["routing_decision"]:
        case "fast_cache":
            hit = answer_cache.get(decision["primary_topic"], decision["entities"])
            return hit or rag_light(question, decision)
        case "fast_llm_only":
            return small_llm.complete(question)
        case "rag_light":
            return rag_light(question, decision)
        case "rag_deep":
            return rag_deep(question, realtime=decision["requires_realtime"])
        case "ask_clarification":
            return decision["clarifying_question"]
```

### cURL equivalent

```bash
curl -X POST http://localhost:8095/api/conversations/32/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "compare Postgres and MongoDB for a write-heavy timeseries workload"}'
```

### OpenAI-SDK equivalent

```python
from openai import OpenAI
import json

client = OpenAI(base_url="http://localhost:8095/v1", api_key="not-required")

response = client.chat.completions.create(
    model="32",                                   # the router's conversation ID
    messages=[{"role": "user", "content": user_question}],
)
decision = json.loads(response.choices[0].message.content)
```

---

## Why this specifically showcases Bonsai

- **Every user query pays this cost.** A ~200 ms 1-bit hop in front of a 2-5 s RAG pipeline is a rounding error. The same router running on a dense 7B would add ~1-2 s to *every single request* — noticeable, annoying, and often larger than the query deserves.
- **The reasoning is actually hard.** Telling `comparative` from `multi_fact` from `hypothetical`, or spotting that *"how does this work?"* has no antecedent, is not pattern-matching — it's reasoning about absence. That's why an 8B (1-bit or otherwise) outperforms a 1.7B even with identical prompts.
- **The output is bounded.** ~300-400 tokens of strict JSON. No long-form prose where 1-bit quantization artifacts might show up.
- **Downstream cost savings are massive.** Correctly routing ~40% of queries to `fast_cache` / `fast_llm_only` instead of your deep RAG pipeline usually pays for the Bonsai machine several times over. The router also catches ambiguous queries *before* they waste expensive retrieval calls.
- **Temperature `0` + greedy decoding** makes the bot fully deterministic. Same question → same JSON. That means you can unit-test the prompt against a fixture set of 50-100 real queries and measure drift across model updates.

---

## Why this is a good microservice demo

- **Critical-path placement.** Sits on the hot path of every user interaction. If it's slow, your whole app is slow. If it's flaky, your whole app is flaky. Perfect stress-test for the per-conversation microservice pattern.
- **Decision without answer.** Unlike the Ticket Router or Lead Qualifier (which produce end-state records), this bot produces an *intermediate decision* that drives further pipeline execution. Same archetype, different phase of the pipeline.
- **Confidence escape hatch.** `confidence < 0.5` means the classifier isn't sure — fall back to the most expensive path rather than mis-route silently.
- **Drop-in for an existing RAG stack.** Your retriever, reranker, and generator don't change. You just add a single HTTP hop at the front door.

---

## Copy-paste variant ideas

Same archetype (fast, bounded, schema-driven decision), different placement:

- **Support Ticket Router** → see [`Support Ticket Router.md`](./Support%20Ticket%20Router.md) — classifies inbound customer messages for Zendesk/Linear routing.
- **Inbound Lead Qualifier** → see [`Inbound Lead Qualifier.md`](./Inbound%20Lead%20Qualifier.md) — scores B2B prospects for CRM routing.
- **Prompt-safety gatekeeper**: `{injection_risk, pii_exfil_risk, policy_violation, action: "allow|challenge|block", confidence}` — sits in front of any downstream LLM call, flags jailbreaks and PII leakage before they happen.
- **Agent-task decomposer**: `{sub_tasks[], required_tools[], estimated_latency_tier, requires_clarification}` — turns a natural-language agent goal into a structured work plan another orchestrator can execute.
- **Cache key canonicalizer**: `{canonical_form, hash_input, is_cacheable, ttl_hint}` — decides whether and how to cache an LLM result based on the user's phrasing.

Each is 150 words of English + a JSON schema. No retraining, no fine-tuning, no cloud bill. Pair with Bonsai's `/v1` endpoint when latency matters; fall back to a 3B on Ollama when it doesn't.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Status

This repository currently contains **specification and planning documents only — no source code has been written yet**. It is not a git repository. The four markdown files define what MiniClosedAI is supposed to become; any implementation work starts from scratch against these specs.

- `MiniClosedAI_BuildPrompt.md` — the authoritative build specification (MVP scope, models, endpoints, UI, file layout, success criteria).
- `MiniClosedAI_ExtendedRoadmap.md` — post-MVP phases (RAG, model comparison, presets, export, etc.). **Do not implement anything from here until the MVP in `BuildPrompt` is complete.**
- `ChefAI_CoreFeatures_Explained.md` — extracted patterns from the ChefAI reference codebase (streaming format, JSON message storage, prompt templates) that MiniClosedAI should reuse.
- `MiniClosedAI_vs_ChefAI_Comparison.md` — what to include vs. deliberately exclude from ChefAI. Treat the "❌" rows as hard exclusions from scope.

When the user asks to "build", "scaffold", or "start implementing", the source of truth is `MiniClosedAI_BuildPrompt.md` — not this file and not the extended roadmap.

## Project Architecture (as specified)

MiniClosedAI is a **single-user, 100% local** LLM playground: Django backend + vanilla-JS frontend + Ollama for inference. The core loop is: *create bot → adjust parameters → chat (streamed) → generate API code*.

Key architectural decisions baked into the spec — do not deviate without asking:

- **Stack**: Django 4.2+, Django Ninja for the REST API, SQLite, LangChain's `Ollama` wrapper talking to `http://localhost:11434`. Frontend is vanilla JS (no React/Vue), marked.js for markdown, Prism/highlight.js for code.
- **No auth**, **no cloud LLMs**, **no RAG/vector store**, **no Celery/Redis**, **no WebSockets** — all of these are deliberate exclusions vs. ChefAI. If a task seems to require them, flag it before adding.
- **Models** (`chat/models.py`): `Bot` (name, model_name, system_prompt, default params), `Conversation` (FK to Bot), `Message` (role, content, `parameters` JSONField). Per-message parameter snapshots are required for reproducibility — don't skip storing them.
- **Parameters are per-request, not global.** The request payload overrides the bot's defaults. This is called out as a key improvement over ChefAI's global-singleton approach.
- **Streaming**: `StreamingHttpResponse` + SSE, format `data: {json}\n\n`, terminator `data: {"end": true}\n\n`. Strip model-specific end tokens (`<|eot_id|>`, `<｜end▁of▁sentence｜>`) from chunks before yielding.
- **Intended file layout** is specified in `MiniClosedAI_BuildPrompt.md` under "File Structure" (Django project `minicloseai/`, app `chat/`, templates under `chat/templates/chat/`, static under `static/`). Follow it unless there's a concrete reason not to.
- **Complexity budget** from the spec: ~500 LoC Python, ~300 LoC JS, ~400 LoC CSS. Prefer small and direct over abstractions.

## API Surface (target)

Endpoints to implement under Django Ninja (`/api/...`):

- `POST /api/chat` — non-streaming
- `POST /api/chat/stream` — SSE streaming
- `GET|POST /api/bots`, `GET|PUT|DELETE /api/bots/{id}`
- `GET /api/conversations/{bot_id}`, `DELETE /api/conversations/{id}`

The API code generator in the UI must produce working cURL / Python / JS snippets that hit these exact endpoints with the user's current bot + parameter values — keep the templates in sync if endpoint shapes change.

## Commands

No build/test/run commands exist yet — there is no `manage.py`, `requirements.txt`, or `package.json`. Once the Django project is scaffolded, the spec expects the standard flow: `pip install -r requirements.txt` → `python manage.py migrate` → `python manage.py runserver`, with Ollama running separately (`ollama pull qwen2.5:3b llama3.2:3b phi3:mini`).

## When Editing the Spec Docs

These four `.md` files are design documents, not living implementation notes. If the user asks to change behavior, figure out whether they want the **spec updated** (edit the markdown) or the **implementation changed** (edit code once it exists). Don't silently update both.

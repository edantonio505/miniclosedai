// MiniClosedAI frontend — vanilla JS.

const els = {
  modelSelect: document.getElementById("model-select"),
  convSelect: document.getElementById("conversation-select"),
  newChatBtn: document.getElementById("new-chat-btn"),
  clearChatBtn: document.getElementById("clear-chat-btn"),
  downloadCsvBtn: document.getElementById("download-csv-btn"),
  deleteChatBtn: document.getElementById("delete-chat-btn"),
  apiCodeBtn: document.getElementById("api-code-btn"),
  systemPrompt: document.getElementById("system-prompt"),
  temperature: document.getElementById("temperature"),
  tempVal: document.getElementById("temp-val"),
  maxTokens: document.getElementById("max-tokens"),
  maxTokensVal: document.getElementById("max-tokens-val"),
  topP: document.getElementById("top-p"),
  topPVal: document.getElementById("top-p-val"),
  topK: document.getElementById("top-k"),
  topKVal: document.getElementById("top-k-val"),
  think: document.getElementById("think"),
  thinkVal: document.getElementById("think-val"),
  maxThinking: document.getElementById("max-thinking"),
  maxThinkingVal: document.getElementById("max-thinking-val"),
  resetParams: document.getElementById("reset-params"),
  stopBtn: document.getElementById("stop-btn"),
  splitter: document.getElementById("splitter"),
  hSplitter: document.getElementById("h-splitter"),
  layout: document.querySelector(".layout"),
  sidebar: document.querySelector(".sidebar"),
  sysPromptPanel: document.querySelector(".sys-prompt-panel"),
  themeToggle: document.getElementById("theme-toggle"),
  themeIconLight: document.getElementById("theme-icon-light"),
  themeIconDark: document.getElementById("theme-icon-dark"),
  themeIconSystem: document.getElementById("theme-icon-system"),
  sidebarToggle: document.getElementById("sidebar-toggle"),
  statusLine: document.getElementById("status-line"),
  messages: document.getElementById("messages"),
  form: document.getElementById("chat-form"),
  input: document.getElementById("input"),
  sendBtn: document.getElementById("send-btn"),
  attachBtn: document.getElementById("attach-btn"),
  attachInput: document.getElementById("attach-input"),
  attachmentList: document.getElementById("attachment-list"),
  attachmentWarning: document.getElementById("attachment-warning"),
  modalBackdrop: document.getElementById("modal-backdrop"),
  modalClose: document.getElementById("modal-close"),
  codeSnippet: document.getElementById("code-snippet"),
  copyCode: document.getElementById("copy-code"),
  langTabs: document.querySelectorAll('.tabs[data-group="lang"] .tab'),
  modeTabs: document.querySelectorAll('.tabs[data-group="mode"] .tab'),
  styleTabs: document.querySelectorAll('.tabs[data-group="style"] .tab'),
};

const DEFAULTS = { temperature: 0.7, max_tokens: 2048, top_p: 0.9, top_k: 40 };
const DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant.";
const SMALL_MODEL_PREFIXES = [
  "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b",
  "llama3.2:1b", "llama3.2:3b", "llama3.1:8b",
  "phi3:mini", "phi3.5",
  "gemma2:2b", "gemma2:9b",
  "mistral:7b",
  "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b",
  "tinyllama",
];

let state = {
  conversationId: null,
  messages: [], // [{role, content, params?}]
  activeTab: "curl",       // "curl" | "python" | "js"
  activeMode: "stream",    // "stream" | "sync"
  activeStyle: "native",   // "native" | "openai"
  abortController: null,
  // Pending attachments for the next outgoing user message. Cleared after
  // each successful send. See ATTACH_* constants and _ingestFile() below
  // for the entry shape.
  attachments: [],
};

// ---------- Utilities ----------
function fmtBytes(n) {
  if (!n) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(1)}${units[i]}`;
}
function esc(s) { return s.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

// If the assistant's reply is valid JSON (bare, or inside a ```fenced block```),
// reformat it with 2-space indentation and wrap it in a ```json code fence so
// the Markdown renderer hands it to highlight.js afterwards. Returns the input
// unchanged when nothing parses — safe to call on every chunk during streaming.
function prettifyJSONInMarkdown(text) {
  if (!text) return text;

  // Case 1: the whole message is JSON.
  const trimmed = text.trim();
  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try {
      const parsed = JSON.parse(trimmed);
      return "```json\n" + JSON.stringify(parsed, null, 2) + "\n```";
    } catch (_) { /* not complete / not valid — fall through */ }
  }

  // Case 2: fenced code blocks whose body is JSON. Also upgrades blocks with
  // no language tag or a different tag (e.g. ```) if the content parses.
  return text.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, body) => {
    const content = body.trim();
    if (!content) return match;
    const looksJson = lang.toLowerCase() === "json" || /^[\{\[]/.test(content);
    if (!looksJson) return match;
    try {
      const parsed = JSON.parse(content);
      return "```json\n" + JSON.stringify(parsed, null, 2) + "\n```";
    } catch (_) {
      return match;
    }
  });
}

function render(md) { return marked.parse(prettifyJSONInMarkdown(md || "")); }

// Run highlight.js over every <pre><code> inside a container. Idempotent.
function highlightCodeBlocks(container) {
  if (!window.hljs || !container) return;
  container.querySelectorAll("pre code").forEach(el => {
    if (el.dataset.highlighted === "yes") return;
    try { hljs.highlightElement(el); } catch (_) {}
  });
}
function scrollToBottom() {
  // Force an instant jump to the true bottom. Using rAF so we measure
  // scrollHeight AFTER any just-appended DOM has laid out.
  requestAnimationFrame(() => {
    els.messages.scrollTop = els.messages.scrollHeight;
  });
}

function getParams() {
  // Always include every param key. Empty/cleared fields become explicit `null`
  // so the server can distinguish "unchanged" from "cleared" and actually wipe
  // the saved value (otherwise a PATCH that omits a key silently preserves
  // the old value).
  const thinkVal = thinkFromSelect();
  const mtRaw = els.maxThinking.value.trim();
  const mtNum = mtRaw === "" ? null : parseInt(mtRaw, 10);
  return {
    temperature: parseFloat(els.temperature.value),
    max_tokens: parseInt(els.maxTokens.value, 10),
    top_p: parseFloat(els.topP.value),
    top_k: parseInt(els.topK.value, 10),
    think: thinkVal === undefined ? null : thinkVal,
    max_thinking_tokens: Number.isFinite(mtNum) && mtNum > 0 ? mtNum : null,
  };
}

// Translate <select> value into the value expected on the wire:
//   "" → undefined (don't send; model default)
//   "false" / "true" → boolean
//   "low" / "medium" / "high" → string
function thinkFromSelect() {
  const v = els.think.value;
  if (v === "") return undefined;
  if (v === "true") return true;
  if (v === "false") return false;
  return v;
}

function thinkToSelect(v) {
  if (v === true) return "true";
  if (v === false) return "false";
  if (typeof v === "string") return v;
  return "";
}

function thinkLabel(v) {
  if (v === undefined || v === "") return "Default";
  if (v === true || v === "true") return "On";
  if (v === false || v === "false") return "Off";
  return v.charAt(0).toUpperCase() + v.slice(1);
}

function saveSettings() {
  const opt = els.modelSelect.selectedOptions[0];
  const backendId = opt && opt.dataset.backendId ? parseInt(opt.dataset.backendId, 10) : undefined;
  const s = {
    ...getParams(),
    model: (opt && opt.value) || "",
    backend_id: Number.isFinite(backendId) ? backendId : undefined,
    system_prompt: els.systemPrompt.value,
    think_select: els.think.value,
  };
  localStorage.setItem("miniclosedai:settings", JSON.stringify(s));
}
function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem("miniclosedai:settings") || "{}");
    if (s.temperature != null) els.temperature.value = s.temperature;
    if (s.max_tokens != null) els.maxTokens.value = s.max_tokens;
    if (s.top_p != null) els.topP.value = s.top_p;
    if (s.top_k != null) els.topK.value = s.top_k;
    if (s.system_prompt) els.systemPrompt.value = s.system_prompt;
    if (s.think_select != null) els.think.value = s.think_select;
    return s;
  } catch { return {}; }
}

function syncParamDisplay() {
  els.tempVal.textContent = parseFloat(els.temperature.value).toFixed(1);
  els.maxTokensVal.textContent = els.maxTokens.value;
  els.topPVal.textContent = parseFloat(els.topP.value).toFixed(2);
  els.topKVal.textContent = els.topK.value;
  els.thinkVal.textContent = thinkLabel(thinkFromSelect());
  const mt = els.maxThinking.value.trim();
  els.maxThinkingVal.textContent = mt === "" ? "—" : mt;
}

// Debounced autosave of the current conversation's config.
let saveTimer = null;

function _buildConfigPatch() {
  const opt = els.modelSelect.selectedOptions[0];
  const backendId = opt && opt.dataset.backendId ? parseInt(opt.dataset.backendId, 10) : undefined;
  return {
    ...getParams(),
    model: (opt && opt.value) || undefined,
    backend_id: Number.isFinite(backendId) ? backendId : undefined,
    system_prompt: els.systemPrompt.value || undefined,
  };
}

function scheduleSaveToConversation() {
  if (!state.conversationId) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    fetch(`/api/conversations/${state.conversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_buildConfigPatch()),
    }).catch(() => {});
  }, 350);
}

// Cancel any pending debounce and PATCH immediately. Returned promise
// resolves once the server has acknowledged the current sidebar state.
async function flushPendingSave() {
  if (!state.conversationId) return;
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
  try {
    await fetch(`/api/conversations/${state.conversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(_buildConfigPatch()),
    });
  } catch (_) { /* offline / transient — snippet still works with prior saved state */ }
}

function bindParamDisplay() {
  ["input", "change"].forEach(evt => {
    [els.temperature, els.maxTokens, els.topP, els.topK, els.maxThinking].forEach(el => el.addEventListener(evt, () => {
      syncParamDisplay();
      saveSettings();
      scheduleSaveToConversation();
    }));
  });
  els.think.addEventListener("change", () => { syncParamDisplay(); saveSettings(); scheduleSaveToConversation(); });
  els.systemPrompt.addEventListener("input", () => { saveSettings(); scheduleSaveToConversation(); });
  els.modelSelect.addEventListener("change", () => { saveSettings(); scheduleSaveToConversation(); });
  els.resetParams.addEventListener("click", () => {
    els.temperature.value = DEFAULTS.temperature;
    els.maxTokens.value = DEFAULTS.max_tokens;
    els.topP.value = DEFAULTS.top_p;
    els.topK.value = DEFAULTS.top_k;
    els.think.value = "";
    els.maxThinking.value = "";
    syncParamDisplay();
    saveSettings();
    scheduleSaveToConversation();
  });
  syncParamDisplay();
}

// ---------- Models (aggregated across all registered endpoints) ----------
//
// Builds a grouped <optgroup> dropdown — one group per enabled+reachable
// backend, with models listed below. Each option carries both the model name
// (value) and its backend id (data-backend-id), so switching models also
// changes the conversation's backend.
//
// OpenWebUI-style: a single picker that shows everything available across all
// registered endpoints.

function _usableOllamaModels(models) {
  return models.filter(m => {
    const fam = (m.details && (m.details.family || "")) + " "
              + ((m.details && m.details.families) || []).join(" ");
    if (/bert|embed/i.test(fam) || /embed/i.test(m.name)) return false;
    return true;
  });
}

function _sortModels(models) {
  return [...models].sort((a, b) => {
    const aRec = SMALL_MODEL_PREFIXES.some(p => a.name.startsWith(p));
    const bRec = SMALL_MODEL_PREFIXES.some(p => b.name.startsWith(p));
    if (aRec !== bRec) return aRec ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

async function loadModels() {
  const r = await fetch("/api/models");
  const data = await r.json();
  els.modelSelect.innerHTML = "";

  const backends = data.backends || [];
  let totalModels = 0;
  let reachableCount = 0;

  for (const b of backends) {
    const group = document.createElement("optgroup");
    // Include a short status hint in the label so disabled / unreachable
    // backends are still represented (greyed out).
    let label = b.name;
    if (!b.enabled) label += " — disabled";
    else if (!b.running) label += " — unreachable";
    group.label = label;

    let models = b.models || [];
    if (b.kind === "ollama") models = _usableOllamaModels(models);
    models = _sortModels(models);

    if (!models.length) {
      const placeholder = document.createElement("option");
      placeholder.textContent = b.enabled
        ? (b.running ? "(no models)" : "(unreachable)")
        : "(disabled)";
      placeholder.disabled = true;
      group.appendChild(placeholder);
    } else {
      for (const m of models) {
        const opt = document.createElement("option");
        const size = m.size ? ` (${fmtBytes(m.size)})` : "";
        opt.textContent = `${m.name}${size}`;
        opt.value = m.name;
        opt.dataset.backendId = String(b.id);
        group.appendChild(opt);
      }
      totalModels += models.length;
      if (b.running) reachableCount += 1;
    }

    els.modelSelect.appendChild(group);
  }

  if (!backends.length) {
    const opt = new Option("(no endpoints registered)", "");
    opt.disabled = true;
    els.modelSelect.add(opt);
    setStatus("err", "No endpoints configured. Open Settings → Add endpoint.");
    _showNoBackendsEmptyState();
    return [];
  }
  // We DO have backends now — restore the regular empty state if it was swapped.
  _restoreDefaultEmptyState();

  // Restore last-used (model, backend_id) pair from localStorage.
  try {
    const saved = JSON.parse(localStorage.getItem("miniclosedai:settings") || "{}");
    if (saved.model) _selectModelOption(saved.model, saved.backend_id);
  } catch {}

  if (totalModels === 0) {
    setStatus("warn", `No models available. Endpoints: ${backends.length} · reachable: ${reachableCount}.`);
  } else {
    const total = backends.length;
    setStatus("ok", `${reachableCount}/${total} endpoint${total === 1 ? "" : "s"} reachable · ${totalModels} model${totalModels === 1 ? "" : "s"}`);
  }
  return backends;
}

/**
 * Select an option by (value, backend_id) pair.
 * Returns true if matched, false otherwise (and clears selection).
 */
function _selectModelOption(modelName, backendId) {
  if (!modelName) return false;
  const bid = backendId != null ? String(backendId) : null;
  for (const group of els.modelSelect.querySelectorAll("optgroup")) {
    for (const opt of group.querySelectorAll("option")) {
      if (opt.disabled) continue;
      if (opt.value === modelName && (bid == null || opt.dataset.backendId === bid)) {
        els.modelSelect.value = opt.value;  // doesn't pick the right option cross-group
        // setting .value alone can pick a different group; mark explicitly:
        opt.selected = true;
        return true;
      }
    }
  }
  // Fallback: match by name only, ignore backend_id
  if (bid != null) return _selectModelOption(modelName, null);
  // No match — deselect.
  els.modelSelect.selectedIndex = -1;
  return false;
}

function setStatus(kind, text) {
  els.statusLine.className = kind;
  els.statusLine.textContent = text;
}

// ---------- Conversations ----------
async function loadConversations() {
  const r = await fetch("/api/conversations");
  const list = await r.json();
  els.convSelect.innerHTML = "";
  if (!list.length) {
    els.convSelect.add(new Option("(no conversations)", ""));
    return list;
  }
  for (const c of list) {
    els.convSelect.add(new Option(`${c.title} · ${c.model}`, c.id));
  }
  return list;
}

async function openConversation(id) {
  const r = await fetch(`/api/conversations/${id}`);
  if (!r.ok) return;
  const c = await r.json();
  state.conversationId = c.id;
  state.messages = c.messages || [];
  if (c.system_prompt) els.systemPrompt.value = c.system_prompt;

  // Match by (model, backend_id) pair. Falls back to model-only if the exact
  // pair can't be found (e.g. the endpoint was deleted). If nothing matches,
  // selection is cleared and the model dropdown shows no option — Send will
  // still attempt to call, and server will 404 on backend_load.
  if (c.model) _selectModelOption(c.model, c.backend_id);

  // Load saved per-conversation params into the sliders.
  const p = c.params || {};
  if (p.temperature != null) els.temperature.value = p.temperature;
  if (p.max_tokens != null) els.maxTokens.value = p.max_tokens;
  if (p.top_p != null) els.topP.value = p.top_p;
  if (p.top_k != null) els.topK.value = p.top_k;
  els.think.value = thinkToSelect(p.think);
  els.maxThinking.value = p.max_thinking_tokens != null ? p.max_thinking_tokens : "";
  syncParamDisplay();
  els.convSelect.value = String(id);
  renderMessages();
}

async function newConversation() {
  const opt = els.modelSelect.selectedOptions[0];
  const model = opt && opt.value;
  if (!model) {
    alert("Pick a model first.");
    return;
  }
  const backendId = opt.dataset.backendId
    ? parseInt(opt.dataset.backendId, 10)
    : 1;
  const input = prompt("Name this chat:", "");
  if (input === null) return;                 // user cancelled
  const title = input.trim() || "New Chat";

  // Every new bot starts from a clean slate — default system prompt and params.
  // Model + backend are carried over from the current selection.
  const r = await fetch("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      backend_id: backendId,
      system_prompt: DEFAULT_SYSTEM_PROMPT,
      title,
      ...DEFAULTS,
    }),
  });
  const c = await r.json();
  state.conversationId = c.id;
  state.messages = [];
  await loadConversations();
  els.convSelect.value = String(c.id);
  renderMessages();

  // Reset the sidebar so the user sees the clean config they're about to edit.
  // Must happen AFTER state.conversationId is set so the debounced auto-save
  // (triggered when the user starts typing) targets the new conversation.
  resetSidebarToDefaults();

  // Focus the system prompt so they can start authoring the bot immediately.
  els.systemPrompt.focus();
}

function resetSidebarToDefaults() {
  els.systemPrompt.value = "";
  els.temperature.value = DEFAULTS.temperature;
  els.maxTokens.value   = DEFAULTS.max_tokens;
  els.topP.value        = DEFAULTS.top_p;
  els.topK.value        = DEFAULTS.top_k;
  els.think.value       = "";
  els.maxThinking.value = "";
  syncParamDisplay();
  saveSettings();   // update localStorage; do NOT trigger scheduleSaveToConversation
                    // (the server already has these defaults from the just-created conv)
}

// ---------- Rendering ----------
const EMPTY_STATE_HTML = `
  <div class="empty-state">
    <h2>Your local LLM playground</h2>
    <p>Pick a model, tune parameters, and chat. Each saved conversation becomes its own callable API endpoint.</p>
    <div class="suggestion-chips">
      <button class="chip" data-prompt="Summarize this in one sentence: [paste text here]">
        <strong>Summarize concisely</strong>
        <span>Condense any text to one sentence</span>
      </button>
      <button class="chip" data-prompt="Extract the key entities (people, orgs, dates) from: [paste text]">
        <strong>Extract entities</strong>
        <span>Names, orgs, dates, amounts</span>
      </button>
      <button class="chip" data-prompt="Write a Python function that deduplicates a list while preserving order.">
        <strong>Write code</strong>
        <span>Short, focused snippets</span>
      </button>
      <button class="chip" data-prompt="Explain the difference between async and threads in Python at a senior level.">
        <strong>Explain concepts</strong>
        <span>Technical explanations</span>
      </button>
    </div>
  </div>
`;

// Shown when zero backends are registered (typically lite-mode first run).
// The suggestion chips wouldn't fire — no model selected — so we replace
// them with a clear CTA that flips to the Settings tab.
const EMPTY_STATE_NO_BACKENDS_HTML = `
  <div class="empty-state empty-state-no-backends">
    <h2>Welcome — let's add your first endpoint</h2>
    <p>This MiniClosedAI install isn't shipping a built-in Ollama. Point it at any external compute source — a remote Ollama, an LM Studio, vLLM, llama.cpp server, or any OpenAI-compatible URL — through the Settings page. The endpoint's models will appear in the dropdown above.</p>
    <button class="btn btn-primary" data-action="open-settings">Open Settings → Add endpoint</button>
  </div>
`;

// Tracks whether the "no endpoints registered" empty-state should show
// instead of the default suggestion-chips one. Flipped from loadModels()
// based on the live backends list — so adding an endpoint and refreshing
// flips us back to the regular onboarding state automatically.
let _noBackendsEmptyState = false;

function _showNoBackendsEmptyState() {
  _noBackendsEmptyState = true;
  if (!state.messages.length) renderMessages();
}

function _restoreDefaultEmptyState() {
  if (!_noBackendsEmptyState) return;
  _noBackendsEmptyState = false;
  if (!state.messages.length) renderMessages();
}

function renderMessages() {
  els.messages.innerHTML = "";
  if (!state.messages.length) {
    els.messages.insertAdjacentHTML(
      "beforeend",
      _noBackendsEmptyState ? EMPTY_STATE_NO_BACKENDS_HTML : EMPTY_STATE_HTML
    );
    return;
  }
  state.messages.forEach((m, i) => renderMessage(m, i));
  scrollToBottom();
}

/**
 * Render one message. `index` is its position in state.messages — stashed on
 * the DOM node so the edit handler can look up the raw content without
 * re-deriving it from the rendered HTML.
 */
function renderMessage(m, index) {
  const div = document.createElement("div");
  div.className = `msg ${m.role}`;
  if (index != null) div.dataset.index = String(index);
  let body;
  if (m.role === "user") {
    body = document.createElement("div");
    body.className = "msg-body";
    // Multimodal-aware: when content is a list of parts, show only the
    // user's typed text (display_text if present, else extracted from the
    // text part) so the bubble doesn't dump full PDF/text bodies. Inline
    // images and doc chips render below the text.
    const visibleText = _userVisibleText(m);
    if (visibleText) body.textContent = visibleText;
    _appendUserAttachments(body, m);
    div.appendChild(body);
  } else {
    // Wrap assistant content in a single child so the flex avatar lays out correctly.
    body = document.createElement("div");
    body.className = "msg-body";
    body.innerHTML = render(typeof m.content === "string" ? m.content : "");
    div.appendChild(body);
    highlightCodeBlocks(body);
    if (m.params) appendParamsBadge(body, m.params);
  }
  if (m.edited) appendEditedBadge(body, m);
  // Pencil button — assistant turns only. Disabled while a stream is active
  // so you can't clobber a message that's still growing.
  if (index != null && m.role === "assistant") _appendEditButton(div, index);

  const emptyState = els.messages.querySelector(".empty-state");
  if (emptyState) emptyState.remove();
  els.messages.appendChild(div);
  return div;
}

function appendParamsBadge(parent, params) {
  const badge = document.createElement("div");
  badge.className = "params-badge";
  badge.textContent = `${params.model || ""} · T=${params.temperature} · max=${params.max_tokens} · top_p=${params.top_p} · top_k=${params.top_k}`;
  parent.appendChild(badge);
}

function appendEditedBadge(msgEl, m) {
  const badge = document.createElement("div");
  badge.className = "msg-edited-badge";
  badge.textContent = "edited";
  if (m.original_content) {
    badge.title = "Click to see the original model output";
    badge.addEventListener("click", () => {
      alert(
        "Original (before editing):\n\n" +
        (m.original_content.length > 2000
          ? m.original_content.slice(0, 2000) + "\n\n…(truncated)"
          : m.original_content)
      );
    });
    badge.style.cursor = "pointer";
  }
  msgEl.appendChild(badge);
}

function _appendEditButton(msgEl, index) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "msg-edit-btn";
  btn.title = "Edit message";
  btn.setAttribute("aria-label", "Edit message");
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>`;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (state.abortController) {
      // Don't let anyone edit a turn while a stream is still growing.
      return;
    }
    openInlineEditor(msgEl, index);
  });
  msgEl.appendChild(btn);
}

function openInlineEditor(msgEl, index) {
  const m = state.messages[index];
  if (!m) return;
  // Only one editor open at a time.
  if (msgEl.querySelector(".msg-edit-area")) return;

  const body = msgEl.querySelector(".msg-body");
  const editBtn = msgEl.querySelector(".msg-edit-btn");
  if (!body) return;
  const originalDisplay = body.style.display;
  body.style.display = "none";
  if (editBtn) editBtn.style.display = "none";

  const wrap = document.createElement("div");
  wrap.className = "msg-edit-area";

  const textarea = document.createElement("textarea");
  // Strip whitespace at BOTH ends — LM Studio + Qwen3 often emit a leading
  // \n\n when thinking ends and the answer starts, plus trailing \n\n on
  // completion. Both pollute the editor and the CSV export.
  const initial = (m.content || "").replace(/^\s+|\s+$/g, "");
  textarea.value = initial;
  textarea.rows = Math.min(24, Math.max(3, initial.split("\n").length + 1));
  wrap.appendChild(textarea);

  const actions = document.createElement("div");
  actions.className = "msg-edit-actions";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "btn btn-primary btn-small";
  saveBtn.textContent = "Save";

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "btn btn-small";
  cancelBtn.textContent = "Cancel";

  actions.appendChild(cancelBtn);
  actions.appendChild(saveBtn);
  wrap.appendChild(actions);
  msgEl.appendChild(wrap);

  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);

  const close = () => {
    wrap.remove();
    body.style.display = originalDisplay;
    if (editBtn) editBtn.style.display = "";
  };

  cancelBtn.addEventListener("click", close);
  saveBtn.addEventListener("click", () => saveInlineEdit(msgEl, index, textarea.value, close, saveBtn));
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if ((e.key === "Enter") && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      saveInlineEdit(msgEl, index, textarea.value, close, saveBtn);
    }
  });
}

async function saveInlineEdit(msgEl, index, content, close, saveBtn) {
  if (!state.conversationId) { close(); return; }
  saveBtn.disabled = true;
  const prevLabel = saveBtn.textContent;
  saveBtn.textContent = "Saving…";
  try {
    const r = await fetch(
      `/api/conversations/${state.conversationId}/messages/${index}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      }
    );
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      const msg = (body.detail && body.detail.message) || body.detail || `HTTP ${r.status}`;
      alert("Edit failed: " + (typeof msg === "string" ? msg : JSON.stringify(msg)));
      return;
    }
    const updated = await r.json();
    state.messages = updated.messages || [];
    // Re-render this one message in place to preserve scroll position.
    const fresh = state.messages[index];
    if (fresh) _rerenderMessageInPlace(msgEl, fresh, index);
    else close();
  } catch (e) {
    alert("Edit failed: " + (e && e.message || e));
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = prevLabel;
  }
}

function _rerenderMessageInPlace(msgEl, m, index) {
  // Wipe children, reuse the existing .msg element so the outer layout / data-
  // index / flex position stay intact.
  msgEl.innerHTML = "";
  let body;
  if (m.role === "user") {
    body = document.createElement("div");
    body.className = "msg-body";
    const visibleText = _userVisibleText(m);
    if (visibleText) body.textContent = visibleText;
    _appendUserAttachments(body, m);
    msgEl.appendChild(body);
  } else {
    body = document.createElement("div");
    body.className = "msg-body";
    body.innerHTML = render(typeof m.content === "string" ? m.content : "");
    msgEl.appendChild(body);
    highlightCodeBlocks(body);
    if (m.params) appendParamsBadge(body, m.params);
  }
  if (m.edited) appendEditedBadge(body, m);
  if (m.role === "assistant") _appendEditButton(msgEl, index);
}

// ---------- Attachments ----------
//
// Pending attachments live in `state.attachments` until the user hits send.
// Each entry is one of:
//   {kind:"image", name, mime, size, data_url}        // FileReader.readAsDataURL
//   {kind:"text",  name, mime, size, text}            // FileReader.readAsText
//   {kind:"pdf",   name, mime, size, text, page_count, char_count, truncated}
// The shape mirrors AttachmentSpec on the server so we can `JSON.stringify`
// straight into the chat request body.

const ATTACH_MAX_BYTES = 10 * 1024 * 1024;          // per-file cap, before base64 inflation
const ATTACH_IMAGE_MAX_DIM = 2048;                  // longest-edge cap; we downscale in-browser
const ATTACH_TEXT_MAX_CHARS = 30_000;               // matches the PDF cap on the server
const VISION_MODEL_PATTERNS = [
  /^llava/i, /-vision/i, /vl[:-]/i, /qwen.*vl/i, /qwen3\.6/i,
  /^gemma4/i, /llama3\.2-vision/i, /minicpm-?v/i, /pixtral/i, /moondream/i,
];

function _looksLikeVisionModel(name) {
  if (!name) return false;
  return VISION_MODEL_PATTERNS.some(re => re.test(name));
}

function _readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(fr.error || new Error("read failed"));
    fr.readAsDataURL(file);
  });
}

function _readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(fr.error || new Error("read failed"));
    fr.readAsText(file);
  });
}

// Downscale large images via canvas to keep base64 payloads sane. Called only
// when an image's longest edge exceeds ATTACH_IMAGE_MAX_DIM. Output is JPEG
// at quality 0.92 (good enough for vision models, 5–10× smaller than PNG).
async function _downscaleImage(dataUrl) {
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = reject;
    img.src = dataUrl;
  });
  const longest = Math.max(img.width, img.height);
  if (longest <= ATTACH_IMAGE_MAX_DIM) return dataUrl;
  const scale = ATTACH_IMAGE_MAX_DIM / longest;
  const w = Math.round(img.width * scale);
  const h = Math.round(img.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  canvas.getContext("2d").drawImage(img, 0, 0, w, h);
  return canvas.toDataURL("image/jpeg", 0.92);
}

function _isImageMime(mime, name) {
  if (mime && mime.startsWith("image/")) return true;
  return /\.(png|jpe?g|webp|gif|bmp)$/i.test(name || "");
}
function _isPdfMime(mime, name) {
  return mime === "application/pdf" || /\.pdf$/i.test(name || "");
}
function _isTextLike(file) {
  if (file.type && file.type.startsWith("text/")) return true;
  // file.type is empty for many code files; fall back to extension.
  return /\.(txt|md|markdown|csv|tsv|json|jsonl|yaml|yml|toml|xml|html?|css|js|jsx|ts|tsx|py|go|rs|java|c|cpp|cc|h|hpp|sh|bash|zsh|sql|log|env|ini|conf|cfg)$/i.test(file.name || "");
}

async function _ingestFile(file) {
  if (file.size > ATTACH_MAX_BYTES) {
    throw new Error(`${file.name} is ${(file.size / 1024 / 1024).toFixed(1)} MB — over the 10 MB cap.`);
  }
  // --- Image ---
  if (_isImageMime(file.type, file.name)) {
    let dataUrl = await _readFileAsDataUrl(file);
    dataUrl = await _downscaleImage(dataUrl);
    return {
      kind: "image",
      name: file.name,
      mime: file.type || "image/jpeg",
      size: file.size,
      data_url: dataUrl,
    };
  }
  // --- PDF ---
  if (_isPdfMime(file.type, file.name)) {
    const fd = new FormData();
    fd.append("file", file, file.name);
    const r = await fetch("/api/extract-pdf", { method: "POST", body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `PDF extraction failed (HTTP ${r.status}).`);
    }
    const j = await r.json();
    return {
      kind: "pdf",
      name: file.name,
      mime: "application/pdf",
      size: file.size,
      text: j.text || "",
      page_count: j.page_count,
      char_count: j.char_count,
      truncated: !!j.truncated,
    };
  }
  // --- Plain text / source code ---
  if (_isTextLike(file)) {
    let text = await _readFileAsText(file);
    let truncated = false;
    if (text.length > ATTACH_TEXT_MAX_CHARS) {
      text = text.slice(0, ATTACH_TEXT_MAX_CHARS);
      truncated = true;
    }
    return {
      kind: "text",
      name: file.name,
      mime: file.type || "text/plain",
      size: text.length,
      text,
      char_count: text.length,
      truncated,
    };
  }
  throw new Error(`${file.name}: unsupported file type. Attach images, PDFs, or text/source files.`);
}

function _formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function _renderAttachmentChips() {
  const list = els.attachmentList;
  list.innerHTML = "";
  const atts = state.attachments || [];
  if (!atts.length) {
    list.hidden = true;
    return;
  }
  list.hidden = false;
  atts.forEach((a, idx) => {
    const chip = document.createElement("span");
    chip.className = "attachment-chip";

    if (a.kind === "image") {
      const img = document.createElement("img");
      img.className = "attachment-chip-thumb";
      img.src = a.data_url;
      img.alt = a.name;
      chip.appendChild(img);
    } else {
      const ic = document.createElement("span");
      ic.className = "attachment-chip-icon";
      ic.innerHTML = a.kind === "pdf"
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M10 13h.01M14 13h.01M10 17h4"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>';
      chip.appendChild(ic);
    }

    const meta = document.createElement("span");
    meta.className = "attachment-chip-meta";
    const nameEl = document.createElement("span");
    nameEl.className = "attachment-chip-name";
    nameEl.textContent = a.name;
    nameEl.title = a.name;
    const subEl = document.createElement("span");
    subEl.className = "attachment-chip-sub";
    if (a.kind === "pdf") {
      subEl.textContent = `${a.page_count || 0} pages${a.truncated ? " · truncated" : ""}`;
    } else if (a.kind === "image") {
      subEl.textContent = _formatBytes(a.size);
    } else {
      subEl.textContent = `${a.char_count || (a.text || "").length} chars${a.truncated ? " · truncated" : ""}`;
    }
    meta.appendChild(nameEl);
    meta.appendChild(subEl);
    chip.appendChild(meta);

    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "attachment-chip-remove";
    rm.textContent = "×";
    rm.title = "Remove";
    rm.addEventListener("click", () => {
      state.attachments.splice(idx, 1);
      _renderAttachmentChips();
      _refreshAttachmentWarning();
    });
    chip.appendChild(rm);

    list.appendChild(chip);
  });
}

function _refreshAttachmentWarning() {
  const w = els.attachmentWarning;
  if (!w) return;
  const hasImage = (state.attachments || []).some(a => a.kind === "image");
  const model = els.modelSelect.value || "";
  if (hasImage && !_looksLikeVisionModel(model)) {
    w.hidden = false;
    w.textContent = `⚠️ "${model}" doesn't look like a vision-capable model. The image will be sent anyway, but the reply may ignore it.`;
  } else {
    w.hidden = true;
    w.textContent = "";
  }
}

async function _addFiles(files) {
  if (!files || !files.length) return;
  const errors = [];
  for (const f of files) {
    try {
      const att = await _ingestFile(f);
      state.attachments.push(att);
    } catch (e) {
      errors.push(e.message || String(e));
    }
  }
  _renderAttachmentChips();
  _refreshAttachmentWarning();
  if (errors.length) alert(errors.join("\n"));
}

function _clearAttachments() {
  state.attachments = [];
  _renderAttachmentChips();
  _refreshAttachmentWarning();
}

// What to display inside a user bubble. Prefers `display_text` (the user's
// actual typed text, no "[Attached: …]" prefixes). Falls back to the raw text
// part of a multimodal content array, or to the plain string content.
function _userVisibleText(m) {
  if (typeof m.display_text === "string") return m.display_text;
  if (typeof m.content === "string") return m.content;
  if (Array.isArray(m.content)) {
    return m.content
      .filter(p => p && p.type === "text")
      .map(p => p.text || "")
      .join("\n");
  }
  return "";
}

// Append inline image previews + doc chips below the user's text inside a bubble.
function _appendUserAttachments(bodyEl, m) {
  const images = [];
  if (Array.isArray(m.content)) {
    for (const p of m.content) {
      if (p && p.type === "image_url" && p.image_url && p.image_url.url) {
        images.push(p.image_url.url);
      }
    }
  }
  const docs = (m.attachments || []).filter(a => a && a.kind !== "image");
  if (!images.length && !docs.length) return;
  const wrap = document.createElement("div");
  wrap.className = "msg-attachments";
  for (const url of images) {
    const img = document.createElement("img");
    img.src = url;
    img.alt = "attached image";
    wrap.appendChild(img);
  }
  for (const a of docs) {
    const chip = document.createElement("span");
    chip.className = "msg-doc-chip";
    const label = a.kind === "pdf"
      ? `${a.name} · ${a.page_count ?? "?"} pages${a.truncated ? " (truncated)" : ""}`
      : `${a.name}`;
    chip.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
    const span = document.createElement("span");
    span.textContent = label;
    chip.appendChild(span);
    wrap.appendChild(chip);
  }
  bodyEl.appendChild(wrap);
}

// Wire the attach UI: button click opens picker, file input triggers ingestion,
// pasted images are captured into state.attachments, and the model dropdown's
// change event refreshes the soft-warn banner.
function bindAttachments() {
  if (!els.attachBtn || !els.attachInput) return;
  els.attachBtn.addEventListener("click", () => els.attachInput.click());
  els.attachInput.addEventListener("change", async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";  // allow re-picking the same file later
    await _addFiles(files);
  });
  // Clipboard paste — only fires when the textarea has focus.
  els.input.addEventListener("paste", async (e) => {
    const items = (e.clipboardData && e.clipboardData.items) || [];
    const files = [];
    for (const it of items) {
      if (it.kind === "file") {
        const f = it.getAsFile();
        if (f) files.push(f);
      }
    }
    if (files.length) {
      e.preventDefault();
      await _addFiles(files);
    }
  });
  els.modelSelect.addEventListener("change", _refreshAttachmentWarning);
}

// ---------- Streaming chat ----------
async function sendMessage(text) {
  const model = els.modelSelect.value;
  if (!model) { alert("Pick a model first."); return; }
  // Allow attachment-only sends ("[image] please describe").
  if (!text.trim() && !(state.attachments && state.attachments.length)) return;

  // Ensure a conversation exists
  if (!state.conversationId) {
    await newConversation();
  }

  const params = getParams();

  // Snapshot attachments at send time so the chips clear immediately and
  // a slow upload doesn't get re-sent if the user adds another file mid-flight.
  const attachmentsForSend = (state.attachments || []).slice();
  _clearAttachments();

  // Build the user-side message for in-page rendering. If there are
  // attachments, mirror the server's content-array shape so renderMessage
  // can show inline images + doc chips. The server applies the same
  // assembly on its side from {message, attachments}.
  let userMsg;
  if (attachmentsForSend.length) {
    const textChunks = [];
    const imageParts = [];
    const meta = [];
    for (const a of attachmentsForSend) {
      if (a.kind === "image") {
        imageParts.push({ type: "image_url", image_url: { url: a.data_url } });
        meta.push({ name: a.name, kind: "image", mime: a.mime });
      } else {
        if (a.text) textChunks.push(`[Attached: ${a.name}]\n${a.text}`);
        const m = { name: a.name, kind: a.kind };
        if (a.page_count != null) m.page_count = a.page_count;
        if (a.char_count != null) m.char_count = a.char_count;
        if (a.truncated) m.truncated = true;
        meta.push(m);
      }
    }
    if (text.trim()) textChunks.push(text);
    const combined = textChunks.join("\n\n");
    const contentParts = [];
    if (combined) contentParts.push({ type: "text", text: combined });
    contentParts.push(...imageParts);
    userMsg = {
      role: "user",
      content: contentParts,
      display_text: text,
      attachments: meta,
    };
  } else {
    userMsg = { role: "user", content: text };
  }
  state.messages.push(userMsg);
  renderMessage(userMsg);
  scrollToBottom();

  // Assistant placeholder with streaming cursor
  const assistantEl = renderMessage({ role: "assistant", content: "" });
  const body = assistantEl.querySelector(".msg-body");
  assistantEl.classList.add("cursor");
  scrollToBottom();
  let assistantText = "";
  let thinkingText = "";
  let thinkingEl = null;
  let contentEl = null;
  let truncatedNotice = null;
  const ac = new AbortController();
  state.abortController = ac;
  els.stopBtn.style.display = "";
  els.sendBtn.style.display = "none";

  els.sendBtn.disabled = true;
  els.input.disabled = true;

  // Ensure the server's saved config matches the sidebar BEFORE we fire
  // the call. This way the GUI Send button is identical to the cURL
  // snippet shown in "Get API Code" — both hit the conversation's pure-
  // function endpoint with just `{message}` and rely on saved state.
  await flushPendingSave();

  try {
    const res = await fetch(`/api/conversations/${state.conversationId}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: ac.signal,
      body: JSON.stringify({
        message: text,
        persist: true,
        // Conversational UI — the model needs to see prior turns. Without this
        // flag the server runs pure-function semantics (each turn stateless),
        // which is correct for classifier/router bots but breaks chat.
        include_history: true,
        // Server combines `message` + `attachments` into a multimodal user
        // turn (text bodies prepended, images become image_url parts).
        attachments: attachmentsForSend.length ? attachmentsForSend : undefined,
      }),
    });

    if (!res.ok || !res.body) {
      const body = await res.text().catch(() => "");
      throw new Error(body || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        let data;
        try { data = JSON.parse(line.slice(5).trim()); } catch { continue; }
        if (data.error) {
          assistantText += `\n\n**Error:** ${data.error}`;
          if (!contentEl) { body.innerHTML = ""; contentEl = document.createElement("div"); body.appendChild(contentEl); }
          contentEl.innerHTML = render(assistantText);
          break;
        }
        if (data.thinking) {
          thinkingText += data.thinking;
          if (!thinkingEl) {
            body.innerHTML = "";
            thinkingEl = document.createElement("details");
            thinkingEl.className = "thinking";
            thinkingEl.open = true;
            thinkingEl.innerHTML = '<summary>💭 Thinking…</summary><div class="thinking-body"></div>';
            body.appendChild(thinkingEl);
            contentEl = document.createElement("div");
            body.appendChild(contentEl);
          }
          thinkingEl.querySelector(".thinking-body").textContent = thinkingText;
          scrollToBottom();
        }
        if (data.chunk) {
          assistantText += data.chunk;
          if (!contentEl) { body.innerHTML = ""; contentEl = document.createElement("div"); body.appendChild(contentEl); }
          contentEl.innerHTML = render(assistantText);
          if (thinkingEl && thinkingEl.open) {
            thinkingEl.open = false;
            thinkingEl.querySelector("summary").textContent = "💭 Thoughts (click to expand)";
          }
          scrollToBottom();
        }
        if (data.thinking_truncated) {
          if (!truncatedNotice) {
            truncatedNotice = document.createElement("div");
            truncatedNotice.className = "truncated-notice";
            truncatedNotice.textContent =
              `✂ Thinking hidden after ${data.limit} tokens. Model still finishing its reasoning; the answer will follow.`;
            body.appendChild(truncatedNotice);
          }
          scrollToBottom();
        }
        if (data.end) break;
      }
    }
  } catch (e) {
    if (e.name === "AbortError") {
      const stoppedNotice = document.createElement("div");
      stoppedNotice.className = "truncated-notice";
      stoppedNotice.textContent = "⏹ Stopped by user.";
      body.appendChild(stoppedNotice);
    } else {
      assistantText += `\n\n**Request failed:** ${e.message}`;
      if (!contentEl) { contentEl = document.createElement("div"); body.appendChild(contentEl); }
      contentEl.innerHTML = render(assistantText);
    }
  } finally {
    state.abortController = null;
    els.stopBtn.style.display = "none";
    els.sendBtn.style.display = "";
    assistantEl.classList.remove("cursor");
    // Params badge inside the body so the flex layout stays clean.
    const badge = document.createElement("div");
    badge.className = "params-badge";
    badge.textContent = `${model} · T=${params.temperature} · max=${params.max_tokens} · top_p=${params.top_p} · top_k=${params.top_k}`;
    body.appendChild(badge);

    // Final pass: pretty-print JSON (render() already calls prettifyJSONInMarkdown
    // on every chunk, but the content only parses once the closing brace arrives)
    // and run syntax highlighting once, now that streaming is done.
    if (contentEl) {
      contentEl.innerHTML = render(assistantText);
      highlightCodeBlocks(contentEl);
    }

    state.messages.push({ role: "assistant", content: assistantText, params: { model, ...params } });
    // Now that streaming is done and the message is in state, attach the edit
    // pencil — the placeholder was rendered without an index since we didn't
    // know the final message count yet.
    const finalIndex = state.messages.length - 1;
    assistantEl.dataset.index = String(finalIndex);
    _appendEditButton(assistantEl, finalIndex);
    els.sendBtn.disabled = false;
    els.input.disabled = false;
    els.input.focus();
    scrollToBottom();   // settle the viewport on the fully-rendered final message
    loadConversations();
  }
}

// ---------- API code modal ----------
// Each conversation is a saved microservice: its model, system prompt, and
// sampling params are locked server-side. The snippet only needs to supply
// the message (or the messages list, for multi-turn).
function buildCodeSnippet(tab, mode, style) {
  const base = window.location.origin;
  const convId = state.conversationId;
  if (!convId) {
    return "# Send a message first to create a conversation.\n# Each chat becomes its own configured API endpoint.";
  }
  if (style === "openai") return buildOpenAISnippet(tab, mode, base, convId);
  return buildNativeSnippet(tab, mode, base, convId);
}

function buildNativeSnippet(tab, mode, base, convId) {
  const msg = "Hello!";
  const streamUrl = `${base}/api/conversations/${convId}/chat/stream`;
  const syncUrl = `${base}/api/conversations/${convId}/chat`;
  const header = `# Chat #${convId}. Config (model, system prompt, temperature, max_tokens,\n# top_p, top_k, thinking) is set in the GUI — this call only supplies the message.`;

  // ---- cURL ----
  if (tab === "curl") {
    if (mode === "stream") {
      return `${header}
curl -N -X POST ${streamUrl} \\
  -H "Content-Type: application/json" \\
  -d '{"message": "${msg}"}'`;
    }
    return `${header}
curl -X POST ${syncUrl} \\
  -H "Content-Type: application/json" \\
  -d '{"message": "${msg}"}'`;
  }

  // ---- Python ----
  if (tab === "python") {
    if (mode === "stream") {
      return `import httpx, json

URL = "${streamUrl}"

with httpx.stream("POST", URL, json={"message": "${msg}"}, timeout=None) as r:
    for line in r.iter_lines():
        if line.startswith("data:"):
            data = json.loads(line[5:].strip())
            if "chunk" in data:
                print(data["chunk"], end="", flush=True)
            if data.get("end"):
                break`;
    }
    return `import httpx

URL = "${syncUrl}"

response = httpx.post(URL, json={"message": "${msg}"}, timeout=120).json()
print(response["response"])`;
  }

  // ---- JavaScript ----
  if (tab === "js") {
    if (mode === "stream") {
      return `const res = await fetch("${streamUrl}", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "${msg}" }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
let buf = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  const parts = buf.split("\\n\\n");
  buf = parts.pop();
  for (const part of parts) {
    if (!part.startsWith("data:")) continue;
    const data = JSON.parse(part.slice(5).trim());
    if (data.chunk) process.stdout.write(data.chunk);
    if (data.end) return;
  }
}`;
    }
    return `const { response } = await fetch("${syncUrl}", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "${msg}" }),
}).then(r => r.json());

console.log(response);`;
  }
  return "";
}

// OpenAI-compatible snippets — caller uses the OpenAI SDK (or the raw HTTP
// schema) pointed at MiniClosedAI's /v1 endpoint. The conversation ID goes
// in the `model` field; any caller-supplied sampling params are ignored by
// the server in favor of the bot's GUI-saved config.
function buildOpenAISnippet(tab, mode, base, convId) {
  const msg = "Hello!";
  const url = `${base}/v1/chat/completions`;
  const header = `# OpenAI-compatible. Use the conversation ID as 'model'. The bot's saved
# config (model, system prompt, temperature, etc.) is the source of truth —
# any caller-provided sampling params are ignored by the server.`;

  // ---- cURL ----
  if (tab === "curl") {
    if (mode === "stream") {
      return `${header}
curl -N -X POST ${url} \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${convId}",
    "messages": [{"role":"user","content":"${msg}"}],
    "stream": true
  }'`;
    }
    return `${header}
curl -X POST ${url} \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${convId}",
    "messages": [{"role":"user","content":"${msg}"}]
  }'`;
  }

  // ---- Python (openai SDK) ----
  if (tab === "python") {
    if (mode === "stream") {
      return `# pip install openai
from openai import OpenAI

# Drop-in for OpenAI: point base_url at MiniClosedAI, use chat id as 'model'.
client = OpenAI(base_url="${base}/v1", api_key="not-required")

stream = client.chat.completions.create(
    model="${convId}",
    messages=[{"role": "user", "content": "${msg}"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)`;
    }
    return `# pip install openai
from openai import OpenAI

client = OpenAI(base_url="${base}/v1", api_key="not-required")

response = client.chat.completions.create(
    model="${convId}",
    messages=[{"role": "user", "content": "${msg}"}],
)
print(response.choices[0].message.content)`;
  }

  // ---- JavaScript (openai SDK) ----
  if (tab === "js") {
    if (mode === "stream") {
      return `// npm install openai
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${base}/v1",
  apiKey: "not-required",
});

const stream = await client.chat.completions.create({
  model: "${convId}",
  messages: [{ role: "user", content: "${msg}" }],
  stream: true,
});

for await (const chunk of stream) {
  const delta = chunk.choices[0]?.delta?.content;
  if (delta) process.stdout.write(delta);
}`;
    }
    return `// npm install openai
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${base}/v1",
  apiKey: "not-required",
});

const response = await client.chat.completions.create({
  model: "${convId}",
  messages: [{ role: "user", content: "${msg}" }],
});

console.log(response.choices[0].message.content);`;
  }
  return "";
}

const LANG_FOR_TAB = { curl: "bash", python: "python", js: "javascript" };

function paintSnippet() {
  const tab = state.activeTab;
  const mode = state.activeMode;
  const style = state.activeStyle;
  const code = buildCodeSnippet(tab, mode, style);
  els.codeSnippet.textContent = code;
  els.codeSnippet.removeAttribute("data-highlighted");
  els.codeSnippet.className = "hljs language-" + (LANG_FOR_TAB[tab] || "plaintext");
  if (window.hljs && typeof hljs.highlightElement === "function") {
    try { hljs.highlightElement(els.codeSnippet); } catch (_) {}
  }
}

async function openModal() {
  // Make sure the server's saved config matches the sidebar before the user
  // copies a snippet that hits the conversation endpoint. Without this, a
  // pending 350ms debounce could leave the server on stale params.
  await flushPendingSave();
  paintSnippet();
  els.modalBackdrop.classList.remove("hidden");
}
function closeModal() { els.modalBackdrop.classList.add("hidden"); }

function bindModal() {
  els.apiCodeBtn.addEventListener("click", openModal);
  els.modalClose.addEventListener("click", closeModal);
  els.modalBackdrop.addEventListener("click", e => { if (e.target === els.modalBackdrop) closeModal(); });
  els.langTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      els.langTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.activeTab = tab.dataset.tab;
      paintSnippet();
    });
  });
  els.modeTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      els.modeTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.activeMode = tab.dataset.mode;
      paintSnippet();
    });
  });
  els.styleTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      els.styleTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.activeStyle = tab.dataset.style;
      paintSnippet();
    });
  });
  els.copyCode.addEventListener("click", async () => {
    const text = els.codeSnippet.textContent;
    const ok = await copyToClipboard(text);
    els.copyCode.textContent = ok ? "Copied!" : "Press Ctrl+C";
    if (ok) {
      setTimeout(() => { els.copyCode.textContent = "Copy"; }, 1200);
    } else {
      // Select the code so the user can hit Ctrl+C themselves.
      const range = document.createRange();
      range.selectNodeContents(els.codeSnippet);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      setTimeout(() => { els.copyCode.textContent = "Copy"; }, 2500);
    }
  });
}

async function copyToClipboard(text) {
  // Modern API — only works in secure contexts (HTTPS or localhost).
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) { /* fall through */ }
  }
  // Legacy fallback for plain-HTTP LAN access.
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (_) {
    return false;
  }
}

// ---------- Wire up ----------
function bindChat() {
  els.form.addEventListener("submit", e => {
    e.preventDefault();
    const text = els.input.value;
    els.input.value = "";
    sendMessage(text);
  });
  els.input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      els.form.requestSubmit();
    }
  });
  els.newChatBtn.addEventListener("click", newConversation);
  els.clearChatBtn.addEventListener("click", clearCurrentConversation);
  els.downloadCsvBtn.addEventListener("click", downloadCurrentConversationCsv);
  els.deleteChatBtn.addEventListener("click", deleteCurrentConversation);
  els.stopBtn.addEventListener("click", () => {
    if (state.abortController) state.abortController.abort();
  });
  els.convSelect.addEventListener("change", e => {
    const id = e.target.value;
    if (id) openConversation(parseInt(id, 10));
  });
}

async function clearCurrentConversation() {
  if (!state.conversationId) {
    // Nothing persisted yet — just wipe the in-memory list.
    state.messages = [];
    renderMessages();
    return;
  }
  if (!confirm("Clear all messages in this conversation? (keeps the model + system prompt)")) return;
  const r = await fetch(`/api/conversations/${state.conversationId}/clear`, { method: "POST" });
  if (!r.ok) { alert("Failed to clear conversation."); return; }
  state.messages = [];
  renderMessages();
  els.input.focus();
}

async function downloadCurrentConversationCsv() {
  if (!state.conversationId) {
    alert("Save at least one exchange to this conversation before exporting.");
    return;
  }
  // Just trigger a navigation — the endpoint returns
  // Content-Disposition: attachment so the browser saves it as <title>.csv.
  const a = document.createElement("a");
  a.href = `/api/conversations/${state.conversationId}/export.csv`;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function deleteCurrentConversation() {
  if (!state.conversationId) return;
  if (!confirm("Delete this conversation entirely? This cannot be undone.")) return;
  const r = await fetch(`/api/conversations/${state.conversationId}`, { method: "DELETE" });
  if (!r.ok) { alert("Failed to delete conversation."); return; }
  state.conversationId = null;
  state.messages = [];
  renderMessages();
  const list = await loadConversations();
  if (list.length) await openConversation(list[0].id);
}

// ---------- Sidebar splitter ----------
const SIDEBAR_DEFAULT = 300;
const SIDEBAR_MIN = 220;
const SIDEBAR_KEY = "miniclosedai:sidebarWidth";

function sidebarMax() {
  return Math.max(SIDEBAR_MIN, Math.min(window.innerWidth * 0.7, 900));
}
function setSidebarWidth(px) {
  const clamped = Math.round(Math.max(SIDEBAR_MIN, Math.min(sidebarMax(), px)));
  els.layout.style.setProperty("--sidebar-width", clamped + "px");
  return clamped;
}
function initSplitter() {
  const saved = parseInt(localStorage.getItem(SIDEBAR_KEY), 10);
  if (Number.isFinite(saved) && saved > 0) setSidebarWidth(saved);

  let dragging = false;
  els.splitter.addEventListener("pointerdown", e => {
    dragging = true;
    els.splitter.classList.add("dragging");
    els.splitter.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  els.splitter.addEventListener("pointermove", e => {
    if (!dragging) return;
    const rect = els.layout.getBoundingClientRect();
    setSidebarWidth(e.clientX - rect.left);
  });
  const end = e => {
    if (!dragging) return;
    dragging = false;
    els.splitter.classList.remove("dragging");
    try { els.splitter.releasePointerCapture(e.pointerId); } catch {}
    const current = parseInt(getComputedStyle(els.layout).getPropertyValue("--sidebar-width"), 10);
    if (Number.isFinite(current)) localStorage.setItem(SIDEBAR_KEY, String(current));
  };
  els.splitter.addEventListener("pointerup", end);
  els.splitter.addEventListener("pointercancel", end);

  // Double-click restores default width.
  els.splitter.addEventListener("dblclick", () => {
    setSidebarWidth(SIDEBAR_DEFAULT);
    localStorage.removeItem(SIDEBAR_KEY);
  });

  // Keep within bounds on window resize.
  window.addEventListener("resize", () => {
    const w = parseInt(getComputedStyle(els.layout).getPropertyValue("--sidebar-width"), 10);
    if (Number.isFinite(w)) setSidebarWidth(w);
  });
}

// ---------- Horizontal splitter (System Prompt height) ----------
const SYS_PROMPT_DEFAULT = 220;
const SYS_PROMPT_MIN = 80;
const SYS_PROMPT_KEY = "miniclosedai:sysPromptHeight";

function sysPromptMax() {
  // Sidebar scrolls now — be generous. Leave a small margin so there's
  // always a visible drag handle and a peek of the next panel.
  const sidebarH = els.sidebar.getBoundingClientRect().height;
  return Math.max(400, sidebarH - 60);
}
function setSysPromptHeight(px) {
  const clamped = Math.round(Math.max(SYS_PROMPT_MIN, Math.min(sysPromptMax(), px)));
  els.sidebar.style.setProperty("--sys-prompt-height", clamped + "px");
  return clamped;
}
function initHSplitter() {
  const saved = parseInt(localStorage.getItem(SYS_PROMPT_KEY), 10);
  if (Number.isFinite(saved) && saved > 0) setSysPromptHeight(saved);

  let dragging = false;
  els.hSplitter.addEventListener("pointerdown", e => {
    dragging = true;
    els.hSplitter.classList.add("dragging");
    els.hSplitter.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  els.hSplitter.addEventListener("pointermove", e => {
    if (!dragging) return;
    const rect = els.sysPromptPanel.getBoundingClientRect();
    setSysPromptHeight(e.clientY - rect.top);
  });
  const end = e => {
    if (!dragging) return;
    dragging = false;
    els.hSplitter.classList.remove("dragging");
    try { els.hSplitter.releasePointerCapture(e.pointerId); } catch {}
    const h = parseInt(getComputedStyle(els.sidebar).getPropertyValue("--sys-prompt-height"), 10);
    if (Number.isFinite(h)) localStorage.setItem(SYS_PROMPT_KEY, String(h));
  };
  els.hSplitter.addEventListener("pointerup", end);
  els.hSplitter.addEventListener("pointercancel", end);

  els.hSplitter.addEventListener("dblclick", () => {
    setSysPromptHeight(SYS_PROMPT_DEFAULT);
    localStorage.removeItem(SYS_PROMPT_KEY);
  });

  window.addEventListener("resize", () => {
    const h = parseInt(getComputedStyle(els.sidebar).getPropertyValue("--sys-prompt-height"), 10);
    if (Number.isFinite(h)) setSysPromptHeight(h);
  });
}

// ---------- Theme (Light / Dark / System) ----------
const THEME_KEY = "miniclosedai:theme";
const THEME_ORDER = ["system", "light", "dark"];

function resolvedTheme(choice) {
  if (choice === "dark") return "dark";
  if (choice === "light") return "light";
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(choice) {
  const effective = resolvedTheme(choice);
  document.documentElement.classList.toggle("dark", effective === "dark");
  // Swap icon to reflect the user's *choice* (not the resolved value).
  els.themeIconLight.style.display = choice === "light" ? "" : "none";
  els.themeIconDark.style.display = choice === "dark" ? "" : "none";
  els.themeIconSystem.style.display = choice === "system" ? "" : "none";
  els.themeToggle.title = `Theme: ${choice} (click to cycle)`;
}

function initTheme() {
  let choice = localStorage.getItem(THEME_KEY);
  if (!THEME_ORDER.includes(choice)) choice = "system";
  applyTheme(choice);

  els.themeToggle.addEventListener("click", () => {
    const current = localStorage.getItem(THEME_KEY) || "system";
    const next = THEME_ORDER[(THEME_ORDER.indexOf(current) + 1) % THEME_ORDER.length];
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  });

  // React to OS theme changes while in "system" mode.
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const current = localStorage.getItem(THEME_KEY) || "system";
    if (current === "system") applyTheme("system");
  });
}

// ---------- Sidebar collapse ----------
const SIDEBAR_COLLAPSED_KEY = "miniclosedai:sidebarCollapsed";

function applySidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  els.sidebarToggle.title = collapsed ? "Show sidebar" : "Hide sidebar";
  els.sidebarToggle.setAttribute("aria-label", collapsed ? "Show sidebar" : "Hide sidebar");
}

function initSidebarToggle() {
  const saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  applySidebarCollapsed(saved);
  els.sidebarToggle.addEventListener("click", () => {
    const now = !document.body.classList.contains("sidebar-collapsed");
    applySidebarCollapsed(now);
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, now);
  });
}

// ---------- Suggestion chips (empty state) — delegated so re-renders work ----------
function initSuggestionChips() {
  els.messages.addEventListener("click", e => {
    // The lite-mode no-backends empty state has a CTA that flips to Settings.
    const cta = e.target.closest('[data-action="open-settings"]');
    if (cta) {
      e.preventDefault();
      applyActivePage("settings");
      return;
    }
    const chip = e.target.closest(".chip[data-prompt]");
    if (!chip) return;
    els.input.value = chip.dataset.prompt;
    els.input.focus();
    autoGrowInput();
  });
}

// Auto-grow the composer textarea up to its max-height.
function autoGrowInput() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(200, els.input.scrollHeight) + "px";
}

// =====================================================================
// Settings page — LLM endpoint CRUD
// =====================================================================

// Fetched on settings open + refreshed after any CRUD action. The Dashboard's
// aggregated-model loader reads /api/models separately, so this cache is
// settings-page local.
let backendCache = [];

// Tracks which backend the modal is editing. null → creating a new one.
let backendModalEditingId = null;

const BACKEND_KIND_LABEL = { ollama: "Ollama", openai: "OpenAI-compat" };
const BACKEND_URL_PLACEHOLDER = {
  ollama: "http://localhost:11434",
  openai: "http://localhost:1234/v1",
};

async function loadBackends() {
  try {
    const r = await fetch("/api/backends");
    backendCache = await r.json();
  } catch {
    backendCache = [];
  }
  return backendCache;
}

function _backendStatusDot(running, enabled, hadErr) {
  if (!enabled) return "warn";
  if (hadErr) return "err";
  if (running) return "ok";
  return "err";
}

function _renderBackendCard(b) {
  const card = document.createElement("div");
  card.className = "backend-card";
  card.dataset.backendId = b.id;

  const top = document.createElement("div");
  top.className = "backend-card-top";

  const meta = document.createElement("div");
  meta.className = "backend-meta";

  const titleRow = document.createElement("div");
  titleRow.className = "backend-title-row";

  const name = document.createElement("span");
  name.className = "backend-name";
  name.textContent = b.name;
  titleRow.appendChild(name);

  const kindBadge = document.createElement("span");
  kindBadge.className = "backend-kind-badge";
  kindBadge.textContent = BACKEND_KIND_LABEL[b.kind] || b.kind;
  titleRow.appendChild(kindBadge);

  if (b.is_builtin) {
    const badge = document.createElement("span");
    badge.className = "backend-kind-badge backend-builtin-badge";
    badge.textContent = "Built-in";
    titleRow.appendChild(badge);
  }
  if (b.api_key_set) {
    const badge = document.createElement("span");
    badge.className = "backend-kind-badge";
    badge.textContent = "Key set";
    titleRow.appendChild(badge);
  }
  if (!b.enabled) {
    const badge = document.createElement("span");
    badge.className = "backend-kind-badge";
    badge.textContent = "Disabled";
    titleRow.appendChild(badge);
  }
  meta.appendChild(titleRow);

  const url = document.createElement("div");
  url.className = "backend-url";
  url.textContent = b.base_url;
  meta.appendChild(url);

  const status = document.createElement("div");
  status.className = "backend-status";
  status.innerHTML = `<span class="status-dot"></span><span class="status-text">checking…</span>`;
  meta.appendChild(status);

  top.appendChild(meta);

  const actions = document.createElement("div");
  actions.className = "backend-actions";

  const editBtn = document.createElement("button");
  editBtn.className = "btn btn-small";
  editBtn.textContent = "Edit";
  editBtn.addEventListener("click", () => openBackendModalForEdit(b));
  actions.appendChild(editBtn);

  if (!b.is_builtin) {
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "btn btn-small";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", () => deleteBackend(b));
    actions.appendChild(deleteBtn);
  }

  top.appendChild(actions);
  card.appendChild(top);

  if (b.kind === "ollama" && b.enabled && _ollamaAllowsPull(b)) {
    card.appendChild(_renderPullSection(b));
  }
  return card;
}

// Pull only makes sense on Ollama instances you control — typically localhost
// or a machine on your LAN. Public-hostname Ollama backends (e.g. an
// authenticating relay like app.interdataresearch.com) generally forward
// `/api/chat` but reject `/api/pull`, since they don't let you write models
// onto someone else's disk. Hide the download UI in that case.
function _ollamaAllowsPull(b) {
  let host;
  try { host = new URL(b.base_url).hostname; } catch { return false; }
  if (host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0") return true;
  if (/^10\./.test(host)) return true;                               // 10.0.0.0/8
  if (/^192\.168\./.test(host)) return true;                         // 192.168.0.0/16
  if (/^172\.(1[6-9]|2\d|3[0-1])\./.test(host)) return true;         // 172.16.0.0/12
  return false;  // public hostname / IP — assume no pull capability
}

function _renderPullSection(b) {
  const wrap = document.createElement("div");
  wrap.className = "backend-pull";
  wrap.dataset.backendId = b.id;

  const form = document.createElement("form");
  form.className = "backend-pull-form";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "e.g. qwen3:30b";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.required = true;
  form.appendChild(input);

  const btn = document.createElement("button");
  btn.type = "submit";
  btn.className = "btn btn-primary btn-small";
  btn.textContent = "Download";
  form.appendChild(btn);

  const err = document.createElement("div");
  err.className = "backend-pull-error";

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = input.value.trim();
    if (!name) return;
    err.textContent = "";
    btn.disabled = true;
    try {
      const res = await fetch(`/api/backends/${b.id}/pull`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      input.value = "";
      // Trigger an immediate poll so the new pull shows up without waiting.
      pollPullsNow();
    } catch (e) {
      err.textContent = String(e.message || e);
    } finally {
      btn.disabled = false;
    }
  });

  wrap.appendChild(form);
  wrap.appendChild(err);

  const list = document.createElement("div");
  list.className = "pull-list";
  list.dataset.pullListBackend = String(b.id);
  wrap.appendChild(list);

  // Initial render from current cached state.
  _renderPullList(list, b.id);
  return wrap;
}

function _formatBytes(n) {
  if (!n || n < 0) return "";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${u[i]}`;
}

function _renderPullList(listEl, backendId) {
  const all = (window.__pullsState && window.__pullsState.pulls) || [];
  const mine = all.filter(p => p.backend_id === backendId);
  listEl.innerHTML = "";
  for (const p of mine) {
    listEl.appendChild(_renderPullItem(p));
  }
}

function _renderPullItem(p) {
  const item = document.createElement("div");
  item.className = "pull-item";

  const row = document.createElement("div");
  row.className = "pull-item-row";

  const inFlight = !p.done;
  if (inFlight) {
    const spin = document.createElement("div");
    spin.className = "pull-spinner";
    row.appendChild(spin);
  }

  const name = document.createElement("span");
  name.className = "pull-name";
  name.textContent = p.name;
  row.appendChild(name);

  const status = document.createElement("span");
  status.className = "pull-status";
  if (p.error && p.status === "cancelled") {
    status.textContent = "cancelled";
  } else if (p.error) {
    status.classList.add("error");
    status.textContent = p.error;
  } else if (p.done) {
    status.classList.add("success");
    status.textContent = "downloaded";
  } else if (p.total && p.completed) {
    const pct = Math.floor((p.completed / p.total) * 100);
    status.textContent = `${p.status} · ${_formatBytes(p.completed)} / ${_formatBytes(p.total)} · ${pct}%`;
  } else {
    status.textContent = p.status || "starting";
  }
  row.appendChild(status);

  const cancelBtn = document.createElement("button");
  cancelBtn.className = "btn btn-small";
  cancelBtn.type = "button";
  cancelBtn.textContent = inFlight ? "Cancel" : "Dismiss";
  cancelBtn.addEventListener("click", async () => {
    cancelBtn.disabled = true;
    try {
      await fetch(
        `/api/backends/${p.backend_id}/pulls/${encodeURIComponent(p.name)}`,
        { method: "DELETE" }
      );
      pollPullsNow();
    } catch {
      cancelBtn.disabled = false;
    }
  });
  row.appendChild(cancelBtn);

  item.appendChild(row);

  // Progress bar
  const bar = document.createElement("div");
  bar.className = "pull-bar";
  const fill = document.createElement("div");
  fill.className = "pull-bar-fill";
  if (p.error && p.status !== "cancelled") {
    fill.classList.add("error");
    fill.style.width = "100%";
  } else if (p.done && !p.error) {
    fill.classList.add("success");
    fill.style.width = "100%";
  } else if (p.total && p.completed) {
    fill.style.width = `${Math.min(100, (p.completed / p.total) * 100)}%`;
  } else if (inFlight) {
    fill.classList.add("indeterminate");
  }
  bar.appendChild(fill);
  item.appendChild(bar);

  return item;
}

async function _pollBackendStatus(backendId, cardEl) {
  try {
    const [statusRes, modelsRes] = await Promise.all([
      fetch(`/api/backends/${backendId}/status`).then(r => r.json()),
      fetch(`/api/backends/${backendId}/models`).then(r => r.json()),
    ]);
    const dot = cardEl.querySelector(".status-dot");
    const text = cardEl.querySelector(".status-text");
    const kind = _backendStatusDot(statusRes.running, statusRes.enabled, false);
    dot.className = "status-dot " + kind;
    const count = (modelsRes.models || []).length;
    if (!statusRes.enabled) {
      text.textContent = "Disabled";
    } else if (statusRes.running) {
      text.textContent = `Reachable · ${count} model${count === 1 ? "" : "s"}`;
    } else {
      text.textContent = `Unreachable at ${statusRes.base_url}`;
    }
  } catch {
    const dot = cardEl.querySelector(".status-dot");
    const text = cardEl.querySelector(".status-text");
    dot.className = "status-dot err";
    text.textContent = "Status check failed";
  }
}

async function renderSettingsPage() {
  const list = document.getElementById("backend-list");
  if (!list) return;
  list.innerHTML = "";
  await loadBackends();
  if (!backendCache.length) {
    const empty = document.createElement("p");
    empty.className = "settings-hint";
    empty.textContent = "No endpoints registered. Add your first one →";
    list.appendChild(empty);
    return;
  }
  for (const b of backendCache) {
    const card = _renderBackendCard(b);
    list.appendChild(card);
    _pollBackendStatus(b.id, card);
  }
}

// --------- Add/Edit modal ---------

function _fillBackendForm(b) {
  document.getElementById("backend-name").value = b ? b.name : "";
  document.getElementById("backend-kind").value = b ? b.kind : "openai";
  document.getElementById("backend-base-url").value = b ? b.base_url : "";
  document.getElementById("backend-base-url").placeholder = BACKEND_URL_PLACEHOLDER[(b && b.kind) || "openai"];

  // Never echo the saved key back into the DOM. When editing a backend that
  // already has one, the placeholder signals that blank = keep-current.
  const apiKeyEl = document.getElementById("backend-api-key");
  apiKeyEl.value = "";
  apiKeyEl.placeholder = (b && b.api_key_set)
    ? "•••••••• (leave blank to keep current key)"
    : "leave blank for local servers";

  document.getElementById("backend-headers").value = b && b.headers && Object.keys(b.headers).length
    ? JSON.stringify(b.headers, null, 2) : "";
  document.getElementById("backend-test-result").textContent = "";
  document.getElementById("backend-headers-error").textContent = "";
}

function openBackendModalForCreate() {
  backendModalEditingId = null;
  document.getElementById("backend-modal-title").textContent = "Add endpoint";
  _fillBackendForm(null);
  // Default to OpenAI-compat for new entries (Ollama's already built-in).
  document.getElementById("backend-kind").value = "openai";
  document.getElementById("backend-kind").disabled = false;
  document.getElementById("backend-base-url").placeholder = BACKEND_URL_PLACEHOLDER.openai;
  document.getElementById("backend-modal-backdrop").classList.remove("hidden");
  document.getElementById("backend-name").focus();
}

function openBackendModalForEdit(b) {
  backendModalEditingId = b.id;
  document.getElementById("backend-modal-title").textContent = `Edit ${b.name}`;
  _fillBackendForm(b);
  // kind is immutable on update.
  document.getElementById("backend-kind").disabled = true;
  document.getElementById("backend-modal-backdrop").classList.remove("hidden");
  document.getElementById("backend-name").focus();
}

function closeBackendModal() {
  document.getElementById("backend-modal-backdrop").classList.add("hidden");
}

function _readBackendForm() {
  const name = document.getElementById("backend-name").value.trim();
  const kind = document.getElementById("backend-kind").value;
  const base_url = document.getElementById("backend-base-url").value.trim().replace(/\/+$/, "");
  const api_key = document.getElementById("backend-api-key").value;
  const headersRaw = document.getElementById("backend-headers").value.trim();
  const headersErrEl = document.getElementById("backend-headers-error");
  headersErrEl.textContent = "";
  let headers = {};
  if (headersRaw) {
    try {
      headers = JSON.parse(headersRaw);
      if (headers === null || typeof headers !== "object" || Array.isArray(headers)) {
        throw new Error("Must be a JSON object");
      }
    } catch (e) {
      headersErrEl.textContent = "Invalid JSON: " + e.message;
      return null;
    }
  }
  return { name, kind, base_url, api_key: api_key || null, headers };
}

async function saveBackend() {
  const data = _readBackendForm();
  if (!data) return;
  if (!data.name || !data.base_url) return;

  // Soft guard: for OpenAI-compat URLs missing a /vN suffix, probe before
  // saving. If 0 models come back, ask the user to confirm — otherwise the
  // saved endpoint quietly contributes no models to the Dashboard dropdown.
  if (data.kind === "openai" && !/\/v\d+\/?$/.test(data.base_url)) {
    try {
      const probe = await fetch("/api/backends/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: data.name || "draft",
          kind: data.kind,
          base_url: data.base_url,
          api_key: data.api_key || null,
          headers: data.headers || {},
        }),
      }).then(r => r.json()).catch(() => ({ running: false }));
      if (probe.running && (probe.models_count || 0) === 0) {
        const ok = confirm(
          `The URL ${data.base_url} reached the server but returned 0 models.\n\n` +
          `Most OpenAI-compatible servers (LM Studio, vLLM, OpenAI) need a '/v1' suffix. ` +
          `Try '${data.base_url.replace(/\/+$/,'')}/v1' first?\n\n` +
          `OK = let me fix the URL   |   Cancel = save anyway (0 models)`
        );
        if (ok) return;   // user wants to edit — leave the modal open
      }
    } catch { /* probe is advisory only; don't block save if it fails */ }
  }

  try {
    if (backendModalEditingId == null) {
      await fetch("/api/backends", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }).then(_throwIfNotOk);
    } else {
      const { kind, ...patch } = data;
      if (!patch.api_key) delete patch.api_key;
      await fetch(`/api/backends/${backendModalEditingId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }).then(_throwIfNotOk);
    }
    closeBackendModal();
    await renderSettingsPage();
    if (typeof loadModels === "function") await loadModels();
  } catch (e) {
    alert("Save failed: " + (e && e.message || e));
  }
}

async function deleteBackend(b) {
  if (!confirm(`Delete endpoint "${b.name}"?`)) return;
  try {
    const r = await fetch(`/api/backends/${b.id}`, { method: "DELETE" });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      const msg = (body.detail && body.detail.message) || body.detail || `HTTP ${r.status}`;
      alert("Delete blocked: " + msg);
      return;
    }
    await renderSettingsPage();
    if (typeof loadModels === "function") await loadModels();
  } catch (e) {
    alert("Delete failed: " + e.message);
  }
}

async function testBackendConnection() {
  const resultEl = document.getElementById("backend-test-result");
  resultEl.textContent = "Testing…";
  const data = _readBackendForm();
  if (!data) { resultEl.textContent = ""; return; }

  // Soft hint: OpenAI-compat URLs nearly always end in /v1. Warn but don't
  // block — occasionally people run a proxy that mounts /v2 or /openai.
  let hint = "";
  if (data.kind === "openai" && !/\/v\d+\/?$/.test(data.base_url)) {
    hint = "  (Hint: URL usually ends in '/v1'.)";
  }

  // Always probe through our server. Cross-origin direct fetches from the
  // browser to LM Studio / vLLM / etc. get CORS-blocked and surface as the
  // unhelpful "Failed to fetch" error. The server has no such restriction.
  //
  // Edit-mode gotcha: the api_key field is intentionally blanked when a
  // backend is opened for edit, so the user's saved secret doesn't echo
  // into the DOM. When they hit Test without re-typing the key, we tell
  // the server to substitute the saved one for this probe only.
  const reqBody = {
    name: data.name || "draft",
    kind: data.kind,
    base_url: data.base_url,
    api_key: data.api_key || null,
    headers: data.headers || {},
  };
  if (!reqBody.api_key && backendModalEditingId != null) {
    reqBody.use_saved_key_from = backendModalEditingId;
  }
  try {
    const r = await fetch("/api/backends/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reqBody),
    });
    const result = await r.json().catch(() => ({}));
    if (r.ok && result.running) {
      resultEl.textContent = "✓ " + (result.message || "Reachable");
    } else {
      resultEl.textContent = "✗ " + (result.message || `HTTP ${r.status}`) + hint;
    }
  } catch (e) {
    resultEl.textContent = "✗ " + (e && e.message || e) + hint;
  }
}

async function _throwIfNotOk(r) {
  if (r.ok) return r;
  const body = await r.json().catch(() => ({}));
  const msg = (body.detail && body.detail.message) || body.detail || `HTTP ${r.status}`;
  throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
}

function initBackendsUI() {
  document.getElementById("add-backend-btn").addEventListener("click", openBackendModalForCreate);
  document.getElementById("backend-modal-close").addEventListener("click", closeBackendModal);
  document.getElementById("backend-cancel-btn").addEventListener("click", closeBackendModal);
  document.getElementById("backend-modal-backdrop").addEventListener("click", e => {
    if (e.target.id === "backend-modal-backdrop") closeBackendModal();
  });
  document.getElementById("backend-kind").addEventListener("change", e => {
    document.getElementById("backend-base-url").placeholder =
      BACKEND_URL_PLACEHOLDER[e.target.value] || "";
  });
  document.getElementById("backend-test-btn").addEventListener("click", testBackendConnection);
  document.getElementById("backend-form").addEventListener("submit", e => {
    e.preventDefault();
    saveBackend();
  });
}

// ---------- Page routing (activity bar) ----------
// Purely CSS-driven — flipping body[data-page] hides/shows .page-* containers
// without unmounting anything. Chat streams keep running across switches.
const ACTIVE_PAGE_KEY = "miniclosedai:activePage";

function applyActivePage(page) {
  const p = (page === "settings") ? "settings" : "dashboard";
  document.body.dataset.page = p;
  document.querySelectorAll(".activity-bar .nav-item").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.page === p);
  });
  try { localStorage.setItem(ACTIVE_PAGE_KEY, p); } catch (_) {}
  if (p === "settings" && typeof renderSettingsPage === "function") {
    renderSettingsPage();
  }
}

function initActivityBar() {
  document.querySelectorAll(".activity-bar .nav-item").forEach(btn => {
    btn.addEventListener("click", () => applyActivePage(btn.dataset.page));
  });
  const saved = (() => { try { return localStorage.getItem(ACTIVE_PAGE_KEY); } catch { return null; } })();
  applyActivePage(saved || "dashboard");
}

// ---------- Pull poller ----------
// Runs once at app load. Polls /api/pulls every second, mirrors the result
// onto window.__pullsState, and re-renders any visible pull lists. Also
// detects done-transitions so the dashboard model dropdown can refresh once
// the new model finishes downloading.

window.__pullsState = { pulls: [] };
let _pullPollTimer = null;
let _pullPollInFlight = false;
const _seenDonePulls = new Set();

async function _pollPullsOnce() {
  if (_pullPollInFlight) return;
  _pullPollInFlight = true;
  try {
    const r = await fetch("/api/pulls");
    if (!r.ok) return;
    const data = await r.json();
    const prev = window.__pullsState.pulls || [];
    window.__pullsState = data;

    // Re-render any pull lists currently in the DOM.
    document.querySelectorAll("[data-pull-list-backend]").forEach(el => {
      const bid = parseInt(el.dataset.pullListBackend, 10);
      if (!Number.isNaN(bid)) _renderPullList(el, bid);
    });

    // Detect newly-done pulls so we can refresh the dashboard model list once.
    let modelsNeedRefresh = false;
    for (const p of data.pulls || []) {
      if (p.done && !p.error && !_seenDonePulls.has(p.key)) {
        _seenDonePulls.add(p.key);
        modelsNeedRefresh = true;
      }
    }
    // Also keep _seenDonePulls from growing forever — drop entries that have
    // since been dismissed from the registry.
    const liveKeys = new Set((data.pulls || []).map(p => p.key));
    for (const k of [..._seenDonePulls]) {
      if (!liveKeys.has(k)) _seenDonePulls.delete(k);
    }

    if (modelsNeedRefresh && typeof loadModels === "function") {
      loadModels().catch(() => {});
    }

    // Suppress unused-var warning in linters that care.
    void prev;
  } catch {
    // swallow — next tick retries
  } finally {
    _pullPollInFlight = false;
  }
}

function pollPullsNow() {
  _pollPullsOnce();
}

function startPullPoller() {
  if (_pullPollTimer) return;
  _pollPullsOnce();
  _pullPollTimer = setInterval(_pollPullsOnce, 1000);
}

async function init() {
  initTheme();
  initSidebarToggle();
  initActivityBar();
  loadSettings();
  bindParamDisplay();
  bindChat();
  bindAttachments();
  bindModal();
  initSplitter();
  initHSplitter();
  initSuggestionChips();
  if (typeof initBackendsUI === "function") initBackendsUI();
  startPullPoller();
  els.input.addEventListener("input", autoGrowInput);
  await loadModels();
  await loadConversations();

  // Auto-open most recent conversation if any
  const list = await (await fetch("/api/conversations")).json();
  if (list.length) await openConversation(list[0].id);
}

init();

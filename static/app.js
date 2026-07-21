// MiniClosedAI frontend — vanilla JS.

const els = {
  modelSelect: document.getElementById("model-select"),
  modelPicker: document.getElementById("model-picker"),
  modelPickerBtn: document.getElementById("model-picker-btn"),
  modelPickerLabel: document.getElementById("model-picker-label"),
  modelPickerPop: document.getElementById("model-picker-pop"),
  modelPickerSearch: document.getElementById("model-picker-search"),
  modelPickerList: document.getElementById("model-picker-list"),
  modelPickerEmpty: document.getElementById("model-picker-empty"),
  // The conversation dropdown was replaced by the Bots tab + a topbar
  // breadcrumb ("← Bots / <Bot name>"). See `renderBreadcrumb()`.
  breadcrumbBack: document.getElementById("breadcrumb-back"),
  breadcrumbCurrent: document.getElementById("breadcrumb-current"),
  botsList: document.getElementById("bots-list"),
  botsFilter: document.getElementById("bots-filter"),
  botsCount: document.getElementById("bots-count"),
  botsEmpty: document.getElementById("bots-empty"),
  botsNewBtn: document.getElementById("bots-new-btn"),
  botsViewList: document.getElementById("bots-view-list"),
  botsViewGrid: document.getElementById("bots-view-grid"),
  voicePicker: document.getElementById("voice-picker"),
  voiceSelect: document.getElementById("voice-select"),
  appsViewList: document.getElementById("apps-view-list"),
  appsViewGrid: document.getElementById("apps-view-grid"),
  kbList: document.getElementById("kb-list"),
  kbEmpty: document.getElementById("kb-empty"),
  kbAddBtn: document.getElementById("kb-add-btn"),
  kbFileInput: document.getElementById("kb-file-input"),
  kbStatus: document.getElementById("kb-status"),
  mcpList: document.getElementById("mcp-list"),
  mcpEmpty: document.getElementById("mcp-empty"),
  mcpUrlInput: document.getElementById("mcp-url-input"),
  mcpAddBtn: document.getElementById("mcp-add-btn"),
  mcpStatus: document.getElementById("mcp-status"),
  botsKbFile: document.getElementById("bots-kb-file"),
  kbModalBackdrop: document.getElementById("kb-modal-backdrop"),
  kbModalBot: document.getElementById("kb-modal-bot"),
  kbModalClose: document.getElementById("kb-modal-close"),
  kbModalList: document.getElementById("kb-modal-list"),
  kbModalEmpty: document.getElementById("kb-modal-empty"),
  kbModalAdd: document.getElementById("kb-modal-add"),
  kbModalStatus: document.getElementById("kb-modal-status"),
  mcpModalBackdrop: document.getElementById("mcp-modal-backdrop"),
  mcpModalBot: document.getElementById("mcp-modal-bot"),
  mcpModalClose: document.getElementById("mcp-modal-close"),
  mcpModalList: document.getElementById("mcp-modal-list"),
  mcpModalEmpty: document.getElementById("mcp-modal-empty"),
  mcpModalUrl: document.getElementById("mcp-modal-url"),
  mcpModalAddBtn: document.getElementById("mcp-modal-add-btn"),
  mcpModalStatus: document.getElementById("mcp-modal-status"),
  newChatBtn: document.getElementById("new-chat-btn"),
  clearChatBtn: document.getElementById("clear-chat-btn"),
  downloadCsvBtn: document.getElementById("download-csv-btn"),
  deleteChatBtn: document.getElementById("delete-chat-btn"),
  apiCodeBtn: document.getElementById("api-code-btn"),
  systemPrompt: document.getElementById("system-prompt"),
  sysPromptClear: document.getElementById("sys-prompt-clear"),
  sysPromptAvatar: document.getElementById("sys-prompt-avatar"),
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
  micBtn: document.getElementById("mic-btn"),
  voiceStopBtn: document.getElementById("voice-stop-btn"),
  voicePreview: document.getElementById("voice-preview"),
  callBtn: document.getElementById("call-btn"),
  callStatus: document.getElementById("call-status"),
  attachInput: document.getElementById("attach-input"),
  attachmentList: document.getElementById("attachment-list"),
  attachmentWarning: document.getElementById("attachment-warning"),
  modalBackdrop: document.getElementById("modal-backdrop"),
  modalClose: document.getElementById("modal-close"),
  codeSnippet: document.getElementById("code-snippet"),
  copyCode: document.getElementById("copy-code"),
  copyBotId: document.getElementById("copy-bot-id"),
  modalBotId: document.getElementById("modal-bot-id"),
  langTabs: document.querySelectorAll('.tabs[data-group="lang"] .tab'),
  modeTabs: document.querySelectorAll('.tabs[data-group="mode"] .tab'),
  styleTabs: document.querySelectorAll('.tabs[data-group="style"] .tab'),
  // Evals
  evalsSummary: document.getElementById("evals-summary"),
  evalsManageBtn: document.getElementById("evals-manage-btn"),
  evalModalBackdrop: document.getElementById("eval-modal-backdrop"),
  evalModalBot: document.getElementById("eval-modal-bot"),
  evalModalClose: document.getElementById("eval-modal-close"),
  evalInput: document.getElementById("eval-input"),
  evalExpected: document.getElementById("eval-expected"),
  evalAddBtn: document.getElementById("eval-add-btn"),
  evalSeedBtn: document.getElementById("eval-seed-btn"),
  evalCsvBtn: document.getElementById("eval-csv-btn"),
  evalCsvFile: document.getElementById("eval-csv-file"),
  evalClearBtn: document.getElementById("eval-clear-btn"),
  evalList: document.getElementById("eval-list"),
  evalEmpty: document.getElementById("eval-empty"),
  evalMode: document.getElementById("eval-mode"),
  evalRunBtn: document.getElementById("eval-run-btn"),
  evalScore: document.getElementById("eval-score"),
  evalResults: document.getElementById("eval-results"),
  evalTarget: document.getElementById("eval-target"),
  evalIters: document.getElementById("eval-iters"),
  evalImproveBtn: document.getElementById("eval-improve-btn"),
  evalImproveLog: document.getElementById("eval-improve-log"),
  evalStatus: document.getElementById("eval-status"),
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
  // Where to send the user when they leave the chat (back button / Esc). Set
  // by enterChat() at the moment of entry, so opening a bot from inside an App
  // returns to that App's detail view, not the global Bots page.
  chatReturnTo: { page: "bots" },
  messages: [], // [{role, content, params?}]
  activeTab: "curl",       // "curl" | "python" | "js"
  activeMode: "stream",    // "stream" | "sync"
  activeStyle: "native",   // "native" | "openai"
  abortController: null,
  // Conv id of the in-flight stream (POST send or resumed generation). Used by
  // the Stop button to tell the server to cancel the background generation.
  streamConvId: null,
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

function _buildVoiceSettingsPatch() {
  // Only emit a voice_settings patch when the picker is actually present
  // and visible — otherwise we'd overwrite an existing setting on every save.
  if (!els.voiceSelect || !els.voicePicker || els.voicePicker.hidden) return undefined;
  const opt = els.voiceSelect.selectedOptions[0];
  if (!opt || !opt.value) return {};   // "Default voice" → clear stored setting
  // voice_id must stay the BARE id (sent verbatim to the voice server);
  // the option's value is the composite "backendId:voiceId" picker key.
  const out = { voice_id: opt.dataset.voiceId || opt.value };
  const bid = parseInt(opt.dataset.backendId, 10);
  if (Number.isFinite(bid)) out.voice_backend_id = bid;
  const lang = opt.dataset.language || "";
  if (lang) out.language = lang;
  return out;
}

function _buildConfigPatch() {
  const opt = els.modelSelect.selectedOptions[0];
  const backendId = opt && opt.dataset.backendId ? parseInt(opt.dataset.backendId, 10) : undefined;
  const voice_settings = _buildVoiceSettingsPatch();
  return {
    ...getParams(),
    model: (opt && opt.value) || undefined,
    backend_id: Number.isFinite(backendId) ? backendId : undefined,
    ...(voice_settings !== undefined ? { voice_settings } : {}),
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
  if (els.sysPromptClear) {
    els.sysPromptClear.addEventListener("click", () => {
      els.systemPrompt.value = "";
      // Reuse the existing input listeners: saveSettings + _updatePromptGenAffordance.
      els.systemPrompt.dispatchEvent(new Event("input"));
      // The debounced full-patch omits system_prompt when empty (the `|| undefined`
      // in _buildConfigPatch), so send an explicit empty prompt to persist the clear.
      if (state.conversationId) {
        fetch(`/api/conversations/${state.conversationId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ system_prompt: "" }),
        }).catch(() => {});
      }
      els.systemPrompt.focus();
    });
  }
  els.modelSelect.addEventListener("change", () => { saveSettings(); scheduleSaveToConversation(); });
  if (els.voiceSelect) {
    els.voiceSelect.addEventListener("change", () => { saveSettings(); scheduleSaveToConversation(); });
  }
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

// =====================================================================
// TTS voice picker. Strictly separate from the LLM model picker — voices
// live on a different backend kind (`kind="voice"`) and are surfaced via
// their own `/api/voices` endpoint. Hidden whenever no voice backend is
// registered (mirrors the mic-button affordance rule). Persisted per-bot
// in `voice_settings.voice_id` / `voice_settings.language` /
// `voice_settings.voice_backend_id` (which backend the voice lives on —
// voices from ALL enabled voice backends are aggregated in the picker).
// =====================================================================
const _voicesState = {
  cache: [],         // [{id, name, language, gender?, backend_id, backend_name}, ...]
  byId: new Map(),   // "backendId:voiceId" → voice. Composite key: two identical
                     // voice servers expose identical voice ids, so id alone
                     // is NOT unique across backends.
  loaded: false,
};

// Composite option key. `backend_id` may be missing on very old cached
// responses — fall back to the bare id so the picker still renders.
function _voiceKey(v) {
  return v.backend_id != null ? `${v.backend_id}:${v.id}` : String(v.id);
}

async function loadVoices() {
  if (!els.voicePicker || !els.voiceSelect) return;
  // Don't probe /api/voices unless a voice backend is actually registered.
  // Otherwise no-voice setups log a confusing (but harmless) 404 on every
  // boot. Visibility is gated on the same predicate, so skipping the fetch
  // here changes nothing the user sees — the picker stays hidden either way.
  // (Relies on loadBackends() having populated backendCache first — see init.)
  if (!_hasVoiceBackend()) {
    _voicesState.cache = [];
    _voicesState.byId.clear();
    _voicesState.loaded = true;
    _renderVoicePicker();
    return;
  }
  try {
    const r = await fetch("/api/voices");
    if (!r.ok) {
      // 404 (no voice backend) or 502 (registered but server unreachable).
      // We just empty the cache here; VISIBILITY is decided separately by
      // `_hasVoiceBackend()` against `backendCache`. So if a voice backend
      // is registered but its server is down, the picker stays visible
      // with only the "Default voice" placeholder — matches the mic and
      // call buttons, which also stay visible in that case.
      _voicesState.cache = [];
      _voicesState.byId.clear();
      _voicesState.loaded = true;
      _renderVoicePicker();
      return;
    }
    const j = await r.json();
    _voicesState.cache = Array.isArray(j.voices) ? j.voices : [];
    _voicesState.byId = new Map(_voicesState.cache.map(v => [_voiceKey(v), v]));
  } catch {
    _voicesState.cache = [];
    _voicesState.byId.clear();
  }
  _voicesState.loaded = true;
  _renderVoicePicker();
}

// True when at least one enabled `kind='voice'` backend is registered. The
// same predicate `_refreshMicAffordance()` uses to show the mic button, so
// the three voice affordances (mic, call, TTS picker) stay perfectly in
// sync: they all appear the instant a voice backend is registered in
// Settings and vanish the instant it's removed/disabled. Read-only against
// `backendCache` so there's no network round-trip — the visibility gate
// updates immediately whenever `loadBackends()` runs.
function _hasVoiceBackend() {
  return (backendCache || []).some(b => b.kind === "voice" && b.enabled);
}

// Toggle just the picker's visibility based on the registered-voice-backend
// predicate. Called from `loadBackends()` alongside the mic / call helpers,
// so Settings edits propagate without waiting for a `/api/voices` round-trip.
function _refreshVoicePickerAffordance() {
  if (!els.voicePicker) return;
  els.voicePicker.hidden = !_hasVoiceBackend();
}

function _renderVoicePicker() {
  const sel = els.voiceSelect;
  const wrap = els.voicePicker;
  if (!sel || !wrap) return;
  // Visibility tracks REGISTRATION (mirrors the mic button), NOT catalog
  // availability. If the voice server is temporarily unreachable the picker
  // still shows — populated only with the "Default voice" placeholder — so
  // the UI doesn't flap when the voice backend flaps. TTS calls will 502
  // at request time, same as the mic / call buttons.
  const visible = _hasVoiceBackend();
  wrap.hidden = !visible;
  if (!visible) return;

  // Preserve current selection across re-renders.
  const prev = sel.value;
  sel.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Default voice";
  sel.appendChild(placeholder);

  // Group by language so the dropdown is browsable when there are many.
  // With voices from MORE THAN ONE backend, group by backend+language and
  // prefix the optgroup label with the backend name so identical voices on
  // two servers are tellable apart. Single-backend installs keep the
  // language-only labels (no visual change).
  const multi = new Set(_voicesState.cache.map(v => v.backend_id)).size > 1;
  const byGroup = new Map();  // key → {label, order, voices}
  for (const v of _voicesState.cache) {
    const lang = v.language || "?";
    const key = multi ? `${v.backend_id} ${lang}` : lang;
    if (!byGroup.has(key)) {
      byGroup.set(key, {
        label: multi ? `${v.backend_name || "backend " + v.backend_id} — ${lang.toUpperCase()}` : lang.toUpperCase(),
        backendId: v.backend_id ?? 0,
        lang,
        voices: [],
      });
    }
    byGroup.get(key).voices.push(v);
  }
  // Backend id ascending (matches the server's fallback order), then
  // English first, then alphabetical — same ordering as before within
  // a single backend.
  const groups = [...byGroup.values()].sort((a, b) => {
    if (a.backendId !== b.backendId && multi) return a.backendId - b.backendId;
    if (a.lang === b.lang) return 0;
    if (a.lang === "en") return -1;
    if (b.lang === "en") return 1;
    return a.lang.localeCompare(b.lang);
  });
  for (const g of groups) {
    const grp = document.createElement("optgroup");
    grp.label = g.label;
    for (const v of g.voices) {
      const opt = document.createElement("option");
      opt.value = _voiceKey(v);
      opt.dataset.language = v.language || "";
      opt.dataset.voiceId = v.id;
      if (v.backend_id != null) opt.dataset.backendId = String(v.backend_id);
      const gender = v.gender ? ` (${v.gender})` : "";
      opt.textContent = `${v.name || v.id}${gender}`;
      grp.appendChild(opt);
    }
    sel.appendChild(grp);
  }
  // Restore previous if still valid.
  if (prev && _voicesState.byId.has(prev)) sel.value = prev;
}

function _setVoiceSelectFromConv(conv) {
  if (!els.voiceSelect || !_voicesState.loaded) return;
  const vs = (conv && conv.voice_settings) || {};
  const vid = vs.voice_id || "";
  if (!vid) { els.voiceSelect.value = ""; return; }
  // Exact match: composite backend+voice key.
  if (vs.voice_backend_id != null) {
    const key = `${vs.voice_backend_id}:${vid}`;
    els.voiceSelect.value = _voicesState.byId.has(key) ? key : "";
    return;
  }
  // Legacy settings (saved before backend tagging) carry only voice_id.
  // Match the first backend that has it — cache is in backend-id order,
  // mirroring the server's lowest-id fallback, so what we display matches
  // what TTS will actually use.
  const hit = _voicesState.cache.find(v => v.id === vid);
  els.voiceSelect.value = hit ? _voiceKey(hit) : "";
}

async function loadModels() {
  const r = await fetch("/api/models");
  const data = await r.json();
  els.modelSelect.innerHTML = "";

  const backends = data.backends || [];

  // The Bots page renders human-readable backend names (e.g. "Ollama (built-in)")
  // instead of raw backend_ids. Refresh the lookup here on every model reload
  // so newly-added endpoints are reflected next time the bots page renders.
  _botsState.backendNames = new Map(backends.map(b => [b.id, b.name]));

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
    _rebuildModelPicker();
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
  _rebuildModelPicker();
  // Refresh the (separate) voice picker on the same trigger — backends were
  // just reloaded, so the voice-backend rowset may have changed too.
  loadVoices().catch(() => {});
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
        if (typeof _syncModelPickerLabel === "function") _syncModelPickerLabel();
        return true;
      }
    }
  }
  // Fallback: match by name only, ignore backend_id
  if (bid != null) return _selectModelOption(modelName, null);
  // No match — deselect.
  els.modelSelect.selectedIndex = -1;
  if (typeof _syncModelPickerLabel === "function") _syncModelPickerLabel();
  return false;
}

function setStatus(kind, text) {
  els.statusLine.className = kind;
  els.statusLine.textContent = text;
}

// ─── Searchable model picker ────────────────────────────────────────────
// A filter layer over the (hidden) native #model-select, which stays the
// source of truth. Built from the select's optgroups/options, so it reflects
// whatever loadModels() produced. Selecting an item writes back to the select
// (via _selectModelOption) + dispatches `change` so all existing logic fires.

function _syncModelPickerLabel() {
  const sel = els.modelSelect.selectedOptions[0];
  if (els.modelPickerLabel) {
    els.modelPickerLabel.textContent = sel && sel.value ? sel.value : "Select model";
  }
  // Re-highlight the active row to match the CURRENT selection. The picker
  // list DOM is only built in _rebuildModelPicker(), so without this the row
  // marked .active stays frozen at whatever was selected when the list was
  // built — reopening it would show the previous model highlighted and the
  // newly-picked one unmarked.
  if (els.modelPickerList) {
    const curKey = sel ? `${sel.value}::${sel.dataset.backendId || ""}` : null;
    for (const item of els.modelPickerList.querySelectorAll(".model-picker-item")) {
      item.classList.toggle("active", curKey != null && item.dataset.key === curKey);
    }
  }
}

function _rebuildModelPicker() {
  if (!els.modelPickerList) return;
  els.modelPickerList.innerHTML = "";
  const current = els.modelSelect.selectedOptions[0];
  const curKey = current ? `${current.value}::${current.dataset.backendId || ""}` : null;

  for (const group of els.modelSelect.querySelectorAll("optgroup")) {
    const header = document.createElement("div");
    header.className = "model-picker-group";
    header.textContent = group.label;
    header.dataset.group = group.label.toLowerCase();
    els.modelPickerList.appendChild(header);

    for (const opt of group.querySelectorAll("option")) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "model-picker-item" + (opt.disabled ? " disabled" : "");
      item.textContent = opt.textContent;
      // Searchable haystack: model text + backend group label.
      item.dataset.search = `${opt.textContent} ${group.label}`.toLowerCase();
      item.dataset.group = group.label.toLowerCase();
      if (!opt.disabled) {
        const key = `${opt.value}::${opt.dataset.backendId || ""}`;
        item.dataset.key = key;  // lets _syncModelPickerLabel re-highlight on change
        if (key === curKey) item.classList.add("active");
        item.addEventListener("click", () => {
          _selectModelOption(opt.value, opt.dataset.backendId);
          els.modelSelect.dispatchEvent(new Event("change", { bubbles: true }));
          _syncModelPickerLabel();
          _closeModelPicker();
        });
      }
      els.modelPickerList.appendChild(item);
    }
  }
  _syncModelPickerLabel();
}

function _filterModelPicker(q) {
  q = (q || "").trim().toLowerCase();
  const items = els.modelPickerList.querySelectorAll(".model-picker-item");
  let anyVisible = false;
  items.forEach(it => {
    const show = !q || it.dataset.search.includes(q);
    it.hidden = !show;
    if (show) anyVisible = true;
  });
  // Hide a group header when none of its items are visible.
  els.modelPickerList.querySelectorAll(".model-picker-group").forEach(h => {
    let sib = h.nextElementSibling;
    let groupHasVisible = false;
    while (sib && sib.classList.contains("model-picker-item")) {
      if (!sib.hidden) { groupHasVisible = true; break; }
      sib = sib.nextElementSibling;
    }
    h.hidden = !groupHasVisible;
  });
  if (els.modelPickerEmpty) els.modelPickerEmpty.hidden = anyVisible;
  // Move the keyboard cursor to the first match (the prior one may be hidden now).
  _highlightModelItem(_modelPickerVisibleItems()[0] || null);
}

// Visible, selectable items (skips hidden + disabled) — the keyboard cursor set.
function _modelPickerVisibleItems() {
  return Array.from(
    els.modelPickerList.querySelectorAll(".model-picker-item:not([hidden]):not(.disabled)")
  );
}

function _highlightModelItem(item) {
  els.modelPickerList.querySelectorAll(".model-picker-item.highlighted")
    .forEach(el => el.classList.remove("highlighted"));
  if (item) {
    item.classList.add("highlighted");
    item.scrollIntoView({ block: "nearest" });
  }
}

function _moveModelHighlight(delta) {
  const items = _modelPickerVisibleItems();
  if (!items.length) return;
  const cur = els.modelPickerList.querySelector(".model-picker-item.highlighted");
  let idx = cur ? items.indexOf(cur) : -1;
  idx = Math.max(0, Math.min(items.length - 1, idx + delta));
  if (!cur) idx = delta > 0 ? 0 : items.length - 1;  // first ArrowDown→top, ArrowUp→bottom
  _highlightModelItem(items[idx]);
}

function _openModelPicker() {
  if (!els.modelPickerPop) return;
  els.modelPickerPop.hidden = false;
  els.modelPickerBtn.setAttribute("aria-expanded", "true");
  els.modelPickerSearch.value = "";
  _filterModelPicker("");
  els.modelPickerSearch.focus();
  // Start the keyboard cursor on the currently-selected model (if visible),
  // else the first item. _filterModelPicker already put it on the first; only
  // override when there's an active selection to land on.
  const active = els.modelPickerList.querySelector(".model-picker-item.active:not([hidden])");
  if (active) _highlightModelItem(active);
}

function _closeModelPicker() {
  if (!els.modelPickerPop) return;
  els.modelPickerPop.hidden = true;
  els.modelPickerBtn.setAttribute("aria-expanded", "false");
}

function initModelPicker() {
  if (!els.modelPickerBtn) return;
  els.modelPickerBtn.addEventListener("click", e => {
    e.stopPropagation();
    els.modelPickerPop.hidden ? _openModelPicker() : _closeModelPicker();
  });
  els.modelPickerSearch.addEventListener("input", () => _filterModelPicker(els.modelPickerSearch.value));
  els.modelPickerSearch.addEventListener("keydown", e => {
    if (e.key === "Escape") { e.preventDefault(); _closeModelPicker(); els.modelPickerBtn.focus(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); _moveModelHighlight(1); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); _moveModelHighlight(-1); return; }
    if (e.key === "Enter") {
      e.preventDefault();
      // Select the keyboard-highlighted item, falling back to the first match.
      const target = els.modelPickerList.querySelector(".model-picker-item.highlighted:not([hidden]):not(.disabled)")
        || _modelPickerVisibleItems()[0];
      if (target) target.click();
    }
  });
  // Click outside closes.
  document.addEventListener("click", e => {
    if (els.modelPickerPop.hidden) return;
    if (!els.modelPicker.contains(e.target)) _closeModelPicker();
  });
  // Keep the label in sync when the model changes programmatically (e.g.
  // opening a conversation calls _selectModelOption then dispatches change).
  els.modelSelect.addEventListener("change", _syncModelPickerLabel);
}

// ─── Bots page ───────────────────────────────────────────────
// Replaces the legacy topbar `<select id="conversation-select">` with a
// dedicated activity-bar tab that lists all saved bots with live search.
const _BOTS_VIEW_KEY = "miniclosedai:botsView";
const _botsState = {
  cache: [],               // last list returned by /api/conversations (newest first)
  filter: "",              // current search input value
  backendNames: new Map(), // backend_id → display name, populated by loadModels()
  // "list" (vertical stack) or "grid" (responsive tiles). Restored from
  // localStorage on init; toggled via the segmented control in the toolbar.
  view: (() => { try { return localStorage.getItem(_BOTS_VIEW_KEY) === "grid" ? "grid" : "list"; } catch { return "list"; } })(),
};

// Apply the current view mode to the list container + toggle buttons.
function _applyBotsView() {
  if (els.botsList) {
    els.botsList.classList.toggle("grid-view", _botsState.view === "grid");
  }
  if (els.botsViewList) {
    const isList = _botsState.view === "list";
    els.botsViewList.classList.toggle("active", isList);
    els.botsViewList.setAttribute("aria-pressed", String(isList));
  }
  if (els.botsViewGrid) {
    const isGrid = _botsState.view === "grid";
    els.botsViewGrid.classList.toggle("active", isGrid);
    els.botsViewGrid.setAttribute("aria-pressed", String(isGrid));
  }
}

function _setBotsView(view) {
  _botsState.view = view === "grid" ? "grid" : "list";
  try { localStorage.setItem(_BOTS_VIEW_KEY, _botsState.view); } catch (_) {}
  _applyBotsView();
}

// "2 hours ago", "yesterday", "just now" — matches the relative-time style
// elsewhere in the UI. Falls back to the raw ISO if anything looks off.
function _formatRelative(iso) {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diffSec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (diffSec < 45) return "just now";
  if (diffSec < 90) return "1 minute ago";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 45) return `${diffMin} minutes ago`;
  if (diffMin < 90) return "1 hour ago";
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hours ago`;
  if (diffHr < 48) return "yesterday";
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 30) return `${diffDay} days ago`;
  const diffMo = Math.round(diffDay / 30);
  if (diffMo < 12) return `${diffMo} months ago`;
  return `${Math.round(diffMo / 12)} years ago`;
}

function _backendNameOf(id) {
  if (id == null) return "(no backend)";
  return _botsState.backendNames.get(id) || `(unknown #${id})`;
}

function _botMatchesFilter(c, q) {
  if (!q) return true;
  const hay = `${c.title || ""} ${c.model || ""} ${_backendNameOf(c.backend_id)}`.toLowerCase();
  return hay.includes(q);
}

const AVATAR_DIM = 128;   // stored avatars are a small square; circles are CSS

// Little bot glyph used as the avatar fallback (lucide-style "bot": a head with
// an antenna and two eyes). Inherits the circle's white `currentColor`.
const _BOT_AVATAR_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>';

// Paint a bot's avatar into the given circle element: the uploaded image if it
// has one, else a little bot icon on a per-bot color. Reused by every re-render
// (cheap; no network).
function _renderAvatarInto(el, c) {
  el.innerHTML = "";
  el.style.removeProperty("--avatar-hue");
  if (c.avatar) {
    const img = document.createElement("img");
    img.src = c.avatar;
    img.alt = "";
    el.appendChild(img);
    el.classList.remove("is-fallback");
  } else {
    el.innerHTML = _BOT_AVATAR_SVG;
    el.classList.add("is-fallback");
    // Stable hue per bot id so the fallback color doesn't shuffle on re-render.
    el.style.setProperty("--avatar-hue", String((c.id * 47) % 360));
  }
}

// Center-crop an image file to a square and downscale to AVATAR_DIM px, returned
// as a JPEG data URL. Keeps the stored avatar a few KB regardless of the source.
async function _makeAvatarDataUrl(file) {
  const dataUrl = await _readFileAsDataUrl(file);
  const img = new Image();
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = dataUrl; });
  const side = Math.min(img.width, img.height);
  const sx = (img.width - side) / 2;
  const sy = (img.height - side) / 2;
  const canvas = document.createElement("canvas");
  canvas.width = AVATAR_DIM;
  canvas.height = AVATAR_DIM;
  canvas.getContext("2d").drawImage(img, sx, sy, side, side, 0, 0, AVATAR_DIM, AVATAR_DIM);
  return canvas.toDataURL("image/jpeg", 0.85);
}

// Shared hidden file input — open the OS picker, then upload the chosen image as
// this bot's avatar and refresh the cards.
let _avatarPickInput = null;
function _pickAvatarFor(c) {
  if (!_avatarPickInput) {
    _avatarPickInput = document.createElement("input");
    _avatarPickInput.type = "file";
    _avatarPickInput.accept = "image/*";
    _avatarPickInput.style.display = "none";
    document.body.appendChild(_avatarPickInput);
  }
  _avatarPickInput.value = "";   // allow re-picking the same file
  _avatarPickInput.onchange = async () => {
    const file = _avatarPickInput.files && _avatarPickInput.files[0];
    if (!file) return;
    try {
      const dataUrl = await _makeAvatarDataUrl(file);
      const r = await fetch(`/api/conversations/${c.id}/avatar`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ avatar: dataUrl }),
      });
      if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`));
      const hit = (_botsState.cache || []).find(x => x.id === c.id);
      if (hit) hit.avatar = dataUrl;
      renderBotsPage();
      renderSysPromptAvatar();   // keep the chat sidebar's avatar in sync
    } catch (e) {
      alert(`Avatar upload failed: ${e.message}`);
    }
  };
  _avatarPickInput.click();
}

// Mirror the open bot's avatar into the chat sidebar's System Prompt header.
// Clicking it uploads/replaces the picture, same as the Bots-page card. With no
// bot saved yet (e.g. a brand-new unsaved chat) it shows a disabled fallback.
function renderSysPromptAvatar(conv) {
  const el = els.sysPromptAvatar;
  if (!el) return;
  const c = conv || (_botsState.cache || []).find(x => x.id === state.conversationId);
  if (!c) {
    _renderAvatarInto(el, { id: 0, title: "", avatar: null });
    el.onclick = null;
    el.disabled = true;
    el.dataset.tooltip = "";
    return;
  }
  _renderAvatarInto(el, c);
  el.disabled = false;
  el.dataset.tooltip = c.avatar ? "Change avatar" : "Add avatar";
  el.onclick = e => { e.stopPropagation(); _pickAvatarFor(c); };
}

function renderBotsPage() {
  if (!els.botsList) return; // page not in DOM yet
  _applyBotsView();  // keep the grid/list class in sync on every re-render
  const q = _botsState.filter.trim().toLowerCase();
  const all = _botsState.cache || [];
  const filtered = all.filter(c => _botMatchesFilter(c, q));

  els.botsList.innerHTML = "";
  for (const c of filtered) {
    const card = document.createElement("div");
    card.className = "bot-card";
    card.dataset.convId = String(c.id);
    if (c.id === state.conversationId) card.classList.add("active");
    if (_streaming.has(c.id) || _unread.has(c.id)) card.classList.add("has-pending");
    card.tabIndex = 0;
    card.setAttribute("role", "button");

    // Circle avatar — sits left of the name in both views. Clicking it lets the
    // user upload/replace the bot's picture; with none it shows an initial.
    const avatar = document.createElement("button");
    avatar.type = "button";
    avatar.className = "bot-card-avatar";
    avatar.dataset.tooltip = c.avatar ? "Change avatar" : "Add avatar";
    avatar.setAttribute("aria-label", `${c.avatar ? "Change" : "Add"} avatar for ${c.title || "bot"}`);
    _renderAvatarInto(avatar, c);
    avatar.addEventListener("click", e => {
      e.stopPropagation();
      _pickAvatarFor(c);
    });

    const title = document.createElement("div");
    title.className = "bot-card-title";
    title.textContent = c.title || "(untitled)";

    const meta = document.createElement("div");
    meta.className = "bot-card-meta";
    const parts = [
      c.model || "(no model)",
      _backendNameOf(c.backend_id),
      _formatRelative(c.updated_at),
    ];
    parts.forEach((p, i) => {
      if (i > 0) {
        const sep = document.createElement("span");
        sep.className = "sep";
        sep.textContent = "·";
        meta.appendChild(sep);
      }
      const span = document.createElement("span");
      span.textContent = p;
      meta.appendChild(span);
    });

    const textWrap = document.createElement("div");
    textWrap.className = "bot-card-text";
    textWrap.appendChild(title);
    textWrap.appendChild(meta);

    card.appendChild(avatar);
    card.appendChild(textWrap);

    // Row actions — hidden until hover/focus. Each button stops propagation so
    // clicking it doesn't also fire the card's "open this bot" handler.
    const actions = document.createElement("div");
    actions.className = "bot-card-actions";

    const codeBtn = document.createElement("button");
    codeBtn.type = "button";
    codeBtn.className = "bot-card-action";
    codeBtn.setAttribute("aria-label", `API code for ${c.title}`);
    codeBtn.dataset.tooltip = "API code";
    codeBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>';
    codeBtn.addEventListener("click", e => {
      e.stopPropagation();
      openApiCodeForConv(c.id);
    });

    const kbBtn = document.createElement("button");
    kbBtn.type = "button";
    kbBtn.className = "bot-card-action";
    kbBtn.setAttribute("aria-label", `Manage knowledge for ${c.title}`);
    kbBtn.dataset.tooltip = "Manage knowledge";
    kbBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>';
    kbBtn.addEventListener("click", e => {
      e.stopPropagation();
      openKnowledgeModal(c.id, c.title);
    });

    const mcpBtn = document.createElement("button");
    mcpBtn.type = "button";
    mcpBtn.className = "bot-card-action";
    mcpBtn.setAttribute("aria-label", `Manage extensions for ${c.title}`);
    mcpBtn.dataset.tooltip = "Manage extensions (MCP plugins)";
    mcpBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>';
    mcpBtn.addEventListener("click", e => {
      e.stopPropagation();
      openMcpModal(c.id, c.title);
    });

    const evalBtn = document.createElement("button");
    evalBtn.type = "button";
    evalBtn.className = "bot-card-action";
    evalBtn.setAttribute("aria-label", `Evals for ${c.title}`);
    evalBtn.dataset.tooltip = "Evals — score & auto-improve";
    evalBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>';
    evalBtn.addEventListener("click", e => {
      e.stopPropagation();
      openEvalModal(c.id, c.title);
    });

    const llmBtn = document.createElement("button");
    llmBtn.type = "button";
    llmBtn.className = "bot-card-action";
    llmBtn.setAttribute("aria-label", `Change model for ${c.title}`);
    llmBtn.dataset.tooltip = "Change model";
    llmBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>';
    llmBtn.addEventListener("click", e => {
      e.stopPropagation();
      openBotModelPicker(llmBtn, c);
    });

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "bot-card-action danger";
    delBtn.setAttribute("aria-label", `Delete ${c.title}`);
    delBtn.dataset.tooltip = "Delete bot";
    delBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
    delBtn.addEventListener("click", e => {
      e.stopPropagation();
      deleteConvById(c.id, { title: c.title });
    });

    actions.appendChild(codeBtn);
    actions.appendChild(kbBtn);
    actions.appendChild(mcpBtn);
    actions.appendChild(evalBtn);
    actions.appendChild(llmBtn);
    actions.appendChild(delBtn);
    card.appendChild(actions);

    const open = () => enterChat(c.id);
    card.addEventListener("click", open);
    card.addEventListener("keydown", e => {
      // Only the card itself navigates on Enter/Space. Without this guard a
      // keypress on a focused child button (avatar, row actions) would bubble
      // up and open the bot in addition to the button's own action.
      if (e.target !== card) return;
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    });

    els.botsList.appendChild(card);
  }

  if (els.botsCount) {
    const total = all.length;
    const shown = filtered.length;
    els.botsCount.textContent = q
      ? `${shown} of ${total} bot${total === 1 ? "" : "s"}`
      : `${total} bot${total === 1 ? "" : "s"}`;
  }
  if (els.botsEmpty) {
    if (!all.length) {
      els.botsEmpty.textContent = "No bots yet. Click + New bot to create one.";
      els.botsEmpty.hidden = false;
    } else if (!filtered.length) {
      els.botsEmpty.textContent = "No bots match your filter.";
      els.botsEmpty.hidden = false;
    } else {
      els.botsEmpty.hidden = true;
    }
  }
}

// =====================================================================
// Per-card "Change model" popover (Bots page). One shared popover, anchored
// to whichever bot card's chip button opened it. Reuses the topbar model
// picker's CSS classes but is fully independent of the topbar <select> —
// picking here PATCHes the bot's {model, backend_id} and re-renders the list.
// =====================================================================
let _botModelPop = null;      // lazily created singleton
let _botModelPopOwner = null; // anchor button while open (aria bookkeeping)

function _closeBotModelPicker() {
  if (!_botModelPop || _botModelPop.hidden) return;
  _botModelPop.hidden = true;
  if (_botModelPopOwner) _botModelPopOwner.setAttribute("aria-expanded", "false");
  _botModelPopOwner = null;
}

function _ensureBotModelPop() {
  if (_botModelPop) return _botModelPop;
  const pop = document.createElement("div");
  pop.id = "bot-model-pop";
  pop.className = "model-picker-pop";
  pop.hidden = true;
  pop.innerHTML =
    '<input type="search" class="model-picker-search" placeholder="Search models…" aria-label="Search models" />' +
    '<div class="model-picker-list"></div>';
  document.body.appendChild(pop);
  _botModelPop = pop;

  // Clicks inside stay inside; any outside click closes. The opening click
  // never reaches this listener (the card handler stopPropagation()s it).
  pop.addEventListener("click", e => e.stopPropagation());
  document.addEventListener("click", e => {
    if (!pop.hidden && !pop.contains(e.target)) _closeBotModelPicker();
  });

  const search = pop.querySelector("input");
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    pop.querySelectorAll(".model-picker-item").forEach(it => {
      it.hidden = !!q && !(it.dataset.key || "").toLowerCase().includes(q);
    });
    // Hide a group header when every item under it is hidden.
    pop.querySelectorAll(".model-picker-group").forEach(g => {
      let sib = g.nextElementSibling, any = false;
      while (sib && !sib.classList.contains("model-picker-group")) {
        if (sib.classList.contains("model-picker-item") && !sib.hidden) any = true;
        sib = sib.nextElementSibling;
      }
      g.hidden = !any;
    });
  });
  search.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      // stopPropagation so the global bots hotkeys (Esc-to-bots) don't fire.
      e.preventDefault(); e.stopPropagation();
      _closeBotModelPicker();
      return;
    }
    const items = [...pop.querySelectorAll(".model-picker-item:not([hidden])")];
    if (!items.length) return;
    let idx = items.findIndex(it => it.classList.contains("highlighted"));
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      idx = e.key === "ArrowDown"
        ? Math.min(idx + 1, items.length - 1)
        : Math.max(idx - 1, 0);
      items.forEach(it => it.classList.remove("highlighted"));
      items[idx].classList.add("highlighted");
      items[idx].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      (idx >= 0 ? items[idx] : items[0]).click();
    }
  });
  return pop;
}

function _positionBotModelPop(anchorBtn) {
  const pop = _botModelPop;
  const r = anchorBtn.getBoundingClientRect();
  const w = Math.max(pop.offsetWidth, 280);
  const h = pop.offsetHeight;
  let left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8));
  // Below the button by default; flip above when it would run off-screen.
  let top = r.bottom + 4;
  if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 4);
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
}

async function openBotModelPicker(anchorBtn, conv) {
  const pop = _ensureBotModelPop();
  if (!pop.hidden && _botModelPopOwner === anchorBtn) {
    _closeBotModelPicker();   // second click on the same button toggles closed
    return;
  }
  _botModelPopOwner = anchorBtn;
  anchorBtn.setAttribute("aria-expanded", "true");
  const list = pop.querySelector(".model-picker-list");
  const search = pop.querySelector("input");
  search.value = "";
  list.innerHTML = '<div class="model-picker-empty">Loading models…</div>';
  pop.hidden = false;
  _positionBotModelPop(anchorBtn);

  let backends = [];
  try {
    const r = await fetch("/api/models");
    backends = (await r.json()).backends || [];
  } catch {
    list.innerHTML = '<div class="model-picker-empty">Could not load models</div>';
    return;
  }
  // The fetch is async — the user may have closed the pop or opened another
  // card's picker meanwhile; only render if we still own it.
  if (pop.hidden || _botModelPopOwner !== anchorBtn) return;

  list.innerHTML = "";
  let total = 0;
  for (const b of backends) {
    if (!b.enabled || !b.running || !(b.models || []).length) continue;
    const grp = document.createElement("div");
    grp.className = "model-picker-group";
    grp.textContent = b.name;
    list.appendChild(grp);
    for (const m of b.models) {
      const it = document.createElement("button");
      it.type = "button";
      it.className = "model-picker-item";
      it.dataset.key = `${m.name}::${b.id}`;
      it.textContent = m.name;
      if (conv.model === m.name && conv.backend_id === b.id) {
        it.classList.add("active");
        it.textContent = `✓ ${m.name}`;
      }
      it.addEventListener("click", () => _chooseBotModel(conv, m.name, b.id));
      list.appendChild(it);
      total++;
    }
  }
  if (!total) {
    list.innerHTML =
      '<div class="model-picker-empty">No models available — is a backend online?</div>';
  }
  _positionBotModelPop(anchorBtn);   // re-clamp now that height is real
  search.focus();
}

async function _chooseBotModel(conv, model, backendId) {
  _closeBotModelPicker();
  try {
    const r = await fetch(`/api/conversations/${conv.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, backend_id: backendId }),
    });
    if (!r.ok) {
      let detail = `HTTP ${r.status}`;
      try { detail = (await r.json()).detail || detail; } catch {}
      alert(`Could not change model: ${detail}`);
      return;
    }
    await loadConversations();   // re-renders the card meta (model · backend)
    // If this bot is the currently open chat, keep the topbar picker in sync.
    if (state.conversationId === conv.id) {
      _selectModelOption(model, String(backendId));
    }
  } catch (e) {
    alert(`Could not change model: ${e?.message || e}`);
  }
}

// Drives the topbar breadcrumb ("← Bots / <name>"). The nav-icon pulse dot
// is NOT driven from here anymore — see _refreshUnreadUI below, which lights
// the dot only when a conv has unread/streaming activity the user hasn't seen.
function renderBreadcrumb() {
  const c = _botsState.cache.find(x => x.id === state.conversationId);
  if (els.breadcrumbCurrent) {
    // Don't clobber an in-progress rename input.
    if (els.breadcrumbCurrent.querySelector("input")) return;
    if (c) {
      els.breadcrumbCurrent.textContent = c.title;
      els.breadcrumbCurrent.classList.remove("is-empty");
      els.breadcrumbCurrent.title = "Click to rename this bot";
    } else {
      els.breadcrumbCurrent.textContent = "(no bot selected)";
      els.breadcrumbCurrent.classList.add("is-empty");
      els.breadcrumbCurrent.removeAttribute("title");
    }
  }
}

// Click the topbar bot-name pill to rename the current bot inline.
// PATCH /api/conversations/{id} {title}; the backend already supports it.
function _beginRenameBot() {
  if (!state.conversationId || !els.breadcrumbCurrent) return;
  if (els.breadcrumbCurrent.querySelector("input")) return;  // already editing
  const c = _botsState.cache.find(x => x.id === state.conversationId);
  const current = c ? c.title : els.breadcrumbCurrent.textContent;

  const input = document.createElement("input");
  input.type = "text";
  input.className = "breadcrumb-rename-input";
  input.value = current;
  input.maxLength = 200;
  els.breadcrumbCurrent.textContent = "";
  els.breadcrumbCurrent.appendChild(input);
  input.focus();
  input.select();

  let settled = false;
  const finish = async (save) => {
    if (settled) return;
    settled = true;
    const name = input.value.trim();
    // Remove the input BEFORE repainting — renderBreadcrumb() skips while an
    // input is present, so it must be gone first or edit mode never exits.
    input.remove();
    if (save && name && name !== current) {
      try {
        await fetch(`/api/conversations/${state.conversationId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: name }),
        });
        await loadConversations();  // refresh cache → breadcrumb + bots list re-render
        return;
      } catch (_) { /* fall through to restore */ }
    }
    renderBreadcrumb();  // cancelled / unchanged / failed → restore label
  };
  input.addEventListener("keydown", e => {
    e.stopPropagation();  // don't trigger global Esc-to-bots / ⌘K while typing
    if (e.key === "Enter") { e.preventDefault(); finish(true); }
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("click", e => e.stopPropagation());
}

// ─── Unread / streaming indicator ───────────────────────────────────────
// Two sets drive the pulse dots:
//   _streaming — convs whose chat stream is currently in flight
//   _unread    — convs whose stream finished while the user wasn't watching
// The nav-icon dot lights when EITHER set has an entry the user isn't currently
// viewing. Bot cards get an inline dot when their id is in either set.
//
// "Currently viewing" = body[data-page="dashboard"] AND state.conversationId
// matches. Marking a conv as viewed clears it from _unread immediately.
const _streaming = new Set();
const _unread = new Set();

function _refreshUnreadUI() {
  const viewing = (document.body.dataset.page === "dashboard") ? state.conversationId : null;
  let hasAny = false;
  for (const id of _streaming) { if (id !== viewing) { hasAny = true; break; } }
  if (!hasAny) {
    for (const id of _unread) { if (id !== viewing) { hasAny = true; break; } }
  }
  document.body.dataset.hasActiveBot = hasAny ? "1" : "0";
  // Re-render the list so per-card dots stay in sync. Cheap — tens of items.
  renderBotsPage();
}

function _onStreamStart(convId) {
  if (convId == null) return;
  _unread.delete(convId);     // any prior pending state is superseded
  _streaming.add(convId);
  _refreshUnreadUI();
}

function _onStreamEnd(convId) {
  if (convId == null) return;
  _streaming.delete(convId);
  // If the user wasn't watching this conv when it finished, leave a breadcrumb
  // in _unread. If they WERE watching, no dot — they saw the reply land.
  const viewing = document.body.dataset.page === "dashboard" && state.conversationId === convId;
  if (!viewing) _unread.add(convId);
  _refreshUnreadUI();
}

function _markConvViewed(convId) {
  if (convId == null) return;
  if (_unread.delete(convId)) _refreshUnreadUI();
}

// Back-compat alias — older call sites still use the old name.
function renderTopbarBotLabel() { renderBreadcrumb(); }

function onBotsPageEntered() {
  // Re-render on entry so a bot freshly created via the dashboard's +New Chat
  // shows up the moment the user flips to the Bots tab.
  renderBotsPage();
  // Refocus the search box so ⌘K / `/` lands you immediately in filter mode.
  if (els.botsFilter && document.activeElement !== els.botsFilter) {
    // Defer so the slide animation isn't fighting an input focus scroll.
    setTimeout(() => els.botsFilter.focus({ preventScroll: true }), 60);
  }
}

// ─── In-app prompt / confirm dialogs ────────────────────────────────────
// Promise-based replacements for native prompt()/confirm(). Browsers let the
// user permanently suppress native dialogs ("prevent additional dialogs"),
// after which prompt() returns null and confirm() returns false — silently
// breaking flows like New bot and Delete. These modals can't be suppressed.
//   uiPrompt({...})  → resolves to the entered string on OK, or null on cancel
//   uiConfirm({...}) → resolves to true on OK, or false on cancel
let _uiDialogResolve = null;

function _uiDialogIsPrompt() {
  const f = document.getElementById("ui-dialog-input-field");
  return f && f.style.display !== "none";
}

function _uiDialogClose(result) {
  const backdrop = document.getElementById("ui-dialog-backdrop");
  if (backdrop) backdrop.classList.add("hidden");
  const resolve = _uiDialogResolve;
  _uiDialogResolve = null;
  if (resolve) resolve(result);
}

function _openUiDialog(opts) {
  const withInput = !!opts.withInput;
  return new Promise(resolve => {
    // Only one dialog at a time — cancel any in-flight one first.
    if (_uiDialogResolve) _uiDialogClose(withInput ? null : false);
    _uiDialogResolve = resolve;

    const $ = id => document.getElementById(id);
    $("ui-dialog-title").textContent = opts.title || "";
    const msg = $("ui-dialog-message");
    msg.textContent = opts.message || "";
    msg.style.display = opts.message ? "" : "none";

    $("ui-dialog-input-field").style.display = withInput ? "" : "none";
    const input = $("ui-dialog-input");
    if (withInput) {
      $("ui-dialog-input-label").textContent = opts.inputLabel || "Name";
      input.value = opts.value || "";
      input.placeholder = opts.placeholder || "";
    }

    const okBtn = $("ui-dialog-ok");
    okBtn.textContent = opts.okText || "OK";
    okBtn.classList.toggle("btn-danger", !!opts.danger);
    okBtn.classList.toggle("btn-primary", !opts.danger);
    $("ui-dialog-cancel").textContent = opts.cancelText || "Cancel";

    $("ui-dialog-backdrop").classList.remove("hidden");
    if (withInput) { input.focus(); input.select(); } else okBtn.focus();
  });
}

function uiPrompt(opts = {})  { return _openUiDialog({ ...opts, withInput: true }); }
function uiConfirm(opts = {}) { return _openUiDialog({ ...opts, withInput: false }); }

function initUiDialog() {
  const $ = id => document.getElementById(id);
  const backdrop = $("ui-dialog-backdrop");
  if (!backdrop) return;
  const input = $("ui-dialog-input");
  const onOk     = () => _uiDialogClose(_uiDialogIsPrompt() ? input.value.trim() : true);
  const onCancel = () => _uiDialogClose(_uiDialogIsPrompt() ? null : false);

  $("ui-dialog-ok").addEventListener("click", onOk);
  $("ui-dialog-cancel").addEventListener("click", onCancel);
  $("ui-dialog-close").addEventListener("click", onCancel);
  backdrop.addEventListener("click", e => { if (e.target === backdrop) onCancel(); });
  // Keydown on the backdrop covers both the input (prompt) and button focus
  // (confirm). stopPropagation keeps global Esc-to-bots / ⌘K from also firing.
  backdrop.addEventListener("keydown", e => {
    if (e.key === "Enter")  { e.preventDefault(); e.stopPropagation(); onOk(); }
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onCancel(); }
  });
}

function initBotsUI() {
  if (els.botsFilter) {
    els.botsFilter.addEventListener("input", () => {
      _botsState.filter = els.botsFilter.value;
      renderBotsPage();
    });
  }
  if (els.botsNewBtn) {
    els.botsNewBtn.addEventListener("click", async () => {
      // Ask for the name FIRST via an in-app dialog (not native prompt(),
      // which browsers can suppress). Cancel → create nothing and stay on the
      // Bots page. Only navigate to the chat once a bot was actually created.
      const name = await uiPrompt({
        title: "New bot",
        inputLabel: "Bot name",
        placeholder: "e.g. Support Assistant",
        okText: "Create",
      });
      if (name === null) return;  // cancelled → no bot created
      const created = await newConversation({ skipPrompt: true, title: name });
      if (created) applyActivePage("dashboard");
    });
  }
  if (els.breadcrumbBack) {
    els.breadcrumbBack.addEventListener("click", () => exitChatToReturn());
  }
  if (els.breadcrumbCurrent) {
    els.breadcrumbCurrent.addEventListener("click", () => {
      if (state.conversationId) _beginRenameBot();
    });
  }
  if (els.botsViewList) {
    els.botsViewList.addEventListener("click", () => _setBotsView("list"));
  }
  if (els.botsViewGrid) {
    els.botsViewGrid.addEventListener("click", () => _setBotsView("grid"));
  }
  // Shared hidden file input for "add knowledge" flows (card + manage modal).
  // `_kbUploadTarget` = { convId, onStatus(msg,err), onDone(added) }.
  if (els.botsKbFile) {
    els.botsKbFile.addEventListener("change", async () => {
      const t = _kbUploadTarget;
      const files = els.botsKbFile.files;
      els.botsKbFile.value = "";   // allow re-picking the same file
      if (!t || !files || !files.length) return;
      const added = await _uploadKnowledgeToConv(t.convId, files, t.onStatus);
      if (t.onDone) t.onDone(added);
    });
  }
  _applyBotsView();  // reflect the restored view on first paint
  // Global keyboard affordances — Esc exits chat, ⌘K / `/` opens the quick switcher.
  document.addEventListener("keydown", _botsHotkeyHandler);
}

// ─── Per-card quick-add actions (Knowledge + MCP, from the bots list) ────
// Equip a bot without opening it. The file picker / URL box act on the card's
// own conversation id; you never leave the list.

let _kbUploadTarget = null;  // { convId, onStatus, onDone } for the shared input

function _triggerKbUpload(target) {
  if (!els.botsKbFile) return;
  _kbUploadTarget = target;
  els.botsKbFile.click();
}

function _findBotCard(convId) {
  return els.botsList && els.botsList.querySelector(`.bot-card[data-conv-id="${convId}"]`);
}

// Transient one-line status under a card (e.g. "Added 2 to knowledge ✓").
function _botCardFlash(convId, msg, isError) {
  const card = _findBotCard(convId);
  if (!card) return;
  let flash = card.querySelector(".bot-card-flash");
  if (!flash) {
    flash = document.createElement("div");
    flash.className = "bot-card-flash";
    card.appendChild(flash);
  }
  flash.textContent = msg;
  flash.classList.toggle("is-error", !!isError);
  clearTimeout(flash._t);
  flash._t = setTimeout(() => { flash.remove(); }, 3000);
}

// ─── Manage Knowledge modal (view + add + delete a bot's documents) ─────
let _kbModalConvId = null;

function _kbModalSetStatus(msg, isError, loading) {
  if (!els.kbModalStatus) return;
  if (!msg) { els.kbModalStatus.hidden = true; els.kbModalStatus.textContent = ""; els.kbModalStatus.classList.remove("loading"); return; }
  els.kbModalStatus.hidden = false;
  els.kbModalStatus.textContent = msg;
  els.kbModalStatus.classList.toggle("kb-error", !!isError);
  els.kbModalStatus.classList.toggle("loading", !!loading);
}

function _fmtBytes(n) {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function _renderKbModalDocs(docs) {
  if (!els.kbModalList) return;
  els.kbModalList.innerHTML = "";
  const list = docs || [];
  if (els.kbModalEmpty) els.kbModalEmpty.hidden = list.length > 0;
  for (const d of list) {
    const row = document.createElement("div");
    row.className = "kb-modal-doc";

    const info = document.createElement("div");
    info.className = "kb-modal-doc-info";
    const name = document.createElement("div");
    name.className = "kb-modal-doc-name";
    name.textContent = d.filename;
    name.title = d.filename;
    const meta = document.createElement("div");
    meta.className = "kb-modal-doc-meta";
    const when = (d.created_at || "").replace("T", " ").slice(0, 16);
    meta.textContent =
      `${d.chunk_count} chunk${d.chunk_count === 1 ? "" : "s"} · ${_fmtBytes(d.char_count)}` +
      (when ? ` · ${when}` : "");
    info.appendChild(name);
    info.appendChild(meta);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "kb-modal-doc-del";
    del.title = "Delete document";
    del.setAttribute("aria-label", `Delete ${d.filename}`);
    del.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>';
    del.addEventListener("click", async () => {
      const r = await fetch(`/api/conversations/${_kbModalConvId}/knowledge/${d.id}`, { method: "DELETE" });
      if (r.ok) {
        await _loadKbModal();
        if (_kbModalConvId === state.conversationId) loadKnowledge();
      }
    });

    row.appendChild(info);
    row.appendChild(del);
    els.kbModalList.appendChild(row);
  }
}

async function _loadKbModal() {
  if (_kbModalConvId == null) return;
  try {
    const r = await fetch(`/api/conversations/${_kbModalConvId}/knowledge`);
    _renderKbModalDocs(r.ok ? ((await r.json()).documents || []) : []);
  } catch (_) {
    _renderKbModalDocs([]);
  }
}

function openKnowledgeModal(convId, title) {
  _kbModalConvId = convId;
  if (els.kbModalBot) els.kbModalBot.textContent = title ? `— ${title}` : "";
  _kbModalSetStatus("", false);
  _renderKbModalDocs([]);
  _loadKbModal();
  if (els.kbModalBackdrop) els.kbModalBackdrop.classList.remove("hidden");
}

function closeKnowledgeModal() {
  if (els.kbModalBackdrop) els.kbModalBackdrop.classList.add("hidden");
  _kbModalConvId = null;
}

function initKnowledgeModalUI() {
  if (els.kbModalClose) els.kbModalClose.addEventListener("click", closeKnowledgeModal);
  if (els.kbModalBackdrop) {
    els.kbModalBackdrop.addEventListener("click", e => {
      if (e.target === els.kbModalBackdrop) closeKnowledgeModal();
    });
  }
  if (els.kbModalAdd) {
    els.kbModalAdd.addEventListener("click", () => {
      _triggerKbUpload({
        convId: _kbModalConvId,
        onStatus: _kbModalSetStatus,
        onDone: async (added) => {
          if (added) _kbModalSetStatus(`Added ${added} document${added === 1 ? "" : "s"} ✓`, false);
          await _loadKbModal();
          if (_kbModalConvId === state.conversationId) loadKnowledge();
        },
      });
    });
  }
}

// ─── Manage Extensions modal (view + toggle + remove + add MCP plugins) ──
let _mcpModalConvId = null;
let _mcpModalServers = [];

function _mcpModalSetStatus(msg, isError) {
  if (!els.mcpModalStatus) return;
  if (!msg) { els.mcpModalStatus.hidden = true; els.mcpModalStatus.textContent = ""; return; }
  els.mcpModalStatus.hidden = false;
  els.mcpModalStatus.textContent = msg;
  els.mcpModalStatus.classList.toggle("kb-error", !!isError);
}

function _renderMcpModalServers() {
  if (!els.mcpModalList) return;
  els.mcpModalList.innerHTML = "";
  const servers = _mcpModalServers || [];
  if (els.mcpModalEmpty) els.mcpModalEmpty.hidden = servers.length > 0;
  servers.forEach((srv, i) => {
    const row = document.createElement("div");
    row.className = "kb-modal-doc" + (srv.enabled === false ? " disabled" : "");

    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.className = "kb-modal-doc-toggle";
    toggle.checked = srv.enabled !== false;
    toggle.title = "Enable/disable this plugin";
    toggle.addEventListener("change", async () => {
      _mcpModalServers[i].enabled = toggle.checked;
      await _saveMcpModal();
      _renderMcpModalServers();
    });

    const info = document.createElement("div");
    info.className = "kb-modal-doc-info";
    const name = document.createElement("div");
    name.className = "kb-modal-doc-name";
    name.textContent = srv.name || srv.url;
    const meta = document.createElement("div");
    meta.className = "kb-modal-doc-meta";
    meta.textContent = srv.url;
    meta.title = srv.url;
    info.appendChild(name);
    info.appendChild(meta);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "kb-modal-doc-del";
    del.title = "Remove plugin";
    del.setAttribute("aria-label", `Remove ${srv.name || srv.url}`);
    del.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>';
    del.addEventListener("click", async () => {
      _mcpModalServers.splice(i, 1);
      await _saveMcpModal();
      _renderMcpModalServers();
    });

    row.appendChild(toggle);
    row.appendChild(info);
    row.appendChild(del);
    els.mcpModalList.appendChild(row);
  });
}

async function _saveMcpModal() {
  if (_mcpModalConvId == null) return;
  await fetch(`/api/conversations/${_mcpModalConvId}/mcp`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ servers: _mcpModalServers }),
  });
  if (_mcpModalConvId === state.conversationId) loadMcp();  // sync sidebar
}

async function _loadMcpModal() {
  if (_mcpModalConvId == null) return;
  try {
    const r = await fetch(`/api/conversations/${_mcpModalConvId}/mcp`);
    _mcpModalServers = r.ok ? ((await r.json()).servers || []) : [];
  } catch (_) {
    _mcpModalServers = [];
  }
  _renderMcpModalServers();
}

function openMcpModal(convId, title) {
  _mcpModalConvId = convId;
  _mcpModalServers = [];
  if (els.mcpModalBot) els.mcpModalBot.textContent = title ? `— ${title}` : "";
  if (els.mcpModalUrl) els.mcpModalUrl.value = "";
  _mcpModalSetStatus("", false);
  _renderMcpModalServers();
  _loadMcpModal();
  if (els.mcpModalBackdrop) els.mcpModalBackdrop.classList.remove("hidden");
}

function closeMcpModal() {
  if (els.mcpModalBackdrop) els.mcpModalBackdrop.classList.add("hidden");
  _mcpModalConvId = null;
}

async function _mcpModalAdd() {
  const url = (els.mcpModalUrl.value || "").trim();
  if (!url || _mcpModalConvId == null) return;
  els.mcpModalAddBtn.disabled = true;
  const ok = await _addMcpToConv(_mcpModalConvId, url, _mcpModalSetStatus);
  els.mcpModalAddBtn.disabled = false;
  if (ok) {
    els.mcpModalUrl.value = "";
    await _loadMcpModal();
    if (_mcpModalConvId === state.conversationId) loadMcp();
  }
}

function initMcpModalUI() {
  if (els.mcpModalClose) els.mcpModalClose.addEventListener("click", closeMcpModal);
  if (els.mcpModalBackdrop) {
    els.mcpModalBackdrop.addEventListener("click", e => {
      if (e.target === els.mcpModalBackdrop) closeMcpModal();
    });
  }
  if (els.mcpModalAddBtn) els.mcpModalAddBtn.addEventListener("click", _mcpModalAdd);
  if (els.mcpModalUrl) {
    els.mcpModalUrl.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); _mcpModalAdd(); }
    });
  }
}

// ─── Evals: per-bot scoring + auto-improve ──────────────────────────────
let _evalModalConvId = null;

// Sidebar summary (just a count + a "Manage evals" affordance).
async function loadEvals() {
  if (!els.evalsSummary) return;
  if (!state.conversationId) { els.evalsSummary.textContent = "No test cases yet."; return; }
  try {
    const r = await fetch(`/api/conversations/${state.conversationId}/eval/cases`);
    const cases = r.ok ? ((await r.json()).cases || []) : [];
    els.evalsSummary.textContent = cases.length
      ? `${cases.length} test case${cases.length === 1 ? "" : "s"}.`
      : "No test cases yet.";
  } catch (_) {
    els.evalsSummary.textContent = "No test cases yet.";
  }
}

function _evalSetStatus(msg, isError) {
  if (!els.evalStatus) return;
  if (!msg) { els.evalStatus.hidden = true; els.evalStatus.textContent = ""; return; }
  els.evalStatus.hidden = false;
  els.evalStatus.textContent = msg;
  els.evalStatus.classList.toggle("kb-error", !!isError);
}

function _renderEvalCases(cases) {
  if (!els.evalList) return;
  els.evalList.innerHTML = "";
  const list = cases || [];
  if (els.evalEmpty) els.evalEmpty.hidden = list.length > 0;
  for (const c of list) {
    const row = document.createElement("div");
    row.className = "eval-case";

    const info = document.createElement("div");
    info.className = "eval-case-info";
    const inp = document.createElement("span");
    inp.className = "eval-case-input"; inp.textContent = c.input; inp.title = c.input;
    const arrow = document.createElement("span");
    arrow.className = "eval-case-arrow"; arrow.textContent = "→";
    const exp = document.createElement("span");
    exp.className = "eval-case-expected"; exp.textContent = c.expected; exp.title = c.expected;
    info.appendChild(inp); info.appendChild(arrow); info.appendChild(exp);

    const del = document.createElement("button");
    del.type = "button"; del.className = "eval-case-del";
    del.title = "Delete case"; del.setAttribute("aria-label", "Delete case");
    del.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>';
    del.addEventListener("click", async () => {
      await fetch(`/api/conversations/${_evalModalConvId}/eval/cases/${c.id}`, { method: "DELETE" });
      await _loadEvalModal();
      loadEvals();
    });

    row.appendChild(info);
    row.appendChild(del);
    els.evalList.appendChild(row);
  }
}

async function _loadEvalModal() {
  if (_evalModalConvId == null) return;
  try {
    const r = await fetch(`/api/conversations/${_evalModalConvId}/eval/cases`);
    _renderEvalCases(r.ok ? ((await r.json()).cases || []) : []);
  } catch (_) { _renderEvalCases([]); }
}

function openEvalModal(convId, title) {
  _evalModalConvId = convId;
  if (els.evalModalBot) els.evalModalBot.textContent = title ? `— ${title}` : "";
  els.evalScore.textContent = "";
  els.evalResults.innerHTML = "";
  els.evalImproveLog.innerHTML = "";
  _evalSetStatus("", false);
  _renderEvalCases([]);
  _loadEvalModal();
  if (els.evalModalBackdrop) els.evalModalBackdrop.classList.remove("hidden");
}

function closeEvalModal() {
  if (els.evalModalBackdrop) els.evalModalBackdrop.classList.add("hidden");
  _evalModalConvId = null;
  loadEvals();  // refresh the sidebar count
}

async function _evalAddCase() {
  const input = (els.evalInput.value || "").trim();
  const expected = (els.evalExpected.value || "").trim();
  if (!input || !expected) return;
  await fetch(`/api/conversations/${_evalModalConvId}/eval/cases`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cases: [{ input, expected }] }),
  });
  els.evalInput.value = ""; els.evalExpected.value = "";
  els.evalInput.focus();
  await _loadEvalModal();
}

async function _evalSeed() {
  _evalSetStatus("Seeding from chat history…", false);
  const r = await fetch(`/api/conversations/${_evalModalConvId}/eval/seed`, { method: "POST" });
  const n = r.ok ? (await r.json()).added : 0;
  _evalSetStatus(n ? `Seeded ${n} case${n === 1 ? "" : "s"} from history.` : "No usable turns to seed from.", !n);
  await _loadEvalModal();
}

// Minimal CSV parse: 2 columns (input,expected). Handles simple quoted fields.
function _parseCsv(text) {
  const rows = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    let cols;
    if (line.includes('"')) {
      cols = []; let cur = ""; let inq = false;
      for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') { if (inq && line[i + 1] === '"') { cur += '"'; i++; } else inq = !inq; }
        else if (ch === "," && !inq) { cols.push(cur); cur = ""; }
        else cur += ch;
      }
      cols.push(cur);
    } else {
      cols = line.split(",");
    }
    if (cols.length >= 2) rows.push([cols[0].trim(), cols.slice(1).join(",").trim()]);
  }
  // Drop a header row if it looks like input,output/expected.
  if (rows.length && /^(input)$/i.test(rows[0][0]) && /^(output|expected)$/i.test(rows[0][1])) rows.shift();
  return rows;
}

async function _evalUploadCsv(file) {
  if (!file) return;
  const text = await file.text();
  const rows = _parseCsv(text);
  if (!rows.length) { _evalSetStatus("No (input,expected) rows found in the CSV.", true); return; }
  await fetch(`/api/conversations/${_evalModalConvId}/eval/cases`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cases: rows.map(([input, expected]) => ({ input, expected })) }),
  });
  _evalSetStatus(`Imported ${rows.length} case${rows.length === 1 ? "" : "s"} from CSV.`, false);
  await _loadEvalModal();
}

// Run the eval set once; render results; return the parsed body (for the loop).
async function runEvals(mode) {
  const payload = { mode };
  if (mode === "judge") {
    if (!_promptGenBackend || !_promptGenModel) {
      _evalSetStatus("Judge mode needs a Prompt-Generator model — set one in Settings → Prompt Generator.", true);
      return null;
    }
    payload.judge_backend_id = _promptGenBackend.id;
    payload.judge_model = _promptGenModel;
  }
  els.evalRunBtn.disabled = true;
  _evalSetStatus("Running…", false);
  let body = null;
  try {
    const r = await fetch(`/api/conversations/${_evalModalConvId}/eval/run`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    body = await r.json();
    if (!r.ok) { _evalSetStatus(body.detail || `Run failed (${r.status}).`, true); return null; }
    _renderEvalResults(body);
    _evalSetStatus("", false);
  } catch (e) {
    _evalSetStatus(`Run failed: ${e.message}`, true);
  } finally {
    els.evalRunBtn.disabled = false;
  }
  return body;
}

function _renderEvalResults(body) {
  if (!body) return;
  const pct = Math.round((body.accuracy || 0) * 100);
  els.evalScore.textContent = `${pct}%  (${body.passed}/${body.total})`;
  els.evalScore.style.color = pct === 100 ? "#16a34a" : (pct >= 50 ? "var(--text)" : "var(--danger)");
  els.evalResults.innerHTML = "";
  for (const res of (body.results || [])) {
    const row = document.createElement("div");
    row.className = "eval-case " + (res.passed ? "pass" : "fail");
    const info = document.createElement("div");
    info.className = "eval-case-info";
    const inp = document.createElement("span");
    inp.className = "eval-case-input"; inp.textContent = res.input; inp.title = res.input;
    const got = document.createElement("span");
    got.className = "eval-case-expected";
    got.textContent = res.passed ? res.expected : `got: ${res.got}`;
    got.title = `expected: ${res.expected}\ngot: ${res.got}`;
    info.appendChild(inp);
    const verdict = document.createElement("span");
    verdict.className = "eval-case-verdict " + (res.passed ? "pass" : "fail");
    verdict.textContent = res.passed ? "✓" : "✗";
    row.appendChild(verdict);
    row.appendChild(info);
    info.appendChild(got);
    els.evalResults.appendChild(row);
  }
}

// Auto-improve: run → if below target, summarize failures into the existing
// Improve-prompt flow → persist → re-run, up to maxIters. Keep the best prompt.
async function autoImproveLoop() {
  const mode = els.evalMode.value;
  const target = Math.max(1, Math.min(100, parseInt(els.evalTarget.value, 10) || 100)) / 100;
  const maxIters = Math.max(1, Math.min(10, parseInt(els.evalIters.value, 10) || 3));
  const ta = document.getElementById("system-prompt");
  if (!ta) return;
  if (!ta.value.trim()) {
    _evalSetStatus("Auto-improve needs a non-empty system prompt to improve.", true);
    return;
  }
  if (!_promptGenBackend || !_promptGenModel) {
    _evalSetStatus("Auto-improve needs a Prompt-Generator model — set one in Settings → Prompt Generator.", true);
    return;
  }
  els.evalImproveBtn.disabled = true;
  els.evalImproveLog.innerHTML = "";
  let best = null;
  try {
    for (let i = 0; i < maxIters; i++) {
      const res = await runEvals(mode);
      if (!res) break;  // run failed / judge misconfigured
      const promptNow = ta.value;
      const line = document.createElement("div");
      line.textContent = `iter ${i + 1}: ${Math.round(res.accuracy * 100)}% (${res.passed}/${res.total})`;
      els.evalImproveLog.appendChild(line);
      if (!best || res.accuracy > best.accuracy) best = { accuracy: res.accuracy, prompt: promptNow };
      if (res.accuracy >= target) { line.classList.add("best"); break; }
      if (i === maxIters - 1) break;  // no improve after the last run
      const failures = (res.results || []).filter(r => !r.passed);
      const summary =
        "These test cases failed. Rewrite the system prompt so they produce the EXPECTED " +
        "output, without breaking the ones that already pass. Be specific and concise.\n\n" +
        failures.map(f => `INPUT: ${f.input}\nEXPECTED: ${f.expected}\nGOT: ${f.got}`).join("\n\n");
      _evalSetStatus(`Improving prompt (iter ${i + 1})…`, false);
      await _runPromptGeneration(summary);   // streams a new prompt into #system-prompt
      await flushPendingSave();              // persist so the next run scores it
    }
    // Restore the best-scoring prompt and persist it.
    if (best && ta.value !== best.prompt) {
      ta.value = best.prompt;
      ta.dispatchEvent(new Event("input", { bubbles: true }));
      await flushPendingSave();
    }
    if (best) {
      const done = document.createElement("div");
      done.className = "best";
      done.textContent = `✓ best: ${Math.round(best.accuracy * 100)}% (kept this prompt)`;
      els.evalImproveLog.appendChild(done);
    }
    _evalSetStatus("", false);
  } finally {
    els.evalImproveBtn.disabled = false;
  }
}

function initEvalsUI() {
  if (els.evalsManageBtn) {
    els.evalsManageBtn.addEventListener("click", () => {
      if (!state.conversationId) { alert("Open or create a bot first, then add evals."); return; }
      const c = _botsState.cache.find(x => x.id === state.conversationId);
      openEvalModal(state.conversationId, c ? c.title : "");
    });
  }
}

function initEvalModalUI() {
  if (els.evalModalClose) els.evalModalClose.addEventListener("click", closeEvalModal);
  if (els.evalModalBackdrop) {
    els.evalModalBackdrop.addEventListener("click", e => {
      if (e.target === els.evalModalBackdrop) closeEvalModal();
    });
  }
  if (els.evalAddBtn) els.evalAddBtn.addEventListener("click", _evalAddCase);
  if (els.evalExpected) {
    els.evalExpected.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); _evalAddCase(); }
    });
  }
  if (els.evalSeedBtn) els.evalSeedBtn.addEventListener("click", _evalSeed);
  if (els.evalClearBtn) {
    els.evalClearBtn.addEventListener("click", async () => {
      if (!confirm("Delete all test cases for this bot?")) return;
      await fetch(`/api/conversations/${_evalModalConvId}/eval/cases`, { method: "DELETE" });
      await _loadEvalModal();
      loadEvals();
    });
  }
  if (els.evalCsvBtn && els.evalCsvFile) {
    els.evalCsvBtn.addEventListener("click", () => els.evalCsvFile.click());
    els.evalCsvFile.addEventListener("change", async () => {
      await _evalUploadCsv(els.evalCsvFile.files[0]);
      els.evalCsvFile.value = "";
    });
  }
  if (els.evalRunBtn) els.evalRunBtn.addEventListener("click", () => runEvals(els.evalMode.value));
  if (els.evalImproveBtn) els.evalImproveBtn.addEventListener("click", autoImproveLoop);
}

// ─── Per-bot Knowledge base (RAG) ───────────────────────────────────────
// Upload PDFs / txt / md to the open bot. PDFs go through the existing
// /api/extract-pdf endpoint; text files are read in-browser. The extracted
// text is POSTed to the bot's knowledge endpoint, which chunks + embeds it.

function _kbSetStatus(msg, isError, loading) {
  if (!els.kbStatus) return;
  if (!msg) { els.kbStatus.hidden = true; els.kbStatus.textContent = ""; els.kbStatus.classList.remove("loading"); return; }
  els.kbStatus.hidden = false;
  els.kbStatus.textContent = msg;
  els.kbStatus.classList.toggle("kb-error", !!isError);
  els.kbStatus.classList.toggle("loading", !!loading);
}

function renderKnowledge(docs) {
  if (!els.kbList) return;
  els.kbList.innerHTML = "";
  const list = docs || [];
  if (els.kbEmpty) els.kbEmpty.hidden = list.length > 0;
  for (const d of list) {
    const row = document.createElement("div");
    row.className = "kb-doc";

    const info = document.createElement("div");
    info.className = "kb-doc-info";
    const name = document.createElement("div");
    name.className = "kb-doc-name";
    name.textContent = d.filename;
    name.title = d.filename;
    const meta = document.createElement("div");
    meta.className = "kb-doc-meta";
    meta.textContent = `${d.chunk_count} chunk${d.chunk_count === 1 ? "" : "s"}`;
    info.appendChild(name);
    info.appendChild(meta);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "kb-doc-del";
    del.title = "Remove from knowledge base";
    del.setAttribute("aria-label", `Remove ${d.filename}`);
    del.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>';
    del.addEventListener("click", () => deleteKnowledgeDoc(d.id));

    row.appendChild(info);
    row.appendChild(del);
    els.kbList.appendChild(row);
  }
}

async function loadKnowledge() {
  if (!els.kbList) return;
  if (!state.conversationId) { renderKnowledge([]); return; }
  try {
    const r = await fetch(`/api/conversations/${state.conversationId}/knowledge`);
    if (!r.ok) { renderKnowledge([]); return; }
    const data = await r.json();
    renderKnowledge(data.documents || []);
  } catch (_) {
    renderKnowledge([]);
  }
}

async function deleteKnowledgeDoc(docId) {
  if (!state.conversationId) return;
  const r = await fetch(
    `/api/conversations/${state.conversationId}/knowledge/${docId}`,
    { method: "DELETE" }
  );
  if (r.ok) loadKnowledge();
}

// Read one file into plain text. PDFs use the server extractor; everything
// else is read directly in the browser.
async function _kbExtractText(file) {
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  if (isPdf) {
    const fd = new FormData();
    fd.append("file", file);
    // full=1 → book-friendly caps; the extracted text is chunked + embedded.
    const r = await fetch("/api/extract-pdf?full=1", { method: "POST", body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `PDF extraction failed (${r.status})`);
    }
    return (await r.json()).text || "";
  }
  return await file.text();
}

// Upload + embed a set of files into a SPECIFIC bot's knowledge base. Conv id
// is explicit (not state.conversationId) so the bots-list cards can target
// their own bot. `onStatus(msg, isError)` receives progress. Returns the count
// of documents successfully added.
async function _uploadKnowledgeToConv(convId, files, onStatus) {
  const list = Array.from(files || []);
  if (!list.length) return 0;
  let added = 0;
  for (let i = 0; i < list.length; i++) {
    const file = list[i];
    if (onStatus) onStatus(`Processing ${file.name} (${i + 1}/${list.length})…`, false, true);  // loading
    try {
      const text = await _kbExtractText(file);
      if (!text.trim()) {
        if (onStatus) onStatus(`${file.name}: no extractable text — skipped.`, true);
        continue;
      }
      const r = await fetch(`/api/conversations/${convId}/knowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, text }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        if (onStatus) onStatus(err.detail || `${file.name}: failed (${r.status}).`, true);
        continue;  // keep going with the rest
      }
      added++;
    } catch (e) {
      if (onStatus) onStatus(`${file.name}: ${e.message}`, true);
    }
  }
  return added;
}

async function addKnowledgeFiles(files) {
  if (!state.conversationId) {
    alert("Open or create a bot first (send a message, or use + New bot), then add knowledge.");
    return;
  }
  const added = await _uploadKnowledgeToConv(state.conversationId, files, _kbSetStatus);
  if (added) _kbSetStatus(`Added ${added} document${added === 1 ? "" : "s"}.`, false);
  await loadKnowledge();
}

function initKnowledgeUI() {
  if (els.kbAddBtn && els.kbFileInput) {
    els.kbAddBtn.addEventListener("click", () => els.kbFileInput.click());
    els.kbFileInput.addEventListener("change", async () => {
      await addKnowledgeFiles(els.kbFileInput.files);
      els.kbFileInput.value = "";  // allow re-selecting the same file
    });
  }
}

// ─── MCP Extensions (per-bot plugins / tool servers) ────────────────────
// A bot's plugins are remote MCP server URLs. We validate a URL by listing
// its tools before saving, then persist the list to the conversation.

const _mcpState = { servers: [] };

function _mcpSetStatus(msg, isError) {
  if (!els.mcpStatus) return;
  if (!msg) { els.mcpStatus.hidden = true; els.mcpStatus.textContent = ""; return; }
  els.mcpStatus.hidden = false;
  els.mcpStatus.textContent = msg;
  els.mcpStatus.classList.toggle("kb-error", !!isError);
}

function renderMcp() {
  if (!els.mcpList) return;
  els.mcpList.innerHTML = "";
  const servers = _mcpState.servers || [];
  if (els.mcpEmpty) els.mcpEmpty.hidden = servers.length > 0;
  servers.forEach((srv, i) => {
    const row = document.createElement("div");
    row.className = "mcp-srv" + (srv.enabled ? "" : " disabled");

    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.className = "mcp-srv-toggle";
    toggle.checked = srv.enabled !== false;
    toggle.title = "Enable/disable this plugin";
    toggle.addEventListener("change", () => {
      _mcpState.servers[i].enabled = toggle.checked;
      saveMcp();
      renderMcp();
    });

    const info = document.createElement("div");
    info.className = "mcp-srv-info";
    const name = document.createElement("div");
    name.className = "mcp-srv-name";
    name.textContent = srv.name || srv.url;
    const url = document.createElement("div");
    url.className = "mcp-srv-url";
    url.textContent = srv.url;
    url.title = srv.url;
    info.appendChild(name);
    info.appendChild(url);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "mcp-srv-del";
    del.title = "Remove plugin";
    del.setAttribute("aria-label", `Remove ${srv.name || srv.url}`);
    del.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>';
    del.addEventListener("click", () => {
      _mcpState.servers.splice(i, 1);
      saveMcp();
      renderMcp();
    });

    row.appendChild(toggle);
    row.appendChild(info);
    row.appendChild(del);
    els.mcpList.appendChild(row);
  });
}

async function loadMcp() {
  if (!els.mcpList) return;
  if (!state.conversationId) { _mcpState.servers = []; renderMcp(); return; }
  try {
    const r = await fetch(`/api/conversations/${state.conversationId}/mcp`);
    _mcpState.servers = r.ok ? ((await r.json()).servers || []) : [];
  } catch (_) {
    _mcpState.servers = [];
  }
  renderMcp();
}

async function saveMcp() {
  if (!state.conversationId) return;
  await fetch(`/api/conversations/${state.conversationId}/mcp`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ servers: _mcpState.servers }),
  });
}

// Validate an MCP server URL (lists its tools) and append it to a SPECIFIC
// bot's plugin list. Conv id is explicit so the bots-list cards can target
// their own bot. Returns true on success. `onStatus(msg, isError)` for feedback.
async function _addMcpToConv(convId, url, onStatus) {
  if (onStatus) onStatus("Connecting to MCP server…", false);
  let resp;
  try {
    const r = await fetch(`/api/conversations/${convId}/mcp/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    resp = await r.json();
  } catch (e) {
    if (onStatus) onStatus(`Could not reach ${url}.`, true);
    return false;
  }
  if (!resp.ok) {
    if (onStatus) onStatus(`Couldn't connect: ${resp.error || "unknown error"}`, true);
    return false;
  }
  // Append to the bot's existing server list and persist.
  let servers = [];
  try {
    servers = (await (await fetch(`/api/conversations/${convId}/mcp`)).json()).servers || [];
  } catch (_) {}
  let host = url;
  try { host = new URL(url).host; } catch (_) {}
  servers.push({ name: host, url, enabled: true });
  await fetch(`/api/conversations/${convId}/mcp`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ servers }),
  });
  const n = (resp.tools || []).length;
  if (onStatus) onStatus(`Added — ${n} tool${n === 1 ? "" : "s"} available.`, false);
  return true;
}

async function addMcpServer() {
  if (!state.conversationId) {
    alert("Open or create a bot first, then add plugins.");
    return;
  }
  const url = (els.mcpUrlInput.value || "").trim();
  if (!url) return;
  const ok = await _addMcpToConv(state.conversationId, url, _mcpSetStatus);
  if (ok) {
    els.mcpUrlInput.value = "";
    await loadMcp();
  }
}

function initMcpUI() {
  if (els.mcpAddBtn) els.mcpAddBtn.addEventListener("click", addMcpServer);
  if (els.mcpUrlInput) {
    els.mcpUrlInput.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); addMcpServer(); }
    });
  }
}

// Esc: if you're in chat, fall back to the bots list. Skip when a modal is open
// (modals own Esc), when you're typing in a textarea/input, or when the chat
// composer is mid-stream (Stop button handles that case).
function _botsHotkeyHandler(e) {
  if (e.defaultPrevented) return;
  const tgt = e.target;
  const inField = tgt && (
    tgt.tagName === "INPUT" ||
    tgt.tagName === "TEXTAREA" ||
    tgt.isContentEditable
  );
  if (e.key === "Escape") {
    // Modals own Esc. Skip if any modal backdrop is currently visible.
    const modalOpen = document.querySelector(".modal-backdrop:not(.hidden)");
    if (modalOpen) return;
    if (document.body.dataset.page === "dashboard") {
      e.preventDefault();
      exitChatToReturn();
    }
    return;
  }
  // ⌘K / Ctrl+K — focus the bots quick switcher from anywhere.
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    applyActivePage("bots");
    if (els.botsFilter) {
      els.botsFilter.focus();
      els.botsFilter.select();
    }
    return;
  }
  // `/` — same as ⌘K but only when you're not already typing somewhere.
  if (e.key === "/" && !inField) {
    e.preventDefault();
    applyActivePage("bots");
    if (els.botsFilter) {
      els.botsFilter.focus();
      els.botsFilter.select();
    }
  }
}

// ---------- Conversations ----------
// Single source of truth for "what bots exist." Called after every mutation
// (create / delete / clear / import). Refreshes the in-memory cache that
// the Bots page renders from + updates the topbar's current-bot label.
async function loadConversations() {
  const r = await fetch("/api/conversations");
  const list = await r.json();
  _botsState.cache = list;
  renderBotsPage();
  renderTopbarBotLabel();
  renderSysPromptAvatar();
  return list;
}

async function openConversation(id) {
  // If this same conversation is mid-stream, do NOT re-fetch/re-render. Rebuilding
  // the message list from the DB snapshot (which lacks the not-yet-persisted
  // in-flight turn) would wipe the live streaming bubble and leave the Stop
  // button stuck. The chat is already showing the live stream — just stay on it.
  // (Navigating away + back during generation is the trigger.)
  if (id === state.conversationId && state.abortController) return;
  const r = await fetch(`/api/conversations/${id}`);
  if (!r.ok) return;
  const c = await r.json();
  state.conversationId = c.id;
  state.messages = c.messages || [];
  els.systemPrompt.value = c.system_prompt || "";
  // Programmatic .value sets don't fire `input`, so the toggle label (and
  // any future prompt-edit observers) won't update on conversation switch
  // without this nudge. The bound listener also re-runs saveSettings, which
  // is a no-op for an unchanged localStorage payload.
  if (typeof _updatePromptGenAffordance === "function") _updatePromptGenAffordance();
  renderSysPromptAvatar(c);   // show this bot's avatar in the sidebar header
  const _cacheHit = (_botsState.cache || []).find(x => x.id === c.id);
  if (_cacheHit) _cacheHit.avatar = c.avatar;   // keep card cache fresh

  // Match by (model, backend_id) pair. Falls back to model-only if the exact
  // pair can't be found (e.g. the endpoint was deleted). If nothing matches,
  // selection is cleared and the model dropdown shows no option — Send will
  // still attempt to call, and server will 404 on backend_load.
  if (c.model) _selectModelOption(c.model, c.backend_id);

  // Restore this bot's TTS voice into the picker (no-op if no voice backend
  // is registered — the picker is hidden in that case).
  _setVoiceSelectFromConv(c);

  // Load saved per-conversation params into the sliders.
  const p = c.params || {};
  if (p.temperature != null) els.temperature.value = p.temperature;
  if (p.max_tokens != null) els.maxTokens.value = p.max_tokens;
  if (p.top_p != null) els.topP.value = p.top_p;
  if (p.top_k != null) els.topK.value = p.top_k;
  els.think.value = thinkToSelect(p.think);
  els.maxThinking.value = p.max_thinking_tokens != null ? p.max_thinking_tokens : "";
  syncParamDisplay();
  renderTopbarBotLabel();
  _markConvViewed(id);  // opening = "I'm reading this now"
  renderBotsPage();
  renderMessages();
  if (c.generating && !state.abortController) {
    // The server is still generating a reply for this conv (we sent a message
    // then reloaded/navigated). Re-attach to the in-flight generation so the
    // streaming/waiting state is restored instead of silently lost.
    resumeGeneration(c);
  } else if (!state.abortController) {
    // Self-heal the composer: this conv isn't streaming, so the Send button
    // must be showing and the input enabled — corrects a Stop button left
    // stuck by an earlier desync.
    els.stopBtn.style.display = "none";
    els.sendBtn.style.display = "";
    els.sendBtn.disabled = false;
    els.input.disabled = false;
  }
  loadKnowledge();
  loadMcp();
  loadEvals();
}

async function newConversation(opts = {}) {
  const opt = els.modelSelect.selectedOptions[0];
  const model = opt && opt.value;
  if (!model) {
    alert("Pick a model first.");
    return false;
  }
  const backendId = opt.dataset.backendId
    ? parseInt(opt.dataset.backendId, 10)
    : 1;
  // `skipPrompt` callers (e.g. the Bots-page "+ New bot" button) name the bot
  // with the non-suppressible inline rename input AFTER creation, instead of a
  // native prompt() — browsers silently no-op prompt()/alert() once the user
  // ticks "prevent additional dialogs", which made New bot appear dead.
  let title;
  if (opts.skipPrompt) {
    title = (opts.title && opts.title.trim()) || "New Chat";
  } else {
    const input = prompt("Name this chat:", "");
    if (input === null) return false;         // user cancelled
    title = input.trim() || "New Chat";
  }

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
  renderTopbarBotLabel();
  renderMessages();
  _kbSetStatus("", false);
  loadKnowledge();  // fresh bot → empty library
  _mcpSetStatus("", false);
  loadMcp();
  loadEvals();

  // Reset the sidebar so the user sees the clean config they're about to edit.
  // Must happen AFTER state.conversationId is set so the debounced auto-save
  // (triggered when the user starts typing) targets the new conversation.
  resetSidebarToDefaults();

  // Focus the system prompt so they can start authoring the bot immediately.
  els.systemPrompt.focus();
  return true;
}

function resetSidebarToDefaults() {
  els.systemPrompt.value = "";
  if (typeof _updatePromptGenAffordance === "function") _updatePromptGenAffordance();
  els.temperature.value = DEFAULTS.temperature;
  els.maxTokens.value   = DEFAULTS.max_tokens;
  els.topP.value        = DEFAULTS.top_p;
  els.topK.value        = DEFAULTS.top_k;
  els.think.value       = "";
  els.maxThinking.value = "";
  if (els.voiceSelect) els.voiceSelect.value = "";  // "Default voice"
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

  // Snapshot the target conv id for unread-indicator bookkeeping. We use the
  // snapshot (not state.conversationId) in the finally block because the user
  // may navigate to a different conv mid-stream.
  const _streamConvId = state.conversationId;
  _onStreamStart(_streamConvId);

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
  const ac = new AbortController();
  state.abortController = ac;
  state.streamConvId = state.conversationId;
  els.stopBtn.style.display = "";
  els.sendBtn.style.display = "none";

  els.sendBtn.disabled = true;
  els.input.disabled = true;

  // Ensure the server's saved config matches the sidebar BEFORE we fire
  // the call. This way the GUI Send button is identical to the cURL
  // snippet shown in "Get API Code" — both hit the conversation's pure-
  // function endpoint with just `{message}` and rely on saved state.
  await flushPendingSave();

  const convId = state.conversationId;
  await _consumeAssistantStream({
    assistantEl, body, model, params, streamConvId: _streamConvId,
    fetchFn: () => fetch(`/api/conversations/${convId}/chat/stream`, {
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
    }),
  });
}

// Re-attach to a generation that's still running server-side (the user sent a
// message and then reloaded/closed the tab). The user turn is already persisted
// and rendered by openConversation; we add the assistant placeholder and stream
// the in-flight reply from the resume endpoint. The generation runs
// independently of this connection, so this is a pure viewer.
async function resumeGeneration(c) {
  const assistantEl = renderMessage({ role: "assistant", content: "" });
  const body = assistantEl.querySelector(".msg-body");
  assistantEl.classList.add("cursor");
  scrollToBottom();
  const ac = new AbortController();
  state.abortController = ac;
  state.streamConvId = c.id;
  els.stopBtn.style.display = "";
  els.sendBtn.style.display = "none";
  els.sendBtn.disabled = true;
  els.input.disabled = true;
  _onStreamStart(c.id);
  await _consumeAssistantStream({
    assistantEl, body, model: c.model, params: c.params || {}, streamConvId: c.id,
    fetchFn: () => fetch(`/api/conversations/${c.id}/generation/stream`, { signal: ac.signal }),
  });
}

// Drive the assistant bubble from an SSE response — shared by sendMessage (POST
// chat/stream) and resumeGeneration (GET generation/stream) so both render
// identically and reset the composer the same way. `fetchFn` runs inside the
// try so network/abort errors are handled uniformly.
async function _consumeAssistantStream({ fetchFn, assistantEl, body, model, params, streamConvId }) {
  let assistantText = "";
  let thinkingText = "";
  let thinkingEl = null;
  let contentEl = null;
  let truncatedNotice = null;
  try {
    const res = await fetchFn();
    if (!res.ok || !res.body) {
      const t = await res.text().catch(() => "");
      throw new Error(t || `HTTP ${res.status}`);
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
    state.streamConvId = null;
    els.stopBtn.style.display = "none";
    els.sendBtn.style.display = "";
    assistantEl.classList.remove("cursor");
    const hasContent = assistantText.trim().length > 0 || thinkingText.trim().length > 0;
    if (!hasContent) {
      // Empty stream — e.g. a resumed generation that already finished and was
      // persisted+evicted, or a no-op reply. Drop the ghost bubble instead of
      // leaving a blank one; the real reply (if any) is already in the DB.
      assistantEl.remove();
    } else {
      // Params badge inside the body so the flex layout stays clean.
      const badge = document.createElement("div");
      badge.className = "params-badge";
      badge.textContent = `${model} · T=${params.temperature} · max=${params.max_tokens} · top_p=${params.top_p} · top_k=${params.top_k}`;
      body.appendChild(badge);
      // Final pass: pretty-print JSON (render() already runs per chunk, but the
      // content only parses once the closing brace arrives) and highlight once.
      if (contentEl) {
        contentEl.innerHTML = render(assistantText);
        highlightCodeBlocks(contentEl);
      }
      state.messages.push({ role: "assistant", content: assistantText, params: { model, ...params } });
      // Now that the message is in state, attach the edit pencil — the
      // placeholder was rendered without an index.
      const finalIndex = state.messages.length - 1;
      assistantEl.dataset.index = String(finalIndex);
      _appendEditButton(assistantEl, finalIndex);
    }
    els.sendBtn.disabled = false;
    els.input.disabled = false;
    els.input.focus();
    scrollToBottom();   // settle the viewport on the fully-rendered final message
    loadConversations();
    _onStreamEnd(streamConvId);
  }
}

// =====================================================================
// Push-to-talk (voice mode)
// =====================================================================
//
// Hold the mic button, release to send. Audio is recorded via MediaRecorder
// (browser default codec — usually webm/opus; the voice service auto-decodes
// via PyAV), POSTed as multipart to /voice/turn, and the merged SSE stream
// drives the same chat bubble + a Web-Audio playback queue.

const _voice = {
  rec: null,             // active MediaRecorder
  chunks: [],            // collected blob parts for the current take
  pressed: false,        // is the button currently held / toggled on?
  abort: null,           // AbortController for the in-flight /voice/turn
  audioCtx: null,        // shared AudioContext, created on first use
  audioCursor: 0,        // currentTime to schedule the next chunk at
  // Live-preview transcript (browser's SpeechRecognition while the user holds
  // the mic). Cleared the moment the server returns the authoritative Whisper
  // transcript, or on release if the API isn't available.
  speechRec: null,       // active SpeechRecognition instance, or null
  previewFinal: "",      // text the recognizer has marked `isFinal: true`
  previewLatest: "",     // most recent text actually rendered in the chip
                         // (final + current interim) — what the user SEES.
                         // Critical for short utterances where Chrome never
                         // finalizes anything before release.
  // Active AudioBufferSourceNodes for the in-flight TTS. The stop button
  // walks this list to .stop() each one, then aborts the SSE so the server
  // doesn't keep sending audio chunks we don't want to play.
  audioSources: [],
  // True once the SSE response has finished. The stop button stays visible
  // as long as either the stream is still active OR audio is still playing,
  // so the user can interrupt at *any* point during the bot's reply.
  streamEnded: false,
  // Pre-created bubbles so the conversation feels instant on release. The
  // user bubble uses the SpeechRecognition preview as a placeholder until the
  // server's authoritative Whisper transcript replaces it.
  pendingUserEl: null,
  pendingUserMsg: null,
  pendingAssistantEl: null,
  pendingAssistantBody: null,
  thinkingPill: null,
};


function _getAudioContext() {
  // Lazy: browsers gate AudioContext creation behind a user gesture, which
  // pressing the mic button counts as.
  if (!_voice.audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    _voice.audioCtx = new Ctx();
  }
  return _voice.audioCtx;
}


// Hide the stop button only when (a) the SSE has finished AND (b) the audio
// playback cursor has actually caught up to the AudioContext's current time
// AND (c) no queued AudioBufferSourceNodes remain. If any of those are still
// pending, we keep the button visible so the user can interrupt at any
// moment, even after the SSE response has officially "ended."
function _maybeHideVoiceStop() {
  if (!els.voiceStopBtn) return;
  if (!_voice.streamEnded) return;
  if (_voice.audioSources.length > 0) return;
  const ctx = _voice.audioCtx;
  if (ctx && _voice.audioCursor > ctx.currentTime + 0.02) return;
  els.voiceStopBtn.hidden = true;
}


// Decode + schedule one base64 PCM-16 chunk for seamless playback. The
// voice-stop button was already made visible at the start of the turn (in
// _consumeVoiceTurn) so we don't need to flip it here — audio playback is
// just one of the things the same Stop button cancels.
function _enqueueAudioChunk(b64, sampleRate) {
  const ctx = _getAudioContext();
  const binary = atob(b64);
  // PCM 16-bit little-endian → Float32 in [-1, 1]
  const len = binary.length / 2;
  const pcm = new Float32Array(len);
  for (let i = 0; i < len; i++) {
    const lo = binary.charCodeAt(i * 2);
    const hi = binary.charCodeAt(i * 2 + 1);
    let s = (hi << 8) | lo;
    if (s >= 0x8000) s -= 0x10000;
    pcm[i] = s / 0x8000;
  }
  const buffer = ctx.createBuffer(1, len, sampleRate);
  buffer.getChannelData(0).set(pcm);
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  // Schedule on a sliding cursor so back-to-back chunks have no gap.
  const startAt = Math.max(ctx.currentTime, _voice.audioCursor);
  source.start(startAt);
  _voice.audioCursor = startAt + buffer.duration;
  // Track the source so a Stop click can interrupt it. Remove it on natural
  // end so the list stays small.
  _voice.audioSources.push(source);
  source.onended = () => {
    const i = _voice.audioSources.indexOf(source);
    if (i >= 0) _voice.audioSources.splice(i, 1);
    // If this was the last queued chunk AND the SSE has already finished,
    // it's safe to take the stop button away now.
    _maybeHideVoiceStop();
  };
}


// Stop everything playing right now AND cancel the in-flight SSE so the
// server doesn't keep producing audio we no longer want. The assistant's
// text bubble (already rendered up to this point) stays in the chat —
// only the spoken half is interrupted.
function _stopVoicePlayback() {
  // 1. Silence the queued buffers. Each call is idempotent so duplicate
  //    stops on a source we already paused are harmless.
  for (const s of _voice.audioSources.splice(0)) {
    try { s.stop(); } catch (_) { /* already stopped */ }
    try { s.disconnect(); } catch (_) {}
  }
  // 2. Cursor reset — next chunk (in a future turn) plays immediately.
  if (_voice.audioCtx) _voice.audioCursor = _voice.audioCtx.currentTime;
  // 3. Abort the SSE so the server's TTS pipeline stops emitting chunks.
  if (_voice.abort) {
    try { _voice.abort.abort(); } catch (_) {}
  }
  if (els.voiceStopBtn) els.voiceStopBtn.hidden = true;
}


// --- Live transcription preview ---------------------------------------
//
// While the user is holding the mic, the browser's built-in SpeechRecognition
// API gives instant partial transcripts (sub-100ms) so they see their words
// appear as they speak. The final word is whatever server-side Whisper says —
// the preview gets cleared the moment the real transcript arrives.
//
// Chrome / Edge / Safari support this. Firefox doesn't — fail silently and
// fall back to "release first, then see the transcript" behavior.

function _hasSpeechRecognition() {
  return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}


function _setVoicePreview(text) {
  if (!els.voicePreview) return;
  const t = (text || "").trim();
  if (!t) {
    els.voicePreview.hidden = true;
    els.voicePreview.textContent = "";
    return;
  }
  els.voicePreview.hidden = false;
  els.voicePreview.textContent = t;
}


function _startSpeechPreview() {
  if (!_hasSpeechRecognition()) return;
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new Ctor();
  rec.continuous = true;
  rec.interimResults = true;
  // No `lang` set ⇒ user's browser locale. Most natural default.
  _voice.previewFinal = "";
  _voice.previewLatest = "";
  rec.addEventListener("result", e => {
    // Late-firing safeguard: Chrome may fire one more `result` event after
    // we already called .stop() while it flushes trailing audio. By that
    // point _stopSpeechPreview has nulled the active reference, so we drop
    // anything for a recognizer we no longer own — otherwise it would
    // re-paint the chip after we already cleared it on release.
    if (_voice.speechRec !== rec) return;
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) {
        _voice.previewFinal += r[0].transcript;
      } else {
        interim += r[0].transcript;
      }
    }
    const combined = _voice.previewFinal + interim;
    _voice.previewLatest = combined;
    _setVoicePreview(combined);
  });
  rec.addEventListener("error", () => { /* swallow — preview is best-effort */ });
  rec.addEventListener("end", () => {
    // If we're still recording, the recognizer auto-stopped (it does that
    // after a few seconds of silence). Restart it.
    if (_voice.pressed) {
      try { rec.start(); } catch (_) {}
    }
  });
  try { rec.start(); } catch (_) { return; }
  _voice.speechRec = rec;
}


function _stopSpeechPreview({clearChip = false} = {}) {
  if (_voice.speechRec) {
    try {
      // Detach the end handler so it doesn't auto-restart after we asked
      // it to stop.
      _voice.speechRec.onend = null;
      _voice.speechRec.stop();
    } catch (_) {}
    _voice.speechRec = null;
  }
  if (clearChip) _setVoicePreview("");
}


async function _startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) {
    // The microphone API is gated behind a "secure context": browsers expose
    // it only on https:// or http://localhost / 127.0.0.1, never on a plain-
    // HTTP LAN IP. Spell that out so the user knows what to fix.
    const isSecure = window.isSecureContext;
    const origin = location.origin;
    const msg = isSecure
      ? `Your browser does not expose a microphone API. Origin: ${origin}.`
      : `Microphone access requires a secure context (https:// or localhost). ` +
        `You're on ${origin}, which the browser treats as insecure. Options: ` +
        `(1) reach MiniClosedAI via http://localhost:8095 from the same machine, ` +
        `(2) put MiniClosedAI behind HTTPS, or ` +
        `(3) Chrome flag: chrome://flags/#unsafely-treat-insecure-origin-as-secure → add ${origin} → relaunch.`;
    alert(msg);
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: true});
  } catch (e) {
    alert(`Could not access the microphone: ${e.message}`); return;
  }
  _voice.chunks = [];
  // Default codec — Chrome gives webm/opus, Firefox ogg/opus, Safari mp4.
  // The voice service decodes any of them via PyAV.
  const rec = new MediaRecorder(stream);
  rec.addEventListener("dataavailable", e => {
    if (e.data && e.data.size > 0) _voice.chunks.push(e.data);
  });
  rec.addEventListener("stop", () => {
    stream.getTracks().forEach(t => t.stop());
  });
  rec.start();
  _voice.rec = rec;
  els.micBtn?.classList.add("recording");
  // Live preview is best-effort — if the browser doesn't have
  // SpeechRecognition (Firefox), we just skip it and the user sees the
  // transcript when the server returns.
  _startSpeechPreview();
}


async function _stopRecordingAndSend() {
  const rec = _voice.rec;
  if (!rec || rec.state === "inactive") return;
  // Stop the preview recognizer so it releases the mic.
  _stopSpeechPreview();
  // The instant the user releases, render the conversation bubbles. The user
  // bubble uses the SpeechRecognition transcript (which is the same text
  // they've been watching appear in the preview chip). The assistant bubble
  // gets a "thinking" pill that flips to "Searching knowledge" / "Thinking"
  // as the server emits {status} events before the first {chunk}.
  //
  // Prefer `previewLatest` (final + interim — what was on screen) over
  // `previewFinal` (only the finalized parts). Otherwise short utterances
  // that the recognizer never had time to mark final would silently fall
  // back to the slow server-Whisper path.
  const previewText = (_voice.previewLatest || _voice.previewFinal || "").trim();
  _setVoicePreview("");
  els.voicePreview?.classList.remove("sending");
  const userMsg = {role: "user", content: previewText || "…"};
  _voice.pendingUserMsg = userMsg;
  state.messages.push(userMsg);
  _voice.pendingUserEl = renderMessage(userMsg);
  if (!previewText) _voice.pendingUserEl?.classList.add("voice-pending");
  const assistantEl = renderMessage({role: "assistant", content: ""});
  assistantEl.classList.add("cursor");
  _voice.pendingAssistantEl = assistantEl;
  _voice.pendingAssistantBody = assistantEl.querySelector(".msg-body");
  const pill = document.createElement("div");
  pill.className = "voice-thinking-pill";
  // If we already have the transcript (browser recognition), the next step is
  // straight to the LLM — no transcription happening on the server.
  pill.textContent = previewText ? "💭 Thinking…" : "🎙 Transcribing…";
  _voice.pendingAssistantBody.innerHTML = "";
  _voice.pendingAssistantBody.appendChild(pill);
  _voice.thinkingPill = pill;
  scrollToBottom();
  // Wait for MediaRecorder's stop event so the audio buffer is finalized.
  // (We don't always upload it — see below — but stopping releases the mic.)
  await new Promise(res => {
    rec.addEventListener("stop", res, {once: true});
    rec.stop();
  });
  els.micBtn?.classList.remove("recording");
  els.micBtn?.classList.add("busy");
  const blob = new Blob(_voice.chunks, {type: rec.mimeType || "audio/webm"});
  _voice.rec = null;
  if (!state.conversationId) {
    await newConversation();
    if (!state.conversationId) { els.micBtn?.classList.remove("busy"); return; }
  }

  // Decision: fast-path or fallback?
  //   • Browser already has the transcript → POST text to /voice/say
  //     (no Whisper, no audio upload — saves ~500ms–2s per turn).
  //   • Browser had nothing (Firefox, mic permission issue, very quiet) →
  //     POST the audio blob to /voice/turn so server Whisper can recover it.
  if (previewText) {
    await _consumeVoiceSay(previewText);
  } else {
    const filename = (blob.type || "").includes("webm") ? "voice.webm"
                    : (blob.type || "").includes("ogg") ? "voice.ogg"
                    : (blob.type || "").includes("mp4") ? "voice.mp4"
                    : "voice.wav";
    await _consumeVoiceTurn(blob, filename);
  }
  els.micBtn?.classList.remove("busy");
}


// Fast push-to-talk path: hand the LLM the browser's transcript verbatim, get
// the merged SSE back (LLM chunks + TTS audio). Same event shape as
// _consumeVoiceTurn so the UI handlers are identical — just a different URL
// and a JSON body instead of multipart audio.
async function _consumeVoiceSay(text) {
  const convId = state.conversationId;
  let assistantEl = _voice.pendingAssistantEl;
  let body = _voice.pendingAssistantBody;
  let contentEl = null;
  let assistantText = "";
  _voice.audioCursor = 0;
  _voice.streamEnded = false;
  const ac = new AbortController();
  _voice.abort = ac;
  if (els.voiceStopBtn) els.voiceStopBtn.hidden = false;
  try {
    const res = await fetch(`/api/conversations/${convId}/voice/say`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      signal: ac.signal,
      body: JSON.stringify({text}),
    });
    if (!res.ok || !res.body) {
      throw new Error(await res.text().catch(() => `HTTP ${res.status}`));
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        let ev;
        try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
        if (ev.transcript != null) {
          // The server echoed our transcript back — undim the user bubble
          // (it was already rendered with the right text on release).
          if (_voice.pendingUserEl) {
            _voice.pendingUserEl.classList.remove("voice-pending");
          }
          _voice.pendingUserMsg = null;
          _voice.pendingUserEl = null;
        } else if (ev.status) {
          if (_voice.thinkingPill) {
            const labels = {
              "transcribing":        "🎙 Transcribing…",
              "searching_knowledge": "📚 Searching knowledge…",
              "thinking":            "💭 Thinking…",
            };
            _voice.thinkingPill.textContent = labels[ev.status] || `· ${ev.status}…`;
          }
        } else if (ev.error) {
          assistantText += `\n\n**Error:** ${ev.error}`;
          if (assistantEl && body) {
            if (!contentEl) { body.innerHTML = ""; contentEl = document.createElement("div"); body.appendChild(contentEl); }
            contentEl.innerHTML = render(assistantText);
          } else {
            alert(`Voice turn failed: ${ev.error}`);
          }
        } else if (ev.chunk != null && body) {
          if (_voice.thinkingPill) {
            _voice.thinkingPill.remove();
            _voice.thinkingPill = null;
          }
          assistantText += ev.chunk;
          if (!contentEl) { body.innerHTML = ""; contentEl = document.createElement("div"); body.appendChild(contentEl); }
          contentEl.innerHTML = render(assistantText);
          scrollToBottom();
        } else if (ev.audio_chunk_b64) {
          _enqueueAudioChunk(ev.audio_chunk_b64, ev.sample_rate || 22050);
        } else if (ev.end) {
          break;
        }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      alert(`Voice turn failed: ${e.message}`);
    }
  } finally {
    _voice.abort = null;
    // Mark the SSE done — the stop button stays visible until the audio
    // queue actually drains. _enqueueAudioChunk's onended handler calls
    // _maybeHideVoiceStop() each time a buffer source finishes.
    _voice.streamEnded = true;
    _maybeHideVoiceStop();
    els.voicePreview?.classList.remove("sending");
    _setVoicePreview("");
    _voice.pendingUserEl = null;
    _voice.pendingUserMsg = null;
    _voice.pendingAssistantEl = null;
    _voice.pendingAssistantBody = null;
    if (_voice.thinkingPill) {
      _voice.thinkingPill.remove();
      _voice.thinkingPill = null;
    }
    if (assistantEl) {
      assistantEl.classList.remove("cursor");
      if (contentEl) { contentEl.innerHTML = render(assistantText); highlightCodeBlocks(contentEl); }
      state.messages.push({role: "assistant", content: assistantText});
      loadConversations();
    }
  }
}


// Render the merged SSE from /voice/turn — three event kinds:
//   {transcript}        → render a user message bubble with that text
//   {chunk}             → assistant text token (one chat bubble streams in)
//   {audio_chunk_b64}   → push into the Web Audio playback queue
async function _consumeVoiceTurn(blob, filename) {
  const convId = state.conversationId;
  // Reuse the bubbles _stopRecordingAndSend already rendered so the
  // conversation feels instant. Fall back to creating them lazily for
  // legacy callers (none right now).
  let assistantEl = _voice.pendingAssistantEl;
  let body = _voice.pendingAssistantBody;
  let contentEl = null;
  let assistantText = "";
  _voice.audioCursor = 0;
  _voice.streamEnded = false;
  const ac = new AbortController();
  _voice.abort = ac;
  // Show the stop button up front — the user might want to cancel during
  // ASR or LLM streaming, not just TTS playback. _stopVoicePlayback() calls
  // ac.abort() which propagates through the fetch below.
  if (els.voiceStopBtn) els.voiceStopBtn.hidden = false;
  try {
    const fd = new FormData();
    fd.append("audio", blob, filename);
    const res = await fetch(`/api/conversations/${convId}/voice/turn`, {
      method: "POST", body: fd, signal: ac.signal,
    });
    if (!res.ok || !res.body) {
      throw new Error(await res.text().catch(() => `HTTP ${res.status}`));
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});
      const parts = buf.split("\n\n");
      buf = parts.pop() || "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        let ev;
        try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
        if (ev.transcript != null) {
          // Authoritative Whisper transcript arrived — replace whatever the
          // browser's SpeechRecognition put in the user bubble.
          const text = ev.transcript || "";
          if (_voice.pendingUserMsg) {
            _voice.pendingUserMsg.content = text;
            if (_voice.pendingUserEl) {
              _voice.pendingUserEl.classList.remove("voice-pending");
              const ub = _voice.pendingUserEl.querySelector(".msg-body");
              if (ub) ub.textContent = text;
            }
            _voice.pendingUserMsg = null;
            _voice.pendingUserEl = null;
          } else {
            const userMsg = {role: "user", content: text};
            state.messages.push(userMsg);
            renderMessage(userMsg);
          }
          // Assistant bubble was pre-created with a "Transcribing…" pill.
          // The transcript arriving means transcription is *done* — so move
          // the pill to "Thinking" right now rather than waiting for the
          // server's next {status} event. If the server later upgrades to
          // {status: "searching_knowledge"}, that overrides this.
          if (_voice.thinkingPill) {
            _voice.thinkingPill.textContent = "💭 Thinking…";
          }
          scrollToBottom();
        } else if (ev.status) {
          if (_voice.thinkingPill) {
            const labels = {
              "transcribing":        "🎙 Transcribing…",
              "searching_knowledge": "📚 Searching knowledge…",
              "thinking":            "💭 Thinking…",
            };
            _voice.thinkingPill.textContent = labels[ev.status] || `· ${ev.status}…`;
          }
        } else if (ev.error) {
          assistantText += `\n\n**Error:** ${ev.error}`;
          if (assistantEl && body) {
            if (!contentEl) { body.innerHTML = ""; contentEl = document.createElement("div"); body.appendChild(contentEl); }
            contentEl.innerHTML = render(assistantText);
          } else {
            alert(`Voice turn failed: ${ev.error}`);
          }
        } else if (ev.chunk != null && body) {
          // First text chunk replaces the thinking pill with real content.
          if (_voice.thinkingPill) {
            _voice.thinkingPill.remove();
            _voice.thinkingPill = null;
          }
          assistantText += ev.chunk;
          if (!contentEl) { body.innerHTML = ""; contentEl = document.createElement("div"); body.appendChild(contentEl); }
          contentEl.innerHTML = render(assistantText);
          scrollToBottom();
        } else if (ev.audio_chunk_b64) {
          _enqueueAudioChunk(ev.audio_chunk_b64, ev.sample_rate || 22050);
        } else if (ev.end) {
          break;
        }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      alert(`Voice turn failed: ${e.message}`);
    }
  } finally {
    _voice.abort = null;
    // SSE done — but audio playback may still be in flight. The stop button
    // stays visible until the audio queue drains (see _maybeHideVoiceStop).
    _voice.streamEnded = true;
    _maybeHideVoiceStop();
    els.voicePreview?.classList.remove("sending");
    _setVoicePreview("");
    // Clean up the pre-created refs — release ended, the bubbles are now
    // either populated (assistantText present) or empty (turn cancelled).
    _voice.pendingUserEl = null;
    _voice.pendingUserMsg = null;
    _voice.pendingAssistantEl = null;
    _voice.pendingAssistantBody = null;
    if (_voice.thinkingPill) {
      _voice.thinkingPill.remove();
      _voice.thinkingPill = null;
    }
    if (assistantEl) {
      assistantEl.classList.remove("cursor");
      if (contentEl) { contentEl.innerHTML = render(assistantText); highlightCodeBlocks(contentEl); }
      // Stash the assistant message so a re-render keeps it.
      state.messages.push({role: "assistant", content: assistantText});
      loadConversations();   // refresh sidebar list + Bots-page card freshness
    }
  }
}


function initMicButton() {
  // Wire the stop-audio button regardless of whether mic-btn is in the DOM —
  // it stops playback for both push-to-talk and (future) call-mode audio.
  if (els.voiceStopBtn) {
    els.voiceStopBtn.addEventListener("click", e => {
      e.preventDefault();
      _stopVoicePlayback();
    });
  }
  const btn = els.micBtn;
  if (!btn) return;
  // Press-and-hold gestures. Also tolerate click (toggle) for accessibility.
  const onPress = e => {
    if (btn.hidden || btn.disabled) return;
    e.preventDefault();
    if (_voice.pressed) return;   // already capturing
    _voice.pressed = true;
    _startRecording();
  };
  const onRelease = e => {
    if (!_voice.pressed) return;
    e?.preventDefault?.();
    _voice.pressed = false;
    _stopRecordingAndSend();
  };
  btn.addEventListener("mousedown", onPress);
  btn.addEventListener("touchstart", onPress, {passive: false});
  // Releasing anywhere counts — user may slide off the button.
  document.addEventListener("mouseup", onRelease);
  document.addEventListener("touchend", onRelease);
  document.addEventListener("touchcancel", onRelease);
  // Keyboard accessibility: Space toggles.
  btn.addEventListener("keydown", e => {
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      _voice.pressed ? onRelease() : onPress(e);
    }
  });
}


// =====================================================================
// Call mode (continuous duplex audio over WebRTC)
// =====================================================================
//
// Click 📞 → handshake with the voice service's FastRTC stream; the browser
// pipes mic audio to it, plays its reply audio inline, and renders transcript
// + assistant tokens as they arrive on the WebRTC DataChannel. Click again to
// hang up. Interrupt-able mid-reply (FastRTC's ReplyOnPause handles barge-in
// server-side; on our side, a fresh `{transcript}` event finalizes the
// previous assistant bubble and opens a new one).

const _call = {
  pc: null,                // RTCPeerConnection
  audioEl: null,           // <audio> playing the remote stream
  events: null,            // EventSource — SSE stream of {transcript}/{chunk}/{end}
  webrtcId: null,          // server-side session id we issued for this call
  micStream: null,         // MediaStream from getUserMedia
  state: "idle",           // idle | dialing | talking | hanging-up
  // Current in-progress assistant bubble being streamed:
  assistantEl: null,
  assistantBody: null,
  assistantContentEl: null,
  assistantText: "",       // full text received so far (target)
  assistantRendered: 0,    // characters actually painted into the DOM
  renderRaf: 0,            // requestAnimationFrame handle (0 = not pumping)
};


// Cloud LLMs (deepseek, openai, etc.) batch multiple tokens per HTTP frame —
// the SSE stream arrives in bursts: 5-10 chunks in a tight ms-scale window,
// then 100-300ms of nothing, repeat. Re-rendering the bubble on every chunk
// reproduces that rhythm visually as smooth-then-pause-then-smooth.
//
// This typewriter pump decouples the DOM update rate from the network arrival
// rate. _call.assistantText is the "target" (everything we've received).
// _call.assistantRendered is what's currently painted. A requestAnimationFrame
// loop drips characters from one to the other; bursts queue, gaps drain.
//
// CATCH_UP_RATIO tunes how aggressively we catch up when we fall behind:
// 1/12 means we'll paint roughly 1/12 of the gap each frame (~60fps), which
// drains a 50-char burst in about 0.5s — fast enough to feel responsive,
// slow enough that the burst doesn't visibly re-create the stutter.
const _CALL_RENDER_CHARS_MIN  = 1;   // always paint at least 1 char/frame while pumping
const _CALL_RENDER_CHARS_MAX  = 8;   // cap so we don't burst the whole queue in one frame
const _CALL_RENDER_CATCH_UP   = 12;  // gap fraction painted per frame


function _pumpCallTypewriter() {
  _call.renderRaf = 0;
  if (!_call.assistantContentEl) return;
  const target = _call.assistantText.length;
  const current = _call.assistantRendered;
  if (current >= target) return;
  const gap = target - current;
  // The further behind we are, the larger the step — keeps text smooth
  // during a slow stream while still draining big bursts in a half-second.
  const step = Math.min(
    _CALL_RENDER_CHARS_MAX,
    Math.max(_CALL_RENDER_CHARS_MIN, Math.ceil(gap / _CALL_RENDER_CATCH_UP)),
  );
  _call.assistantRendered = current + step;
  _call.assistantContentEl.innerHTML = render(
    _call.assistantText.slice(0, _call.assistantRendered),
  );
  scrollToBottom();
  if (_call.assistantRendered < _call.assistantText.length) {
    _call.renderRaf = requestAnimationFrame(_pumpCallTypewriter);
  }
}


function _finalizeCallAssistantBubble() {
  if (!_call.assistantEl) return;
  // Cancel any in-flight typewriter pump and flush the final text in one
  // shot — the turn is over, no reason to keep dripping characters when
  // the bubble is being finalized (the user might re-open the chat right
  // after hanging up and we want the full reply there immediately).
  if (_call.renderRaf) {
    cancelAnimationFrame(_call.renderRaf);
    _call.renderRaf = 0;
  }
  _call.assistantEl.classList.remove("cursor");
  if (_call.assistantContentEl) {
    _call.assistantContentEl.innerHTML = render(_call.assistantText);
    highlightCodeBlocks(_call.assistantContentEl);
  }
  if (_call.assistantText.trim()) {
    state.messages.push({role: "assistant", content: _call.assistantText});
    const finalIndex = state.messages.length - 1;
    _call.assistantEl.dataset.index = String(finalIndex);
    _appendEditButton(_call.assistantEl, finalIndex);
  } else {
    // Empty bubble — never got any chunks. Remove it.
    _call.assistantEl.remove();
  }
  _call.assistantEl = null;
  _call.assistantBody = null;
  _call.assistantContentEl = null;
  _call.assistantText = "";
  _call.assistantRendered = 0;
}


// Per-stage status labels with emoji prefixes — server emits the raw stage,
// browser maps to the user-facing string. `null` hides the pill.
const _CALL_STATUS_LABELS = {
  connecting:   "🔌 Connecting…",
  listening:    "🎙 Listening…",
  transcribing: "✍ Transcribing…",
  thinking:     "💭 Thinking…",
  speaking:     "🔊 Speaking…",
};


function _setCallStatus(stage) {
  if (!els.callStatus) return;
  const label = stage ? (_CALL_STATUS_LABELS[stage] || stage) : "";
  if (!label) {
    els.callStatus.hidden = true;
    els.callStatus.textContent = "";
    return;
  }
  els.callStatus.hidden = false;
  els.callStatus.textContent = label;
}


function _onCallDataEvent(ev) {
  if (ev.error) {
    // Don't tear down the whole call on a single-sentence TTS hiccup — just
    // surface the error. The server keeps streaming the next sentence.
    console.warn("voice service event error:", ev.error);
  }
  if (ev.status) {
    _setCallStatus(ev.status);
  }
  if (ev.transcript != null) {
    // Finalize any previous (possibly interrupted) assistant bubble before
    // starting the new turn.
    _finalizeCallAssistantBubble();
    const userMsg = {role: "user", content: ev.transcript};
    state.messages.push(userMsg);
    renderMessage(userMsg);
    _call.assistantEl = renderMessage({role: "assistant", content: ""});
    _call.assistantBody = _call.assistantEl.querySelector(".msg-body");
    _call.assistantEl.classList.add("cursor");
    _call.assistantText = "";
    scrollToBottom();
    return;
  }
  if (ev.chunk != null && _call.assistantEl) {
    // Append to the "target" text but DON'T re-render the bubble here.
    // The requestAnimationFrame typewriter pump (above) renders at a steady
    // ~60fps cadence regardless of how bursty the upstream is, so a 10-token
    // batch arriving in 1ms is dripped into the DOM as 10 frames instead of
    // a single jarring repaint followed by a 200ms gap.
    _call.assistantText += ev.chunk;
    if (!_call.assistantContentEl) {
      _call.assistantBody.innerHTML = "";
      _call.assistantContentEl = document.createElement("div");
      _call.assistantBody.appendChild(_call.assistantContentEl);
    }
    if (!_call.renderRaf) {
      _call.renderRaf = requestAnimationFrame(_pumpCallTypewriter);
    }
    return;
  }
  if (ev.end) {
    _finalizeCallAssistantBubble();
    loadConversations();   // keep the sidebar list fresh
    return;
  }
}


async function _startCall() {
  if (_call.state !== "idle") return;
  _call.state = "dialing";
  els.callBtn.classList.add("calling");
  // Show "Connecting…" until the WebRTC peer connection actually establishes
  // and the voice server is ready to receive audio. Once the connectionstate
  // listener (below) flips to "connected", we switch the pill to "Listening".
  // Otherwise the UI says "Listening" while the call is still in the multi-
  // second WebRTC handshake / model-warmup window — misleading the user
  // into talking before the pipeline can hear them.
  _setCallStatus("connecting");

  const voiceBackend = (backendCache || []).find(b => b.kind === "voice" && b.enabled);
  if (!voiceBackend) {
    _endCall();
    alert("No voice backend configured. Add one in Settings → + Add endpoint (kind=Voice).");
    return;
  }

  if (!state.conversationId) {
    await newConversation();
    if (!state.conversationId) { _endCall(); return; }
  }

  // Read the bot's voice prefs (if any) from the persisted conv. The server
  // proxy will fill in defaults from /voices if these are empty.
  let convVoice = "", convLang = "en";
  try {
    const conv = await fetch(`/api/conversations/${state.conversationId}`).then(r => r.json());
    const vs = (conv && conv.voice_settings) || {};
    convVoice = vs.voice_id || "";
    convLang = vs.language || "en";
  } catch (_) {}

  // All three signaling calls go through MiniClosedAI (same origin = HTTPS).
  // This avoids the "Mixed Content" block browsers slap on HTTP fetches from
  // an HTTPS page. The audio stream itself flows direct browser ↔ voice
  // container via WebRTC's UDP transport (not subject to mixed-content
  // policy) once the SDP exchange is done.
  const callBase = `/api/conversations/${state.conversationId}/call`;

  // 1. Tell the voice service which bot is being called. The server proxy
  //    fills in conv_id and the miniclosedai_url itself — the browser only
  //    sends voice/language preferences.
  try {
    const r = await fetch(`${callBase}/configure`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        voice: convVoice || null,
        language: convLang,
      }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text().catch(() => "")}`);
  } catch (e) {
    _endCall();
    alert(`Could not configure the call: ${e.message}`);
    return;
  }

  // 2. Grab the microphone.
  try {
    _call.micStream = await navigator.mediaDevices.getUserMedia({audio: true});
  } catch (e) {
    _endCall();
    alert(`Microphone access failed: ${e.message}`);
    return;
  }

  // 3. Build the peer connection + audio element + DataChannel.
  _call.pc = new RTCPeerConnection({
    iceServers: [{urls: "stun:stun.l.google.com:19302"}],
  });
  _call.micStream.getAudioTracks().forEach(t => _call.pc.addTrack(t, _call.micStream));

  // FastRTC's AudioCallback gates the entire input pump on a DataChannel
  // being ready (see wait_for_channel() in fastrtc/tracks.py) — without one
  // in the offer SDP, RTP audio arrives at aiortc but is never drained into
  // the VAD, and the handler never fires. The channel itself stays unused on
  // our side; events ride the SSE stream below.
  _call.dc = _call.pc.createDataChannel("text");

  _call.audioEl = document.createElement("audio");
  _call.audioEl.autoplay = true;
  _call.audioEl.playsInline = true;
  _call.audioEl.style.display = "none";
  document.body.appendChild(_call.audioEl);
  _call.pc.addEventListener("track", e => {
    if (e.streams && e.streams[0]) _call.audioEl.srcObject = e.streams[0];
  });

  _call.pc.addEventListener("connectionstatechange", () => {
    const s = _call.pc?.connectionState;
    if (s === "connected") {
      _call.state = "talking";
      // Audio is now actually flowing — flip the pill from "Connecting…"
      // to "Listening" so the user knows it's safe to speak. The server
      // will overwrite this with transcribing / thinking / speaking as
      // each pipeline stage takes over.
      _setCallStatus("listening");
    } else if (s === "failed" || s === "disconnected" || s === "closed") {
      if (_call.state !== "hanging-up" && _call.state !== "idle") _endCall();
    }
  });

  // 4. SDP offer/answer with the voice service. FastRTC keys its per-session
  //    state on a client-supplied webrtc_id, so we generate one here and reuse
  //    it for the lifetime of this call.
  const webrtcId = (crypto.randomUUID && crypto.randomUUID())
    || `call-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  _call.webrtcId = webrtcId;
  try {
    await _call.pc.setLocalDescription(await _call.pc.createOffer());
    // Non-trickle ICE: wait until all candidates are gathered, then send the
    // *complete* SDP. FastRTC's /webrtc/offer doesn't support trickling, so a
    // partial offer would leave us with no usable candidates server-side.
    await _waitForIceGatheringComplete(_call.pc, 3000);
    const local = _call.pc.localDescription;
    const r = await fetch(`${callBase}/offer`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({sdp: local.sdp, type: local.type, webrtc_id: webrtcId}),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text().catch(() => "")}`);
    const answer = await r.json();
    await _call.pc.setRemoteDescription(answer);
  } catch (e) {
    _endCall();
    alert(`Call failed: ${e.message}`);
    return;
  }

  // 5. Subscribe to the server's AdditionalOutputs stream (transcript /
  //    chunk / end / error). FastRTC keeps these in an internal queue keyed
  //    by webrtc_id; the SSE endpoint forwards them to us.
  try {
    _call.events = new EventSource(`${callBase}/events/${webrtcId}`);
    _call.events.onmessage = e => {
      let ev;
      try { ev = JSON.parse(e.data); } catch { return; }
      _onCallDataEvent(ev);
    };
    _call.events.onerror = () => {
      // EventSource will auto-reconnect; we only care if the call itself ended.
      if (_call.state === "idle" || _call.state === "hanging-up") {
        try { _call.events?.close(); } catch (_) {}
      }
    };
  } catch (e) {
    console.warn("Could not open call events stream:", e);
  }
}


function _waitForIceGatheringComplete(pc, timeoutMs) {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise(resolve => {
    let done = false;
    const finish = () => { if (done) return; done = true; resolve(); };
    const handler = () => { if (pc.iceGatheringState === "complete") finish(); };
    pc.addEventListener("icegatheringstatechange", handler);
    // Hard timeout — some networks never reach "complete"; the SDP we have
    // already has *some* candidates, send it and let the other side cope.
    setTimeout(finish, timeoutMs || 3000);
  });
}


function _endCall() {
  _call.state = "hanging-up";
  _finalizeCallAssistantBubble();
  if (_call.events) {
    try { _call.events.close(); } catch (_) {}
    _call.events = null;
  }
  if (_call.pc) {
    try { _call.pc.close(); } catch (_) {}
    _call.pc = null;
  }
  if (_call.micStream) {
    _call.micStream.getTracks().forEach(t => { try { t.stop(); } catch (_) {} });
    _call.micStream = null;
  }
  if (_call.audioEl) {
    _call.audioEl.srcObject = null;
    try { _call.audioEl.remove(); } catch (_) {}
    _call.audioEl = null;
  }
  _call.webrtcId = null;
  els.callBtn?.classList.remove("calling");
  _setCallStatus(null);
  _call.state = "idle";
}


function initCallButton() {
  if (!els.callBtn) return;
  els.callBtn.addEventListener("click", () => {
    if (_call.state === "idle") _startCall();
    else _endCall();
  });
}


// ---------- API code modal ----------
// Each conversation is a saved microservice: its model, system prompt, and
// sampling params are locked server-side. The snippet only needs to supply
// the message (or the messages list, for multi-turn).
// _modalConvId overrides state.conversationId for the API code modal, used
// when the modal was opened from a bot card's `</>` button on the Bots list.
// Cleared in closeModal so a subsequent topbar open uses the live conversation.
let _modalConvId = null;

// API token baked into copied snippets when authentication is enabled — so a
// pasted snippet works immediately instead of landing in the "connections
// needing attention" list. Refreshed on every modal open (cheap, and stays
// correct across token regeneration). null = auth off → snippets unchanged.
let _apiCodeToken = null;
async function _refreshApiCodeToken() {
  const before = _apiCodeToken;
  _apiCodeToken = null;
  try {
    if (_authState.enabled && _authState.loggedIn) {
      const r = await fetch("/api/auth/token");
      if (r.ok) _apiCodeToken = (await r.json()).api_token || null;
    }
  } catch (e) {}
  if (_apiCodeToken !== before) paintSnippet();   // repaint if it changed mid-open
}

function buildCodeSnippet(tab, mode, style) {
  const base = window.location.origin;
  const convId = _modalConvId != null ? _modalConvId : state.conversationId;
  if (!convId) {
    return "# Send a message first to create a conversation.\n# Each chat becomes its own configured API endpoint.";
  }
  if (style === "openai") return buildOpenAISnippet(tab, mode, base, convId);
  return buildNativeSnippet(tab, mode, base, convId);
}

// Open the API-code modal scoped to a specific conv id, regardless of which
// bot (if any) is currently the active selection. Called from the row `</>`
// button on bot cards. Doesn't disturb state.conversationId.
async function openApiCodeForConv(convId) {
  if (convId == null) return;
  // flushPendingSave keeps the snippet's params in sync with the GUI for the
  // *currently open* bot. For a non-current bot we skip the flush — its saved
  // params are already on disk and the snippet renders from server state.
  _modalConvId = convId;
  paintSnippet();
  els.modalBackdrop.classList.remove("hidden");
  _refreshApiCodeToken();   // repaints with the bearer once fetched (auth on)
}

function buildNativeSnippet(tab, mode, base, convId) {
  const msg = "Hello!";
  const tok = _apiCodeToken;
  const streamUrl = `${base}/api/conversations/${convId}/chat/stream`;
  const syncUrl = `${base}/api/conversations/${convId}/chat`;
  const header = `# Chat #${convId}. Config (model, system prompt, temperature, max_tokens,\n# top_p, top_k, thinking) is set in the GUI — this call only supplies the message.`;
  // Auth (when enabled): the copied code carries the instance's API token so
  // it authenticates immediately instead of tripping the grace-mode alerts.
  const curlAuth = tok ? `\n  -H "Authorization: Bearer ${tok}" \\` : "";
  const pyHeaders = tok ? `\nHEADERS = {"Authorization": "Bearer ${tok}"}` : "";
  const pyKw = tok ? ", headers=HEADERS" : "";
  const jsAuth = tok ? `, "Authorization": "Bearer ${tok}"` : "";

  // ---- cURL ----
  if (tab === "curl") {
    if (mode === "stream") {
      return `${header}
curl -N -X POST ${streamUrl} \\
  -H "Content-Type: application/json" \\${curlAuth}
  -d '{"message": "${msg}"}'`;
    }
    return `${header}
curl -X POST ${syncUrl} \\
  -H "Content-Type: application/json" \\${curlAuth}
  -d '{"message": "${msg}"}'`;
  }

  // ---- Python ----
  if (tab === "python") {
    if (mode === "stream") {
      return `import json
import requests

URL = "${streamUrl}"${pyHeaders}

with requests.post(URL, json={"message": "${msg}"}, stream=True, timeout=None${pyKw}) as r:
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue  # SSE keep-alives are empty lines
        if line.startswith("data:"):
            data = json.loads(line[5:].strip())
            if "chunk" in data:
                print(data["chunk"], end="", flush=True)
            if data.get("end"):
                break`;
    }
    return `import requests

URL = "${syncUrl}"${pyHeaders}

response = requests.post(URL, json={"message": "${msg}"}, timeout=120${pyKw}).json()
print(response["response"])`;
  }

  // ---- JavaScript ----
  if (tab === "js") {
    if (mode === "stream") {
      return `const res = await fetch("${streamUrl}", {
  method: "POST",
  headers: { "Content-Type": "application/json"${jsAuth} },
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
  headers: { "Content-Type": "application/json"${jsAuth} },
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
  const tok = _apiCodeToken;
  const url = `${base}/v1/chat/completions`;
  const header = `# OpenAI-compatible. Use the conversation ID as 'model'. The bot's saved
# config (model, system prompt, temperature, etc.) is the source of truth —
# any caller-provided sampling params are ignored by the server.`;
  const curlAuth = tok ? `\n  -H "Authorization: Bearer ${tok}" \\` : "";
  // With auth enabled the token IS the OpenAI api_key; otherwise any string works.
  const sdkKey = tok || "not-required";

  // ---- cURL ----
  if (tab === "curl") {
    if (mode === "stream") {
      return `${header}
curl -N -X POST ${url} \\
  -H "Content-Type: application/json" \\${curlAuth}
  -d '{
    "model": "${convId}",
    "messages": [{"role":"user","content":"${msg}"}],
    "stream": true
  }'`;
    }
    return `${header}
curl -X POST ${url} \\
  -H "Content-Type: application/json" \\${curlAuth}
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
client = OpenAI(base_url="${base}/v1", api_key="${sdkKey}")

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

client = OpenAI(base_url="${base}/v1", api_key="${sdkKey}")

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
  apiKey: "${sdkKey}",
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
  apiKey: "${sdkKey}",
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
  _updateModalBotId();
}

// Sync the "Bot #N" pill in the modal header with whichever conv the modal
// is currently scoped to (row-opened or topbar-opened). Disables the pill
// when no conv exists so a misclick can't copy a stale id.
function _updateModalBotId() {
  if (!els.modalBotId) return;
  const convId = _modalConvId != null ? _modalConvId : state.conversationId;
  if (convId != null) {
    els.modalBotId.textContent = `Bot #${convId}`;
    if (els.copyBotId) els.copyBotId.disabled = false;
  } else {
    els.modalBotId.textContent = "Bot #—";
    if (els.copyBotId) els.copyBotId.disabled = true;
  }
}

async function openModal() {
  // Make sure the server's saved config matches the sidebar before the user
  // copies a snippet that hits the conversation endpoint. Without this, a
  // pending 350ms debounce could leave the server on stale params.
  await flushPendingSave();
  paintSnippet();
  els.modalBackdrop.classList.remove("hidden");
  _refreshApiCodeToken();   // repaints with the bearer once fetched (auth on)
}
function closeModal() {
  els.modalBackdrop.classList.add("hidden");
  _modalConvId = null;  // next regular open uses state.conversationId again
}

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
  if (els.copyBotId) {
    els.copyBotId.addEventListener("click", async () => {
      const convId = _modalConvId != null ? _modalConvId : state.conversationId;
      if (convId == null) return;
      const ok = await copyToClipboard(String(convId));
      if (!ok) return;
      // Brief flip to "Copied!" — same pattern as the main Copy button so the
      // feedback feels consistent across the modal.
      const orig = els.modalBotId.textContent;
      els.copyBotId.classList.add("copied");
      els.modalBotId.textContent = "Copied!";
      setTimeout(() => {
        els.copyBotId.classList.remove("copied");
        els.modalBotId.textContent = orig;
      }, 1200);
    });
  }
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
  bindDownloadMenu();
  els.deleteChatBtn.addEventListener("click", deleteCurrentConversation);
  els.stopBtn.addEventListener("click", () => {
    if (state.abortController) state.abortController.abort();
    // Generation now runs server-side independent of this SSE connection, so
    // aborting the fetch only stops *watching*. Tell the server to truly cancel
    // the background task (it persists whatever partial reply it produced).
    if (state.streamConvId != null) {
      fetch(`/api/conversations/${state.streamConvId}/generation/cancel`, { method: "POST" }).catch(() => {});
    }
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

// Three export formats are available — see /api/conversations/{id}/export.csv,
// .../export.zip, and .../export.classify.zip. The icon button opens a small
// popover; clicking any menu item triggers the corresponding download via
// Content-Disposition.
const _DOWNLOAD_PATHS = {
  csv:                "export.csv",                  // text-only input,output CSV
  zip:                "export.zip",                  // multimodal SFT (JSONL + images)
  classify:           "export.classify.zip",         // image-classification (CSV + images)
  "bot-config":       "export?include_history=false",        // portable config-only JSON
  "bot-with-history": "export?include_history=true",         // portable config + messages
};

function _downloadCurrentConversation(format) {
  if (!state.conversationId) {
    alert("Save at least one exchange to this conversation before exporting.");
    return;
  }
  const path = _DOWNLOAD_PATHS[format] || _DOWNLOAD_PATHS.csv;
  const a = document.createElement("a");
  a.href = `/api/conversations/${state.conversationId}/${path}`;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function _toggleDownloadMenu(force) {
  const btn = els.downloadCsvBtn;
  const menu = document.getElementById("download-menu");
  if (!btn || !menu) return;
  const willOpen = force != null ? force : menu.hasAttribute("hidden");
  if (willOpen) {
    menu.removeAttribute("hidden");
    btn.setAttribute("aria-expanded", "true");
  } else {
    menu.setAttribute("hidden", "");
    btn.setAttribute("aria-expanded", "false");
  }
}

// Bound from bindChat(): clicking the tray icon opens the menu; clicking
// outside closes it; clicking a menu item triggers the corresponding
// download and closes the menu. Replaces the old direct-CSV behavior.
function bindDownloadMenu() {
  const menu = document.getElementById("download-menu");
  if (!menu) return;
  els.downloadCsvBtn.addEventListener("click", e => {
    e.stopPropagation();
    _toggleDownloadMenu();
  });
  menu.addEventListener("click", e => {
    const item = e.target.closest('.download-menu-item[data-format]');
    if (!item) return;
    e.stopPropagation();
    _toggleDownloadMenu(false);
    _downloadCurrentConversation(item.dataset.format);
  });
  document.addEventListener("click", e => {
    if (menu.contains(e.target) || els.downloadCsvBtn.contains(e.target)) return;
    _toggleDownloadMenu(false);
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") _toggleDownloadMenu(false);
  });
}

// Delete any conv by id, with the right post-delete behavior depending on
// whether it was the currently-open bot or just one in the list:
//   - clears in-memory state if id === state.conversationId
//   - drops the id from _streaming/_unread so a stale dot doesn't linger
//   - reloads the bots list
//   - if the deleted bot was open: opens the next-most-recent OR goes to
//     the Bots home if the list is now empty
// Returns true if the delete went through, false if cancelled or failed.
async function deleteConvById(id, opts = {}) {
  if (id == null) return false;
  const title = opts.title || "this bot";
  const ok = opts.skipConfirm || await uiConfirm({
    title: "Delete bot",
    message: `Delete "${title}"? This cannot be undone.`,
    okText: "Delete",
    danger: true,
  });
  if (!ok) return false;
  const r = await fetch(`/api/conversations/${id}`, { method: "DELETE" });
  if (!r.ok) { alert("Failed to delete bot."); return false; }

  const wasOpen = (id === state.conversationId);
  _streaming.delete(id);
  _unread.delete(id);
  if (wasOpen) {
    state.conversationId = null;
    state.messages = [];
    renderMessages();
  }
  const list = await loadConversations();
  if (wasOpen) {
    if (list.length) {
      await openConversation(list[0].id);
    } else {
      // No bots left — fall back to the Bots home so the user sees the empty
      // state with a clear "+ New bot" affordance instead of an empty chat.
      applyActivePage("bots");
    }
  }
  return true;
}

async function deleteCurrentConversation() {
  if (!state.conversationId) return;
  await deleteConvById(state.conversationId);
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
  // Native title (matches the other activity-bar items + avoids the custom
  // tooltip clipping off the left edge of the narrow activity bar).
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
  els.sidebarToggle.dataset.tooltip = collapsed ? "Show sidebar" : "Hide sidebar";
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
  _refreshMicAffordance();
  _refreshVoicePickerAffordance();
  return backendCache;
}

// Show the push-to-talk mic button only when at least one enabled voice
// backend is registered. Hidden by default so users without a voice service
// see no dead UI.
function _refreshMicAffordance() {
  if (!els.micBtn) return;
  const hasVoice = (backendCache || []).some(b => b.kind === "voice" && b.enabled);
  els.micBtn.hidden = !hasVoice;
  _refreshCallAffordance();
}

// Show the 📞 button only when a voice backend is registered AND we're on a
// secure context (WebRTC requires it). On plain-HTTP LAN access, the button
// stays hidden so users don't get a confusing failure when they click.
function _refreshCallAffordance() {
  if (!els.callBtn) return;
  const hasVoice = (backendCache || []).some(b => b.kind === "voice" && b.enabled);
  const secure = window.isSecureContext;
  els.callBtn.hidden = !(hasVoice && secure);
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

  // Delete is allowed on every backend now — including the built-in. The
  // `deleteBackend` helper handles the extra confirms and the `?force=true`
  // flag the server requires for the built-in case.
  const deleteBtn = document.createElement("button");
  deleteBtn.className = "btn btn-small";
  deleteBtn.textContent = "Delete";
  deleteBtn.addEventListener("click", () => deleteBackend(b));
  actions.appendChild(deleteBtn);

  top.appendChild(actions);
  card.appendChild(top);

  if (b.kind === "ollama" && b.enabled && _ollamaAllowsPull(b)) {
    card.appendChild(_renderPullSection(b));
  }
  return card;
}

// Hostnames known to forward `/api/chat` but reject `/api/pull` (typically
// authenticating relays where models live on someone else's disk and only
// inference is exposed). Substring match so `.com` and `.ai` variants both
// hit; lowercased before comparison.
const _OLLAMA_PULL_DENY_HOST_FRAGMENTS = ["app.interdataresearch"];

// Pull is allowed by default for any Ollama backend the user has registered
// — if they added it, they likely admin the target machine. The denylist
// above suppresses the form for known relay providers where attempting a
// pull would 403 on every keystroke.
function _ollamaAllowsPull(b) {
  let host;
  try { host = new URL(b.base_url).hostname.toLowerCase(); } catch { return false; }
  for (const frag of _OLLAMA_PULL_DENY_HOST_FRAGMENTS) {
    if (host.includes(frag)) return false;
  }
  return true;
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
  // Built-in deletion needs an extra-stern first confirm (the action is
  // unusual and survives across restarts only when at least one other backend
  // remains in the table — see `db.init_db`). It also requires `?force=true`
  // server-side, which we always set for the built-in case below.
  const isBuiltin = !!b.is_builtin;
  const opening = isBuiltin
    ? `Delete the BUILT-IN endpoint "${b.name}"?\n\n` +
      `It will be re-seeded automatically only if you delete every other backend too.\n` +
      `In lite mode (or with another backend kept) it stays gone across restarts.`
    : `Delete endpoint "${b.name}"?`;
  if (!confirm(opening)) return;

  // For the built-in we always pass force=true (server requires it). For
  // non-built-ins we try without first to surface the bound-bots 409.
  const url = (extra) => `/api/backends/${b.id}${extra ? `?force=true` : ``}`;

  try {
    const firstUrl = isBuiltin ? url(true) : url(false);
    const r = await fetch(firstUrl, { method: "DELETE" });
    if (r.ok) {
      await renderSettingsPage();
      if (typeof loadModels === "function") await loadModels();
      return;
    }

    // Surface the rebind/cascade choice when the server reports 409 with a
    // bound-conversations list. (Built-in path already used force=true so
    // it won't hit this branch — its bound bots cascade-delete in one shot.)
    const body = await r.json().catch(() => ({}));
    const detail = body.detail;
    const bound = detail && Array.isArray(detail.bound_conversations) ? detail.bound_conversations : null;

    if (r.status === 409 && bound && bound.length) {
      const titles = bound.slice(0, 8).map(c => `  • ${c.title || `(conv ${c.id})`}`).join("\n");
      const more = bound.length > 8 ? `\n  …and ${bound.length - 8} more` : "";
      const cascadeOK = confirm(
        `"${b.name}" is still pinned by ${bound.length} bot(s):\n\n${titles}${more}\n\n` +
        `Cancel to rebind those bots manually first (recommended).\n` +
        `OK to delete the endpoint AND all ${bound.length} bot(s) — cannot be undone.`
      );
      if (!cascadeOK) return;
      if (!confirm(`Really delete ${bound.length} bot(s)? This is permanent.`)) return;
      const r2 = await fetch(url(true), { method: "DELETE" });
      if (!r2.ok) {
        const body2 = await r2.json().catch(() => ({}));
        alert("Force delete failed: " + (body2.detail?.message || body2.detail || `HTTP ${r2.status}`));
        return;
      }
      await renderSettingsPage();
      if (typeof loadModels === "function") await loadModels();
      return;
    }

    const msg = (detail && detail.message) || detail || `HTTP ${r.status}`;
    alert("Delete blocked: " + msg);
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

// "dashboard" is still a valid internal page — it's the chat surface — but it
// no longer has its own button in the activity bar. The Bots nav icon stays
// highlighted whether you're on the list (page=bots) or inside a chat
// (page=dashboard), reinforcing the parent/child relationship.
const VALID_PAGES = new Set(["dashboard", "bots", "settings", "logs", "apps", "app-detail",
                             "models", "voice-studio"]);
const _BOTS_AREA = new Set(["bots", "dashboard"]);
// The Apps nav-item owns both the applications list and a single app's detail.
const _APPS_AREA = new Set(["apps", "app-detail"]);
// Navigation hierarchy as a flat depth map. Drives the drill-in / drill-out
// animation: a transition into a DEEPER page (apps → app-detail → dashboard,
// or bots → dashboard) animates forward; a transition into a SHALLOWER page
// animates back; same-depth peer hops (activity-bar clicks between top-level
// pages) don't animate. Adding a new page = add it here and pick its depth.
const _PAGE_DEPTH = {
  bots: 0, apps: 0, logs: 0, settings: 0, models: 0, "voice-studio": 0,
  "app-detail": 1,
  dashboard: 2,
};

function applyActivePage(page) {
  const from = document.body.dataset.page;
  const p = VALID_PAGES.has(page) ? page : "bots";

  // Spatial drill-in / drill-out animation. Direction is derived from page
  // depth, not from a hard-coded bots-vs-dashboard pair, so EVERY drill-in
  // (apps → app-detail, app-detail → dashboard, bots → dashboard, etc.) and
  // every back step (back button or activity-bar climb-out) gets the same
  // animation treatment. The CSS keyframes live on body[data-page-transition].
  if (from && from !== p) {
    const fromDepth = _PAGE_DEPTH[from] ?? 0;
    const toDepth = _PAGE_DEPTH[p] ?? 0;
    if (fromDepth !== toDepth) {
      const dir = toDepth > fromDepth ? "forward" : "back";
      document.body.dataset.pageTransition = dir;
      // Clear after the keyframe duration so a future toggle re-fires it.
      setTimeout(() => {
        if (document.body.dataset.pageTransition === dir) {
          delete document.body.dataset.pageTransition;
        }
      }, 240);
    }
  }

  document.body.dataset.page = p;
  document.querySelectorAll(".activity-bar .nav-item[data-page]").forEach(btn => {
    // The Bots nav-item owns BOTH the bots list and the chat (dashboard); the
    // Apps nav-item owns both the apps list and a single app's detail page.
    let owns;
    if (btn.dataset.page === "bots") owns = _BOTS_AREA.has(p);
    else if (btn.dataset.page === "apps") owns = _APPS_AREA.has(p);
    else owns = btn.dataset.page === p;
    btn.classList.toggle("active", owns);
  });
  try { localStorage.setItem(ACTIVE_PAGE_KEY, p); } catch (_) {}
  // Page change may affect the unread-dot rule (which excludes the currently-
  // viewed conv). Landing on dashboard with a conv loaded marks it read.
  if (p === "dashboard" && state.conversationId != null) {
    _markConvViewed(state.conversationId);
  }
  if (typeof _refreshUnreadUI === "function") _refreshUnreadUI();
  if (p === "settings" && typeof renderSettingsPage === "function") {
    renderSettingsPage();
    if (typeof loadAuthState === "function") loadAuthState();
  }
  if (p === "bots" && typeof onBotsPageEntered === "function") {
    onBotsPageEntered();
  }
  if (p === "apps" && typeof onAppsPageEntered === "function") {
    onAppsPageEntered();
  }
  if (p === "logs" && typeof onLogsPageEntered === "function") {
    onLogsPageEntered();
  } else if (typeof onLogsPageLeft === "function") {
    onLogsPageLeft();
  }
  // Models + Voice Studio follow the Logs pattern: poll/stream only while
  // the page is visible; everything stops the moment the user navigates away.
  if (p === "models" && typeof onModelsPageEntered === "function") {
    onModelsPageEntered();
  } else if (typeof onModelsPageLeft === "function") {
    onModelsPageLeft();
  }
  if (p === "voice-studio" && typeof onVoiceStudioPageEntered === "function") {
    onVoiceStudioPageEntered();
  } else if (typeof onVoiceStudioPageLeft === "function") {
    onVoiceStudioPageLeft();
  }
}

function initActivityBar() {
  // Only page buttons get the page-switch handler. The theme toggle is a
  // .nav-item WITHOUT data-page and owns its own click handler (see initTheme).
  document.querySelectorAll(".activity-bar .nav-item[data-page]").forEach(btn => {
    btn.addEventListener("click", () => applyActivePage(btn.dataset.page));
  });
  const saved = (() => { try { return localStorage.getItem(ACTIVE_PAGE_KEY); } catch { return null; } })();
  // First-time visitors land on the Bots list (the home surface). Returning
  // users get back to wherever they were — typically the chat they had open.
  applyActivePage(saved || "bots");
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

// =====================================================================
// Self-upgrade — "Update available" badge + click-to-upgrade modal.
// Backed by /api/upgrade/status (read-only) and /api/upgrade/run (loopback,
// spawns upgrade.sh in a detached session).
// =====================================================================

const UPGRADE_PHASES = [
  { key: "pulling",    label: "Pulling latest code from GitHub" },
  { key: "installing", label: "Installing Python dependencies" },
  { key: "restarting", label: "Restarting server" },
  { key: "verifying",  label: "Verifying new server is healthy" },
];

let _upgradeStatus = null;
let _upgradePollTimer = null;

async function _fetchUpgradeStatus() {
  try {
    const r = await fetch("/api/upgrade/status", { cache: "no-store" });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

function _renderUpgradeBadge(status) {
  const btn = document.getElementById("upgrade-badge");
  const count = document.getElementById("upgrade-badge-count");
  if (!btn || !count) return;
  if (status && status.behind > 0) {
    btn.hidden = false;
    count.textContent = String(status.behind);
    btn.dataset.tooltip = `${status.behind} commit${status.behind === 1 ? "" : "s"} behind — click to upgrade`;
  } else {
    btn.hidden = true;
  }
}

function _renderUpgradeModalBody(status, opts = {}) {
  const body = document.getElementById("upgrade-modal-body");
  const runBtn = document.getElementById("upgrade-run-btn");
  if (!body || !runBtn) return;
  body.innerHTML = "";

  if (opts.running) {
    // ----- progress UI while the script is running -----
    const last = (status && status.last_run) || {};
    const phaseKey = last.state || "pulling";
    const failed = phaseKey === "failed";
    const done = phaseKey === "done";

    const shaLine = document.createElement("div");
    shaLine.className = "upgrade-shas";
    shaLine.textContent = `${last.from_sha || status.current_short} → ${last.to_sha || status.latest_short}`;
    body.appendChild(shaLine);

    const progress = document.createElement("div");
    progress.className = "upgrade-progress";
    let crossedActive = false;
    for (const phase of UPGRADE_PHASES) {
      const step = document.createElement("div");
      step.className = "upgrade-progress-step";
      if (failed && phase.key === phaseKey) {
        step.classList.add("failed");
      } else if (done) {
        step.classList.add("done");
      } else if (phase.key === phaseKey) {
        step.classList.add("active");
        crossedActive = true;
      } else if (!crossedActive) {
        step.classList.add("done");
      }
      step.textContent = phase.label;
      progress.appendChild(step);
    }
    body.appendChild(progress);

    if (failed) {
      const err = document.createElement("div");
      err.className = "upgrade-error";
      err.textContent = `Upgrade failed: ${last.error || "unknown error"}`;
      body.appendChild(err);
      const note = document.createElement("div");
      note.style.color = "var(--text-muted)";
      note.style.fontSize = "12px";
      note.textContent = "Auto-rollback ran — your install is back on the previous version. See /tmp/miniclosedai-upgrade.log for details.";
      body.appendChild(note);
      runBtn.textContent = "Close";
      runBtn.disabled = false;
    } else if (done) {
      const ok = document.createElement("div");
      ok.className = "upgrade-success";
      ok.textContent = `Upgraded ${last.from_sha} → ${last.to_sha}. Reloading…`;
      body.appendChild(ok);
      runBtn.disabled = true;
    } else {
      runBtn.disabled = true;
      runBtn.textContent = "Upgrading…";
    }
    return;
  }

  // ----- pre-upgrade UI: show current → latest + diff list -----
  if (!status) {
    body.textContent = "Checking for updates…";
    runBtn.disabled = true;
    return;
  }

  if (status.installed_via === "docker") {
    body.innerHTML = `
      <p>Docker installs upgrade from the host shell, not from inside the container. The image tags in this project are built from source (not published to a registry), so <code>docker compose pull</code> won't work — rebuild instead:</p>
      <pre>git pull
docker compose up -d --build</pre>`;
    runBtn.hidden = true;
    return;
  }

  if (status.installed_via !== "git") {
    body.innerHTML = `
      <p>${status.reason || "This install isn't a git checkout — in-place upgrades aren't available."}</p>
      <p>Re-clone from <code>https://github.com/edantonio505/miniclosedai.git</code> if you want one-click upgrades.</p>`;
    runBtn.hidden = true;
    return;
  }

  const shaLine = document.createElement("div");
  shaLine.className = "upgrade-shas";
  shaLine.textContent = `${status.current_short} → ${status.latest_short}  (${status.behind} commit${status.behind === 1 ? "" : "s"} behind)`;
  body.appendChild(shaLine);

  if (status.behind === 0) {
    const ok = document.createElement("div");
    ok.className = "upgrade-success";
    ok.textContent = "You're already on the latest version.";
    body.appendChild(ok);
    runBtn.hidden = true;
    return;
  }

  if (status.dirty) {
    const warn = document.createElement("div");
    warn.className = "upgrade-warning";
    warn.innerHTML = "You have uncommitted changes. Commit, stash, or run <code>git checkout -- .</code> before upgrading. The upgrade button is disabled until your tree is clean.";
    body.appendChild(warn);
  }

  // "Available since X" line — server stamps `first_seen_at` the first time
  // a given remote SHA is observed and clears it once the install catches up.
  // Useful when a release has been sitting available for a while and the user
  // just opened the modal.
  if (status.first_seen_at) {
    const since = document.createElement("div");
    since.className = "upgrade-since";
    since.style.color = "var(--text-muted)";
    since.style.fontSize = "11.5px";
    since.style.marginTop = "6px";
    const d = new Date(status.first_seen_at);
    since.textContent = isNaN(d.valueOf())
      ? `Available since ${status.first_seen_at}`
      : `Available since ${d.toLocaleString()}`;
    body.appendChild(since);
  }

  if (status.latest_messages && status.latest_messages.length) {
    const list = document.createElement("ul");
    list.className = "upgrade-commit-list";
    for (const msg of status.latest_messages) {
      const li = document.createElement("li");
      li.textContent = msg;
      list.appendChild(li);
    }
    body.appendChild(list);
  }

  const note = document.createElement("div");
  note.style.color = "var(--text-faint)";
  note.style.fontSize = "11.5px";
  note.style.marginTop = "10px";
  note.innerHTML = `Or run <code>./upgrade.sh</code> from the project directory.`;
  body.appendChild(note);

  runBtn.hidden = false;
  runBtn.textContent = "Run upgrade";
  runBtn.disabled = !status.can_upgrade;
}

function _openUpgradeModal() {
  document.getElementById("upgrade-modal-backdrop")?.classList.remove("hidden");
  _renderUpgradeModalBody(_upgradeStatus);
  // Refresh in the background in case it's been a while since the last poll.
  _fetchUpgradeStatus().then(s => {
    if (s) {
      _upgradeStatus = s;
      _renderUpgradeModalBody(s);
    }
  });
}

function _closeUpgradeModal() {
  document.getElementById("upgrade-modal-backdrop")?.classList.add("hidden");
  if (_upgradePollTimer) {
    clearInterval(_upgradePollTimer);
    _upgradePollTimer = null;
  }
}

async function _runUpgrade() {
  // Capture the target SHA so we know what to expect when polling.
  const expectedSha = _upgradeStatus?.latest_short;
  const fromSha = _upgradeStatus?.current_short;

  let started = false;
  try {
    const r = await fetch("/api/upgrade/run", { method: "POST" });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${r.status}`);
    }
    started = true;
  } catch (e) {
    const body = document.getElementById("upgrade-modal-body");
    if (body) {
      body.innerHTML = `<div class="upgrade-error">Couldn't start upgrade: ${(e && e.message) || e}</div>`;
    }
    return;
  }

  // Render an "in progress" view immediately, even before the script writes
  // its first state record. The script does that quickly but there's a tiny
  // window where last_run is still null (or stale from a previous run).
  _upgradeStatus = {
    ..._upgradeStatus,
    last_run: { state: "pulling", from_sha: fromSha, to_sha: expectedSha, error: null },
  };
  _renderUpgradeModalBody(_upgradeStatus, { running: true });

  // Poll. Server can disappear briefly during restart — fetch errors are
  // expected. When the server is back AND last_run.state === "done" AND
  // current_sha matches the target, we cache-bust reload.
  let pollCount = 0;
  if (_upgradePollTimer) clearInterval(_upgradePollTimer);
  _upgradePollTimer = setInterval(async () => {
    pollCount += 1;
    const s = await _fetchUpgradeStatus();
    if (s) {
      _upgradeStatus = s;
      _renderUpgradeModalBody(s, { running: true });
      const lr = s.last_run || {};
      if (lr.state === "done" && (s.current_short === expectedSha || s.current_short === lr.to_sha)) {
        clearInterval(_upgradePollTimer);
        _upgradePollTimer = null;
        // Force a cache-busted reload so fresh JS / CSS land too.
        setTimeout(() => {
          location.href = location.pathname + "?_ts=" + Date.now();
        }, 800);
      } else if (lr.state === "failed") {
        clearInterval(_upgradePollTimer);
        _upgradePollTimer = null;
      }
    }
    // Safety cutoff: 90s ≈ pull + install + restart + verify even on slow boxes.
    if (pollCount > 60) {
      clearInterval(_upgradePollTimer);
      _upgradePollTimer = null;
    }
  }, 1500);
}

function initUpgradeUI() {
  const badge = document.getElementById("upgrade-badge");
  const closeBtn = document.getElementById("upgrade-modal-close");
  const cancelBtn = document.getElementById("upgrade-cancel-btn");
  const runBtn = document.getElementById("upgrade-run-btn");
  const backdrop = document.getElementById("upgrade-modal-backdrop");

  if (badge) badge.addEventListener("click", _openUpgradeModal);
  if (closeBtn) closeBtn.addEventListener("click", _closeUpgradeModal);
  if (cancelBtn) cancelBtn.addEventListener("click", _closeUpgradeModal);
  if (backdrop) backdrop.addEventListener("click", e => {
    if (e.target === backdrop) _closeUpgradeModal();
  });
  if (runBtn) runBtn.addEventListener("click", () => {
    // Reuses the same button as a "Close" affordance after a failed/done run.
    if (runBtn.textContent === "Close") {
      _closeUpgradeModal();
      return;
    }
    _runUpgrade();
  });

  // Initial probe + light periodic refresh (every 10 min so a long-open tab
  // notices new releases without hammering origin).
  _fetchUpgradeStatus().then(s => {
    _upgradeStatus = s;
    _renderUpgradeBadge(s);
  });
  setInterval(() => {
    _fetchUpgradeStatus().then(s => {
      _upgradeStatus = s;
      _renderUpgradeBadge(s);
    });
  }, 10 * 60 * 1000);
}

// =====================================================================
// Bot import — file picker → POST /api/conversations/import. Two paths:
//   (a) server auto-matches a backend → 201, switch to the new bot.
//   (b) server returns 409 needs_backend → modal with the candidate list.
// =====================================================================

let _importPending = null;  // { data, available_backends } while picker is up

function _openImportPickerModal() {
  document.getElementById("import-modal-backdrop")?.classList.remove("hidden");
}

function _closeImportPickerModal() {
  document.getElementById("import-modal-backdrop")?.classList.add("hidden");
  _importPending = null;
  const confirmBtn = document.getElementById("import-confirm-btn");
  if (confirmBtn) confirmBtn.disabled = true;
}

function _renderImportPickerBody(parsed, payload) {
  const body = document.getElementById("import-modal-body");
  const confirmBtn = document.getElementById("import-confirm-btn");
  if (!body) return;
  const wantedModel = payload.model || "(unknown)";
  const backends = payload.available_backends || [];
  const lines = backends.length
    ? backends.map(b => {
        const label = `${b.name} (${b.kind})${b.model_present ? " — has the model" : ` — ${b.model_count} models, none match`}`;
        return `<label style="display:block; padding:6px 0;">
          <input type="radio" name="import-backend" value="${b.id}" ${b.model_present ? "checked" : ""} />
          ${label}
        </label>`;
      }).join("")
    : `<p>No enabled backends found. Add one from Settings, then retry.</p>`;
  body.innerHTML = `
    <p>This bot wants model <code>${wantedModel}</code>, but no enabled backend currently advertises it. Pick a backend to use anyway:</p>
    ${lines}
    <p style="color: var(--text-muted); font-size: 12px; margin-top: 10px;">
      Tip: choose a backend that has the same or a closely-related model. The imported bot will run against whichever backend you pick.
    </p>`;
  if (confirmBtn) {
    confirmBtn.disabled = !backends.some(b => b.model_present);
    body.querySelectorAll('input[name="import-backend"]').forEach(r => {
      r.addEventListener("change", () => { confirmBtn.disabled = false; });
    });
  }
}

async function _runImport(data, backendId) {
  const r = await fetch("/api/conversations/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data, backend_id: backendId }),
  });
  const body = await r.json().catch(() => ({}));
  if (r.status === 201) {
    if (body.warnings && body.warnings.length) {
      console.warn("import warnings:", body.warnings);
    }
    await loadConversations();
    if (body.id) await openConversation(body.id);
    return { ok: true };
  }
  if (r.status === 409 && body.needs_backend) {
    return { needsBackend: true, payload: body };
  }
  return { ok: false, error: body.detail || `HTTP ${r.status}` };
}

async function _handleImportFile(file) {
  let parsed;
  try {
    parsed = JSON.parse(await file.text());
  } catch (e) {
    alert(`Couldn't parse ${file.name} as JSON: ${e.message}`);
    return;
  }
  if (parsed?.format !== "miniclosed-bot") {
    alert(`Not a MiniClosedAI bot file (format=${parsed?.format ?? "missing"}).`);
    return;
  }
  const result = await _runImport(parsed, null);
  if (result.ok) return;
  if (result.needsBackend) {
    _importPending = { kind: "bot", data: parsed, payload: result.payload };
    _setImportModalTitle("Import bot — pick a backend");
    _renderImportPickerBody(parsed, result.payload);
    _openImportPickerModal();
    return;
  }
  alert(`Import failed: ${result.error}`);
}

function _setImportModalTitle(text) {
  const modal = document.getElementById("import-modal-backdrop");
  const h3 = modal && modal.querySelector(".modal-header h3");
  if (h3) h3.textContent = text;
}

function initImportBotUI() {
  const btn = document.getElementById("import-bot-btn");
  const input = document.getElementById("import-bot-file");
  const closeBtn = document.getElementById("import-modal-close");
  const cancelBtn = document.getElementById("import-cancel-btn");
  const confirmBtn = document.getElementById("import-confirm-btn");
  const backdrop = document.getElementById("import-modal-backdrop");

  if (btn && input) {
    btn.addEventListener("click", () => input.click());
    input.addEventListener("change", async () => {
      const f = input.files && input.files[0];
      input.value = "";  // reset so picking the same file twice still fires change
      if (f) await _handleImportFile(f);
    });
  }
  if (closeBtn) closeBtn.addEventListener("click", _closeImportPickerModal);
  if (cancelBtn) cancelBtn.addEventListener("click", _closeImportPickerModal);
  if (backdrop) backdrop.addEventListener("click", e => {
    if (e.target === backdrop) _closeImportPickerModal();
  });
  if (confirmBtn) confirmBtn.addEventListener("click", async () => {
    if (!_importPending) return;
    const picked = document.querySelector('input[name="import-backend"]:checked');
    if (!picked) return;
    const backendId = parseInt(picked.value, 10);
    const { kind, data } = _importPending;
    _closeImportPickerModal();
    const result = kind === "app"
      ? await _runAppImport(data, backendId)
      : await _runImport(data, backendId);
    if (!result.ok) alert(`Import failed: ${result.error || "unknown"}`);
  });
}

// =====================================================================
// Application import — same shape as the bot importer, one level up. The
// file is .miniclosed-app.json; we POST to /api/apps/import and reuse the
// same backend-picker modal. One backend is chosen for every bot in the
// imported app (matches the user's chosen UX over a per-bot picker).
// =====================================================================

async function _runAppImport(data, backendId) {
  const r = await fetch("/api/apps/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data, backend_id: backendId }),
  });
  const body = await r.json().catch(() => ({}));
  if (r.status === 201) {
    if (body.warnings && body.warnings.length) {
      console.warn("app import warnings:", body.warnings);
    }
    // Refresh the bot list (the new app's bots showed up there too) and the
    // app list, then drop the user into the freshly-imported app.
    if (typeof loadConversations === "function") await loadConversations();
    if (typeof loadApps === "function") await loadApps();
    if (typeof renderAppsPage === "function") renderAppsPage();
    if (body.id && typeof openApp === "function") await openApp(body.id);
    return { ok: true };
  }
  if (r.status === 409 && body.needs_backend) {
    return { needsBackend: true, payload: body };
  }
  return { ok: false, error: body.detail || `HTTP ${r.status}` };
}

function _renderAppImportPickerBody(parsed, payload) {
  const body = document.getElementById("import-modal-body");
  const confirmBtn = document.getElementById("import-confirm-btn");
  if (!body) return;
  const models = (payload.models || []).slice();
  const backends = payload.available_backends || [];
  const botCount = (parsed.bots || []).length;
  const lines = backends.length
    ? backends.map(b => {
        const need = b.needed_count ?? models.length;
        const have = b.matched_count ?? 0;
        const tail = b.model_present
          ? " — has every model in this app"
          : ` — has ${have}/${need} required models`;
        const label = `${b.name} (${b.kind})${tail}`;
        return `<label style="display:block; padding:6px 0;">
          <input type="radio" name="import-backend" value="${b.id}" ${b.model_present ? "checked" : ""} />
          ${label}
        </label>`;
      }).join("")
    : `<p>No enabled backends found. Add one from Settings, then retry.</p>`;
  body.innerHTML = `
    <p>This application bundles <strong>${botCount}</strong> bot${botCount === 1 ? "" : "s"} that need these models: <code>${models.join(", ") || "(none)"}</code>. No enabled backend covers them all. Pick one backend to run every bot against:</p>
    ${lines}
    <p style="color: var(--text-muted); font-size: 12px; margin-top: 10px;">
      Tip: the cleanest fit is a backend that lists all the required models. If none does, pick the closest match — bots will still run, just against whatever models that backend actually serves.
    </p>`;
  if (confirmBtn) {
    // Enable as soon as any backend is selected; default-checked if any backend has them all.
    confirmBtn.disabled = !backends.some(b => b.model_present);
    body.querySelectorAll('input[name="import-backend"]').forEach(r => {
      r.addEventListener("change", () => { confirmBtn.disabled = false; });
    });
  }
}

async function _handleAppImportFile(file) {
  let parsed;
  try {
    parsed = JSON.parse(await file.text());
  } catch (e) {
    alert(`Couldn't parse ${file.name} as JSON: ${e.message}`);
    return;
  }
  if (parsed?.format !== "miniclosed-app") {
    alert(`Not a MiniClosedAI application file (format=${parsed?.format ?? "missing"}).`);
    return;
  }
  const result = await _runAppImport(parsed, null);
  if (result.ok) return;
  if (result.needsBackend) {
    _importPending = { kind: "app", data: parsed, payload: result.payload };
    _setImportModalTitle("Import application — pick a backend for all bots");
    _renderAppImportPickerBody(parsed, result.payload);
    _openImportPickerModal();
    return;
  }
  alert(`Import failed: ${result.error}`);
}

function initAppsImportUI() {
  const btn = document.getElementById("apps-import-btn");
  const input = document.getElementById("apps-import-file");
  if (!btn || !input) return;
  btn.addEventListener("click", () => input.click());
  input.addEventListener("change", async () => {
    const f = input.files && input.files[0];
    input.value = "";  // reset so picking the same file twice still fires change
    if (f) await _handleAppImportFile(f);
  });
}

function _downloadApp(appId, includeHistory) {
  const path = includeHistory
    ? `export?include_history=true`
    : `export?include_history=false`;
  const a = document.createElement("a");
  a.href = `/api/apps/${appId}/${path}`;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// =====================================================================
// Logs page — LM-Studio-style request/response viewer.
//
// Pull-polls `/api/logs?since_id=N` every 2 s while the page is visible,
// merges new entries into a client-side buffer, renders newest-first. Each
// entry is a collapsed one-liner (status pill, endpoint, model, latency,
// timestamp); clicking expands to show params + the message preview +
// response body + thinking trace if present. Filter input does an in-memory
// substring match across endpoint / model / message text.
// =====================================================================

const LOGS_POLL_INTERVAL_MS = 2000;
const LOGS_MAX_CLIENT_ENTRIES = 500;

const _logsState = {
  buffer: [],          // newest-first list of entries
  expanded: new Set(), // entry ids the user has clicked open
  filter: "",
  paused: false,
  maxSeenId: 0,
  pollTimer: null,
  active: false,       // is the Logs page currently displayed?
};

function _logsFmtLatency(ms) {
  if (ms == null) return "";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function _logsFmtTs(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return iso;
  // HH:MM:SS — date is implicit (logs are within the current session).
  return d.toLocaleTimeString();
}

function _logsMatchesFilter(entry, q) {
  if (!q) return true;
  const haystack = [
    entry.endpoint || "",
    entry.model || "",
    entry.backend_name || "",
    (entry.response && entry.response.preview) || "",
    ...(entry.messages || []).map(m => m.content_preview || ""),
  ].join(" ").toLowerCase();
  return haystack.includes(q);
}

function _logsRenderEntry(entry) {
  const wrap = document.createElement("div");
  wrap.className = `log-entry ${entry.status === "error" ? "error" : "ok"}`;
  wrap.dataset.id = String(entry.id);
  if (_logsState.expanded.has(entry.id)) wrap.classList.add("open");

  const header = document.createElement("div");
  header.className = "log-entry-header";
  header.innerHTML = `
    <span class="log-entry-pill">${entry.status === "error" ? "error" : entry.kind}</span>
    <span class="log-entry-endpoint" title="${entry.endpoint || ""}">${entry.endpoint || ""}</span>
    <span class="log-entry-model" title="backend: ${entry.backend_name || "—"}">${entry.model || "—"}</span>
    <span class="log-entry-latency">${_logsFmtLatency(entry.latency_ms)}</span>
    <span class="log-entry-ts">${_logsFmtTs(entry.ts)}</span>
  `;
  header.addEventListener("click", () => {
    if (_logsState.expanded.has(entry.id)) {
      _logsState.expanded.delete(entry.id);
      wrap.classList.remove("open");
    } else {
      _logsState.expanded.add(entry.id);
      wrap.classList.add("open");
    }
  });
  wrap.appendChild(header);

  // Body is built lazily-ish — always present in DOM but only rendered when
  // open via CSS. Keep entry HTML small to avoid hammering the DOM on every
  // 2s tick when the list is long.
  const body = document.createElement("div");
  body.className = "log-entry-body";

  // Params
  const params = entry.params || {};
  const paramBits = Object.entries(params)
    .filter(([k, v]) => v != null && v !== "" && !(typeof v === "number" && Number.isNaN(v)))
    .map(([k, v]) => `${k}=<code>${typeof v === "object" ? JSON.stringify(v) : v}</code>`);
  if (paramBits.length || entry.backend_name) {
    const meta = document.createElement("div");
    meta.className = "log-entry-section";
    meta.innerHTML = `
      <div class="log-entry-section-title">Backend &amp; params</div>
      <div class="log-entry-params">
        <span>backend: <code>${entry.backend_name || "—"}</code> (${entry.backend_kind || "—"})</span>
        ${paramBits.map(b => `<span>${b}</span>`).join("")}
      </div>
    `;
    body.appendChild(meta);
  }

  // Messages
  if (entry.messages && entry.messages.length) {
    const msgs = document.createElement("div");
    msgs.className = "log-entry-section";
    const escape = s => String(s ?? "").replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
    msgs.innerHTML = `
      <div class="log-entry-section-title">Request (last ${entry.messages.length} message${entry.messages.length === 1 ? "" : "s"})</div>
      ${entry.messages.map(m => `
        <div class="log-entry-msg ${m.role || "user"}">
          <div class="log-entry-msg-role">${m.role || "?"}</div>
          <div>${escape(m.content_preview)}</div>
        </div>
      `).join("")}
      ${entry.attachments && entry.attachments.length ? `
        <div class="log-entry-params" style="margin-top:6px">
          <span>attachments: ${entry.attachments.map(a => `<code>${a}</code>`).join(" ")}</span>
        </div>
      ` : ""}
    `;
    body.appendChild(msgs);
  }

  // Response preview
  if (entry.response && (entry.response.preview || entry.response.char_count)) {
    const resp = document.createElement("div");
    resp.className = "log-entry-section";
    const trunc = entry.response.truncated
      ? `<div class="log-entry-truncated">Truncated — first 2000 chars of a ${entry.response.char_count}-char response.</div>`
      : "";
    resp.innerHTML = `
      <div class="log-entry-section-title">Response (${entry.response.char_count} chars)</div>
      <pre class="log-entry-pre"></pre>
      ${trunc}
    `;
    // Use textContent to safely render whatever the model returned, including
    // backticks / HTML / JSON without re-escaping in a template literal.
    resp.querySelector("pre").textContent = entry.response.preview;
    body.appendChild(resp);
  }

  // Thinking trace
  if (entry.thinking && entry.thinking.preview) {
    const th = document.createElement("div");
    th.className = "log-entry-section";
    const trunc = entry.thinking.truncated
      ? `<div class="log-entry-truncated">Truncated — first 1000 chars of a ${entry.thinking.char_count}-char trace.</div>`
      : "";
    th.innerHTML = `
      <div class="log-entry-section-title">Thinking trace (${entry.thinking.char_count} chars)</div>
      <pre class="log-entry-pre"></pre>
      ${trunc}
    `;
    th.querySelector("pre").textContent = entry.thinking.preview;
    body.appendChild(th);
  }

  if (entry.error) {
    const err = document.createElement("div");
    err.className = "log-entry-section";
    err.innerHTML = `<div class="log-entry-section-title">Error</div><pre class="log-entry-pre"></pre>`;
    err.querySelector("pre").textContent = entry.error;
    body.appendChild(err);
  }

  wrap.appendChild(body);
  return wrap;
}

function _logsRender() {
  const listEl = document.getElementById("logs-list");
  const emptyEl = document.getElementById("logs-empty");
  const countEl = document.getElementById("logs-count");
  if (!listEl) return;

  const q = _logsState.filter.trim().toLowerCase();
  const filtered = q
    ? _logsState.buffer.filter(e => _logsMatchesFilter(e, q))
    : _logsState.buffer;

  listEl.innerHTML = "";
  for (const entry of filtered) {
    listEl.appendChild(_logsRenderEntry(entry));
  }
  if (countEl) {
    countEl.textContent = q
      ? `${filtered.length} of ${_logsState.buffer.length} entries`
      : `${_logsState.buffer.length} ${_logsState.buffer.length === 1 ? "entry" : "entries"}`;
  }
  if (emptyEl) emptyEl.style.display = filtered.length === 0 ? "block" : "none";
}

async function _logsPoll() {
  if (_logsState.paused || !_logsState.active) return;
  try {
    const url = _logsState.maxSeenId > 0
      ? `/api/logs?since_id=${_logsState.maxSeenId}`
      : `/api/logs`;
    const r = await fetch(url);
    if (!r.ok) return;
    const data = await r.json();
    const incoming = data.logs || [];
    if (!incoming.length) return;
    // Server returns newest-first; merge into the front of the client buffer.
    _logsState.buffer = incoming.concat(_logsState.buffer);
    if (_logsState.buffer.length > LOGS_MAX_CLIENT_ENTRIES) {
      _logsState.buffer.length = LOGS_MAX_CLIENT_ENTRIES;
    }
    const newMax = Math.max(...incoming.map(e => e.id || 0), _logsState.maxSeenId);
    _logsState.maxSeenId = newMax;
    _logsRender();
  } catch {
    // network blips are fine — next tick retries
  }
}

function onLogsPageEntered() {
  _logsState.active = true;
  // Force a full refresh on entry — server may have been restarted, in which
  // case our cached entries are stale and `since_id` would miss everything.
  if (_logsState.maxSeenId === 0) {
    _logsRender();
  }
  _logsPoll();
  if (!_logsState.pollTimer) {
    _logsState.pollTimer = setInterval(_logsPoll, LOGS_POLL_INTERVAL_MS);
  }
}

function onLogsPageLeft() {
  _logsState.active = false;
  if (_logsState.pollTimer) {
    clearInterval(_logsState.pollTimer);
    _logsState.pollTimer = null;
  }
}

function initLogsUI() {
  const filterEl = document.getElementById("logs-filter");
  const pauseEl = document.getElementById("logs-pause-toggle");
  const clearEl = document.getElementById("logs-clear-btn");
  const exportEl = document.getElementById("logs-export-btn");
  if (exportEl) {
    exportEl.addEventListener("click", async () => {
      // Hit the export endpoint and trigger a browser save via Content-
      // Disposition. We use a Blob URL + click rather than location.assign
      // so we can surface a failure as an alert instead of a blank tab.
      exportEl.disabled = true;
      const orig = exportEl.textContent;
      exportEl.textContent = "Exporting…";
      try {
        const r = await fetch("/api/logs/export");
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        const disp = r.headers.get("Content-Disposition") || "";
        const m = /filename="([^"]+)"/.exec(disp);
        const fname = m ? m[1] : `miniclosedai-logs-${Date.now()}.json`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = fname;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } catch (e) {
        alert("Export failed: " + (e?.message || e));
      } finally {
        exportEl.textContent = orig;
        exportEl.disabled = false;
      }
    });
  }
  if (filterEl) {
    filterEl.addEventListener("input", () => {
      _logsState.filter = filterEl.value || "";
      _logsRender();
    });
  }
  if (pauseEl) {
    pauseEl.addEventListener("change", () => { _logsState.paused = !!pauseEl.checked; });
  }
  if (clearEl) {
    clearEl.addEventListener("click", async () => {
      if (!confirm("Clear all log entries? Affects this server's in-memory buffer.")) return;
      try {
        await fetch("/api/logs", { method: "DELETE" });
        _logsState.buffer = [];
        _logsState.expanded.clear();
        _logsState.maxSeenId = 0;
        _logsRender();
      } catch (e) {
        alert("Clear failed: " + e.message);
      }
    });
  }
}

// =====================================================================
// Global tooltip — ONE fixed-positioned element on <body> that shows
// the `data-tooltip` text for whichever element you hover or focus.
//
// Why a global element instead of a per-trigger `::after` pseudo:
//   • Every `::after` is rendered inside its parent's stacking + clipping
//     contexts. Any ancestor with `overflow: hidden`, `transform`, or a
//     stacking context (sidebar, modal, sticky toolbar, etc.) would clip
//     or layer-cover the tooltip.
//   • A single fixed-positioned <body> child sits in the root stacking
//     context with the maximum z-index, so it's GUARANTEED to render
//     above every other element on the page.
//
// Positioning runs on every show — we compute the trigger's bounding rect
// in viewport coordinates and place the tooltip directly under it (or
// above when `data-tooltip-side="top"` is set), clamped to the viewport
// so it never falls off-screen at narrow widths.
// =====================================================================
const _GLOBAL_TOOLTIP_GAP_PX = 6;       // gap between trigger and bubble
const _GLOBAL_TOOLTIP_VIEWPORT_PAD = 8;  // clamp this far from each edge

let _globalTooltipEl = null;
let _globalTooltipTrigger = null;        // element currently advertising

function _shouldShowTooltip(trigger) {
  if (!trigger || !trigger.isConnected) return false;
  const text = trigger.getAttribute("data-tooltip");
  if (!text) return false;
  // Match the old `::after` behaviour: don't compete with an open menu/popover.
  if (trigger.getAttribute("aria-expanded") === "true") return false;
  // Don't show on hidden / off-screen elements.
  if (trigger.hidden || trigger.closest("[hidden]")) return false;
  return true;
}

function _showGlobalTooltip(trigger) {
  if (!_globalTooltipEl || !_shouldShowTooltip(trigger)) return;
  _globalTooltipTrigger = trigger;
  const text = trigger.getAttribute("data-tooltip");
  _globalTooltipEl.textContent = text;
  _globalTooltipEl.setAttribute("aria-hidden", "false");

  // Reset side class so this measurement is consistent.
  const wantTop = trigger.getAttribute("data-tooltip-side") === "top";
  _globalTooltipEl.classList.toggle("side-top", wantTop);

  // Make sure the element is laid out so we can read its size, but stays
  // invisible until we position it (avoids a one-frame flash at 0,0).
  _globalTooltipEl.style.visibility = "hidden";
  _globalTooltipEl.classList.add("visible");

  const triggerRect = trigger.getBoundingClientRect();
  const ttRect = _globalTooltipEl.getBoundingClientRect();
  const vw = document.documentElement.clientWidth;
  const vh = document.documentElement.clientHeight;

  // Horizontal: center under the trigger, then clamp into the viewport so
  // wide tooltips on edge-aligned buttons don't fall off-screen.
  let left = triggerRect.left + (triggerRect.width - ttRect.width) / 2;
  left = Math.max(
    _GLOBAL_TOOLTIP_VIEWPORT_PAD,
    Math.min(left, vw - ttRect.width - _GLOBAL_TOOLTIP_VIEWPORT_PAD)
  );

  // Vertical: prefer the requested side; if it would clip the viewport,
  // auto-flip.
  let top;
  let placedTop = wantTop;
  if (placedTop) {
    top = triggerRect.top - ttRect.height - _GLOBAL_TOOLTIP_GAP_PX;
    if (top < _GLOBAL_TOOLTIP_VIEWPORT_PAD) {
      placedTop = false;
      top = triggerRect.bottom + _GLOBAL_TOOLTIP_GAP_PX;
    }
  } else {
    top = triggerRect.bottom + _GLOBAL_TOOLTIP_GAP_PX;
    if (top + ttRect.height > vh - _GLOBAL_TOOLTIP_VIEWPORT_PAD) {
      placedTop = true;
      top = triggerRect.top - ttRect.height - _GLOBAL_TOOLTIP_GAP_PX;
    }
  }
  _globalTooltipEl.classList.toggle("side-top", placedTop);

  _globalTooltipEl.style.left = `${Math.round(left)}px`;
  _globalTooltipEl.style.top = `${Math.round(top)}px`;
  _globalTooltipEl.style.visibility = "";
}

function _hideGlobalTooltip() {
  if (!_globalTooltipEl) return;
  _globalTooltipEl.classList.remove("visible");
  _globalTooltipEl.setAttribute("aria-hidden", "true");
  _globalTooltipTrigger = null;
}

function _findTooltipTarget(el) {
  // Walk up to find an element advertising a `data-tooltip` attribute,
  // skipping the global tooltip itself.
  if (!el || el === _globalTooltipEl) return null;
  return el.closest ? el.closest("[data-tooltip]") : null;
}

function initGlobalTooltip() {
  _globalTooltipEl = document.getElementById("global-tooltip");
  if (!_globalTooltipEl) return;

  // Delegated pointer + keyboard events on document so dynamically-added
  // [data-tooltip] elements (cards built by JS, modal contents, etc.) get
  // the tooltip behaviour for free.
  document.addEventListener("pointerover", e => {
    const target = _findTooltipTarget(e.target);
    if (target === _globalTooltipTrigger) return;
    // Moved off the current trigger (or onto a different one) — drop the
    // existing tooltip first, then show the new one if present.
    if (_globalTooltipTrigger) _hideGlobalTooltip();
    if (target) _showGlobalTooltip(target);
  });
  document.addEventListener("pointerout", e => {
    if (!_globalTooltipTrigger) return;
    // relatedTarget is where the pointer is going. If it's still inside the
    // active trigger we're not actually leaving it — let the move stand.
    const next = e.relatedTarget;
    if (next && _globalTooltipTrigger.contains(next)) return;
    // If we're moving from the trigger directly onto another tooltip
    // trigger, pointerover above will handle the swap — so just hide.
    _hideGlobalTooltip();
  });
  document.addEventListener("focusin", e => {
    const t = _findTooltipTarget(e.target);
    if (t) _showGlobalTooltip(t);
  });
  document.addEventListener("focusout", e => {
    const t = _findTooltipTarget(e.target);
    if (t && _globalTooltipTrigger === t) _hideGlobalTooltip();
  });

  // Hide on scroll/resize — the cached rect is now wrong, and reshowing on
  // pointermove is good enough.
  window.addEventListener("scroll", _hideGlobalTooltip, true);
  window.addEventListener("resize", _hideGlobalTooltip);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") _hideGlobalTooltip();
  });
}

// =====================================================================
// Shared small helpers introduced with the Models / Voice Studio tabs.
// =====================================================================
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

let _toastTimer = null;
function showToast(msg, kind = "") {
  let el = document.getElementById("app-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "app-toast";
    el.className = "app-toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = "app-toast" + (kind ? " is-" + kind : "");
  el.hidden = false;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.hidden = true; }, 4000);
}

function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      ok ? resolve() : reject(new Error("copy failed"));
    } catch (e) { reject(e); }
  });
}

// =====================================================================
// Models page — native port of the miniclosedai-llm dashboard. The manager
// stays its own process; everything here talks to it through the same-origin
// /api/llm/* proxy (which injects auth server-side). Polling and log streams
// run ONLY while the page is visible (Logs-page pattern).
// =====================================================================
const _mpState = {
  cards: new Map(),   // model id → {node, es, file, expanded, model, lastStatus}
  active: false,
  pollTimer: null,
  bannerTimer: null,
  info: null,         // /api/llm-info result ({manager_url, reachable})
};

async function _mpApi(path, opts = {}) {
  const r = await fetch(`/api/llm/${path}`, opts);
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try { const b = await r.json(); if (b.detail !== undefined) detail = b.detail; } catch (e) {}
    const msg = (detail && detail.message) || (typeof detail === "string" ? detail : JSON.stringify(detail));
    const err = new Error(msg);
    err.status = r.status;
    err.detail = detail;
    throw err;
  }
  return r.status === 204 ? null : r.json();
}

function _mpSetOffline(offline, msg) {
  const box = document.getElementById("mp-offline");
  if (!box) return;
  box.hidden = !offline;
  if (offline) box.textContent = msg ||
    "Model server not reachable. Start it with ./dev.sh up (it launches the miniclosedai-llm manager alongside the app).";
  for (const id of ["mp-add-section", "mp-cache-section", "mp-models-section"]) {
    const el = document.getElementById(id);
    if (el) el.hidden = offline;
  }
  const banner = document.getElementById("mp-banner");
  if (banner) banner.hidden = offline;
}

async function mpLoadBanner() {
  const el = document.getElementById("mp-banner");
  if (!el || !_mpState.active) return;
  let h;
  try { h = await _mpApi("health"); }
  catch (e) { _mpSetOffline(true); return; }
  _mpSetOffline(false);

  let gpuTxt = "";
  try {
    const g = await _mpApi("gpu");
    if (g.gpus && g.gpus.length) {
      gpuTxt = g.gpus.map((x) => {
        const mem = (x.mem_total_mb == null)
          ? "unified memory" : `${x.mem_used_mb}/${x.mem_total_mb} MB`;
        return `GPU${x.index} ${x.name} — ${mem} (${x.util_pct}%)`;
      }).join(" · ");
    } else { gpuTxt = "GPU: " + (g.error || "not detected"); }
  } catch (e) { gpuTxt = "GPU: unknown"; }

  let cls = "ok", msg;
  if (h.no_engine) {
    cls = "bad"; msg = "No launch engine — install Docker, or pip install vllm.";
  } else if (!h.gpu_ok) {
    cls = "warn"; msg = "Engine ready, but no GPU detected.";
  } else {
    msg = "Ready.";
  }
  const engLabel = h.engine === "docker" ? "Docker engine"
    : h.engine === "native" ? "Native (vllm serve)" : (h.engine || "?");
  el.className = "mp-banner " + cls;
  el.innerHTML =
    `<span class="mp-engine-badge">${escapeHtml(engLabel)}</span>` +
    `<span>${escapeHtml(msg)}</span>` +
    `<span class="mp-dim">${escapeHtml(gpuTxt)}</span>` +
    (h.llamacpp_ok ? `<span class="mp-dim">· GGUF ready</span>` : "");
}

function _mpReadAdvanced() {
  const $id = (i) => document.getElementById(i);
  const num = (i) => { const v = $id(i).value.trim(); return v === "" ? undefined : Number(v); };
  const str = (i) => { const v = $id(i).value.trim(); return v === "" ? undefined : v; };
  const params = {};
  const maxlen = num("mp-adv-maxlen"); if (maxlen !== undefined) params.max_model_len = maxlen;
  const gpumem = num("mp-adv-gpumem"); if (gpumem !== undefined) params.gpu_memory_util = gpumem;
  const tp = num("mp-adv-tp"); if (tp !== undefined) params.tensor_parallel = tp;
  const maximg = num("mp-adv-maximg"); if (maximg !== undefined) params.max_images = maximg;
  const quant = str("mp-adv-quant"); if (quant !== undefined) params.quantization = quant;
  if ($id("mp-adv-trust").checked) params.trust_remote_code = true;
  const mm = str("mp-adv-mmproc"); if (mm !== undefined) params.mm_processor_kwargs = mm;
  const hf = str("mp-adv-hfover"); if (hf !== undefined) params.hf_overrides = hf;
  const extra = str("mp-adv-extra"); if (extra !== undefined) params.extra_args = extra.split(/\s+/);
  return {
    served_name: str("mp-adv-served"),
    port: num("mp-adv-port"),
    params: Object.keys(params).length ? params : undefined,
  };
}

function _mpFmtAnalysis(a) {
  const rows = [];
  const typ = a.multimodal ? "vision + text" : (a.is_llm ? "text LLM" : "⚠ not a text-gen model?");
  rows.push(["Type", typ]);
  if (a.params) rows.push(["Parameters", (a.params / 1e9).toFixed(1) + " B" + (a.dtype ? " · " + a.dtype : "")]);
  if (a.size_gb != null) rows.push(["Weights", "~" + a.size_gb + " GB"]);
  if (a.need_gb != null) rows.push(["Needs (est.)", "~" + a.need_gb + " GB"]);
  rows.push(["Available", a.available_gb + " GB" + (a.total_gb ? " / " + a.total_gb + " GB total" : "")]);
  if (a.gated) rows.push(["Gated", a.hf_token_present ? "yes (HF_TOKEN set ✓)" : "yes — set HF_TOKEN ⚠"]);
  return rows.map(([k, v]) => `<span>${escapeHtml(k)}</span><span>${escapeHtml(v)}</span>`).join("");
}

async function mpAnalyze() {
  const hf = document.getElementById("mp-hf-id").value.trim();
  const out = document.getElementById("mp-analyze-result");
  if (!hf) return;
  out.hidden = false; out.className = "mp-analyze-result"; out.innerHTML = "Analyzing…";
  try {
    const a = await _mpApi("analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hf_id: hf }),
    });
    if (!a.exists) {
      out.className = "mp-analyze-result bad";
      out.innerHTML = `<strong>Can't use this model.</strong> ${escapeHtml(a.error || "not found")}`;
      return;
    }
    const cls = a.fits ? "ok" : "warn";
    out.className = "mp-analyze-result " + cls;
    out.innerHTML =
      `<div class="mp-a-title">${escapeHtml(a.hf_id)} <span class="mp-type-pill">${a.fmt === "gguf" ? "gguf" : (a.multimodal ? "vision" : "text")}</span></div>` +
      `<div class="mp-a-grid">${_mpFmtAnalysis(a)}</div>` +
      `<div class="mp-a-actions"><button id="mp-analyze-run" class="btn btn-small btn-primary" type="button">${a.fits ? "Download & Run" : "Run anyway"}</button></div>`;
    document.getElementById("mp-analyze-run")
      .addEventListener("click", () => mpAdd(hf, !a.fits));
  } catch (err) {
    out.className = "mp-analyze-result bad"; out.textContent = err.message;
  }
}

let _mpAddInFlight = false;
async function mpAdd(hf, force) {
  if (_mpAddInFlight) return;
  _mpAddInFlight = true;
  const errEl = document.getElementById("mp-add-error");
  errEl.hidden = true;
  try {
    await _mpApi("models", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hf_id: hf, run: true, force: !!force, ..._mpReadAdvanced() }),
    });
    document.getElementById("mp-hf-id").value = "";
    document.getElementById("mp-analyze-result").hidden = true;
    showToast("Launching — watch the logs for download progress.", "ok");
    await mpLoadModels();
  } catch (err) {
    errEl.hidden = false;
    if (err.status === 409) {
      errEl.innerHTML = escapeHtml(err.message) +
        ` <button id="mp-force-run" class="btn btn-small" type="button">Run anyway</button>`;
      const f = document.getElementById("mp-force-run");
      if (f) f.addEventListener("click", () => mpAdd(hf, true));
    } else {
      errEl.textContent = err.message;
    }
  } finally {
    _mpAddInFlight = false;
  }
}

const _MP_STATUS_LABEL = {
  stopped: "Stopped", queued: "Queued", pulling: "Pulling image",
  downloading: "Downloading", loading: "Loading", ready: "Ready", error: "Error",
};

function _mpIsRegistered(m) {
  return (backendCache || []).some(b =>
    b.base_url === m.base_url || (m.alt_base_url && b.base_url === m.alt_base_url));
}

function mpRenderCard(m) {
  const q = (sel, root) => root.querySelector(sel);
  let st = _mpState.cards.get(m.id);
  if (!st) {
    const node = document.getElementById("mp-card-tpl").content.firstElementChild.cloneNode(true);
    st = { node, es: null, file: null, expanded: false };
    _mpState.cards.set(m.id, st);
    _mpWireCard(st, m);
    document.getElementById("mp-models-list").appendChild(node);
  }
  const n = st.node;
  q(".mp-id", n).textContent = m.served_name;
  q(".mp-sub", n).textContent = `${m.hf_id} · :${m.port}`
    + (m.fmt === "gguf" ? " · GGUF" : "") + (m.multimodal ? " · vision" : "");

  const pill = q(".mp-status-pill", n);
  pill.className = "mp-status-pill mp-status-" + m.status;
  q(".mp-status-text", n).textContent = _MP_STATUS_LABEL[m.status] || m.status;

  const active = m.status !== "stopped" && m.status !== "error";
  q(".mp-act-run", n).hidden = active;
  q(".mp-act-run", n).textContent = m.status === "error" ? "Retry" : "Run";
  q(".mp-act-stop", n).hidden = !active;

  q(".mp-base-url", n).textContent = m.base_url;
  q(".mp-register-block", n).hidden = !m.ready;
  const registered = _mpIsRegistered(m);
  q(".mp-act-register", n).hidden = registered;
  q(".mp-registered-note", n).hidden = !registered;
  if (!st.imgShown) q(".mp-act-addimg", n).hidden = !m.multimodal;
  q(".mp-test-block", n).hidden = !m.ready;

  const errEl = q(".mp-model-error", n);
  if (m.status === "error" && (m.error || m.detail)) {
    errEl.hidden = false; errEl.textContent = m.error || m.detail;
    if (st.lastStatus !== "error") _mpSetExpanded(st, true);
  } else {
    errEl.hidden = true;
  }
  q(".mp-body", n).hidden = !st.expanded;
  n.classList.toggle("expanded", !!st.expanded);
  st.lastStatus = m.status;
  st.model = m;
}

function _mpSetExpanded(st, val) {
  st.expanded = val;
  st.node.querySelector(".mp-body").hidden = !val;
  st.node.classList.toggle("expanded", val);
  if (!val) {
    st.node.querySelector(".mp-logs-block").hidden = true;
    _mpCloseLogs(st);
  }
}

function _mpWireCard(st, m) {
  const n = st.node;
  const id = m.id;
  const q = (sel) => n.querySelector(sel);

  q(".mp-act-run").addEventListener("click", () => _mpAct(id, "start"));
  q(".mp-act-stop").addEventListener("click", () => _mpAct(id, "stop"));
  q(".mp-act-remove").addEventListener("click", async () => {
    const ok = await uiConfirm({
      title: `Remove ${id}?`,
      message: "Stops the model and removes it from the manager. Downloaded weights are kept.",
      okText: "Remove", danger: true,
    });
    if (!ok) return;
    _mpCloseLogs(st);
    try { await _mpApi(`models/${encodeURIComponent(id)}`, { method: "DELETE" }); }
    catch (e) { showToast(e.message, "error"); return; }
    _mpState.cards.delete(id); n.remove();
    showToast("Removed " + id, "ok");
  });

  n.querySelector(".mp-card-top").addEventListener("click", (e) => {
    if (e.target.closest("button")) return;
    _mpSetExpanded(st, !st.expanded);
  });

  q(".mp-act-logs").addEventListener("click", () => {
    const lb = q(".mp-logs-block");
    if (lb.hidden) { _mpSetExpanded(st, true); lb.hidden = false; _mpOpenLogs(st, id); }
    else { lb.hidden = true; _mpCloseLogs(st); }
  });

  q(".mp-act-copy").addEventListener("click", () => {
    copyText(q(".mp-base-url").textContent).then(
      () => showToast("Copied base URL", "ok"),
      () => showToast("Copy failed — select the URL manually", "error"));
  });

  // The integration win over the standalone dashboard: one click registers
  // the ready model as a kind='openai' backend, so it shows up in the model
  // pickers (topbar + bot cards) immediately.
  q(".mp-act-register").addEventListener("click", async () => {
    const btn = q(".mp-act-register");
    btn.disabled = true;
    try {
      const info = _mpState.info || await fetch("/api/llm-info").then(r => r.json());
      const r = await fetch("/api/backends/auto-register", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manager_url: info.manager_url, model_id: id }),
      });
      if (!r.ok) {
        let d = `HTTP ${r.status}`;
        try { const b = await r.json(); d = (b.detail && b.detail.message) || b.detail || d; } catch (e) {}
        throw new Error(typeof d === "string" ? d : JSON.stringify(d));
      }
      const b = await r.json();
      showToast(`Registered '${b.name}' as a backend — it's in the model pickers now.`, "ok");
      await loadBackends();
      await loadModels();     // refresh the topbar/grouped pickers
      mpLoadModels();         // repaint cards (registered ✓)
    } catch (e) {
      showToast("Register failed: " + e.message, "error");
    } finally {
      btn.disabled = false;
    }
  });

  q(".mp-act-addimg").addEventListener("click", async () => {
    st.imgShown = true;
    q(".mp-act-addimg").hidden = true;
    q(".mp-test-img-wrap").hidden = false;
    q(".mp-test-img").src = "/api/llm/test-image";
    try {
      const blob = await (await fetch("/api/llm/test-image")).blob();
      st.file = new File([blob], "test.png", { type: "image/png" });
    } catch (e) {}
  });
  q(".mp-act-pick").addEventListener("click", () => q(".mp-test-file").click());
  q(".mp-test-file").addEventListener("change", (ev) => {
    const f = ev.target.files[0]; if (!f) return;
    st.file = f; q(".mp-test-img").src = URL.createObjectURL(f);
  });
  q(".mp-act-test").addEventListener("click", () => _mpRunTest(st, id));
}

async function _mpAct(id, verb) {
  try {
    await _mpApi(`models/${encodeURIComponent(id)}/${verb}`, { method: "POST" });
    await mpLoadModels();
  } catch (e) { showToast(e.message, "error"); }
}

async function _mpRunTest(st, id) {
  const n = st.node;
  const ansEl = n.querySelector(".mp-test-answer");
  ansEl.hidden = false; ansEl.textContent = "Running…";
  try {
    const fd = new FormData();
    fd.append("prompt", n.querySelector(".mp-test-prompt").value);
    if (st.file) fd.append("image", st.file);
    const r = await _mpApi(`models/${encodeURIComponent(id)}/test`, { method: "POST", body: fd });
    ansEl.innerHTML = escapeHtml(r.answer || "(empty response)") +
      `<div class="mp-dim">${r.latency_ms} ms${r.usage ? " · " + (r.usage.total_tokens || "?") + " tokens" : ""}</div>`;
  } catch (e) {
    ansEl.textContent = "Test failed: " + e.message;
  }
}

function _mpOpenLogs(st, id) {
  _mpCloseLogs(st);
  const view = st.node.querySelector(".mp-logs-view");
  view.textContent = "";
  // EventSource through the same-origin proxy — the manager's SSE stream.
  const es = new EventSource(`/api/llm/models/${encodeURIComponent(id)}/logs`);
  st.es = es;
  es.onmessage = (ev) => {
    let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
    if (d.line !== undefined) {
      const atBottom = view.scrollTop + view.clientHeight >= view.scrollHeight - 30;
      view.textContent += d.line + "\n";
      if (view.textContent.length > 200000) view.textContent = view.textContent.slice(-150000);
      if (atBottom) view.scrollTop = view.scrollHeight;
    }
    if (d.status !== undefined && st.model) {
      const pill = st.node.querySelector(".mp-status-pill");
      pill.className = "mp-status-pill mp-status-" + d.status;
      st.node.querySelector(".mp-status-text").textContent = _MP_STATUS_LABEL[d.status] || d.status;
      if (d.ready) mpLoadModels();
    }
    if (d.eof) _mpCloseLogs(st);
  };
  es.onerror = () => { /* browser auto-retries; partial logs stay */ };
}

function _mpCloseLogs(st) {
  if (st.es) { st.es.close(); st.es = null; }
}

async function mpLoadCache() {
  if (!_mpState.active) return;
  let data;
  try { data = await _mpApi("cache"); }
  catch (e) { return; }
  const models = data.models || [];
  const list = document.getElementById("mp-cache-list");
  list.innerHTML = "";
  document.getElementById("mp-cache-count").textContent = models.length
    ? `· ${models.length} on disk (${data.total_gb} GB)` : "";
  document.getElementById("mp-cache-empty").hidden = models.length > 0;
  for (const m of models) {
    const li = document.createElement("li");
    li.className = "mp-cache-row";
    li.innerHTML =
      `<span class="mp-c-id">${escapeHtml(m.hf_id)}` +
      (m.multimodal ? ` <span class="mp-type-pill">vision</span>` : "") + `</span>` +
      `<span class="mp-c-size">${m.size_gb} GB</span>` +
      `<span class="mp-c-actions">` +
      `<button class="btn btn-small btn-primary mp-c-run" type="button">Run</button>` +
      `<button class="btn btn-small btn-danger mp-c-free" type="button">Free</button></span>`;
    li.querySelector(".mp-c-run").addEventListener("click", () => {
      showToast("Launching " + m.hf_id + " from cache…", "ok");
      mpAdd(m.hf_id, false);
    });
    li.querySelector(".mp-c-free").addEventListener("click", async () => {
      const ok = await uiConfirm({
        title: `Free ${m.hf_id}?`,
        message: `Deletes ${m.size_gb} GB of weights from disk. Re-running later re-downloads.`,
        okText: "Free", danger: true,
      });
      if (!ok) return;
      try {
        await _mpApi("cache/delete", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hf_id: m.hf_id }),
        });
        showToast("Freed " + m.hf_id, "ok");
        mpLoadCache();
      } catch (e) { showToast(e.message, "error"); }
    });
    list.appendChild(li);
  }
}

async function mpLoadModels() {
  if (!_mpState.active) return;
  let data;
  try { data = await _mpApi("models"); }
  catch (e) { _mpSetOffline(true); return; }
  _mpSetOffline(false);
  const models = data.models || [];
  const seen = new Set();
  for (const m of models) { mpRenderCard(m); seen.add(m.id); }
  for (const [id, st] of _mpState.cards) {
    if (!seen.has(id)) { _mpCloseLogs(st); st.node.remove(); _mpState.cards.delete(id); }
  }
  document.getElementById("mp-models-empty").hidden = models.length > 0;
}

function onModelsPageEntered() {
  if (_mpState.active) return;
  _mpState.active = true;
  fetch("/api/llm-info").then(r => r.json()).then(i => { _mpState.info = i; }).catch(() => {});
  mpLoadBanner(); mpLoadModels(); mpLoadCache();
  _mpState.pollTimer = setInterval(mpLoadModels, 5000);
  _mpState.bannerTimer = setInterval(mpLoadBanner, 15000);
}

function onModelsPageLeft() {
  if (!_mpState.active) return;
  _mpState.active = false;
  clearInterval(_mpState.pollTimer); _mpState.pollTimer = null;
  clearInterval(_mpState.bannerTimer); _mpState.bannerTimer = null;
  for (const [, st] of _mpState.cards) _mpCloseLogs(st);
}

function initModelsPage() {
  const form = document.getElementById("mp-add-form");
  if (!form) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const hf = document.getElementById("mp-hf-id").value.trim();
    if (hf) mpAdd(hf, false);
  });
  document.getElementById("mp-analyze-btn").addEventListener("click", mpAnalyze);
  document.getElementById("mp-refresh-btn").addEventListener("click", () => { mpLoadBanner(); mpLoadModels(); });
  document.getElementById("mp-cache-refresh").addEventListener("click", mpLoadCache);
}

// =====================================================================
// Voice Studio page — native port of miniclosedai-voice's Voice Studio.
// Targets ANY registered kind='voice' backend (local or remote) through the
// same-origin /api/voicestudio/{backend_id}/* proxy. Clone flow: record via
// mic (or upload audio) → mono WAV in the browser → POST /voices.
// =====================================================================
const _VS_MAX_RECORD_S = 30;   // recorder auto-stop
const _VS_MAX_UPLOAD_S = 90;   // matches the server's trim cap

const _vsState = {
  active: false,
  backendId: null,
  blob: null,          // staged WAV for the save form
  rec: null,           // live recording state
};

const _VS_SCRIPTS = {
  en: "The quick brown fox jumps over the lazy dog. I enjoy reading aloud in a calm, natural voice — clear consonants, easy pace, and a friendly tone that sounds like everyday conversation.",
  es: "El veloz zorro marrón salta sobre el perro perezoso. Me gusta leer en voz alta con calma y naturalidad — consonantes claras, ritmo tranquilo y un tono amable de conversación cotidiana.",
};

function _vsApi(path, opts = {}) {
  const bid = _vsState.backendId;
  return fetch(`/api/voicestudio/${bid}/${path}`, opts).then(async (r) => {
    if (!r.ok) {
      let detail = `HTTP ${r.status}`;
      try { const b = await r.json(); detail = b.detail || detail; } catch (e) {}
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return r.status === 204 ? null : r.json();
  });
}

// WAV encoder — ported verbatim from miniclosedai-voice's Voice Studio so the
// wire format stays byte-identical (float32 mono chunks → int16 PCM WAV).
function _vsEncodeWav(chunks, srcRate, dstRate) {
  let totalLen = 0;
  for (const c of chunks) totalLen += c.length;
  const merged = new Float32Array(totalLen);
  let offset = 0;
  for (const c of chunks) { merged.set(c, offset); offset += c.length; }
  let resampled;
  if (srcRate === dstRate) {
    resampled = merged;
  } else {
    const newLen = Math.round(merged.length * (dstRate / srcRate));
    resampled = new Float32Array(newLen);
    const ratio = (merged.length - 1) / (newLen - 1);
    for (let i = 0; i < newLen; i++) {
      const idx = i * ratio;
      const lo = Math.floor(idx);
      const hi = Math.min(lo + 1, merged.length - 1);
      const t = idx - lo;
      resampled[i] = merged[lo] * (1 - t) + merged[hi] * t;
    }
  }
  const i16 = new Int16Array(resampled.length);
  for (let i = 0; i < resampled.length; i++) {
    const s = Math.max(-1, Math.min(1, resampled[i]));
    i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const blockAlign = 2;
  const byteRate = dstRate * blockAlign;
  const dataSize = i16.length * 2;
  const buf = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buf);
  const writeStr = (off, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, dstRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);
  new Int16Array(buf, 44).set(i16);
  return new Blob([buf], { type: "audio/wav" });
}

function _vsBackends() {
  return (backendCache || []).filter(b => b.kind === "voice" && b.enabled);
}

function vsRenderBackendSelect() {
  const sel = document.getElementById("vs-backend-select");
  if (!sel) return;
  const backends = _vsBackends();
  sel.innerHTML = "";
  if (!backends.length) {
    sel.innerHTML = '<option value="">No voice services — add one in Settings</option>';
    _vsState.backendId = null;
    document.getElementById("vs-health").textContent = "";
    document.getElementById("vs-voices-list").innerHTML = "";
    return;
  }
  let saved = null;
  try { saved = parseInt(localStorage.getItem("miniclosedai:vsBackend"), 10); } catch (e) {}
  for (const b of backends) {
    const opt = document.createElement("option");
    opt.value = String(b.id);
    opt.textContent = `${b.name} — ${b.base_url}`;
    sel.appendChild(opt);
  }
  const pick = backends.some(b => b.id === saved) ? saved : backends[0].id;
  sel.value = String(pick);
  _vsState.backendId = pick;
}

async function vsLoadHealth() {
  const el = document.getElementById("vs-health");
  if (!el || _vsState.backendId == null) return;
  try {
    const h = await _vsApi("health");
    el.innerHTML =
      `ASR <strong>${escapeHtml(h.asr_model || "?")}</strong> · ` +
      `TTS <strong>${escapeHtml(h.tts_model || "?")}</strong> · ` +
      `device ${escapeHtml(h.device || "?")} · ` +
      (h.voices_loaded ? "voices loaded ✓" : "warming up…") +
      (h.relay_capable ? " · relay-capable ✓" : "");
  } catch (e) {
    el.textContent = `Service unreachable: ${e.message}`;
  }
}

async function vsLoadVoices() {
  const list = document.getElementById("vs-voices-list");
  const empty = document.getElementById("vs-voices-empty");
  if (!list || _vsState.backendId == null) return;
  let cat;
  try { cat = await _vsApi("voices"); }
  catch (e) { list.innerHTML = ""; empty.hidden = true; return; }
  list.innerHTML = "";
  let total = 0;
  for (const lang of Object.keys(cat).sort()) {
    const voices = cat[lang] || [];
    if (!voices.length) continue;
    const head = document.createElement("div");
    head.className = "vs-lang-head";
    head.textContent = lang.toUpperCase();
    list.appendChild(head);
    for (const v of voices) {
      total++;
      const row = document.createElement("div");
      row.className = "vs-voice-row";
      const label = document.createElement("span");
      label.textContent = v.name || v.id;
      const idc = document.createElement("code");
      idc.className = "vs-voice-id";
      idc.textContent = v.id;
      row.append(label, idc);
      if (v.id !== "default") {
        const del = document.createElement("button");
        del.type = "button";
        del.className = "btn btn-small btn-danger";
        del.textContent = "Delete";
        del.addEventListener("click", async () => {
          const ok = await uiConfirm({
            title: `Delete voice '${v.name || v.id}'?`,
            message: "Removes the cloned reference clip from the voice service.",
            okText: "Delete", danger: true,
          });
          if (!ok) return;
          try {
            await _vsApi(`voices/${encodeURIComponent(v.id)}`, { method: "DELETE" });
            showToast(`Deleted voice ${v.id}`, "ok");
            vsLoadVoices();
            loadVoices();   // chat topbar voice picker stays in sync
          } catch (e) { showToast(e.message, "error"); }
        });
        row.appendChild(del);
      }
      list.appendChild(row);
    }
  }
  empty.hidden = total > 0;
}

// ---- recorder (ScriptProcessor capture → float32 chunks) ----
async function vsStartRecording() {
  const status = document.getElementById("vs-status");
  status.textContent = "";
  if (!navigator.mediaDevices?.getUserMedia) {
    status.textContent = "This browser doesn't support audio recording.";
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
  } catch (e) {
    status.textContent = `Microphone access denied: ${e?.message || e}`;
    return;
  }
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  source.connect(processor);
  const silence = ctx.createGain();
  silence.gain.value = 0;
  processor.connect(silence);
  silence.connect(ctx.destination);

  const rec = { ctx, stream, source, processor, chunks: [], sampleRate: ctx.sampleRate,
                startedAt: performance.now(), timer: null };
  _vsState.rec = rec;
  const levelBar = document.getElementById("vs-level-bar");
  processor.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    rec.chunks.push(new Float32Array(input));
    let sumSq = 0;
    for (let i = 0; i < input.length; i++) sumSq += input[i] * input[i];
    const pct = Math.min(100, Math.round(Math.sqrt(sumSq / input.length) * 250));
    if (levelBar) levelBar.style.width = pct + "%";
  };

  const btn = document.getElementById("vs-record-btn");
  btn.textContent = "■ Stop";
  btn.classList.add("is-recording");
  document.getElementById("vs-rec-timer").hidden = false;
  document.getElementById("vs-level").hidden = false;
  const script = document.getElementById("vs-script");
  script.hidden = false;
  script.textContent = _VS_SCRIPTS[document.getElementById("vs-lang").value] || _VS_SCRIPTS.en;

  rec.timer = setInterval(() => {
    const s = (performance.now() - rec.startedAt) / 1000;
    document.getElementById("vs-rec-timer").textContent =
      `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
    if (s >= _VS_MAX_RECORD_S) vsStopRecording();
  }, 250);
}

async function vsStopRecording() {
  const rec = _vsState.rec;
  if (!rec) return;
  _vsState.rec = null;
  clearInterval(rec.timer);
  try {
    rec.processor.disconnect();
    rec.source.disconnect();
    rec.processor.onaudioprocess = null;
    for (const t of rec.stream.getTracks()) t.stop();
    await rec.ctx.close();
  } catch (e) {}
  const btn = document.getElementById("vs-record-btn");
  btn.textContent = "● Record";
  btn.classList.remove("is-recording");
  document.getElementById("vs-rec-timer").hidden = true;
  document.getElementById("vs-level").hidden = true;
  document.getElementById("vs-script").hidden = true;
  if (!rec.chunks.length) {
    document.getElementById("vs-status").textContent = "Captured zero audio — try again.";
    return;
  }
  _vsStage(_vsEncodeWav(rec.chunks, rec.sampleRate, rec.sampleRate));
}

// Decode an uploaded audio file (any browser-decodable format), downmix to
// mono, trim to the server's cap, and re-encode as WAV — same pipeline as
// the original Voice Studio uploader.
async function vsLoadAudioFile(file) {
  const status = document.getElementById("vs-status");
  status.textContent = "";
  if (!file) return;
  if (file.size > 40 * 1024 * 1024) {
    status.textContent = `File too large (${(file.size / 1024 / 1024).toFixed(1)} MB; max 40 MB).`;
    return;
  }
  let audioBuffer;
  try {
    const arrayBuf = await file.arrayBuffer();
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    audioBuffer = await ctx.decodeAudioData(arrayBuf);
    try { await ctx.close(); } catch (e) {}
  } catch (e) {
    status.textContent = `Could not decode this file: ${e?.message || e}. Try WAV / MP3 / M4A / OGG.`;
    return;
  }
  if (audioBuffer.duration < 0.5) {
    status.textContent = `Audio is only ${audioBuffer.duration.toFixed(2)} s — at least 0.5 s required.`;
    return;
  }
  const maxSamples = Math.floor(_VS_MAX_UPLOAD_S * audioBuffer.sampleRate);
  const n = Math.min(audioBuffer.length, maxSamples);
  const channels = audioBuffer.numberOfChannels;
  const mono = new Float32Array(n);
  if (channels === 1) {
    mono.set(audioBuffer.getChannelData(0).subarray(0, n));
  } else {
    const cs = [];
    for (let i = 0; i < channels; i++) cs.push(audioBuffer.getChannelData(i));
    for (let i = 0; i < n; i++) {
      let sum = 0;
      for (let c = 0; c < channels; c++) sum += cs[c][i];
      mono[i] = sum / channels;
    }
  }
  if (audioBuffer.duration > _VS_MAX_UPLOAD_S) {
    showToast(`Audio trimmed to the first ${_VS_MAX_UPLOAD_S} s.`, "warn");
  }
  _vsStage(_vsEncodeWav([mono], audioBuffer.sampleRate, audioBuffer.sampleRate));
  const base = (file.name || "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  const nameEl = document.getElementById("vs-name");
  if (base && !nameEl.value) {
    nameEl.value = base.charAt(0).toUpperCase() + base.slice(1);
  }
}

function _vsStage(blob) {
  _vsState.blob = blob;
  const audio = document.getElementById("vs-audio");
  if (audio.src) URL.revokeObjectURL(audio.src);
  audio.src = URL.createObjectURL(blob);
  document.getElementById("vs-review").hidden = false;
  document.getElementById("vs-name").focus();
}

function vsDiscard() {
  const audio = document.getElementById("vs-audio");
  if (audio.src) URL.revokeObjectURL(audio.src);
  audio.src = "";
  _vsState.blob = null;
  document.getElementById("vs-review").hidden = true;
  document.getElementById("vs-name").value = "";
  document.getElementById("vs-file").value = "";
  document.getElementById("vs-status").textContent = "";
}

async function vsSaveVoice() {
  const status = document.getElementById("vs-status");
  const name = document.getElementById("vs-name").value.trim();
  if (!_vsState.blob) { status.textContent = "Record or upload a sample first."; return; }
  if (!name) { status.textContent = "Give the voice a name."; return; }
  const btn = document.getElementById("vs-save-btn");
  btn.disabled = true;
  status.textContent = "Uploading + conditioning…";
  try {
    const fd = new FormData();
    fd.append("audio", _vsState.blob, "sample.wav");
    fd.append("name", name);
    fd.append("language", document.getElementById("vs-lang").value);
    const r = await _vsApi("voices", { method: "POST", body: fd });
    showToast(`Voice '${r.name}' created (${r.voice_id})`, "ok");
    status.textContent = "";
    vsDiscard();
    vsLoadVoices();
    loadVoices();   // new clone appears in the chat voice picker immediately
  } catch (e) {
    status.textContent = "Save failed: " + e.message;
  } finally {
    btn.disabled = false;
  }
}

function onVoiceStudioPageEntered() {
  if (_vsState.active) return;
  _vsState.active = true;
  vsRenderBackendSelect();
  vsLoadHealth();
  vsLoadVoices();
}

function onVoiceStudioPageLeft() {
  if (!_vsState.active) return;
  _vsState.active = false;
  if (_vsState.rec) vsStopRecording();
}

function initVoiceStudioPage() {
  const sel = document.getElementById("vs-backend-select");
  if (!sel) return;
  sel.addEventListener("change", () => {
    _vsState.backendId = parseInt(sel.value, 10) || null;
    try { localStorage.setItem("miniclosedai:vsBackend", String(_vsState.backendId)); } catch (e) {}
    vsLoadHealth();
    vsLoadVoices();
  });
  document.getElementById("vs-record-btn").addEventListener("click", () => {
    _vsState.rec ? vsStopRecording() : vsStartRecording();
  });
  document.getElementById("vs-file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (f) vsLoadAudioFile(f);
  });
  document.getElementById("vs-save-btn").addEventListener("click", vsSaveVoice);
  document.getElementById("vs-discard-btn").addEventListener("click", vsDiscard);
}

// =====================================================================
// Security (Settings → Security). Opt-in auth: create the account here;
// afterwards the server serves the landing page to signed-out visitors and
// expects a bearer token on the API — in GRACE MODE: unauthenticated API
// requests still work but land in the "connections needing attention" list.
// =====================================================================
const _authState = { enabled: false, loggedIn: false, alertCount: 0, pollTimer: null };

function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function _refreshAuthAlertDot() {
  const dot = document.getElementById("settings-alert-dot");
  if (dot) dot.hidden = !(_authState.enabled && _authState.alertCount > 0);
}

async function loadAuthState() {
  try {
    const r = await fetch("/api/auth/state");
    if (!r.ok) return;
    const j = await r.json();
    _authState.enabled = !!j.enabled;
    _authState.loggedIn = !!j.logged_in;
    _authState.alertCount = j.alert_count || 0;
    _authState.username = j.username || "";
  } catch (e) { return; }
  _refreshAuthAlertDot();
  _renderSecuritySection();
}

function _renderSecuritySection() {
  const setup = document.getElementById("auth-setup-box");
  const manage = document.getElementById("auth-manage-box");
  const signout = document.getElementById("auth-signout-btn");
  if (!setup || !manage) return;
  setup.hidden = _authState.enabled;
  manage.hidden = !(_authState.enabled && _authState.loggedIn);
  if (signout) signout.hidden = !(_authState.enabled && _authState.loggedIn);
  if (_authState.loggedIn) {
    _setText("auth-username", _authState.username || "");
    _loadAuthAlerts();
  }
}

async function _loadAuthAlerts() {
  const list = document.getElementById("auth-alerts-list");
  const empty = document.getElementById("auth-alerts-empty");
  if (!list) return;
  let alerts = [];
  try {
    const r = await fetch("/api/auth/alerts");
    if (r.ok) alerts = (await r.json()).alerts || [];
  } catch (e) {}
  _authState.alertCount = alerts.length;
  _refreshAuthAlertDot();
  _setText("auth-alert-count", alerts.length ? `· ${alerts.length}` : "");
  list.innerHTML = "";
  if (empty) empty.hidden = alerts.length > 0;
  for (const a of alerts) {
    const row = document.createElement("div");
    row.className = "auth-alert-row";
    const meta = document.createElement("div");
    meta.className = "auth-alert-meta";
    meta.innerHTML =
      `<code>${escapeHtml(a.method)} ${escapeHtml(a.path)}</code>` +
      `<span class="mp-dim"> from ${escapeHtml(a.ip)} · ×${a.count} · last ${escapeHtml(a.last_seen)}` +
      (a.user_agent ? ` · ${escapeHtml(a.user_agent.slice(0, 60))}` : "") + `</span>`;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-small";
    btn.textContent = "Dismiss";
    btn.addEventListener("click", async () => {
      try {
        await fetch("/api/auth/alerts/dismiss", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fingerprint: a.fingerprint }),
        });
      } catch (e) {}
      _loadAuthAlerts();
    });
    row.append(meta, btn);
    list.appendChild(row);
  }
}

async function _authPost(path, body) {
  const r = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) {
    let d = `HTTP ${r.status}`;
    try { d = (await r.json()).detail || d; } catch (e) {}
    throw new Error(typeof d === "string" ? d : JSON.stringify(d));
  }
  return r.json();
}

function initSecurityUI() {
  const setupBtn = document.getElementById("auth-setup-btn");
  if (!setupBtn) return;

  setupBtn.addEventListener("click", async () => {
    const user = document.getElementById("auth-setup-user").value.trim();
    const p1 = document.getElementById("auth-setup-pass").value;
    const p2 = document.getElementById("auth-setup-pass2").value;
    const status = document.getElementById("auth-setup-status");
    if (!user || !p1) { status.textContent = "Username and password required."; return; }
    if (p1.length < 6) { status.textContent = "Password must be at least 6 characters."; return; }
    if (p1 !== p2) { status.textContent = "Passwords don't match."; return; }
    setupBtn.disabled = true;
    try {
      const j = await _authPost("/api/auth/setup", { username: user, password: p1 });
      await loadAuthState();
      // Reveal the token immediately — this is the one guaranteed sighting.
      const tokEl = document.getElementById("auth-token-value");
      if (tokEl) tokEl.textContent = j.api_token;
      showToast("Account created — auth is ON. Copy your API token now.", "ok");
    } catch (e) {
      status.textContent = e.message;
    } finally {
      setupBtn.disabled = false;
    }
  });

  document.getElementById("auth-signout-btn")?.addEventListener("click", async () => {
    try { await _authPost("/api/auth/logout"); } catch (e) {}
    location.replace("/");   // server now serves the landing page
  });

  document.getElementById("auth-token-reveal")?.addEventListener("click", async () => {
    try {
      const r = await fetch("/api/auth/token");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      _setText("auth-token-value", (await r.json()).api_token);
    } catch (e) { showToast("Could not load token: " + e.message, "error"); }
  });

  document.getElementById("auth-token-copy")?.addEventListener("click", async () => {
    try {
      const r = await fetch("/api/auth/token");
      const tok = (await r.json()).api_token;
      await copyText(tok);
      showToast("API token copied", "ok");
    } catch (e) { showToast("Copy failed", "error"); }
  });

  document.getElementById("auth-token-regen")?.addEventListener("click", async () => {
    const ok = await uiConfirm({
      title: "Regenerate API token?",
      message: "Every client using the current token will start showing up in " +
               "'connections needing attention' until you update it.",
      okText: "Regenerate", danger: true,
    });
    if (!ok) return;
    try {
      const j = await _authPost("/api/auth/token/regenerate");
      _setText("auth-token-value", j.api_token);
      showToast("New token generated — update your clients.", "ok");
    } catch (e) { showToast(e.message, "error"); }
  });

  document.getElementById("auth-change-btn")?.addEventListener("click", async () => {
    const cur = document.getElementById("auth-cur-pass").value;
    const nw = document.getElementById("auth-new-pass").value;
    const status = document.getElementById("auth-manage-status");
    try {
      await _authPost("/api/auth/change", { current_password: cur, new_password: nw });
      status.textContent = "Password changed.";
      document.getElementById("auth-cur-pass").value = "";
      document.getElementById("auth-new-pass").value = "";
    } catch (e) { status.textContent = e.message; }
  });

  document.getElementById("auth-disable-btn")?.addEventListener("click", async () => {
    const cur = document.getElementById("auth-cur-pass").value;
    const status = document.getElementById("auth-manage-status");
    if (!cur) { status.textContent = "Enter your current password above to disable."; return; }
    const ok = await uiConfirm({
      title: "Disable authentication?",
      message: "The app becomes open again: no sign-in, no API token, alerts cleared.",
      okText: "Disable", danger: true,
    });
    if (!ok) return;
    try {
      await _authPost("/api/auth/disable", { password: cur });
      showToast("Authentication disabled.", "ok");
      await loadAuthState();
    } catch (e) { status.textContent = e.message; }
  });

  document.getElementById("auth-alerts-clear")?.addEventListener("click", async () => {
    try { await _authPost("/api/auth/alerts/clear"); } catch (e) {}
    _loadAuthAlerts();
  });

  // Light poll: keep the gear's amber dot honest while auth is on.
  _authState.pollTimer = setInterval(() => {
    if (_authState.enabled) loadAuthState();
  }, 60000);
}

// =====================================================================
// Instance identity (Settings → Instance identity). Server-side per-install
// name + description: the name becomes the browser-tab title, and because a
// tab's hover card shows the full document.title, appending the description
// makes it visible on hover — so multiple MiniClosedAI installs are tellable
// apart in a crowded tab strip. Nothing else in the app touches
// document.title, so this owns it outright.
// =====================================================================
let _instanceMeta = { name: "", description: "" };

function _applyInstanceTitle() {
  const name = (_instanceMeta.name || "").trim();
  const desc = (_instanceMeta.description || "").trim();
  const base = name || "MiniClosedAI";
  document.title = desc ? `${base} — ${desc}` : base;
}

async function loadInstanceMeta() {
  try {
    const r = await fetch("/api/instance");
    if (!r.ok) return;
    const j = await r.json();
    _instanceMeta = { name: j.name || "", description: j.description || "" };
  } catch {
    return;   // unreachable — keep the static <title> fallback
  }
  _applyInstanceTitle();
  const nameEl = document.getElementById("instance-name");
  const descEl = document.getElementById("instance-description");
  if (nameEl) nameEl.value = _instanceMeta.name;
  if (descEl) descEl.value = _instanceMeta.description;
}

function initInstanceMetaUI() {
  const nameEl = document.getElementById("instance-name");
  const descEl = document.getElementById("instance-description");
  const statusEl = document.getElementById("instance-meta-status");
  if (!nameEl || !descEl) return;

  let saveTimer = null;
  const save = async () => {
    const body = { name: nameEl.value.trim(), description: descEl.value.trim() };
    try {
      const r = await fetch("/api/instance", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      _instanceMeta = await r.json();
      _applyInstanceTitle();   // tab renames the moment the save lands
      if (statusEl) {
        statusEl.textContent = "Saved.";
        setTimeout(() => { if (statusEl.textContent === "Saved.") statusEl.textContent = ""; }, 1500);
      }
    } catch (e) {
      if (statusEl) statusEl.textContent = `Could not save: ${e?.message || e}`;
    }
  };
  const scheduleSave = () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 500);   // debounce while typing
  };
  for (const el of [nameEl, descEl]) {
    el.addEventListener("input", scheduleSave);
    el.addEventListener("change", () => { clearTimeout(saveTimer); save(); });
  }
}

async function init() {
  initGlobalTooltip();
  initTheme();
  initSidebarToggle();
  initActivityBar();
  loadSettings();
  // Fire-and-forget: rename the tab from this server's saved identity as
  // early as possible — independent of backend reachability below.
  initInstanceMetaUI();
  loadInstanceMeta().catch(() => {});
  bindParamDisplay();
  bindChat();
  bindAttachments();
  bindModal();
  initSplitter();
  initHSplitter();
  initSuggestionChips();
  initMicButton();
  initCallButton();
  if (typeof initBackendsUI === "function") initBackendsUI();
  initUiDialog();
  initLogsUI();
  initBotsUI();
  initAppsUI();
  initKnowledgeUI();
  initKnowledgeModalUI();
  initMcpUI();
  initMcpModalUI();
  initEvalsUI();
  initEvalModalUI();
  initModelPicker();
  startPullPoller();
  initUpgradeUI();
  initImportBotUI();
  initModelsPage();
  initVoiceStudioPage();
  initSecurityUI();
  loadAuthState().catch(() => {});
  els.input.addEventListener("input", autoGrowInput);
  // Warm the backend cache FIRST so the dashboard's push-to-talk affordance
  // (which checks for a kind='voice' row) shows up without first opening
  // Settings — and so loadModels()'s internal loadVoices() call can tell
  // whether a voice backend exists before deciding to probe /api/voices.
  // loadBackends() also re-runs every time Settings renders, so adding /
  // removing a voice endpoint there propagates here on the next save.
  await loadBackends();
  await loadModels();
  // Populate the TTS voice picker. Returns silently (no /api/voices probe)
  // when no voice backend is registered — the picker stays hidden until one
  // is added in Settings.
  await loadVoices();
  await loadConversations();
  initPromptGenUI();

  // Auto-open most recent conversation if any
  const list = await (await fetch("/api/conversations")).json();
  if (list.length) await openConversation(list[0].id);
}

// =====================================================================
// "Generate prompt" affordance — sidebar button that conjures a system
// prompt from a free-text description, using a remote Ollama hosted on
// app.interdataresearch.{com,ai}. Hidden unless that backend is both
// registered AND reachable.
// =====================================================================

// Storage: JSON-encoded {backend_id, model} so we can re-resolve the chosen
// pair after a reload. Old format (bare model name) is migrated on read.
const _PROMPT_GEN_CHOICE_KEY = "miniclosedai:promptGenChoice";

// Two meta-prompts. The "generate" path takes a free-text description and
// produces a system prompt from scratch. The "improve" path takes the current
// system prompt + the conversation transcript + a user instruction and
// rewrites the prompt to incorporate the change.
const _PROMPT_GEN_META_PROMPT = `You are an expert prompt engineer. Given a short description of what an AI assistant should do, write a single complete system prompt that defines:
- The assistant's role and tone
- What it should do (concrete, actionable instructions)
- What it should NOT do (only when relevant — guardrails, scope limits)
- The output format the assistant should follow (only if relevant)

Output ONLY the system prompt itself. Do not preface it with "Here is the prompt:" or explain your choices. Do not wrap it in code fences or quotation marks. Begin directly with the prompt body.`;

const _PROMPT_IMPROVE_META_PROMPT = `You are an expert prompt engineer. The user will send you three labeled sections:
1. CURRENT SYSTEM PROMPT — the system prompt as it stands now.
2. CONVERSATION TRANSCRIPT — recent turns between a user and the assistant running on that prompt. May be empty if the prompt has not been tested yet.
3. IMPROVEMENT REQUEST — what the prompt's owner wants changed or added.

Rewrite the system prompt to incorporate the improvement. Preserve everything that should stay; change only what is needed. When the conversation transcript shows the assistant doing the wrong thing, treat those turns as concrete failure cases the new prompt must prevent. When the transcript shows the assistant succeeding, preserve the behavior that produced those wins.

Output ONLY the improved system prompt body. No preface ("Here is the improved prompt:"), no commentary, no code fences, no quotation marks. Begin directly with the new prompt body.`;

// Currently-selected pair (resolved from saved choice or defaulted).
let _promptGenBackend = null;
let _promptGenModel = null;
// Latest snapshot of every enabled+running backend with at least one model,
// used to populate the Settings dropdown's optgroups.
let _promptGenAllBackends = [];

function _readSavedPromptGenChoice() {
  try {
    const raw = localStorage.getItem(_PROMPT_GEN_CHOICE_KEY);
    if (!raw) return null;
    // Old format: a bare model name string. Migrate by treating backend_id as
    // unknown so we'll just match by model name on first available backend.
    if (raw[0] !== "{") return { backend_id: null, model: raw };
    const parsed = JSON.parse(raw);
    if (typeof parsed?.model !== "string") return null;
    return { backend_id: parsed.backend_id ?? null, model: parsed.model };
  } catch {
    return null;
  }
}

function _resolvePromptGenChoice(allBackends) {
  if (!allBackends.length) return null;
  const saved = _readSavedPromptGenChoice();
  if (saved) {
    // Prefer exact (backend_id, model) match.
    if (saved.backend_id != null) {
      const b = allBackends.find(x => x.id === saved.backend_id);
      if (b) {
        const names = (b.models || []).map(m => m && m.name).filter(Boolean);
        if (names.includes(saved.model)) return { backend: b, model: saved.model };
      }
    }
    // Fall back to model-name match across any backend (handles migrated
    // old-format entries and the case where the user removed/re-added the
    // backend so its id changed).
    for (const b of allBackends) {
      const names = (b.models || []).map(m => m && m.name).filter(Boolean);
      if (names.includes(saved.model)) return { backend: b, model: saved.model };
    }
  }
  // Nothing saved or saved choice has vanished — pick the first model on the
  // first backend.
  const first = allBackends[0];
  const firstNames = (first.models || []).map(m => m && m.name).filter(Boolean);
  return { backend: first, model: firstNames[0] };
}

function _collectUsableBackends(modelsResponse) {
  const backends = (modelsResponse && modelsResponse.backends) || [];
  return backends.filter(b => {
    if (!b.enabled || !b.running) return false;
    const names = (b.models || []).map(m => m && m.name).filter(Boolean);
    return names.length > 0;
  });
}

function _renderPromptGenSettings() {
  const section = document.getElementById("prompt-gen-settings-section");
  const select = document.getElementById("prompt-gen-model-select");
  const hint = document.getElementById("prompt-gen-model-hint");
  if (!section || !select) return;

  if (!_promptGenAllBackends.length) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  // Group by backend, mirroring the Dashboard's model dropdown.
  select.innerHTML = "";
  let totalModels = 0;
  for (const b of _promptGenAllBackends) {
    const group = document.createElement("optgroup");
    group.label = `${b.name} — ${b.kind}`;
    const names = (b.models || []).map(m => m && m.name).filter(Boolean);
    for (const name of names) {
      const opt = document.createElement("option");
      // Encode backend_id in the value so the change handler can recover it.
      opt.value = `${b.id}::${name}`;
      opt.textContent = name;
      group.appendChild(opt);
      totalModels += 1;
    }
    select.appendChild(group);
  }
  if (_promptGenBackend && _promptGenModel) {
    select.value = `${_promptGenBackend.id}::${_promptGenModel}`;
  }
  if (hint) {
    const backendCount = _promptGenAllBackends.length;
    hint.textContent = `${totalModels} model${totalModels === 1 ? "" : "s"} across ${backendCount} reachable backend${backendCount === 1 ? "" : "s"}. The first model on the first backend is used by default; pick a larger or instruction-tuned one for better-quality prompts. Selection persists across reloads.`;
  }
}

async function _refreshPromptGenAvailability() {
  const bar = document.getElementById("prompt-gen-bar");
  const reset = () => {
    _promptGenBackend = null;
    _promptGenModel = null;
    _promptGenAllBackends = [];
    if (bar) bar.hidden = true;
    _renderPromptGenSettings();
  };
  try {
    const r = await fetch("/api/models");
    if (!r.ok) { reset(); return; }
    const data = await r.json();
    const usable = _collectUsableBackends(data);
    if (!usable.length) { reset(); return; }
    const chosen = _resolvePromptGenChoice(usable);
    if (!chosen) { reset(); return; }
    _promptGenAllBackends = usable;
    _promptGenBackend = chosen.backend;
    _promptGenModel = chosen.model;
    if (bar) bar.hidden = false;
    _renderPromptGenSettings();
  } catch {
    reset();
  }
}

// Status line under the prompt-gen bar. Three states:
//   _setPromptGenStatus("")                       → hidden
//   _setPromptGenStatus("…working…")              → "loading" with spinner
//   _setPromptGenStatus("…failed…", true)         → "error" tint, no spinner
// The loading state is visible AS SOON AS the request fires, so the user
// gets immediate feedback even before the first streamed token shows up
// in the System Prompt textarea (which can take several seconds on a
// cold-loaded model).
function _setPromptGenStatus(text, isError = false) {
  const el = document.getElementById("prompt-gen-status");
  if (!el) return;
  if (!text) {
    el.hidden = true;
    el.textContent = "";
    el.classList.remove("loading", "error");
    return;
  }
  el.hidden = false;
  el.textContent = text;
  el.classList.toggle("error", !!isError);
  el.classList.toggle("loading", !isError);
}

// Show / clear a spinner on the prompt-gen toggle button itself, so the
// trigger that the user just clicked visibly acknowledges the click rather
// than going silent. The button text/label stays in place — the icon swaps
// to a spinner via the `.is-busy` CSS class.
function _setPromptGenBusy(busy) {
  const toggle = document.getElementById("prompt-gen-toggle");
  if (!toggle) return;
  toggle.classList.toggle("is-busy", !!busy);
  toggle.setAttribute("aria-busy", busy ? "true" : "false");
  if (busy) toggle.setAttribute("aria-disabled", "true");
  else toggle.removeAttribute("aria-disabled");
}

// Mode is decided by whether the System Prompt textarea has any content.
// Empty → "generate" (build from scratch). Non-empty → "improve" (rewrite
// using the existing prompt + chat transcript + user instruction).
function _promptGenMode() {
  const ta = document.getElementById("system-prompt");
  return (ta && ta.value.trim()) ? "improve" : "generate";
}

function _updatePromptGenAffordance() {
  const labelEl = document.getElementById("prompt-gen-toggle-label");
  const toggle = document.getElementById("prompt-gen-toggle");
  const inputEl = document.getElementById("prompt-gen-input");
  const submitBtn = document.getElementById("prompt-gen-submit");
  if (!labelEl || !toggle) return;
  if (_promptGenMode() === "improve") {
    labelEl.textContent = "Improve prompt";
    toggle.dataset.tooltip = "Rewrite the existing prompt using the conversation as evidence";
    if (inputEl) inputEl.placeholder = "What should be improved? e.g. 'Be more concise', 'Always confirm before booking', 'Refuse off-topic questions politely'";
    if (submitBtn) submitBtn.textContent = "Improve";
  } else {
    labelEl.textContent = "Generate prompt";
    toggle.dataset.tooltip = "Generate a system prompt from a description";
    if (inputEl) inputEl.placeholder = "Describe the bot, e.g. 'Polite customer support agent for a SaaS company that escalates billing questions to humans'";
    if (submitBtn) submitBtn.textContent = "Generate";
  }
}

// Compact, plain-text transcript of the visible chat messages for the
// "improve" path. Long conversations get tail-trimmed (last 30 turns) to keep
// the prompt-gen request well under any backend's context window.
function _promptImproveTranscript() {
  const msgs = (typeof state !== "undefined" && Array.isArray(state.messages)) ? state.messages : [];
  if (!msgs.length) return "";
  const tail = msgs.slice(-30);
  const lines = [];
  for (const m of tail) {
    if (!m || !m.role) continue;
    const text = (typeof _userVisibleText === "function") ? _userVisibleText(m) : (typeof m.content === "string" ? m.content : "");
    const cleaned = (text || "").trim();
    if (!cleaned) continue;
    const speaker = m.role === "assistant" ? "Assistant" : (m.role === "user" ? "User" : m.role);
    lines.push(`${speaker}: ${cleaned}`);
  }
  return lines.join("\n\n");
}

async function _runPromptGeneration(description) {
  if (!_promptGenBackend || !_promptGenModel) return;
  const ta = document.getElementById("system-prompt");
  if (!ta) return;

  const mode = _promptGenMode();
  const isImprove = mode === "improve";

  // Build the meta-prompt + user payload for the chosen mode.
  let metaPrompt, userContent, statusVerb, savedOriginal = null;
  if (isImprove) {
    savedOriginal = ta.value;  // restore on failure so the user doesn't lose their prompt
    metaPrompt = _PROMPT_IMPROVE_META_PROMPT;
    const transcript = _promptImproveTranscript();
    const sections = [
      `=== CURRENT SYSTEM PROMPT ===\n${savedOriginal.trim()}`,
      transcript
        ? `=== CONVERSATION TRANSCRIPT ===\n${transcript}`
        : `=== CONVERSATION TRANSCRIPT ===\n(no conversation has been run against this prompt yet)`,
      `=== IMPROVEMENT REQUEST ===\n${description}`,
    ];
    userContent = sections.join("\n\n");
    statusVerb = "Improving";
  } else {
    metaPrompt = _PROMPT_GEN_META_PROMPT;
    userContent = description;
    statusVerb = "Generating";
  }

  _setPromptGenStatus(`${statusVerb} with ${_promptGenModel} on ${_promptGenBackend.name}…`);
  _setPromptGenBusy(true);
  ta.value = "";
  ta.disabled = true;

  try {
    const r = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        backend_id: _promptGenBackend.id,
        model: _promptGenModel,
        system_prompt: metaPrompt,
        messages: [{ role: "user", content: userContent }],
        // Higher cap than chat default — system prompts can be long.
        max_tokens: 4000,
        temperature: 0.5,
        // Keep model from "thinking" out loud for non-reasoning hosts;
        // reasoning hosts will ignore the flag.
        think: false,
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${r.status}`);
    }
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let done = false;
    while (!done) {
      const { value, done: streamDone } = await reader.read();
      done = streamDone;
      if (value) {
        buffer += decoder.decode(value, { stream: !done });
        // SSE frames are separated by \n\n; keep any partial frame in buffer.
        let idx;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          for (const line of frame.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.slice(6).trim();
            if (!payload) continue;
            let evt;
            try { evt = JSON.parse(payload); } catch { continue; }
            if (typeof evt.chunk === "string") {
              ta.value += evt.chunk;
              ta.scrollTop = ta.scrollHeight;
            } else if (evt.error) {
              throw new Error(evt.error);
            }
          }
        }
      }
    }
    // Trim trailing whitespace — the model often appends a stray newline.
    ta.value = ta.value.replace(/\s+$/, "");
    // The textarea's `input` listener (saveSettings + scheduleSaveToConversation)
    // doesn't fire when JS sets `.value` directly, so fire it ourselves to
    // persist into the active conversation.
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    _setPromptGenStatus("");
  } catch (e) {
    // On failure — especially in "improve" mode — restore the prompt the
    // user already had so they don't lose work to a streaming hiccup.
    if (isImprove && savedOriginal) ta.value = savedOriginal;
    const verb = isImprove ? "Improvement" : "Generation";
    _setPromptGenStatus(`${verb} failed: ${(e && e.message) || e}`, true);
  } finally {
    ta.disabled = false;
    _setPromptGenBusy(false);
    _updatePromptGenAffordance();
    ta.focus();
  }
}

function initPromptGenUI() {
  const bar = document.getElementById("prompt-gen-bar");
  if (!bar) return;
  const toggle = document.getElementById("prompt-gen-toggle");
  const row = document.getElementById("prompt-gen-input-row");
  const input = document.getElementById("prompt-gen-input");
  const submit = document.getElementById("prompt-gen-submit");
  const cancel = document.getElementById("prompt-gen-cancel");

  const showInput = (show) => {
    if (!row || !toggle) return;
    row.hidden = !show;
    toggle.hidden = show;
    if (show && input) { input.value = ""; input.focus(); }
  };

  toggle?.addEventListener("click", () => showInput(true));
  cancel?.addEventListener("click", () => { showInput(false); _setPromptGenStatus(""); });
  // Submit handler. We INTENTIONALLY keep the input row visible during the
  // request — collapsing it on click would hide the very button the user just
  // pressed before they can see it acknowledge their click. Instead, we mark
  // the submit button `.is-busy` (spinner replaces its label) and disable the
  // row's controls. The row collapses only when streaming is done so the
  // result lands cleanly into the System Prompt textarea.
  const fire = async () => {
    const desc = (input?.value || "").trim();
    if (!desc) { input?.focus(); return; }
    if (submit) { submit.classList.add("is-busy"); submit.disabled = true; submit.setAttribute("aria-busy", "true"); }
    if (input) input.disabled = true;
    if (cancel) cancel.disabled = true;
    try {
      await _runPromptGeneration(desc);
    } finally {
      if (submit) { submit.classList.remove("is-busy"); submit.disabled = false; submit.removeAttribute("aria-busy"); }
      if (input) input.disabled = false;
      if (cancel) cancel.disabled = false;
      showInput(false);
    }
  };
  submit?.addEventListener("click", fire);
  input?.addEventListener("keydown", e => {
    // Match the chat composer: Enter submits, Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); fire(); }
    else if (e.key === "Escape") { e.preventDefault(); showInput(false); }
  });

  // Settings → "Prompt Generator" model picker. Option values are encoded
  // as `<backend_id>::<model>` so we can persist both halves and re-resolve
  // them after a reload.
  const modelSelect = document.getElementById("prompt-gen-model-select");
  modelSelect?.addEventListener("change", () => {
    const v = modelSelect.value;
    if (!v) return;
    const sep = v.indexOf("::");
    if (sep < 0) return;
    const backendId = parseInt(v.slice(0, sep), 10);
    const modelName = v.slice(sep + 2);
    if (!modelName || Number.isNaN(backendId)) return;
    const b = _promptGenAllBackends.find(x => x.id === backendId);
    if (!b) return;
    _promptGenBackend = b;
    _promptGenModel = modelName;
    try {
      localStorage.setItem(
        _PROMPT_GEN_CHOICE_KEY,
        JSON.stringify({ backend_id: backendId, model: modelName }),
      );
    } catch {}
  });

  // Toggle button label flips between "Generate prompt" and "Improve prompt"
  // depending on whether the system-prompt textarea has content. Hook into
  // the existing `input` listener pipeline.
  els.systemPrompt?.addEventListener("input", _updatePromptGenAffordance);
  _updatePromptGenAffordance();

  // Initial probe + light periodic refresh so the button appears/disappears
  // as the backend's reachability flips. Same cadence as upgrade-status poll.
  _refreshPromptGenAvailability();
  setInterval(_refreshPromptGenAvailability, 60 * 1000);
}

// ─── Applications (groups of bots) ───────────────────────────
// An "application" is a named group of bots that maps to a real app. Mirrors
// the Bots page: an overview of cards, a detail view to chat with each bot
// individually, plus a generated TypeScript SDK per application.
const _APPS_VIEW_KEY = "miniclosedai:appsView";
const _appsState = {
  cache: [], filter: "", current: null,
  // "list" (vertical stack) or "grid" (responsive tiles). Same toggle pattern
  // as the bots page (`_botsState.view`); persisted under its own key so the
  // two views are independent.
  view: (() => { try { return localStorage.getItem(_APPS_VIEW_KEY) === "grid" ? "grid" : "list"; } catch { return "list"; } })(),
};

// Apply the current view mode to the apps list container + toggle buttons.
// Direct clone of `_applyBotsView`, swapped to the apps els + state.
function _applyAppsView() {
  const listEl = document.getElementById("apps-list");
  if (listEl) listEl.classList.toggle("grid-view", _appsState.view === "grid");
  if (els.appsViewList) {
    const isList = _appsState.view === "list";
    els.appsViewList.classList.toggle("active", isList);
    els.appsViewList.setAttribute("aria-pressed", String(isList));
  }
  if (els.appsViewGrid) {
    const isGrid = _appsState.view === "grid";
    els.appsViewGrid.classList.toggle("active", isGrid);
    els.appsViewGrid.setAttribute("aria-pressed", String(isGrid));
  }
}

function _setAppsView(view) {
  _appsState.view = view === "grid" ? "grid" : "list";
  try { localStorage.setItem(_APPS_VIEW_KEY, _appsState.view); } catch (_) {}
  _applyAppsView();
}
const _sdkState = { files: [], active: 0, appId: null, appName: "", lang: "ts" };
const _SDK_LANG_LABELS = { ts: "TypeScript", js: "JavaScript", py: "Python" };
const _SDK_LANG_HINTS = {
  ts: "Drop this folder into a TypeScript project to call this application's bots over the MiniClosedAI HTTP API. The server must be running and reachable. Each bot is exposed as a function named after it.",
  js: "Drop this folder into any Node 18+ project (or load it in a browser) to call this application's bots over the MiniClosedAI HTTP API. The server must be running and reachable. Each bot is exposed as a function named after it.",
  py: "Drop this package into your Python project (anywhere on sys.path — stdlib only, no pip install) to call this application's bots over the MiniClosedAI HTTP API. The server must be running and reachable. Each bot is exposed as a function named after it.",
};

const _X_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
// Feather: layers — the application (group) avatar fallback.
const _APP_AVATAR_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>';

function _renderAppAvatarInto(el, a) {
  el.innerHTML = "";
  el.style.removeProperty("--avatar-hue");
  if (a.avatar) {
    const img = document.createElement("img");
    img.src = a.avatar; img.alt = "";
    el.appendChild(img);
    el.classList.remove("is-fallback");
  } else {
    el.innerHTML = _APP_AVATAR_SVG;
    el.classList.add("is-fallback");
    // Offset hue from the bot formula so app fallbacks read distinct from bots.
    el.style.setProperty("--avatar-hue", String((a.id * 67 + 23) % 360));
  }
}

function _linkHost(link) {
  if (!link) return "";
  try { return new URL(link).host; } catch { return link; }
}

// JS mirror of sdkgen.function_names — the SDK reference name for each bot.
const _APP_FN_RESERVED = new Set(["break","case","catch","class","const","continue","debugger","default","delete","do","else","enum","export","extends","false","finally","for","function","if","import","in","instanceof","new","null","return","super","switch","this","throw","true","try","typeof","var","void","while","with","yield","let","static","await","async","Bot","DEFAULT_BASE_URL","MiniClosedAIError"]);
function _appCamel(name) {
  const parts = (name || "").split(/[^a-zA-Z0-9]+/).filter(Boolean);
  if (!parts.length) return "";
  let head = parts[0];
  head = head === head.toUpperCase() ? head.toLowerCase() : head[0].toLowerCase() + head.slice(1);
  let ident = head + parts.slice(1).map(p => p[0].toUpperCase() + p.slice(1)).join("");
  if (/^[0-9]/.test(ident)) ident = "bot" + ident[0].toUpperCase() + ident.slice(1);
  return ident;
}
function _appFnNames(bots) {
  const seen = new Set(), out = {};
  for (const b of bots) {
    let base = _appCamel(b.title || "");
    if (!base || _APP_FN_RESERVED.has(base)) base = "bot" + b.id;
    let name = base;
    if (seen.has(name)) name = base + "_" + b.id;
    seen.add(name);
    out[b.id] = name;
  }
  return out;
}

async function loadApps() {
  try {
    const r = await fetch("/api/apps");
    _appsState.cache = r.ok ? await r.json() : [];
  } catch { _appsState.cache = []; }
  renderAppsPage();
  return _appsState.cache;
}

function onAppsPageEntered() { loadApps(); }

function _appMatchesFilter(a, q) {
  if (!q) return true;
  return `${a.name || ""} ${a.description || ""} ${a.link || ""}`.toLowerCase().includes(q);
}

function renderAppsPage() {
  const listEl = document.getElementById("apps-list");
  if (!listEl) return;
  _applyAppsView();
  const q = _appsState.filter.trim().toLowerCase();
  const all = _appsState.cache || [];
  const filtered = all.filter(a => _appMatchesFilter(a, q));

  listEl.innerHTML = "";
  for (const a of filtered) {
    const card = document.createElement("div");
    card.className = "bot-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");

    const avatar = document.createElement("button");
    avatar.type = "button";
    avatar.className = "bot-card-avatar";
    avatar.dataset.tooltip = a.avatar ? "Change logo" : "Add logo";
    avatar.setAttribute("aria-label", `${a.avatar ? "Change" : "Add"} logo for ${a.name}`);
    _renderAppAvatarInto(avatar, a);
    avatar.addEventListener("click", e => { e.stopPropagation(); _pickAppAvatar(a); });

    const title = document.createElement("div");
    title.className = "bot-card-title";
    title.textContent = a.name || "(unnamed application)";

    const meta = document.createElement("div");
    meta.className = "bot-card-meta";
    const parts = [`${a.bot_count} bot${a.bot_count === 1 ? "" : "s"}`];
    if (a.link) parts.push(_linkHost(a.link));
    parts.push(_formatRelative(a.updated_at));
    parts.forEach((p, i) => {
      if (i > 0) { const sep = document.createElement("span"); sep.className = "sep"; sep.textContent = "·"; meta.appendChild(sep); }
      const span = document.createElement("span"); span.textContent = p; meta.appendChild(span);
    });

    const textWrap = document.createElement("div");
    textWrap.className = "bot-card-text";
    textWrap.appendChild(title); textWrap.appendChild(meta);
    card.appendChild(avatar); card.appendChild(textWrap);

    const actions = document.createElement("div");
    actions.className = "bot-card-actions";
    const sdkBtn = document.createElement("button");
    sdkBtn.type = "button"; sdkBtn.className = "bot-card-action"; sdkBtn.dataset.tooltip = "Generate SDK";
    sdkBtn.setAttribute("aria-label", `Generate SDK for ${a.name}`);
    sdkBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>';
    sdkBtn.addEventListener("click", e => { e.stopPropagation(); openSdkModal(a.id, a.name); });
    const exportBtn = document.createElement("button");
    exportBtn.type = "button"; exportBtn.className = "bot-card-action";
    exportBtn.dataset.tooltip = "Export as .miniclosed-app.json (config-only — Shift-click to include history)";
    exportBtn.setAttribute("aria-label", `Export ${a.name}`);
    // Download-cloud icon (matches the import button's family).
    exportBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="8 17 12 21 16 17"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>';
    exportBtn.addEventListener("click", e => { e.stopPropagation(); _downloadApp(a.id, e.shiftKey); });
    const editBtn = document.createElement("button");
    editBtn.type = "button"; editBtn.className = "bot-card-action"; editBtn.dataset.tooltip = "Edit application";
    editBtn.setAttribute("aria-label", `Edit ${a.name}`);
    editBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/></svg>';
    editBtn.addEventListener("click", e => { e.stopPropagation(); _openAppFormModal({ app: a }); });
    const delBtn = document.createElement("button");
    delBtn.type = "button"; delBtn.className = "bot-card-action danger"; delBtn.dataset.tooltip = "Delete application";
    delBtn.setAttribute("aria-label", `Delete ${a.name}`);
    delBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
    delBtn.addEventListener("click", e => { e.stopPropagation(); _deleteApp(a); });
    actions.append(sdkBtn, exportBtn, editBtn, delBtn);
    card.appendChild(actions);

    const open = () => openApp(a.id);
    card.addEventListener("click", open);
    card.addEventListener("keydown", e => {
      if (e.target !== card) return;
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    });
    listEl.appendChild(card);
  }

  const countEl = document.getElementById("apps-count");
  if (countEl) {
    const total = all.length, shown = filtered.length;
    countEl.textContent = q ? `${shown} of ${total} application${total === 1 ? "" : "s"}` : `${total} application${total === 1 ? "" : "s"}`;
  }
  const emptyEl = document.getElementById("apps-empty");
  if (emptyEl) {
    if (!all.length) { emptyEl.textContent = "No applications yet. Click + New application to group your bots."; emptyEl.hidden = false; }
    else if (!filtered.length) { emptyEl.textContent = "No applications match your filter."; emptyEl.hidden = false; }
    else emptyEl.hidden = true;
  }
}

async function openApp(appId) {
  let app;
  try {
    const r = await fetch(`/api/apps/${appId}`);
    if (!r.ok) { alert("Application not found."); return; }
    app = await r.json();
  } catch (e) { alert(`Could not load application: ${e.message}`); return; }
  _appsState.current = app;
  applyActivePage("app-detail");
  renderAppDetail(app);
}


// ---------- Chat-entry / chat-exit helpers ----------
//
// Centralize the two-step "switch to chat + open conversation" pattern so every
// entry point captures where the user came from. The back button (and Esc on
// dashboard) restores that return target — so a bot opened from inside an App
// returns to that App's detail view, not the global Bots page.

function enterChat(convId) {
  const here = document.body.dataset.page;
  if (here === "app-detail" && _appsState.current?.id != null) {
    state.chatReturnTo = { page: "app-detail", appId: _appsState.current.id };
  } else {
    state.chatReturnTo = { page: "bots" };
  }
  applyActivePage("dashboard");
  openConversation(convId);
}

async function exitChatToReturn() {
  const r = state.chatReturnTo || { page: "bots" };
  if (r.page === "app-detail" && r.appId != null) {
    // openApp() alerts + returns silently on failure without setting current;
    // if loading didn't end up on the app we wanted, fall back to the Apps list.
    await openApp(r.appId);
    if (_appsState.current?.id !== r.appId) applyActivePage("apps");
    return;
  }
  applyActivePage(r.page || "bots");
}

function renderAppDetail(app) {
  const c = document.getElementById("app-detail-container");
  if (!c) return;
  c.innerHTML = "";
  const bots = app.bots || [];
  const fnNames = _appFnNames(bots);

  const back = document.createElement("button");
  back.className = "btn btn-small";
  back.textContent = "← Applications";
  back.style.marginBottom = "10px";
  back.addEventListener("click", () => applyActivePage("apps"));
  c.appendChild(back);

  const head = document.createElement("div");
  head.className = "app-detail-head";
  const avatar = document.createElement("button");
  avatar.type = "button";
  avatar.className = "bot-card-avatar";
  avatar.dataset.tooltip = app.avatar ? "Change logo" : "Add logo";
  _renderAppAvatarInto(avatar, app);
  avatar.addEventListener("click", () => _pickAppAvatar(app));
  const htext = document.createElement("div");
  htext.className = "app-detail-head-text";
  const h1 = document.createElement("h1"); h1.textContent = app.name; htext.appendChild(h1);
  if (app.link) {
    const link = document.createElement("a");
    link.className = "app-detail-link"; link.href = app.link;
    link.target = "_blank"; link.rel = "noopener";
    link.textContent = app.link; htext.appendChild(link);
  }
  if (app.description) {
    const d = document.createElement("p"); d.className = "app-detail-desc"; d.textContent = app.description; htext.appendChild(d);
  }
  head.append(avatar, htext);
  c.appendChild(head);

  const actions = document.createElement("div");
  actions.className = "app-detail-actions";
  const count = document.createElement("span");
  count.className = "bots-count";
  count.textContent = `${bots.length} bot${bots.length === 1 ? "" : "s"}`;
  const spacer = document.createElement("span"); spacer.className = "spacer";
  const addBtn = document.createElement("button"); addBtn.className = "btn btn-small"; addBtn.textContent = "+ Add bot";
  addBtn.addEventListener("click", () => _openAddBotModal(app));
  const editBtn = document.createElement("button"); editBtn.className = "btn btn-small"; editBtn.textContent = "Edit";
  editBtn.addEventListener("click", () => _openAppFormModal({ app }));
  const exportBtn = document.createElement("button");
  exportBtn.className = "btn btn-small";
  exportBtn.textContent = "Export";
  exportBtn.title = "Download as .miniclosed-app.json — config only. Shift-click to also include each bot's message history.";
  exportBtn.addEventListener("click", e => _downloadApp(app.id, e.shiftKey));
  const sdkBtn = document.createElement("button"); sdkBtn.className = "btn btn-primary btn-small"; sdkBtn.textContent = "Generate SDK";
  sdkBtn.addEventListener("click", () => openSdkModal(app.id, app.name));
  actions.append(count, spacer, addBtn, editBtn, exportBtn, sdkBtn);
  c.appendChild(actions);

  const list = document.createElement("div");
  list.className = "bots-list";
  for (const b of bots) {
    const card = document.createElement("div");
    card.className = "bot-card"; card.tabIndex = 0; card.setAttribute("role", "button");
    const av = document.createElement("button");
    av.type = "button"; av.className = "bot-card-avatar"; av.dataset.tooltip = "Change avatar";
    _renderAvatarInto(av, b);
    av.addEventListener("click", e => { e.stopPropagation(); _pickAvatarFor(b); });
    const title = document.createElement("div"); title.className = "bot-card-title"; title.textContent = b.title || "(untitled)";
    const meta = document.createElement("div"); meta.className = "bot-card-meta";
    const m1 = document.createElement("span"); m1.textContent = b.model || "(no model)"; meta.appendChild(m1);
    const sep = document.createElement("span"); sep.className = "sep"; sep.textContent = "·"; meta.appendChild(sep);
    const fn = document.createElement("span"); fn.className = "bot-card-fn"; fn.textContent = `${fnNames[b.id]}()`;
    fn.title = `SDK reference — bot #${b.id}`; meta.appendChild(fn);
    const textWrap = document.createElement("div"); textWrap.className = "bot-card-text"; textWrap.append(title, meta);
    card.append(av, textWrap);

    const cardActions = document.createElement("div"); cardActions.className = "bot-card-actions";
    const rm = document.createElement("button");
    rm.type = "button"; rm.className = "bot-card-action danger"; rm.dataset.tooltip = "Remove from application";
    rm.setAttribute("aria-label", `Remove ${b.title} from ${app.name}`);
    rm.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>';
    rm.addEventListener("click", async e => {
      e.stopPropagation();
      try {
        const r = await fetch(`/api/apps/${app.id}/bots/${b.id}`, { method: "DELETE" });
        if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`));
        await loadConversations();
        await openApp(app.id);
      } catch (err) { alert(`Could not remove bot: ${err.message}`); }
    });
    cardActions.appendChild(rm);
    card.appendChild(cardActions);

    const open = () => enterChat(b.id);
    card.addEventListener("click", open);
    card.addEventListener("keydown", e => { if (e.target === card && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); open(); } });
    list.appendChild(card);
  }
  c.appendChild(list);
  if (!bots.length) {
    const empty = document.createElement("div"); empty.className = "bots-empty";
    empty.textContent = "No bots in this application yet. Click + Add bot to put some in.";
    c.appendChild(empty);
  }
}

// Upload a logo for an application (reuses the bot-avatar downscale pipeline).
let _appAvatarInput = null;
function _pickAppAvatar(app) {
  if (!_appAvatarInput) {
    _appAvatarInput = document.createElement("input");
    _appAvatarInput.type = "file"; _appAvatarInput.accept = "image/*"; _appAvatarInput.style.display = "none";
    document.body.appendChild(_appAvatarInput);
  }
  _appAvatarInput.value = "";
  _appAvatarInput.onchange = async () => {
    const file = _appAvatarInput.files && _appAvatarInput.files[0];
    if (!file) return;
    try {
      const dataUrl = await _makeAvatarDataUrl(file);
      const r = await fetch(`/api/apps/${app.id}/avatar`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ avatar: dataUrl }),
      });
      if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`));
      await loadApps();
      if (document.body.dataset.page === "app-detail" && _appsState.current && _appsState.current.id === app.id) {
        await openApp(app.id);
      }
    } catch (e) { alert(`Logo upload failed: ${e.message}`); }
  };
  _appAvatarInput.click();
}

// Minimal dynamically-built modal that reuses the existing .modal styling.
function _spawnModal(buildBody) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const modal = document.createElement("div");
  modal.className = "modal";
  backdrop.appendChild(modal);
  const close = () => backdrop.remove();
  backdrop.addEventListener("click", e => { if (e.target === backdrop) close(); });
  buildBody(modal, close);
  document.body.appendChild(backdrop);
  return { backdrop, modal, close };
}

function _modalHeader(modal, titleText, close) {
  const header = document.createElement("div");
  header.className = "modal-header";
  const h = document.createElement("h3"); h.textContent = titleText;
  const x = document.createElement("button"); x.className = "icon-btn"; x.setAttribute("aria-label", "Close"); x.innerHTML = _X_SVG; x.onclick = close;
  header.append(h, x); modal.appendChild(header);
}

function _formField(labelText, { value = "", placeholder = "", multiline = false } = {}) {
  const label = document.createElement("label"); label.className = "form-field";
  const span = document.createElement("span"); span.textContent = labelText;
  const input = multiline ? document.createElement("textarea") : document.createElement("input");
  if (!multiline) input.type = "text";
  input.value = value; input.placeholder = placeholder;
  if (multiline) input.rows = 3;
  label.append(span, input);
  return { label, input };
}

function _openAppFormModal({ app = null } = {}) {
  _spawnModal((modal, close) => {
    _modalHeader(modal, app ? "Edit application" : "New application", close);
    const form = document.createElement("div"); form.className = "backend-form";
    const name = _formField("Name", { value: app ? app.name : "", placeholder: "My probate app" });
    const link = _formField("Link (optional)", { value: app ? app.link : "", placeholder: "https://myapp.example" });
    const desc = _formField("Description (optional)", { value: app ? app.description : "", placeholder: "What this application is and which bots belong to it.", multiline: true });
    form.append(name.label, link.label, desc.label);
    const actions = document.createElement("div"); actions.className = "modal-actions";
    const spacer = document.createElement("div"); spacer.style.flex = "1";
    const cancel = document.createElement("button"); cancel.className = "btn btn-small"; cancel.textContent = "Cancel"; cancel.onclick = close;
    const save = document.createElement("button"); save.className = "btn btn-primary btn-small"; save.textContent = "Save";
    save.addEventListener("click", async () => {
      const payload = { name: name.input.value.trim(), link: link.input.value.trim(), description: desc.input.value.trim() };
      if (!payload.name) { name.input.focus(); return; }
      try {
        const r = app
          ? await fetch(`/api/apps/${app.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
          : await fetch("/api/apps", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`));
        const created = app ? null : await r.json();
        close();
        await loadApps();
        if (app && document.body.dataset.page === "app-detail" && _appsState.current && _appsState.current.id === app.id) {
          await openApp(app.id);
        } else if (!app && created) {
          await openApp(created.id);
        }
      } catch (e) { alert(`Save failed: ${e.message}`); }
    });
    actions.append(spacer, cancel, save);
    modal.append(form, actions);
    setTimeout(() => name.input.focus(), 0);
  });
}

async function _deleteApp(app) {
  if (!confirm(`Delete the application "${app.name}"? Its bots are kept — they just become ungrouped.`)) return;
  try {
    const r = await fetch(`/api/apps/${app.id}`, { method: "DELETE" });
    if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`));
    await loadConversations();
    if (document.body.dataset.page === "app-detail") applyActivePage("apps");
    await loadApps();
  } catch (e) { alert(`Delete failed: ${e.message}`); }
}

function _openAddBotModal(app) {
  _spawnModal((modal, close) => {
    _modalHeader(modal, "Add a bot", close);
    const hint = document.createElement("p"); hint.className = "kb-modal-hint";
    hint.textContent = "Pick a bot to add to this application. A bot belongs to one application — adding it here moves it from any previous one.";
    modal.appendChild(hint);
    const list = document.createElement("div"); list.className = "kb-modal-list";
    const appNameById = new Map((_appsState.cache || []).map(a => [a.id, a.name]));
    const bots = _botsState.cache || [];
    if (!bots.length) {
      const e = document.createElement("div"); e.className = "kb-modal-empty"; e.textContent = "No bots yet — create one on the Bots page first.";
      modal.appendChild(e);
    }
    for (const b of bots) {
      const row = document.createElement("div"); row.className = "bot-card";
      const av = document.createElement("span"); av.className = "bot-card-avatar"; _renderAvatarInto(av, b);
      const tw = document.createElement("div"); tw.className = "bot-card-text";
      const t = document.createElement("div"); t.className = "bot-card-title"; t.textContent = b.title || "(untitled)";
      const m = document.createElement("div"); m.className = "bot-card-meta";
      const here = b.app_id === app.id;
      const status = here ? "in this application" : (b.app_id != null ? `in ${appNameById.get(b.app_id) || "another application"}` : "ungrouped");
      const ms = document.createElement("span"); ms.textContent = status; m.appendChild(ms);
      tw.append(t, m); row.append(av, tw);
      const add = document.createElement("button");
      add.className = "btn btn-small"; add.style.marginLeft = "auto";
      add.textContent = here ? "Added" : "Add"; add.disabled = here;
      add.addEventListener("click", async () => {
        add.disabled = true;
        try {
          const r = await fetch(`/api/apps/${app.id}/bots`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ conversation_id: b.id }) });
          if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`));
          await loadConversations();
          close();
          await openApp(app.id);
        } catch (e) { alert(`Could not add bot: ${e.message}`); add.disabled = false; }
      });
      row.appendChild(add);
      list.appendChild(row);
    }
    modal.appendChild(list);
    const actions = document.createElement("div"); actions.className = "modal-actions";
    const spacer = document.createElement("div"); spacer.style.flex = "1";
    const done = document.createElement("button"); done.className = "btn btn-primary btn-small"; done.textContent = "Done"; done.onclick = close;
    actions.append(spacer, done); modal.appendChild(actions);
  });
}

// ── SDK preview modal (static markup in index.html) ──
async function openSdkModal(appId, appName, lang) {
  _sdkState.appId = appId;
  _sdkState.appName = appName || "";
  _sdkState.lang = lang || _sdkState.lang || "ts";
  const ok = await _loadSdkFiles();
  if (!ok) return;
  const bd = document.getElementById("sdk-modal-backdrop");
  if (bd) bd.classList.remove("hidden");
}

// Fetch the SDK files for the current (_sdkState.appId, _sdkState.lang) and
// re-render the modal. Returns false on error so callers can bail without
// opening/keeping the modal in a broken state.
async function _loadSdkFiles() {
  if (_sdkState.appId == null) return false;
  let data;
  try {
    const r = await fetch(`/api/apps/${_sdkState.appId}/sdk?lang=${_sdkState.lang}`);
    if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`));
    data = await r.json();
  } catch (e) { alert(`Could not generate SDK: ${e.message}`); return false; }
  _sdkState.files = data.files || [];
  _sdkState.active = 0;
  const nameEl = document.getElementById("sdk-modal-app");
  if (nameEl) nameEl.textContent = data.app ? `· ${data.app.name}` : (_sdkState.appName ? `· ${_sdkState.appName}` : "");
  const langLbl = document.getElementById("sdk-modal-lang-label");
  if (langLbl) langLbl.textContent = _SDK_LANG_LABELS[_sdkState.lang] || _sdkState.lang;
  const hint = document.getElementById("sdk-modal-hint");
  if (hint) hint.textContent = _SDK_LANG_HINTS[_sdkState.lang] || hint.textContent;
  document.querySelectorAll(".sdk-lang-tab").forEach(b => {
    const active = b.dataset.lang === _sdkState.lang;
    b.classList.toggle("active", active);
    b.setAttribute("aria-selected", active ? "true" : "false");
  });
  _renderSdkModal();
  return true;
}

function _renderSdkModal() {
  const listEl = document.getElementById("sdk-file-list");
  const codeEl = document.getElementById("sdk-code");
  if (!listEl || !codeEl) return;
  listEl.innerHTML = "";
  _sdkState.files.forEach((f, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "sdk-file-item" + (i === _sdkState.active ? " active" : "");
    // Drop the root "<slug>-sdk/" prefix for a cleaner tree.
    b.textContent = f.path.split("/").slice(1).join("/") || f.path;
    b.title = f.path;
    b.addEventListener("click", () => { _sdkState.active = i; _renderSdkModal(); });
    listEl.appendChild(b);
  });
  const f = _sdkState.files[_sdkState.active];
  codeEl.className = "";
  codeEl.removeAttribute("data-highlighted");
  codeEl.textContent = f ? f.content : "";
  if (window.hljs) { try { window.hljs.highlightElement(codeEl); } catch (_) {} }
}

function _closeSdkModal() {
  const bd = document.getElementById("sdk-modal-backdrop");
  if (bd) bd.classList.add("hidden");
}

function initAppsUI() {
  const newBtn = document.getElementById("apps-new-btn");
  if (newBtn) newBtn.addEventListener("click", () => _openAppFormModal({}));
  const filter = document.getElementById("apps-filter");
  if (filter) filter.addEventListener("input", () => { _appsState.filter = filter.value; renderAppsPage(); });
  if (els.appsViewList) els.appsViewList.addEventListener("click", () => _setAppsView("list"));
  if (els.appsViewGrid) els.appsViewGrid.addEventListener("click", () => _setAppsView("grid"));
  _applyAppsView();
  initAppsImportUI();

  const close = document.getElementById("sdk-modal-close");
  if (close) close.addEventListener("click", _closeSdkModal);
  const bd = document.getElementById("sdk-modal-backdrop");
  if (bd) bd.addEventListener("click", e => { if (e.target === bd) _closeSdkModal(); });
  const copy = document.getElementById("sdk-copy");
  if (copy) copy.addEventListener("click", async () => {
    const f = _sdkState.files[_sdkState.active];
    if (!f) return;
    try { await navigator.clipboard.writeText(f.content); copy.textContent = "Copied!"; setTimeout(() => { copy.textContent = "Copy file"; }, 1200); }
    catch { alert("Copy failed — select the text manually."); }
  });
  const dl = document.getElementById("sdk-download");
  if (dl) dl.addEventListener("click", () => {
    if (_sdkState.appId == null) return;
    const a = document.createElement("a");
    a.href = `/api/apps/${_sdkState.appId}/sdk.zip?lang=${_sdkState.lang}`; a.rel = "noopener";
    document.body.appendChild(a); a.click(); a.remove();
  });
  // Language tabs — switch lang, re-fetch, re-render. Disabled while loading
  // so a quick double-click doesn't leave the modal showing stale files.
  document.querySelectorAll(".sdk-lang-tab").forEach(b => {
    b.addEventListener("click", async () => {
      const next = b.dataset.lang;
      if (!next || next === _sdkState.lang) return;
      _sdkState.lang = next;
      document.querySelectorAll(".sdk-lang-tab").forEach(x => x.disabled = true);
      try { await _loadSdkFiles(); }
      finally { document.querySelectorAll(".sdk-lang-tab").forEach(x => x.disabled = false); }
    });
  });
}

init();

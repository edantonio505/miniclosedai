// MiniClosedAI frontend — vanilla JS.

const els = {
  modelSelect: document.getElementById("model-select"),
  convSelect: document.getElementById("conversation-select"),
  newChatBtn: document.getElementById("new-chat-btn"),
  clearChatBtn: document.getElementById("clear-chat-btn"),
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
  statusLine: document.getElementById("status-line"),
  messages: document.getElementById("messages"),
  form: document.getElementById("chat-form"),
  input: document.getElementById("input"),
  sendBtn: document.getElementById("send-btn"),
  modalBackdrop: document.getElementById("modal-backdrop"),
  modalClose: document.getElementById("modal-close"),
  codeSnippet: document.getElementById("code-snippet"),
  copyCode: document.getElementById("copy-code"),
  tabs: document.querySelectorAll(".tab"),
};

const DEFAULTS = { temperature: 0.7, max_tokens: 2048, top_p: 0.9, top_k: 40 };
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
  activeTab: "curl",
  abortController: null,
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
function render(md) { return marked.parse(md || ""); }
function scrollToBottom() { els.messages.scrollTop = els.messages.scrollHeight; }

function getParams() {
  const p = {
    temperature: parseFloat(els.temperature.value),
    max_tokens: parseInt(els.maxTokens.value, 10),
    top_p: parseFloat(els.topP.value),
    top_k: parseInt(els.topK.value, 10),
  };
  const t = thinkFromSelect();
  if (t !== undefined) p.think = t;
  const mt = els.maxThinking.value.trim();
  if (mt !== "") {
    const n = parseInt(mt, 10);
    if (Number.isFinite(n) && n > 0) p.max_thinking_tokens = n;
  }
  return p;
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
  const s = {
    ...getParams(),
    model: els.modelSelect.value,
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
function scheduleSaveToConversation() {
  if (!state.conversationId) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const patch = {
      ...getParams(),
      model: els.modelSelect.value || undefined,
      system_prompt: els.systemPrompt.value || undefined,
    };
    fetch(`/api/conversations/${state.conversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }).catch(() => {});
  }, 350);
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

// ---------- Models ----------
async function loadModels() {
  const r = await fetch("/api/models");
  const data = await r.json();
  els.modelSelect.innerHTML = "";

  if (!data.ollama_running) {
    const opt = new Option("(Ollama not running)", "");
    opt.disabled = true;
    els.modelSelect.add(opt);
    setStatus("err", "Ollama is not running. Start it with `ollama serve` (see INSTALL.md).");
    return [];
  }
  // Filter out cloud proxies (not local) and embedding-only models
  const usable = data.models.filter(m => {
    if (m.name.includes(":cloud") || m.remote_model) return false;
    const fam = (m.details && (m.details.family || "")) + " " + ((m.details && m.details.families) || []).join(" ");
    if (/bert|embed/i.test(fam) || /embed/i.test(m.name)) return false;
    return true;
  });

  if (!usable.length) {
    const opt = new Option("(no local chat models installed)", "");
    opt.disabled = true;
    els.modelSelect.add(opt);
    setStatus("warn", "Ollama is running but no local chat models are installed. Try: ollama pull llama3.2:3b");
    return [];
  }

  // Sort: small/recommended first, then alphabetical
  const models = [...usable].sort((a, b) => {
    const aRec = SMALL_MODEL_PREFIXES.some(p => a.name.startsWith(p));
    const bRec = SMALL_MODEL_PREFIXES.some(p => b.name.startsWith(p));
    if (aRec !== bRec) return aRec ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  for (const m of models) {
    const size = m.size ? ` (${fmtBytes(m.size)})` : "";
    els.modelSelect.add(new Option(`${m.name}${size}`, m.name));
  }

  const saved = JSON.parse(localStorage.getItem("miniclosedai:settings") || "{}");
  if (saved.model && models.some(m => m.name === saved.model)) {
    els.modelSelect.value = saved.model;
  }
  setStatus("ok", `Ollama connected · ${models.length} model${models.length === 1 ? "" : "s"} available`);
  return models;
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
  if (c.model) {
    const opts = [...els.modelSelect.options].map(o => o.value);
    if (opts.includes(c.model)) els.modelSelect.value = c.model;
  }
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
  const model = els.modelSelect.value;
  if (!model) {
    alert("Pick a model first.");
    return;
  }
  const r = await fetch("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      system_prompt: els.systemPrompt.value || "You are a helpful AI assistant.",
      title: "New Chat",
      ...getParams(),
    }),
  });
  const c = await r.json();
  state.conversationId = c.id;
  state.messages = [];
  await loadConversations();
  els.convSelect.value = String(c.id);
  renderMessages();
}

// ---------- Rendering ----------
function renderMessages() {
  els.messages.innerHTML = "";
  if (!state.messages.length) {
    const e = document.createElement("div");
    e.className = "empty-state";
    e.innerHTML = "<h2>Local LLM playground</h2><p>Type a message below to start. Parameters on the left apply to the next turn.</p>";
    els.messages.appendChild(e);
    return;
  }
  for (const m of state.messages) renderMessage(m);
  scrollToBottom();
}

function renderMessage(m) {
  const div = document.createElement("div");
  div.className = `msg ${m.role}`;
  if (m.role === "user") {
    div.textContent = m.content;
  } else {
    div.innerHTML = render(m.content);
  }
  if (m.params) {
    const badge = document.createElement("div");
    badge.className = "params-badge";
    badge.textContent = `${m.params.model || ""} · T=${m.params.temperature} · max=${m.params.max_tokens} · top_p=${m.params.top_p} · top_k=${m.params.top_k}`;
    div.appendChild(badge);
  }
  const emptyState = els.messages.querySelector(".empty-state");
  if (emptyState) emptyState.remove();
  els.messages.appendChild(div);
  return div;
}

// ---------- Streaming chat ----------
async function sendMessage(text) {
  const model = els.modelSelect.value;
  if (!model) { alert("Pick a model first."); return; }
  if (!text.trim()) return;

  // Ensure a conversation exists
  if (!state.conversationId) {
    await newConversation();
  }

  const params = getParams();
  const userMsg = { role: "user", content: text };
  state.messages.push(userMsg);
  renderMessage(userMsg);
  scrollToBottom();

  // Assistant placeholder with streaming cursor
  const assistantEl = renderMessage({ role: "assistant", content: "" });
  assistantEl.classList.add("cursor");
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

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: ac.signal,
      body: JSON.stringify({
        model,
        messages: state.messages.filter(m => m.role !== "system").map(m => ({ role: m.role, content: m.content })),
        system_prompt: els.systemPrompt.value || "You are a helpful AI assistant.",
        conversation_id: state.conversationId,
        ...params,
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
          if (!contentEl) { assistantEl.innerHTML = ""; contentEl = document.createElement("div"); assistantEl.appendChild(contentEl); }
          contentEl.innerHTML = render(assistantText);
          break;
        }
        if (data.thinking) {
          thinkingText += data.thinking;
          if (!thinkingEl) {
            assistantEl.innerHTML = "";
            thinkingEl = document.createElement("details");
            thinkingEl.className = "thinking";
            thinkingEl.open = true;
            thinkingEl.innerHTML = '<summary>💭 Thinking…</summary><div class="thinking-body"></div>';
            assistantEl.appendChild(thinkingEl);
            contentEl = document.createElement("div");
            assistantEl.appendChild(contentEl);
          }
          thinkingEl.querySelector(".thinking-body").textContent = thinkingText;
          scrollToBottom();
        }
        if (data.chunk) {
          assistantText += data.chunk;
          if (!contentEl) { assistantEl.innerHTML = ""; contentEl = document.createElement("div"); assistantEl.appendChild(contentEl); }
          contentEl.innerHTML = render(assistantText);
          // Collapse "thinking" once real content starts streaming
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
            truncatedNotice.textContent = `⛔ Stopped: thinking exceeded ${data.limit} tokens.`;
            assistantEl.appendChild(truncatedNotice);
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
      assistantEl.appendChild(stoppedNotice);
    } else {
      assistantText += `\n\n**Request failed:** ${e.message}`;
      if (!contentEl) { contentEl = document.createElement("div"); assistantEl.appendChild(contentEl); }
      contentEl.innerHTML = render(assistantText);
    }
  } finally {
    state.abortController = null;
    els.stopBtn.style.display = "none";
    els.sendBtn.style.display = "";
    assistantEl.classList.remove("cursor");
    // Add params badge to the final assistant message
    const badge = document.createElement("div");
    badge.className = "params-badge";
    badge.textContent = `${model} · T=${params.temperature} · max=${params.max_tokens} · top_p=${params.top_p} · top_k=${params.top_k}`;
    assistantEl.appendChild(badge);

    state.messages.push({ role: "assistant", content: assistantText, params: { model, ...params } });
    els.sendBtn.disabled = false;
    els.input.disabled = false;
    els.input.focus();
    loadConversations(); // refresh timestamps
  }
}

// ---------- API code modal ----------
// Each conversation is its own addressable "microservice function" on the server.
// The saved model + system prompt + sampling params are stored with the conversation,
// so the snippet just points at /api/conversations/{id}/chat/stream and sends a message.
function buildCodeSnippet(tab) {
  const base = window.location.origin;
  const convId = state.conversationId;
  if (!convId) {
    return "# Send a message first to create a conversation.\n# Each chat becomes its own configured API endpoint.";
  }
  const url = `${base}/api/conversations/${convId}/chat/stream`;
  const urlSync = `${base}/api/conversations/${convId}/chat`;
  const msg = "Hello!";

  if (tab === "curl") {
    return `# Streaming (SSE) — uses the saved model, system prompt & params for chat #${convId}
curl -N -X POST ${url} \\
  -H "Content-Type: application/json" \\
  -d '{"message": "${msg}"}'

# Non-streaming equivalent:
# curl -X POST ${urlSync} -H "Content-Type: application/json" -d '{"message":"${msg}"}'

# Any field is overridable per-call, e.g. {"message":"...","temperature":0.2,"persist":true}`;
  }
  if (tab === "python") {
    return `import httpx, json

# Each conversation is a saved function on the server — just send a message.
URL = "${url}"

with httpx.stream("POST", URL, json={"message": "${msg}"}, timeout=None) as r:
    for line in r.iter_lines():
        if line.startswith("data:"):
            data = json.loads(line[5:].strip())
            if "chunk" in data:
                print(data["chunk"], end="", flush=True)
            if data.get("end"):
                break

# Non-streaming: httpx.post("${urlSync}", json={"message": "${msg}"}).json()["response"]
# Override anything: {"message": "...", "temperature": 0.2, "persist": True}`;
  }
  if (tab === "js") {
    return `// Streaming call to saved chat #${convId}
const res = await fetch("${url}", {
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
}

// Non-streaming:
// const { response } = await fetch("${urlSync}", { method:"POST",
//   headers:{"Content-Type":"application/json"},
//   body: JSON.stringify({ message: "${msg}" })
// }).then(r => r.json());`;
  }
  return "";
}

function openModal() {
  els.codeSnippet.textContent = buildCodeSnippet(state.activeTab);
  els.modalBackdrop.classList.remove("hidden");
}
function closeModal() { els.modalBackdrop.classList.add("hidden"); }

function bindModal() {
  els.apiCodeBtn.addEventListener("click", openModal);
  els.modalClose.addEventListener("click", closeModal);
  els.modalBackdrop.addEventListener("click", e => { if (e.target === els.modalBackdrop) closeModal(); });
  els.tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      els.tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.activeTab = tab.dataset.tab;
      els.codeSnippet.textContent = buildCodeSnippet(state.activeTab);
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

async function init() {
  loadSettings();
  bindParamDisplay();
  bindChat();
  bindModal();
  initSplitter();
  initHSplitter();
  await loadModels();
  await loadConversations();

  // Auto-open most recent conversation if any
  const list = await (await fetch("/api/conversations")).json();
  if (list.length) await openConversation(list[0].id);
}

init();

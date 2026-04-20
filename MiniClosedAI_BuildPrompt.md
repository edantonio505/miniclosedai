# MiniClosedAI - Build Specification

## Project Overview

Build **MiniClosedAI**: A lightweight, local LLM experimentation platform for researchers, startup founders, and college students. Think "OpenAI Playground meets Local Ollama" - a simple dashboard to chat with multiple local AI models, adjust parameters in real-time, and generate API integration code.

**Target Users:**
- 🎓 College students learning prompt engineering
- 🚀 Startup founders prototyping AI features
- 🔬 Researchers testing different model configurations
- 💻 Developers who want local, privacy-focused AI experimentation

**Core Philosophy:**
- **100% Local**: All models run via Ollama (no API keys, no cloud)
- **Lightweight**: Small models only (qwen2.5:3b, llama3.2:3b, phi3:mini)
- **OpenAI-Like UX**: Familiar interface for anyone who's used ChatGPT or Claude
- **API-First**: Every chat interaction has copy-paste API code
- **Educational**: Help users understand how LLM parameters affect output

---

## Tech Stack

### Backend
- **Framework**: Django 4.2+ with Django Ninja (REST API)
- **Database**: SQLite (simple, portable)
- **LLM Integration**: LangChain + Ollama (via HTTP localhost:11434)
- **Streaming**: Server-Sent Events (SSE)

### Frontend
- **Style**: Vanilla JavaScript + minimal CSS (no React/Vue complexity)
- **Markdown**: marked.js for response rendering
- **Code Highlighting**: Prism.js or highlight.js for code blocks
- **UI Framework**: Simple responsive CSS (similar to Tailwind utility classes)

### Models (All via Ollama)
```bash
# Install these by default
ollama pull qwen2.5:3b
ollama pull llama3.2:3b
ollama pull phi3:mini
```

---

## Feature Requirements

### 1. **Chat Interface** (PRIORITY: HIGH)

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  [MiniClosedAI Logo]     [Bot Dropdown] [Get API Code]  │
├───────────────────┬─────────────────────────────────────┤
│                   │                                     │
│  Parameter Panel  │     Chat Messages Area              │
│                   │                                     │
│  🌡️ Temperature   │  [User bubble: "Hello!"]           │
│  [Slider: 0-2]    │  [AI bubble: "Hi there! How..."]   │
│                   │                                     │
│  🎯 Max Tokens    │                                     │
│  [Input: 2048]    │                                     │
│                   │                                     │
│  🎲 Top P         │  [Streaming indicator: "⚡..."]    │
│  [Slider: 0-1]    │                                     │
│                   │                                     │
│  🔄 Top K         │                                     │
│  [Input: 40]      │                                     │
│                   │                                     │
│  [Reset Params]   │                                     │
│                   │                                     │
├───────────────────┴─────────────────────────────────────┤
│  [Type message...]                      [Send Button]   │
└─────────────────────────────────────────────────────────┘
```

**Key Behaviors:**
- **Streaming responses**: Show text as it's generated (SSE)
- **Markdown rendering**: Format code blocks, lists, headers
- **Parameter changes**: Apply immediately to next message (no save button)
- **Conversation history**: Persist in SQLite, reload on page refresh
- **Auto-scroll**: Keep latest message in view during streaming

**Implementation Notes from ChefAI:**
- Use SSE with `text/event-stream` content type
- Stream format: `data: {"chunk": "text here"}\n\n`
- End stream with: `data: {"end": true}\n\n`
- Clean up special tokens: `<|eot_id|>`, `<｜end▁of▁sentence｜>`

---

### 2. **Bot Management** (PRIORITY: HIGH)

**Bot Creation Form:**
```
Create New Bot
─────────────────
Name: [Input: "My Research Assistant"]
Model: [Dropdown: qwen2.5:3b, llama3.2:3b, phi3:mini]
System Prompt: [Textarea: "You are a helpful..."]

[Create Bot]  [Cancel]
```

**Bot Model (Django):**
```python
class Bot(models.Model):
    name = models.CharField(max_length=100)
    model_name = models.CharField(max_length=50)  # e.g., "qwen2.5:3b"
    system_prompt = models.TextField(default="You are a helpful AI assistant.")
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Default parameters (can be overridden per chat)
    default_temperature = models.FloatField(default=0.7)
    default_max_tokens = models.IntegerField(default=2048)
    default_top_p = models.FloatField(default=0.9)
    default_top_k = models.IntegerField(default=40)
```

**Bot List View:**
- Simple card grid showing bot name, model, creation date
- Click to switch active bot
- Edit button opens form with pre-filled values
- Delete button (with confirmation)

---

### 3. **LLM Parameter Controls** (PRIORITY: HIGH)

**Real-Time Adjustable Parameters:**

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| **Temperature** | Slider | 0.0 - 2.0 | 0.7 | Controls randomness (0=deterministic, 2=creative) |
| **Max Tokens** | Number | 256 - 8192 | 2048 | Maximum response length |
| **Top P** | Slider | 0.0 - 1.0 | 0.9 | Nucleus sampling threshold |
| **Top K** | Number | 1 - 100 | 40 | Limits vocabulary to top K tokens |

**UI Elements:**
```html
<!-- Temperature Slider -->
<div class="param-control">
  <label>
    🌡️ Temperature <span class="value">0.7</span>
    <button class="info-btn" title="Higher = more creative">ⓘ</button>
  </label>
  <input type="range" min="0" max="2" step="0.1" value="0.7" 
         oninput="updateTemperature(this.value)">
  <div class="range-labels">
    <span>Precise</span>
    <span>Balanced</span>
    <span>Creative</span>
  </div>
</div>

<!-- Max Tokens Input -->
<div class="param-control">
  <label>🎯 Max Tokens <span class="value">2048</span></label>
  <input type="number" min="256" max="8192" value="2048"
         oninput="updateMaxTokens(this.value)">
</div>
```

**Visual Feedback:**
- Show current value next to label
- Slider track colors: cold (blue) → neutral → hot (red) for temperature
- Validation: Prevent invalid ranges
- Tooltip on hover explaining each parameter

**Storage:**
- Store current parameters in `localStorage` for persistence
- Include parameters in conversation history for reproducibility

---

### 4. **API Code Generator** (PRIORITY: HIGH)

**Modal Popup:**
When user clicks "Get API Code" button, show modal with tabs:

```
┌─────────────────────────────────────────────────────┐
│  API Integration Code                    [✕ Close]  │
├─────────────────────────────────────────────────────┤
│  [cURL]  [Python]  [JavaScript]                     │
├─────────────────────────────────────────────────────┤
│                                                      │
│  # Python (requests)                                │
│  import requests                                    │
│                                                      │
│  response = requests.post(                          │
│      'http://localhost:8000/api/chat',              │
│      json={                                         │
│          'bot_id': 1,                               │
│          'message': 'Hello!',                       │
│          'temperature': 0.7,                        │
│          'max_tokens': 2048                         │
│      }                                              │
│  )                                                  │
│  print(response.json()['response'])                 │
│                                                      │
│  [Copy Code]                                        │
└─────────────────────────────────────────────────────┘
```

**Code Templates:**

**cURL:**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "bot_id": {bot_id},
    "message": "{message}",
    "temperature": {temperature},
    "max_tokens": {max_tokens},
    "top_p": {top_p},
    "top_k": {top_k}
  }'
```

**Python:**
```python
import requests

response = requests.post(
    'http://localhost:8000/api/chat',
    json={
        'bot_id': {bot_id},
        'message': '{message}',
        'temperature': {temperature},
        'max_tokens': {max_tokens},
        'top_p': {top_p},
        'top_k': {top_k}
    }
)
print(response.json()['response'])
```

**JavaScript (Streaming):**
```javascript
const response = await fetch('http://localhost:8000/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        bot_id: {bot_id},
        message: '{message}',
        temperature: {temperature},
        max_tokens: {max_tokens}
    })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    for (const line of lines) {
        if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));
            if (data.chunk) process.stdout.write(data.chunk);
        }
    }
}
```

**Features:**
- Auto-fill with current bot/parameters
- Syntax highlighting
- One-click copy button
- Show both streaming and non-streaming versions

---

### 5. **Conversation Management** (PRIORITY: MEDIUM)

**Django Models:**
```python
class Conversation(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=[('user', 'User'), ('assistant', 'Assistant')])
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Parameters used for this message
    parameters = models.JSONField(default=dict)  # {temperature: 0.7, max_tokens: 2048, ...}
```

**Features:**
- One active conversation per bot
- "New Chat" button clears current conversation, creates new one
- Message history persists across page reloads
- Show parameter badge on each assistant message (e.g., "T=0.7 | 2048 tokens")

**Conversation List (Optional):**
```
Recent Conversations
────────────────────
🤖 Research Bot - 2 hours ago
   "Can you explain..."
   
🤖 Code Helper - Yesterday
   "Write a Python script..."
```

---

### 6. **API Endpoints** (PRIORITY: HIGH)

**Django Ninja API Structure:**

```python
from ninja import NinjaAPI, Schema
from pydantic import BaseModel

api = NinjaAPI()

class ChatRequest(Schema):
    bot_id: int
    message: str
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9
    top_k: int = 40

class ChatResponse(Schema):
    response: str
    conversation_id: int
    tokens_used: int

@api.post("/chat", response=ChatResponse)
def chat(request, data: ChatRequest):
    """Non-streaming chat endpoint"""
    bot = Bot.objects.get(id=data.bot_id)
    response = generate_response(bot, data.message, data.temperature, ...)
    return {
        'response': response,
        'conversation_id': conv.id,
        'tokens_used': count_tokens(response)
    }

@api.post("/chat/stream")
def chat_stream(request, data: ChatRequest):
    """Streaming chat endpoint (SSE)"""
    def event_stream():
        bot = Bot.objects.get(id=data.bot_id)
        for chunk in stream_response(bot, data.message, data.temperature, ...):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        yield f"data: {json.dumps({'end': True})}\n\n"
    
    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )

@api.get("/bots")
def list_bots(request):
    """Get all bots"""
    bots = Bot.objects.all()
    return [{'id': b.id, 'name': b.name, 'model': b.model_name} for b in bots]

@api.post("/bots")
def create_bot(request, data: BotCreateSchema):
    """Create new bot"""
    bot = Bot.objects.create(**data.dict())
    return {'id': bot.id, 'message': 'Bot created successfully'}

@api.get("/conversations/{bot_id}")
def get_conversation(request, bot_id: int):
    """Get conversation history for a bot"""
    conv = Conversation.objects.filter(bot_id=bot_id).first()
    if not conv:
        return {'messages': []}
    messages = conv.messages.all().order_by('timestamp')
    return {
        'messages': [
            {'role': m.role, 'content': m.content, 'timestamp': m.timestamp}
            for m in messages
        ]
    }
```

**Endpoint Summary:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat` | POST | Non-streaming chat |
| `/api/chat/stream` | POST | Streaming chat (SSE) |
| `/api/bots` | GET | List all bots |
| `/api/bots` | POST | Create new bot |
| `/api/bots/{id}` | GET | Get bot details |
| `/api/bots/{id}` | PUT | Update bot |
| `/api/bots/{id}` | DELETE | Delete bot |
| `/api/conversations/{bot_id}` | GET | Get conversation history |
| `/api/conversations/{id}` | DELETE | Clear conversation |

---

### 7. **Ollama Integration** (PRIORITY: HIGH)

**LangChain + Ollama Setup:**

```python
# llm_service.py
from langchain_community.llms import Ollama
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

class ChatService:
    def __init__(self, model_name="qwen2.5:3b", temperature=0.7, max_tokens=2048):
        self.llm = Ollama(
            model=model_name,
            base_url="http://localhost:11434",
            temperature=temperature,
            num_predict=max_tokens,  # max_tokens in Ollama
            top_p=0.9,
            top_k=40,
        )
    
    def chat(self, system_prompt: str, user_message: str):
        """Non-streaming chat"""
        full_prompt = f"{system_prompt}\n\nUser: {user_message}\nAssistant:"
        response = self.llm(full_prompt)
        return response
    
    def stream_chat(self, system_prompt: str, user_message: str):
        """Streaming chat (generator)"""
        full_prompt = f"{system_prompt}\n\nUser: {user_message}\nAssistant:"
        
        # Use Ollama's streaming via callbacks
        for chunk in self.llm.stream(full_prompt):
            if chunk:
                yield chunk

# Usage in view
def generate_response(bot, message, temperature, max_tokens, top_p, top_k):
    service = ChatService(
        model_name=bot.model_name,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return service.chat(bot.system_prompt, message)

def stream_response(bot, message, temperature, max_tokens, top_p, top_k):
    service = ChatService(
        model_name=bot.model_name,
        temperature=temperature,
        max_tokens=max_tokens
    )
    for chunk in service.stream_chat(bot.system_prompt, message):
        yield chunk
```

**Error Handling:**
```python
import requests

def check_ollama_available():
    """Check if Ollama server is running"""
    try:
        response = requests.get("http://localhost:11434/api/tags")
        return response.status_code == 200
    except requests.RequestException:
        return False

def get_available_models():
    """Fetch installed Ollama models"""
    try:
        response = requests.get("http://localhost:11434/api/tags")
        models = response.json().get('models', [])
        return [m['name'] for m in models]
    except:
        return []
```

**Setup Instructions (in README):**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull small models
ollama pull qwen2.5:3b
ollama pull llama3.2:3b
ollama pull phi3:mini

# Verify installation
ollama list
```

---

## UI/UX Design Guidelines

### Color Scheme (Dark Mode Default)
```css
:root {
    --bg-primary: #1e1e1e;
    --bg-secondary: #2d2d2d;
    --text-primary: #e0e0e0;
    --text-secondary: #a0a0a0;
    --accent-blue: #3b82f6;
    --accent-green: #10b981;
    --border: #404040;
    --user-bubble: #3b82f6;
    --ai-bubble: #374151;
}
```

### Component Styles

**Message Bubbles:**
```css
.message-user {
    align-self: flex-end;
    background: var(--user-bubble);
    color: white;
    border-radius: 18px 18px 4px 18px;
    padding: 10px 16px;
    max-width: 70%;
}

.message-ai {
    align-self: flex-start;
    background: var(--ai-bubble);
    color: var(--text-primary);
    border-radius: 18px 18px 18px 4px;
    padding: 10px 16px;
    max-width: 80%;
}
```

**Parameter Slider:**
```css
input[type="range"] {
    width: 100%;
    height: 6px;
    background: linear-gradient(to right, #3b82f6 0%, #10b981 50%, #f59e0b 100%);
    border-radius: 3px;
    outline: none;
}
```

### Responsive Design
- Desktop: Side-by-side parameter panel + chat
- Tablet: Collapsible parameter panel
- Mobile: Bottom sheet for parameters

---

## Key Differences from ChefAI

| ChefAI Feature | MiniClosedAI Approach |
|----------------|----------------------|
| Multi-user with auth | Single-user (no login) |
| Plugin system (custom code) | Fixed LLM integration (Ollama only) |
| RAG/Knowledgebase | **Excluded** (too complex) |
| Voice/phone integrations | **Excluded** |
| Complex bot relationships | Simple bot list |
| Template versioning (osyn_dev) | **Excluded** |
| Data labeling (datajobs) | **Excluded** |
| CRM features (allies) | **Excluded** |
| Cloud LLM APIs (OpenAI, Bedrock) | **Local Ollama only** |
| Mobile app support | Web-only responsive UI |

---

## Development Roadmap

### Phase 1: MVP (Week 1-2)
- [ ] Django project setup + SQLite
- [ ] Bot model (name, model_name, system_prompt)
- [ ] Basic chat UI (no streaming)
- [ ] Ollama integration (single model)
- [ ] Parameter controls (temperature, max_tokens)

### Phase 2: Streaming & API (Week 3)
- [ ] SSE streaming implementation
- [ ] Frontend streaming handler
- [ ] Django Ninja API endpoints
- [ ] API code generator modal

### Phase 3: Polish (Week 4)
- [ ] Conversation history persistence
- [ ] Multiple bot management
- [ ] Markdown rendering + syntax highlighting
- [ ] Responsive design
- [ ] Error handling (Ollama not running, etc.)

### Phase 4: Enhancements (Optional)
- [ ] Conversation export (JSON/Markdown)
- [ ] Bot templates (pre-configured bots)
- [ ] Parameter presets (e.g., "Creative", "Balanced", "Precise")
- [ ] Token counting and stats
- [ ] Model comparison view (side-by-side)

---

## File Structure

```
minicloseai/
├── manage.py
├── requirements.txt
├── README.md
├── minicloseai/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── chat/
│   ├── models.py          # Bot, Conversation, Message
│   ├── views.py           # Chat UI views
│   ├── api.py             # Django Ninja API
│   ├── llm_service.py     # Ollama integration
│   ├── forms.py           # Bot creation form
│   └── templates/
│       └── chat/
│           ├── index.html      # Main chat UI
│           ├── bot_form.html   # Create/edit bot
│           └── bot_list.html   # Bot management
└── static/
    ├── css/
    │   └── style.css      # Main styles
    └── js/
        ├── chat.js        # Chat logic + streaming
        ├── api-modal.js   # API code generator
        └── marked.min.js  # Markdown rendering
```

---

## Success Criteria

✅ **Functional:**
- User can create multiple bots with different models
- Real-time streaming chat works smoothly
- Parameters adjust output as expected
- API code generator produces working code
- Conversations persist across sessions

✅ **Performance:**
- Responses start streaming within 1 second
- UI remains responsive during streaming
- Handles conversations up to 50 messages

✅ **Usability:**
- Setup takes < 5 minutes (Ollama + Django)
- No configuration files to edit
- Works offline (no internet required)
- Clear documentation for getting started

---

## Reference Implementation Notes from ChefAI

### Streaming Implementation
From `chef_assistant_app/views.py:844-887` and `bots/models.py:491-623`:
- Use `StreamingHttpResponse` with generator function
- SSE format: `data: {json}\n\n`
- Clean up model-specific tokens in stream
- Yield `{"end": true}` to signal completion

### Message Storage
From `bots/models.py:156-167`:
- Store as JSON array: `[{"role": "user", "content": "..."}, ...]`
- Append new messages with `messages.append({...})`
- Save entire array to database after each turn

### Prompt Template
From `bots/models.py:388-413`:
- Use Jinja2-style placeholders: `{question}`, `[HISTORY]`
- Replace `[HISTORY]` with formatted conversation
- Build final prompt: `system_prompt + history + user_message`

### Parameter Passing
From `osyn_dev/views.py` and `chef_assistant_app/api.py`:
- Pass parameters per-request (not stored globally)
- Override bot defaults with request params
- Include parameters in response metadata for debugging

---

## Testing Checklist

- [ ] Create bot with each supported model (qwen2.5:3b, llama3.2:3b, phi3:mini)
- [ ] Send message and verify streaming response
- [ ] Adjust temperature slider - verify behavior changes
- [ ] Set max_tokens to 100 - verify short responses
- [ ] Generate API code (cURL/Python/JS) - copy and test externally
- [ ] Refresh page - conversation history persists
- [ ] Delete bot - conversations deleted
- [ ] Create second bot - switch between bots without mixing conversations
- [ ] Disconnect Ollama - error message appears
- [ ] Markdown rendering - code blocks, lists, headers display correctly

---

## Documentation to Include

### README.md
```markdown
# MiniClosedAI

Local LLM experimentation platform. Chat with multiple AI models, adjust parameters, generate API code.

## Quick Start

1. Install Ollama:
   ```
   curl -fsSL https://ollama.ai/install.sh | sh
   ```

2. Pull models:
   ```
   ollama pull qwen2.5:3b
   ollama pull llama3.2:3b
   ```

3. Run MiniClosedAI:
   ```
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py runserver
   ```

4. Open http://localhost:8000

## Features
- 💬 Chat with local AI models (no API keys)
- 🎛️ Adjust temperature, max_tokens, top_p in real-time
- 🔧 Generate API integration code (cURL, Python, JS)
- 🤖 Create unlimited custom bots
- 📝 Conversation history auto-saves

## API Usage
See http://localhost:8000/api/docs for interactive API documentation.
```

---

## Final Notes

**Keep It Simple:**
- No authentication (single-user mode)
- No cloud APIs (Ollama only)
- No complex features (RAG, voice, scheduling)
- Focus on the core loop: **Create bot → Adjust parameters → Chat → Generate API code**

**Inspirations:**
- OpenAI Playground's parameter controls
- Anthropic Console's markdown rendering
- ChefAI's streaming implementation
- Ollama's local-first philosophy

**Target Complexity:**
- ~500 lines of Python (models + views + API)
- ~300 lines of JavaScript (chat + streaming + API modal)
- ~400 lines of CSS (responsive + dark mode)
- Total: Can be built in 2-4 weeks by solo developer

**Success Metric:**
A college student should be able to:
1. Install in 5 minutes
2. Create their first chatbot in 2 minutes
3. Understand how temperature affects output after 3 experiments
4. Copy API code and integrate into their project in 10 minutes

---

## Additional Resources

**Ollama Docs:** https://ollama.ai/docs
**LangChain Ollama:** https://python.langchain.com/docs/integrations/llms/ollama
**Django Ninja:** https://django-ninja.rest-framework.com/
**SSE Guide:** https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
**Marked.js:** https://marked.js.org/

**ChefAI Reference Files:**
- Bot streaming: `/bots/models.py` lines 525-623
- SSE view: `/chef_assistant_app/views.py` lines 844-887
- Chat UI: `/chef_assistant_app/templates/chef_assistant_app/index.html`
- API structure: `/chef_assistant_app/api.py`

---

**END OF SPECIFICATION**

This document provides everything needed to build MiniClosedAI from scratch. Focus on delivering a polished, educational tool that helps users understand how LLMs work while providing a professional API integration workflow.

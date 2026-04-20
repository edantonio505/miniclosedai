# ChefAI Core Features - Technical Explanation

## How ChefAI Works (Relevant Features for MiniClosedAI)

This document explains how the ChefAI project implements its core chat and bot management features, extracted from the actual codebase to inform the MiniClosedAI build.

---

## 1. Bot System Architecture

### Bot Model (`bots/models.py`)

ChefAI uses a **Bot** model as the central abstraction for AI assistants:

```python
class Bot(models.Model):
    name = CharField              # Display name
    user = ForeignKey(User)       # Owner
    prompt_template = TextField   # Jinja2-style with placeholders
    description = TextField       # Bot purpose
    is_active = BooleanField      # Enable/disable
    plugin = ForeignKey(Plugin)   # Custom LLM/processing code
    current_context = TextField   # RAG/system context
    conversation = OneToOne       # Active conversation
    api_token = CharField         # For external API access
    can_stream = BooleanField     # SSE support flag
```

**Key Concept: Lazy Loading**
Bots don't initialize their LLM until first chat:
```python
def initialize_for_chat(self):
    if not self.LLM:
        self.LLM = self.plugin.set_llm()  # Run plugin code
```

This saves memory when managing many bots.

---

## 2. Conversation & Message Storage

### Conversation Model
ChefAI stores conversations as **JSON arrays** in a single field:

```python
class Conversation(models.Model):
    bot = OneToOneField(Bot)
    messages = JSONField(default=list)  # [{"role": "user", "content": "..."}]
    created_at = DateTimeField
    last_interaction = DateTimeField
```

### Message Format
```json
{
  "messages": [
    {"role": "user", "content": "Hello!"},
    {"role": "assistant", "content": "Hi there! How can I help?"},
    {"role": "user", "content": "What's the weather?"}
  ]
}
```

### Saving Messages (`bots/models.py:156-167`)
```python
def save_current_conversation(self, question, answer):
    if not self.conversation:
        self.conversation = Conversation.objects.create(bot=self)
    
    messages = self.conversation.messages or []
    messages.append({"role": "user", "content": question})
    messages.append({"role": "assistant", "content": answer})
    
    self.conversation.messages = messages
    self.conversation.last_interaction = timezone.now()
    self.conversation.save()
```

**Why JSON Array?**
- Simple structure for LLM context window
- Easy to serialize for API responses
- Can be directly passed to OpenAI/Anthropic format
- No complex ORM queries for message history

---

## 3. Streaming Implementation (SSE)

### Backend: Streaming View (`chef_assistant_app/views.py:844-887`)

ChefAI uses **Server-Sent Events** for real-time streaming:

```python
def ask_stream_view(request):
    bot = Bot.objects.get(id=bot_id, user=request.user)
    question = request.POST.get('question')
    
    def event_stream():
        # Generator function yields SSE-formatted chunks
        for chunk in bot.ask_stream_prompt(question):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        yield f"data: {json.dumps({'end': True})}\n\n"
    
    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
```

### Bot Streaming Logic (`bots/models.py:525-577`)

ChefAI supports **two streaming modes**:

**A. OpenAI API Streaming:**
```python
def ask_stream_openai(self, user_prompt):
    for chunk in self.LLM.stream(user_prompt):
        text = chunk.content
        # Clean up model artifacts
        text = text.replace("<|eot_id|>", "")
        text = text.replace("\n", "<br>")
        yield text
```

**B. Custom LLM Server Streaming:**
```python
def ask_stream(self, user_prompt):
    stream_url = f"{self.URL_HOST}/ask-stream"
    params = {
        "prompt": user_prompt,
        "context": self.current_context,
        "temperature": 0.7
    }
    
    with requests.post(stream_url, json=params, stream=True) as r:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                decoded = chunk.decode('utf-8')
                yield decoded
```

### Frontend: SSE Handler (`index.html:2095-2289`)

JavaScript receives and displays streaming text:

```javascript
fetch(streamUrl, {
    method: 'POST',
    body: formData
})
.then(response => {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    function readStream() {
        reader.read().then(({ done, value }) => {
            if (done) return;
            
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));
                    
                    if (data.end) {
                        // Stream complete
                        saveConversation();
                        return;
                    }
                    
                    if (data.chunk) {
                        // Append chunk to message bubble
                        aiMessageElement.innerHTML += data.chunk;
                        scrollToBottom();
                    }
                }
            }
            
            readStream(); // Continue reading
        });
    }
    
    readStream();
});
```

**SSE Format:**
```
data: {"chunk": "Hello"}\n\n
data: {"chunk": " there"}\n\n
data: {"chunk": "!"}\n\n
data: {"end": true}\n\n
```

---

## 4. Prompt Template System

### Template with Placeholders (`bots/models.py:388-413`)

Bots use **Jinja2-style templates** for flexibility:

```python
prompt_template = """
You are a helpful research assistant.

[HISTORY]

User: {question}
Assistant:
"""
```

### Template Rendering
```python
def build_prompt(self, question, context=""):
    # 1. Format conversation history
    history = self.format_conversation_history()
    
    # 2. Replace placeholders
    prompt = self.prompt_template
    prompt = prompt.replace('[HISTORY]', history)
    prompt = prompt.replace('{question}', question)
    prompt = prompt.replace('{context}', context)
    
    return prompt

def format_conversation_history(self):
    if not self.conversation:
        return ""
    
    formatted = []
    for msg in self.conversation.messages[-10:]:  # Last 10 messages
        role = msg['role'].capitalize()
        content = msg['content']
        formatted.append(f"{role}: {content}")
    
    return '\n'.join(formatted)
```

**Placeholders:**
- `[HISTORY]` → Last N conversation turns
- `{question}` → Current user input
- `{context}` → RAG/document context (optional)
- `[EXAMPLE_CONTEXT]` → Few-shot examples

---

## 5. Plugin System (Custom LLM Code)

### Plugin Model (`bots/models.py:233-309`)

ChefAI allows **user-defined Python code** for LLM integration:

```python
class Plugin(models.Model):
    name = CharField
    code = TextField              # User writes Python here
    config = JSONField            # {"temperature": 0.7, ...}
    user = ForeignKey(User)
```

### Plugin Code Structure
Users write plugins like this:

```python
# Stored in Plugin.code field
from langchain_community.llms import Ollama

def set_llm(context=None):
    """Initialize and return LLM instance"""
    llm = Ollama(
        model="qwen2.5:7b",
        base_url="http://localhost:11434",
        temperature=0.7,
        num_predict=4096
    )
    return llm

def transform_question(question):
    """Pre-process user input (optional)"""
    return question.strip().lower()

def transform_answer(answer):
    """Post-process LLM output (optional)"""
    return answer.replace("AI:", "").strip()

config = {
    "temperature": 0.7,
    "max_tokens": 4096,
    "model": "qwen2.5:7b"
}
```

### Plugin Execution (`bots/models.py:86-93`)
```python
def initialize_for_chat(self):
    if self.plugin:
        # Execute user's plugin code
        exec(self.plugin.code, globals())
        
        # Call set_llm() function from plugin
        self.LLM = set_llm(context=self.current_context)
        
        # Store transform functions
        self.transform_question = globals().get('transform_question')
        self.transform_answer = globals().get('transform_answer')
```

**Security Note:** ChefAI runs plugin code directly with `exec()` - this is **only safe** because it's a personal tool. MiniClosedAI should avoid this pattern.

---

## 6. API Implementation (Django Ninja)

### API Structure (`chef_assistant_app/api.py`)

ChefAI uses **Django Ninja** for REST APIs:

```python
from ninja import NinjaAPI, Schema
from pydantic import BaseModel

api = NinjaAPI()

class AskModel(BaseModel):
    question: str
    name: str = None              # Bot name
    save_conversation: bool = True
    context: str = None

@api.post("/ask")
def ask_endpoint(request, data: AskModel):
    """Non-streaming chat"""
    bot = Bot.objects.get(name=data.name, user=request.user)
    
    # Generate response
    answer = bot.ask_prompt(
        question=data.question,
        context=data.context
    )
    
    # Save to conversation
    if data.save_conversation:
        bot.save_current_conversation(data.question, answer)
    
    return {
        "answer": answer,
        "bot_name": bot.name,
        "conversation_id": bot.conversation.id
    }
```

### API Authentication
ChefAI uses **token-based auth**:

```python
# Generate token per bot
@api.post("/bot/{bot_id}/generate-token/")
def generate_token(request, bot_id: int):
    bot = Bot.objects.get(id=bot_id, user=request.user)
    bot.api_token = secrets.token_urlsafe(32)
    bot.save()
    return {"token": bot.api_token}

# Authenticate requests
def get_user_from_token(request):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    profile = Profile.objects.get(token=token)
    return profile.user
```

### API Usage Example
```bash
# Get token
curl -X POST http://localhost:8000/api/bot/1/generate-token/ \
  -H "Authorization: Bearer <user_token>"

# Chat with bot
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <bot_token>" \
  -d '{
    "question": "Hello!",
    "name": "Research Bot"
  }'
```

---

## 7. LLM Parameter Handling

### Temperature Storage (`osyn_dev/models.py`)

ChefAI stores temperature as a **singleton**:

```python
class LLMConfig(models.Model):
    temperature = FloatField(default=0.7)
    
    @classmethod
    def get_temperature(cls):
        config, _ = cls.objects.get_or_create(id=1)
        return config.temperature
```

### API Endpoint (`api.py:1572-1586`)
```python
@api.get("/llm/temperature")
def get_llm_temperature(request):
    from osyn_dev.models import LLMConfig
    temp = LLMConfig.get_temperature()
    return {"temperature": temp}
```

### Using Parameters in LLM Calls
```python
from chef_assistant_app.helper import get_llm

def generate_response(question):
    llm = get_llm()  # Returns ChatOpenAI(temperature=0.8, max_tokens=12000)
    response = llm(question)
    return response
```

**Limitation:** ChefAI doesn't have **per-message parameter adjustment** - parameters are set at plugin/default level.

---

## 8. Chat UI Design

### Layout (`index.html`)

ChefAI uses a **two-column layout**:

```html
<div class="container">
    <!-- Left sidebar: Bot list (11% width) -->
    <div class="sidebar">
        <div class="bot-item" data-bot-id="1">
            <img src="bot-icon.png">
            <span>Research Bot</span>
        </div>
        <div class="bot-item" data-bot-id="2">
            <span>Code Helper</span>
        </div>
    </div>
    
    <!-- Right: Chat area (88% width) -->
    <div class="chat-area">
        <!-- Messages -->
        <div id="messages-container">
            <div class="message user-message">
                <div class="content">Hello!</div>
            </div>
            <div class="message ai-message">
                <div class="content">Hi there! How can I help?</div>
            </div>
        </div>
        
        <!-- Input -->
        <div class="input-area">
            <textarea id="user-input" placeholder="Type a message..."></textarea>
            <button id="send-btn">Send</button>
        </div>
    </div>
</div>
```

### Message Rendering with Markdown

ChefAI uses **marked.js** for markdown:

```javascript
// Render assistant message
const aiMessage = document.createElement('div');
aiMessage.className = 'message ai-message';

// Convert markdown to HTML
const htmlContent = marked.parse(assistantText);
aiMessage.innerHTML = htmlContent;

// Syntax highlighting for code blocks
aiMessage.querySelectorAll('pre code').forEach(block => {
    hljs.highlightBlock(block);
});
```

### Auto-Scroll During Streaming
```javascript
function scrollToBottom() {
    const container = document.getElementById('messages-container');
    container.scrollTop = container.scrollHeight;
}

// Call after each chunk
if (data.chunk) {
    aiMessageElement.innerHTML += data.chunk;
    scrollToBottom();
}
```

---

## 9. Bot Management UI

### Bot Creation Form (`new_bot.html`)

Simple form for bot creation:

```html
<form method="post">
    {% csrf_token %}
    
    <label>Bot Name</label>
    <input type="text" name="name" required>
    
    <label>Description</label>
    <textarea name="description"></textarea>
    
    <label>Prompt Template</label>
    <textarea name="prompt_template" rows="10">
You are a helpful assistant.

[HISTORY]

User: {question}
Assistant:
    </textarea>
    
    <label>Plugin (optional)</label>
    <select name="plugin">
        <option value="">-- Use default --</option>
        {% for plugin in plugins %}
        <option value="{{ plugin.id }}">{{ plugin.name }}</option>
        {% endfor %}
    </select>
    
    <button type="submit">Create Bot</button>
</form>
```

### Bot List View (`views.py:123-141`)
```python
def bot_list(request):
    bots = Bot.objects.filter(user=request.user, is_active=True)
    context = {
        'bots': bots,
        'can_create_more': bots.count() < 50  # Limit
    }
    return render(request, 'bots/list.html', context)
```

---

## 10. RAG/Context System (Optional Feature)

### Context Model (`bots/models.py:311-387`)

ChefAI supports **vector store context**:

```python
class Context(models.Model):
    name = CharField
    description = TextField
    file = FileField                    # PDF/DOCX/TXT upload
    vectorstore_index_name = CharField  # Pinecone index ID
    bot = ForeignKey(Bot)
```

### RAG Flow
1. User uploads document
2. Extract text → chunk into paragraphs
3. Generate embeddings (OpenAI `text-embedding-ada-002`)
4. Store in Pinecone vector DB
5. On chat: Query Pinecone for relevant chunks
6. Inject into prompt as `{context}` placeholder

```python
def retrieve_context(self, question):
    from langchain.vectorstores import Pinecone
    from langchain.embeddings import OpenAIEmbeddings
    
    embeddings = OpenAIEmbeddings()
    vectorstore = Pinecone.from_existing_index(
        index_name=self.context.vectorstore_index_name,
        embedding=embeddings
    )
    
    # Semantic search
    docs = vectorstore.similarity_search(question, k=1)
    return docs[0].page_content if docs else ""
```

**Note:** MiniClosedAI should **skip RAG** for simplicity - it adds significant complexity (embedding model, vector DB, chunking logic).

---

## Key Takeaways for MiniClosedAI

### ✅ What to Keep:
1. **Bot model** with name, model_name, system_prompt
2. **JSON array conversation storage** - simple and effective
3. **SSE streaming** with `data: {}\n\n` format
4. **Django Ninja API** - clean REST endpoints
5. **Marked.js markdown rendering** - professional chat UI
6. **Prompt template system** - flexible but not complex

### ❌ What to Skip:
1. **Plugin system** - security risk, too complex
2. **RAG/vector stores** - overkill for experimentation tool
3. **Multi-user auth** - single-user mode is fine
4. **Voice/phone integrations** - out of scope
5. **Chat buddy (bot-to-bot)** - niche feature

### 💡 What to Improve:
1. **Per-message parameters** - Let users adjust temperature/tokens per request (ChefAI doesn't have this!)
2. **Parameter UI** - Sliders and inputs visible in chat (ChefAI buries it in plugin code)
3. **API code generator** - ChefAI has modal but no auto-generation
4. **Model selection** - Make it visual (dropdown with model cards)
5. **Token counting** - Show usage stats (ChefAI doesn't track this)

---

## Technical Decisions from ChefAI

### Why Django?
- ChefAI is a multi-app platform (12 Django apps)
- Django admin provides quick CRUD UI
- ORM simplifies database operations
- Django Ninja adds modern API layer

### Why JSON for Conversations?
- Avoids N+1 queries for message history
- Compatible with OpenAI/Anthropic message format
- Easy to serialize for API responses
- Can store metadata (timestamps, parameters) per message

### Why SSE over WebSockets?
- Simpler implementation (HTTP-based)
- No persistent connection management
- Works through most proxies/firewalls
- Native browser support with `EventSource` or `fetch`

### Why Plugins?
- ChefAI started as personal tool for experimenting with different LLM APIs
- Plugins let the developer swap Bedrock → OpenAI → Ollama without code changes
- **Not recommended for MiniClosedAI** - hardcode Ollama integration instead

---

## File References

All line numbers are from the actual ChefAI codebase:

- **Bot model**: `bots/models.py` lines 41-230
- **Streaming logic**: `bots/models.py` lines 525-623
- **SSE view**: `chef_assistant_app/views.py` lines 844-887
- **API endpoints**: `chef_assistant_app/api.py`
- **Chat UI**: `chef_assistant_app/templates/chef_assistant_app/index.html`
- **LLM helper**: `chef_assistant_app/helper.py` lines 262-341
- **Plugin execution**: `bots/models.py` lines 86-93
- **Conversation save**: `bots/models.py` lines 156-167
- **Prompt building**: `bots/models.py` lines 388-413

---

This document provides a technical deep-dive into ChefAI's core features. Use it as a reference when building MiniClosedAI, adapting the patterns that work while avoiding the complexity that doesn't fit a lightweight experimentation tool.

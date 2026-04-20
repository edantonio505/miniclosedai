# MiniClosedAI - Extended Roadmap

**Post-MVP Feature Development Plan**

This document outlines advanced features to add **after** the core MiniClosedAI MVP is complete and stable. These features transform MiniClosedAI from a simple experimentation tool into a more powerful local AI platform.

---

## Phase 1-4: MVP (Core Features)

See `MiniClosedAI_BuildPrompt.md` for details. Summary:

- ✅ Phase 1: Basic chat + Ollama integration
- ✅ Phase 2: Streaming + API endpoints
- ✅ Phase 3: UI polish + conversation history
- ✅ Phase 4: Enhancements (export, templates, stats)

**Timeline:** 4 weeks  
**Status:** Primary development focus

---

## Phase 5: RAG / Knowledge Base (Post-MVP)

### Overview
Add document upload and semantic search capabilities so bots can answer questions based on user-provided documents.

### Why Add This?
- **Educational Value:** Teaches how RAG (Retrieval-Augmented Generation) works
- **Use Cases:** 
  - Students can chat with their textbooks
  - Researchers can query their papers
  - Founders can search product docs
- **Local-First:** Use local embedding models (no cloud APIs)

### Features

#### 5.1 Document Upload & Processing
```
Document Upload Interface
─────────────────────────

[Drop files here or click to browse]

Supported formats:
- PDF (.pdf)
- Word (.docx, .doc)
- Text (.txt, .md)
- CSV (.csv)

[Upload & Index]

Recent Documents:
├── research_paper.pdf (45 pages) - Indexed
├── textbook_chapter3.pdf (12 pages) - Indexed
└── lecture_notes.txt (5 pages) - Processing...
```

**Django Models:**
```python
class Document(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/')
    file_type = models.CharField(max_length=10)  # pdf, docx, txt
    page_count = models.IntegerField(default=0)
    
    # Processing status
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('indexed', 'Indexed'),
        ('error', 'Error')
    ], default='pending')
    
    created_at = models.DateTimeField(auto_now_add=True)

class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    content = models.TextField()
    chunk_index = models.IntegerField()
    page_number = models.IntegerField(null=True, blank=True)
    embedding = models.JSONField()  # Store vector as JSON array
    
    class Meta:
        indexes = [
            models.Index(fields=['document', 'chunk_index'])
        ]
```

#### 5.2 Local Embedding Model

**Use Ollama's Embedding API** (no cloud dependency):

```python
# llm_service.py
import requests
import numpy as np

def generate_embedding(text: str) -> list[float]:
    """Generate embedding using Ollama"""
    response = requests.post(
        'http://localhost:11434/api/embeddings',
        json={
            'model': 'nomic-embed-text',  # Small, fast embedding model
            'prompt': text
        }
    )
    return response.json()['embedding']

def chunk_document(text: str, chunk_size: int = 500) -> list[str]:
    """Split document into overlapping chunks"""
    words = text.split()
    chunks = []
    overlap = 50  # Word overlap between chunks
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        chunks.append(chunk)
    
    return chunks

def process_document(document_id: int):
    """Extract text → chunk → embed → save"""
    doc = Document.objects.get(id=document_id)
    doc.status = 'processing'
    doc.save()
    
    try:
        # Extract text from file
        if doc.file_type == 'pdf':
            text = extract_pdf_text(doc.file.path)
        elif doc.file_type == 'docx':
            text = extract_docx_text(doc.file.path)
        else:
            text = doc.file.read().decode('utf-8')
        
        # Chunk text
        chunks = chunk_document(text)
        
        # Generate embeddings and save
        for idx, chunk_text in enumerate(chunks):
            embedding = generate_embedding(chunk_text)
            DocumentChunk.objects.create(
                document=doc,
                content=chunk_text,
                chunk_index=idx,
                embedding=embedding
            )
        
        doc.status = 'indexed'
        doc.save()
        
    except Exception as e:
        doc.status = 'error'
        doc.save()
        raise
```

#### 5.3 Semantic Search

**Simple cosine similarity search** (no vector DB required):

```python
def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    a = np.array(vec1)
    b = np.array(vec2)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def search_documents(bot_id: int, query: str, top_k: int = 3) -> list[dict]:
    """Search bot's documents for relevant chunks"""
    # Generate query embedding
    query_embedding = generate_embedding(query)
    
    # Get all chunks for bot's documents
    chunks = DocumentChunk.objects.filter(
        document__bot_id=bot_id,
        document__status='indexed'
    ).select_related('document')
    
    # Calculate similarity scores
    results = []
    for chunk in chunks:
        similarity = cosine_similarity(query_embedding, chunk.embedding)
        results.append({
            'chunk': chunk,
            'similarity': similarity,
            'document_title': chunk.document.title
        })
    
    # Sort by similarity and return top K
    results.sort(key=lambda x: x['similarity'], reverse=True)
    return results[:top_k]
```

#### 5.4 RAG-Enhanced Chat

**Inject relevant context into prompt:**

```python
def chat_with_rag(bot: Bot, message: str, temperature: float, max_tokens: int):
    """Chat with document context"""
    # Search for relevant chunks
    relevant_chunks = search_documents(bot.id, message, top_k=3)
    
    # Build context section
    context = ""
    if relevant_chunks:
        context = "# Relevant Context from Documents\n\n"
        for i, result in enumerate(relevant_chunks, 1):
            context += f"## Source {i}: {result['document_title']}\n"
            context += f"{result['chunk'].content}\n\n"
    
    # Build full prompt
    full_prompt = f"""{bot.system_prompt}

{context}

User Question: {message}
Assistant:"""
    
    # Generate response with context
    service = ChatService(
        model_name=bot.model_name,
        temperature=temperature,
        max_tokens=max_tokens
    )
    
    response = service.chat(full_prompt)
    return response, relevant_chunks  # Return sources for citation
```

#### 5.5 UI Additions

**Document Tab in Bot Settings:**
```html
<div class="bot-documents">
    <h3>📚 Knowledge Base</h3>
    <p>Upload documents for this bot to reference during conversations.</p>
    
    <div class="upload-zone">
        <input type="file" id="doc-upload" accept=".pdf,.docx,.txt,.md">
        <button onclick="uploadDocument()">Upload & Index</button>
    </div>
    
    <div class="document-list">
        {% for doc in bot.documents.all %}
        <div class="doc-item">
            <span class="doc-icon">📄</span>
            <div class="doc-info">
                <strong>{{ doc.title }}</strong>
                <span class="doc-meta">{{ doc.page_count }} pages · {{ doc.status }}</span>
            </div>
            <button class="btn-sm" onclick="deleteDocument({{ doc.id }})">Delete</button>
        </div>
        {% endfor %}
    </div>
</div>
```

**Source Citations in Chat:**
```html
<div class="message ai-message">
    <div class="content">
        The capital of France is Paris...
    </div>
    <div class="sources">
        <small>📚 Sources: textbook_chapter3.pdf (page 42)</small>
    </div>
</div>
```

### Technical Requirements

**Dependencies to Add:**
```bash
pip install pypdf2          # PDF text extraction
pip install python-docx     # Word document extraction
pip install numpy           # Vector operations
```

**Ollama Model:**
```bash
ollama pull nomic-embed-text  # 274MB embedding model
```

### Development Checklist

- [ ] Add Document + DocumentChunk models
- [ ] Implement file upload endpoint
- [ ] Add text extraction for PDF/DOCX
- [ ] Integrate Ollama embeddings API
- [ ] Build cosine similarity search
- [ ] Modify chat flow to include RAG
- [ ] Add document management UI
- [ ] Display source citations in responses
- [ ] Add "Enable RAG" toggle per bot
- [ ] Write documentation for RAG usage

**Estimated Time:** 2-3 weeks  
**Complexity:** Medium-High

---

## Phase 6: Voice / Audio Integration (Post-MVP)

### Overview
Add voice input/output capabilities for hands-free interaction with bots.

### Why Add This?
- **Accessibility:** Voice is more natural for some users
- **Use Cases:**
  - Students can dictate questions while studying
  - Founders can brainstorm while commuting
  - Accessibility for visually impaired users
- **Local-First:** Use Whisper (local ASR) and local TTS models

### Features

#### 6.1 Voice Input (Speech-to-Text)

**Use Whisper.cpp (local ASR):**

```python
# voice_service.py
import subprocess
import tempfile

def transcribe_audio(audio_file_path: str) -> str:
    """Transcribe audio using local Whisper model"""
    # Use whisper.cpp CLI
    result = subprocess.run(
        ['whisper-cpp', '--model', 'base.en', '--file', audio_file_path],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

# API endpoint
@api.post("/voice/transcribe")
def transcribe_voice(request, file: UploadedFile):
    """Convert speech to text"""
    # Save uploaded audio temporarily
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp.write(file.read())
        tmp_path = tmp.name
    
    try:
        text = transcribe_audio(tmp_path)
        return {'text': text, 'status': 'success'}
    finally:
        os.unlink(tmp_path)
```

**Frontend - Voice Input Button:**

```javascript
// Record audio from microphone
let mediaRecorder;
let audioChunks = [];

async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    
    mediaRecorder.ondataavailable = (e) => {
        audioChunks.push(e.data);
    };
    
    mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
        audioChunks = [];
        
        // Send to backend for transcription
        const formData = new FormData();
        formData.append('file', audioBlob, 'recording.wav');
        
        const response = await fetch('/api/voice/transcribe', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        document.getElementById('user-input').value = data.text;
    };
    
    mediaRecorder.start();
}

function stopRecording() {
    mediaRecorder.stop();
}
```

**UI Element:**
```html
<div class="voice-controls">
    <button id="voice-btn" 
            onmousedown="startRecording()" 
            onmouseup="stopRecording()"
            title="Hold to speak">
        🎤 Hold to Speak
    </button>
    <div id="recording-indicator" style="display:none;">
        🔴 Recording...
    </div>
</div>
```

#### 6.2 Voice Output (Text-to-Speech)

**Use Piper TTS (local, fast):**

```python
# voice_service.py
import subprocess

def text_to_speech(text: str, output_path: str):
    """Convert text to speech using Piper TTS"""
    subprocess.run([
        'piper',
        '--model', 'en_US-lessac-medium',
        '--output_file', output_path
    ], input=text.encode(), check=True)

# API endpoint
@api.post("/voice/speak")
def speak_text(request, text: str):
    """Generate audio from text"""
    # Generate unique filename
    audio_id = uuid.uuid4().hex
    output_path = f'/tmp/speech_{audio_id}.wav'
    
    text_to_speech(text, output_path)
    
    return FileResponse(output_path, content_type='audio/wav')
```

**Frontend - Auto-Play Response:**

```javascript
// After receiving AI response
async function speakResponse(text) {
    const response = await fetch('/api/voice/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
    });
    
    const audioBlob = await response.blob();
    const audioUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(audioUrl);
    audio.play();
}

// Add speaker button to AI messages
function addSpeakerButton(messageElement, text) {
    const btn = document.createElement('button');
    btn.className = 'speaker-btn';
    btn.innerHTML = '🔊 Listen';
    btn.onclick = () => speakResponse(text);
    messageElement.appendChild(btn);
}
```

#### 6.3 Voice-Only Mode

**Continuous conversation mode:**

```html
<div class="voice-mode-panel">
    <h3>🎙️ Voice Mode</h3>
    <p>Hands-free conversation with your bot</p>
    
    <button id="voice-mode-toggle" onclick="toggleVoiceMode()">
        Start Voice Mode
    </button>
    
    <div id="voice-mode-active" style="display:none;">
        <div class="voice-visualizer">
            <canvas id="audio-viz"></canvas>
        </div>
        <p id="voice-status">Listening...</p>
        <button onclick="toggleVoiceMode()">Stop Voice Mode</button>
    </div>
</div>
```

**Voice Mode Flow:**
```
1. User presses "Start Voice Mode"
2. System listens for speech (Voice Activity Detection)
3. Transcribe user speech → Send to LLM
4. Stream LLM response → Convert to speech
5. Play audio response
6. Loop back to step 2 (continuous listening)
```

### Technical Requirements

**Dependencies:**
```bash
# Whisper.cpp (local ASR)
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
make
./models/download-ggml-model.sh base.en

# Piper TTS (local TTS)
pip install piper-tts
piper --download-model en_US-lessac-medium
```

**Audio Processing:**
```bash
pip install pydub           # Audio format conversion
pip install soundfile       # Audio I/O
pip install webrtcvad       # Voice Activity Detection
```

### UI/UX Considerations

**Voice Button States:**
```css
.voice-btn {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    transition: transform 0.1s;
}

.voice-btn:active {
    transform: scale(0.95);
    background: #ff6b6b;
}

.recording {
    animation: pulse 1s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
```

**Audio Waveform Visualization:**
```javascript
// Visualize audio input during recording
function visualizeAudio(stream) {
    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
    
    const canvas = document.getElementById('audio-viz');
    const ctx = canvas.getContext('2d');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    
    function draw() {
        requestAnimationFrame(draw);
        analyser.getByteTimeDomainData(dataArray);
        
        ctx.fillStyle = 'rgb(20, 20, 20)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        ctx.lineWidth = 2;
        ctx.strokeStyle = 'rgb(0, 255, 0)';
        ctx.beginPath();
        
        const sliceWidth = canvas.width / bufferLength;
        let x = 0;
        
        for (let i = 0; i < bufferLength; i++) {
            const v = dataArray[i] / 128.0;
            const y = v * canvas.height / 2;
            
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
            
            x += sliceWidth;
        }
        
        ctx.stroke();
    }
    
    draw();
}
```

### Development Checklist

- [ ] Install Whisper.cpp locally
- [ ] Install Piper TTS
- [ ] Add voice transcription endpoint
- [ ] Add TTS generation endpoint
- [ ] Build microphone recording UI
- [ ] Add speaker button to messages
- [ ] Implement voice-only mode
- [ ] Add audio visualization
- [ ] Add voice activity detection
- [ ] Handle browser permissions (mic access)
- [ ] Optimize audio latency
- [ ] Add voice settings (speed, pitch)

**Estimated Time:** 3-4 weeks  
**Complexity:** High

---

## Phase 7: Additional Enhancements (Optional)

### 7.1 Model Comparison View
Side-by-side chat with multiple models:
```
┌─────────────────────────────────────────┐
│  [qwen2.5:3b]    [llama3.2:3b]          │
├──────────────────┬──────────────────────┤
│ User: Explain AI │ User: Explain AI     │
│                  │                      │
│ AI: [qwen resp]  │ AI: [llama resp]     │
└──────────────────┴──────────────────────┘
```

### 7.2 Prompt Library
Save and share prompt templates:
```python
class PromptTemplate(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)  # coding, writing, research
    template = models.TextField()
    variables = models.JSONField()  # {var_name: description}
    is_public = models.BooleanField(default=False)
```

### 7.3 Response Regeneration
```html
<button onclick="regenerateResponse(messageId)">
    🔄 Regenerate
</button>
```

### 7.4 Response Forking
Create alternate conversation paths:
```
Message A → Response 1 (original)
         └─ Response 2 (fork with temp=1.5)
```

### 7.5 Token Usage Analytics
```python
class UsageStats(models.Model):
    bot = models.ForeignKey(Bot)
    date = models.DateField()
    total_tokens = models.IntegerField()
    total_messages = models.IntegerField()
    avg_response_time = models.FloatField()
```

Dashboard:
```
📊 Token Usage This Week
─────────────────────────
Total: 45,234 tokens
Avg per message: 234 tokens
Most active bot: Research Assistant (18K tokens)
```

### 7.6 Multi-Language Support
```python
SUPPORTED_LANGUAGES = [
    ('en', 'English'),
    ('es', 'Spanish'),
    ('fr', 'French'),
    ('de', 'German'),
    ('zh', 'Chinese'),
]
```

Auto-detect language and translate:
```python
def detect_language(text: str) -> str:
    # Use Ollama with multilingual model
    pass
```

### 7.7 Code Execution Sandbox
Run code snippets from LLM responses:
```python
import subprocess
import docker

def execute_python_code(code: str) -> dict:
    """Run Python code in isolated Docker container"""
    client = docker.from_env()
    container = client.containers.run(
        'python:3.11-slim',
        f'python -c "{code}"',
        remove=True,
        stdout=True,
        stderr=True,
        timeout=5
    )
    return {'output': container.decode()}
```

### 7.8 Conversation Search
```python
@api.get("/search")
def search_conversations(request, query: str):
    """Full-text search across all conversations"""
    from django.db.models import Q
    
    messages = Message.objects.filter(
        Q(content__icontains=query)
    ).select_related('conversation__bot')
    
    return [{'message': m.content, 'bot': m.conversation.bot.name} for m in messages]
```

---

## Implementation Priority

### Must-Have (Phase 5-6)
1. ✅ **RAG/Knowledge Base** - High educational value, teaches core AI concept
2. ✅ **Voice Input** - Accessibility + user convenience

### Nice-to-Have (Phase 7)
3. 🌟 Model comparison - Useful for experimentation
4. 🌟 Prompt library - Accelerates learning
5. 🌟 Token analytics - Helps understand usage patterns

### Advanced (Future)
6. 💡 Code execution - Security concerns, requires sandboxing
7. 💡 Multi-language - Niche use case
8. 💡 Response forking - Complex UI/UX

---

## Complexity vs. Value Matrix

```
High Value, Low Complexity:
├─ Prompt library
├─ Response regeneration
└─ Token analytics

High Value, Medium Complexity:
├─ RAG/Knowledge Base ⭐ Priority
├─ Voice input ⭐ Priority
└─ Model comparison

High Value, High Complexity:
├─ Voice-only mode
├─ Code execution sandbox
└─ Multi-language support

Low Value, Any Complexity:
└─ (Skip these)
```

---

## Estimated Timeline

| Phase | Features | Duration | Status |
|-------|----------|----------|--------|
| 1-4 | MVP | 4 weeks | 🔵 Primary |
| 5 | RAG/Knowledge Base | 2-3 weeks | 🟢 Post-MVP |
| 6 | Voice Integration | 3-4 weeks | 🟢 Post-MVP |
| 7 | Additional Features | 2-4 weeks | 🟡 Optional |

**Total Time:** 11-15 weeks (3-4 months) for full feature set

---

## Learning Path for Users

### Week 1: Basic Chat (MVP)
- Create first bot
- Understand temperature effects
- Copy API code

### Week 2-3: Advanced Parameters
- Experiment with top_p/top_k
- Compare model outputs
- Export conversations

### Week 4-5: RAG (Phase 5)
- Upload first document
- See semantic search in action
- Understand embeddings

### Week 6-7: Voice (Phase 6)
- Try voice input
- Enable auto-read responses
- Use voice-only mode

---

## Success Metrics

**Phase 5 (RAG) Success:**
- ✅ User uploads PDF and chats with it within 5 minutes
- ✅ Search returns relevant chunks 80%+ of time
- ✅ Sources cited in responses
- ✅ Indexing completes in <30 seconds for 100-page PDF

**Phase 6 (Voice) Success:**
- ✅ Voice transcription accuracy >90%
- ✅ End-to-end voice latency <3 seconds
- ✅ TTS sounds natural (subjective)
- ✅ Voice mode works hands-free

---

## Technical Debt to Avoid

### ❌ Don't Do This:
- Cloud embedding APIs (defeats local-first goal)
- Vector databases (Pinecone, Weaviate) - overkill for <10K docs
- Complex chunking strategies - keep it simple
- Real-time STT (streaming ASR) - too complex for MVP

### ✅ Do This Instead:
- Local Ollama embeddings
- SQLite with JSON array storage
- Fixed 500-word chunks with 50-word overlap
- Post-recording transcription

---

## Resources

### RAG Implementation
- **Ollama Embeddings:** https://ollama.ai/blog/embedding-models
- **nomic-embed-text:** https://huggingface.co/nomic-ai/nomic-embed-text-v1
- **Chunking Strategies:** https://www.pinecone.io/learn/chunking-strategies/

### Voice Integration
- **Whisper.cpp:** https://github.com/ggerganov/whisper.cpp
- **Piper TTS:** https://github.com/rhasspy/piper
- **Web Audio API:** https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API

### ChefAI Reference
- **RAG Implementation:** `/allies/llm_service.py` (lines 871-920)
- **Voice Integration:** `/voice/` app (full implementation)
- **Document Processing:** `/chef_assistant_app/views.py` (dashboard)

---

## Final Notes

**Build Order:**
1. ✅ MVP (Phase 1-4) first - get chat working perfectly
2. ✅ Add RAG (Phase 5) - high value, teaches core concept
3. ✅ Add Voice (Phase 6) - nice UX upgrade
4. 💡 Pick from Phase 7 based on user feedback

**Keep It Local:**
- Every feature should work offline
- No cloud APIs unless absolutely necessary
- Favor simplicity over feature completeness

**Educational Focus:**
- Explain *why* RAG works (vector similarity)
- Show *how* voice transcription works (Whisper model)
- Make parameters visible and tweakable

---

**END OF EXTENDED ROADMAP**

This document provides a clear path to evolve MiniClosedAI from a simple chat tool into a powerful local AI platform while maintaining the core principles of simplicity, education, and local-first architecture.
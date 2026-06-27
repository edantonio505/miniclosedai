I turned a 2,500-year-old book into a personal advisor in about two minutes — and it never left my laptop.

In the video below I build a "War Expert" in MiniClosedAI from an empty bot:

1. Bots page → **+ New bot** → name it **"War Expert."**
2. Describe it in one sentence — *"You are a wise man who advises me on how to approach war. Teach me, using The Art of War as reference."* — and let MiniClosedAI **generate the full system prompt** for me.
3. **Hand it the actual book.** Upload *The Art of War* (PDF) as the bot's knowledge base. No external vector database — the text is chunked, embedded, and stored right next to the bot in SQLite.
4. Ask for help with a conflict I'm facing. It answers like a strategist — grounded in the book, not made up.
5. Give it a **face.** Drop in a portrait of Sun Tzu as the bot's avatar.
6. Click back to the Bots page in grid view — and there's my new expert in the gallery, next to MiniClosedChatGPT and the rest, each with its own picture and name.

That's the whole loop: **name → describe → feed it a book → give it a face → ship.** No prompt-engineering degree, no vector-DB setup, no monthly bill.

And every one of those bots is a callable API endpoint on *your* hardware, running *your* model, on *your* data — $0 per message, MIT-licensed, yours forever.

Give your bot a book. Give it a face. Then go build your own experts.

⭐ GitHub (code + templates): https://github.com/edantonio505/miniclosedai
🚀 Free GPU compute when you outgrow your laptop: interdataresearch.ai

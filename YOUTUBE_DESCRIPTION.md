Build a "War Expert" in MiniClosedAI — turn a 2,500-year-old book into a personal advisor in about two minutes, running entirely on your own machine.

This video walks the whole flow end to end:

1. Go to the Bots page and click + New bot, then name it "War Expert."
2. Describe the bot in one sentence — "You are a wise man who advises me on how to approach war. Teach me, using The Art of War as reference." — and let MiniClosedAI generate the full system prompt for you.
3. Hand it the actual book. Upload The Art of War (PDF) as the bot's knowledge base. No external vector database — the text is chunked, embedded, and stored right next to the bot in SQLite.
4. Ask it for advice on a conflict you're facing. It answers like a strategist, grounded in the book instead of making things up.
5. Give it a face. Drop in a portrait of Sun Tzu as the bot's avatar.
6. Click back to the Bots page in grid view and see your new expert in the gallery, next to MiniClosedChatGPT and the rest, each with its own picture and name.

That's the whole loop: name, describe, feed it a book, give it a face, ship. No prompt-engineering degree, no vector-DB setup, no monthly bill.

Every bot is a callable API endpoint on your hardware, running your model, on your data — $0 per message, MIT-licensed, yours forever.

All the code and templates are in the GitHub repo, with a step-by-step writeup in the README and DOCUMENTATION.

⭐ GitHub (code + templates): https://github.com/edantonio505/miniclosedai
🚀 Free GPU compute when you outgrow your laptop: interdataresearch.ai

MiniClosedAI is MIT-licensed. Your hardware, your model, your data, your $0 bill. Be your own chatbot platform.

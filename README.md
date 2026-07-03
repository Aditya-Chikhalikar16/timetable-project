# College Timetable AI Chatbot

An AI-powered chatbot for browsing, querying, and editing your college timetable.
Supports **Google Gemini** and **OpenAI GPT** for natural language questions.

## Features

- **AI Chat** — Ask in plain English ("I'm in AD1, what's on Monday?")
- **Gemini or GPT** — Choose provider in sidebar or `.env`
- **Grid View** — Weekly timetable grid per division
- **List View** — Filterable table with search
- **Edit Mode** — Add, update, or delete entries

## Quick Start

```powershell
cd d:\timetable-chatbot
py -m pip install -r requirements.txt
copy .env.example .env
py -m streamlit run app.py
```

Or double-click **`run.bat`**.

Open http://localhost:8501

## API Keys (pick one or both)

### Gemini (recommended — free tier)
1. Get a key at https://aistudio.google.com/apikey
2. Add to `.env`: `GEMINI_API_KEY=your-key`
3. Or paste it in the **AI Settings** sidebar when the app is running

### OpenAI GPT
1. Get a key at https://platform.openai.com/api-keys
2. Add to `.env`: `OPENAI_API_KEY=sk-your-key`
3. Or paste it in the sidebar

Set `LLM_PROVIDER=gemini` or `LLM_PROVIDER=openai` to force a provider.
Default `auto` prefers Gemini if both keys are set.

## Example Questions

- "I'm in AD1 — what classes do I have on Monday?"
- "When is the physics lab for CE2?"
- "Who teaches math in IT3?"
- "Show all Friday tutorials for ME1"
- "What's Dr. Dhabekar teaching this week?"

## Without an API key

Basic pattern matching still works for simple queries like "AD1 Monday schedule".
Add a Gemini or OpenAI key for full natural language understanding.

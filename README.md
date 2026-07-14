# College Timetable Chatbot

An AI-powered chatbot for browsing, querying, and editing your college timetable.
Powered by **Ollama** (local LLM — no API key, no internet required).

## Features

- **Natural Language Chat** — Ask anything: *"What labs does CE2 have on Friday?"*, *"Who teaches IT1 Monday morning?"*, *"Show Dr. Sharma's full schedule"*
- **Full Edit via Chat** — Add, update, delete, replace entries in plain English
- **Grid View** — Weekly timetable grid per division
- **List View** — Filterable table with search
- **Edit Mode** — Form-based add/update/delete
- **Offline fallback** — Rule-based mode works without Ollama

## Quick Start

### 1. Install Ollama
Download from https://ollama.com and install it.

### 2. Pull a model
```powershell
ollama pull llama3.2
```
*(One-time download, ~2GB. With your specs you can also try `llama3.1:8b` for even better quality.)*

### 3. Run the chatbot
```powershell
cd d:\timetable-chatbot
py -m pip install -r requirements.txt
py -m streamlit run app.py
```
Or double-click **`run.bat`**.

Open http://localhost:8501

The sidebar shows 🟢 when Ollama is connected, 🟡 when offline (rule-based fallback).

## Example Queries

- *"What's happening in CE2 tomorrow?"*
- *"Do IT1 students have anything after lunch on Wednesday?"*
- *"Who's free on Friday morning in room AC301?"*
- *"Show me all labs for ME1 this week"*
- *"Which professor teaches the most classes?"*

## Example Edits (via chat)

- *"Add a Theory class for AD1 on Tuesday at 11am, subject OS, professor Dr. Mehta, room AC301"*
- *"Update id 93 room to AC 401"*
- *"Delete id 113"*
- *"Replace CE2 BET with AP"*

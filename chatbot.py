"""Timetable chatbot — Ollama LLM with rule-based fallback."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from timetable import TimetableStore
from edit_parser import handle_edit_command, is_edit_command, format_edit_result

import os
OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

EXTRACT_SYSTEM = """You are a college timetable assistant. Your job is to parse the user's message and return a JSON action plan.

The timetable has these divisions: AD1, AD2, AD3, CE1, CE2, CE3, ET1, ET2, ET3, EL, IT1, IT2, IT3, ME1, ME2.
Days: Monday, Tuesday, Wednesday, Thursday, Friday.
Class types: Theory, Lab, Tutorial, Practical.

CONVERSATION CONTEXT — CRITICAL:
You will receive the conversation history before the current message. Use it to resolve any references:
- Pronouns: "they", "them", "it", "those", "that" → resolve from prior messages
- Implicit references: "same day", "same division", "that professor", "those labs" → carry over from prior context
- Follow-up questions: "what about Monday?", "and for CE1?", "how many are there?" → inherit the division/day/type from the last relevant exchange
- If the user says "same" or "again" or gives a partial query, fill in the blanks from prior context

Respond with ONLY valid JSON — no prose, no markdown fences. Use this schema:

{
  "intent": "<one of: query_timetable | get_day_schedule | get_filtered_schedule | get_professor_schedule | get_division_timetable | who_teaches_at | list_divisions | get_timetable_summary | add_class | update_class | delete_class | replace_subject | find_class | chitchat>",
  "division": "<division or null>",
  "day": "<day or null>",
  "time_slot": "<time slot string or null>",
  "subject": "<subject code or null>",
  "professor": "<professor name or partial name or null>",
  "class_type": "<Theory|Lab|Tutorial|Practical or null>",
  "room": "<room or null>",
  "entry_id": <integer or null>,
  "new_professor": "<new value or null>",
  "new_day": "<new value or null>",
  "new_time_slot": "<new value or null>",
  "new_division": "<new value or null>",
  "new_subject": "<new value or null>",
  "new_room": "<new value or null>",
  "new_type": "<new value or null>",
  "old_subject": "<for replace_subject: subject to replace or null>",
  "new_subject_replace": "<for replace_subject: new subject or null>"
}

Rules:
- ALWAYS resolve references from conversation history before filling JSON fields.
- For vague time words like "morning" map to approximate slots (9:00 am - 10:00 am range), "afternoon" to 1pm+, "after lunch" to 1pm+.
- "tomorrow", "today" etc. — leave day as null (you don't know the actual date).
- For chitchat (greetings, thanks, unrelated questions) use intent "chitchat".
- Normalize division names: "CE 2" → "CE2", "it1" → "IT1".
- If the user says "labs" without specifying Theory/Lab/etc., set class_type to "Lab"."""

ANSWER_SYSTEM = """You are a friendly college timetable assistant.
You have retrieved data from the timetable database to answer the user's latest question.
You also have the conversation history so you can naturally refer to what was discussed before.

Guidelines:
- Write a clear, concise, natural-language answer based ONLY on the retrieved data.
- Reference prior conversation naturally when relevant (e.g. "As I mentioned...", "Unlike CE2 which had 3 labs, CE1 has...").
- Do not guess or invent any timetable information not present in the retrieved data.
- If the data is empty, say so naturally.
- Keep answers brief unless the user asked for everything."""


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

def detect_ollama() -> dict:
    """Return {"available": bool, "models": [...]}"""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            return {"available": True, "models": models}
    except Exception:
        return {"available": False, "models": []}


def _ollama_chat(model: str, messages: list[dict], temperature: float = 0.2, timeout: int = 60) -> str:
    """Call Ollama /api/chat and return the assistant content string."""
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "").strip()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama not reachable: {e}") from e

def detect_gemini() -> dict:
    """Return {'available': bool, 'api_key_set': bool}"""
    import streamlit as st
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass
    return {"available": bool(api_key), "api_key_set": bool(api_key)}

def _gemini_chat(messages: list[dict], temperature: float = 0.2, timeout: int = 60) -> str:
    """Call Google Gemini API and return the assistant content string."""
    import streamlit as st
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found.")

    # Convert OpenAI-style messages to Gemini format
    system_text = ""
    contents = []
    for msg in messages:
        if msg["role"] == "system":
            system_text += msg["content"] + "\n"
        elif msg["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
        elif msg["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": msg["content"]}]})

    body = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
        },
    }
    if system_text:
        body["systemInstruction"] = {"parts": [{"text": system_text.strip()}]}

    url = f"{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            return ""
    except urllib.error.HTTPError as e:
        err_data = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        raise RuntimeError(f"Gemini API error: {err_data}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gemini not reachable: {e}") from e


# ---------------------------------------------------------------------------
# Rule-based helpers (kept as fallback)
# ---------------------------------------------------------------------------

def _extract_time(msg: str) -> str | None:
    m = re.search(
        r"(?:from\s+)?(\d{1,2}:?\d{0,2}\s*(?:am|pm))(?:\s+to\s+\d{1,2}:?\d{0,2}\s*(?:am|pm))?",
        msg, re.I,
    )
    if m:
        t = m.group(1).strip()
        if ":" not in t:
            t = re.sub(r"(\d{1,2})\s*(am|pm)", r"\1:00 \2", t, flags=re.I)
        return t
    m = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)", msg, re.I)
    return f"{m.group(1)}:{m.group(2)} {m.group(3)}" if m else None


def _wants_full_timetable(msg: str) -> bool:
    return bool(re.search(r"\b(full|entire|whole|complete)\s+(timetable|schedule)\b", msg, re.I))


def _asks_faculty(msg: str) -> bool:
    return bool(re.search(r"\b(faculty|professor|prof|teacher|who\s+teach)", msg, re.I))


def _extract_class_type(msg: str) -> str | None:
    m = msg.lower()
    if re.search(r"\b(labs?|laboratory|laboratories)\b", m):
        return "Lab"
    if re.search(r"\b(tutorials?|tut)\b", m):
        return "Tutorial"
    if re.search(r"\b(practicals?|prac)\b", m):
        return "Practical"
    if re.search(r"\b(theory|lectures?|lecture)\b", m):
        return "Theory"
    return None


def _extract_professor_query(msg: str) -> str | None:
    patterns = [
        r"(?:all\s+)?slots?\s+of\s+(.+)",
        r"(?:schedule|classes|timetable)\s+of\s+(.+)",
        r"(?:professor|prof|teacher|faculty)\s+(.+)",
        r"(?:taught by)\s+(.+)",
        r"who teaches\s+(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, msg, re.I)
        if m:
            return m.group(1).strip().rstrip("?.!")
    return None


# ---------------------------------------------------------------------------
# Main chatbot class
# ---------------------------------------------------------------------------

class TimetableChatbot:
    def __init__(self, store: TimetableStore | None = None, model: str | None = None, provider: str = "auto", **kwargs):
        self.store = store or TimetableStore()
        self.model = model or DEFAULT_MODEL
        self.provider = provider  # "auto", "ollama", or "groq"
        self._ollama_status: dict | None = None
        self._groq_status: dict | None = None
        self._gemini_status: dict | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        if self._ollama_status is None:
            self._ollama_status = detect_ollama()
        if self._gemini_status is None:
            self._gemini_status = detect_gemini()
            
        active_provider = "offline"
        if self.provider == "gemini" and self._gemini_status["available"]:
            active_provider = "gemini"
        elif self.provider == "ollama" and self._ollama_status["available"]:
            active_provider = "ollama"
        elif self.provider == "auto":
            if self._ollama_status["available"]:
                active_provider = "ollama"
            elif self._gemini_status["available"]:
                active_provider = "gemini"
                
        return {
            "ollama": self._ollama_status,
            "gemini": self._gemini_status,
            "active_provider": active_provider
        }

    def is_ai_available(self) -> bool:
        return self.get_status()["active_provider"] != "offline"

    def provider_label(self) -> str:
        status = self.get_status()
        active = status["active_provider"]
        if active == "ollama":
            return f"Ollama · {self.model}"
        elif active == "gemini":
            return f"Gemini · {GEMINI_MODEL}"
        return "Rule-based (offline)"

    def refresh_status(self):
        self._ollama_status = detect_ollama()
        self._gemini_status = detect_gemini()

    def chat(self, user_message: str, history: list[dict] | None = None) -> str:
        if is_edit_command(user_message):
            edit_reply = handle_edit_command(self.store, user_message)
            if edit_reply:
                return edit_reply

        status = self.get_status()
        active = status["active_provider"]

        if active != "offline":
            try:
                return self._chat_llm(user_message, history or [], active)
            except Exception as exc:
                fallback = self._fallback_chat(user_message)
                return f"{fallback}\n\n*⚠️ {active.title()} error — used offline mode: {exc}*"

        return self._fallback_chat(user_message)

    # ------------------------------------------------------------------
    # LLM two-phase chat
    # ------------------------------------------------------------------

    def _call_llm(self, messages: list[dict], provider: str, temperature: float = 0.2) -> str:
        if provider == "gemini":
            return _gemini_chat(messages, temperature=temperature)
        else:
            return _ollama_chat(self.model, messages, temperature=temperature)

    def _chat_llm(self, user_message: str, history: list[dict], provider: str) -> str:
        # ── Phase 1: extract intent + entities ──────────────────────────
        extract_messages = [{"role": "system", "content": EXTRACT_SYSTEM}]
        # Provide recent history as context (last 4 turns)
        for m in history[-8:]:
            if m["role"] in ("user", "assistant"):
                extract_messages.append({"role": m["role"], "content": m["content"]})
        extract_messages.append({"role": "user", "content": user_message})

        raw = self._call_llm(extract_messages, provider, temperature=0.0)
        plan = self._parse_json_plan(raw)

        intent = plan.get("intent", "chitchat")

        # Chitchat — just ask the model to reply directly
        if intent == "chitchat":
            return self._llm_direct(user_message, history, provider)

        # ── Phase 2: fetch data ──────────────────────────────────────────
        data_text = self._execute_plan(intent, plan)

        # ── Phase 3: generate natural answer (with full history context) ──
        answer_messages = [{"role": "system", "content": ANSWER_SYSTEM}]
        # Include recent conversation so model can reference prior turns
        for m in history[-8:]:
            if m["role"] in ("user", "assistant"):
                answer_messages.append({"role": m["role"], "content": m["content"]})
        answer_messages.append({"role": "user", "content": (
            f"{user_message}\n\n"
            f"[Retrieved timetable data for this question:]\n{data_text}"
        )})
        return self._call_llm(answer_messages, provider, temperature=0.3)

    def _llm_direct(self, user_message: str, history: list[dict], provider: str) -> str:
        """For chitchat / meta questions — reply without timetable data."""
        messages = [
            {"role": "system", "content": (
                "You are a friendly college timetable assistant. "
                "Answer naturally. If you don't know the answer, say so."
            )},
        ]
        for m in history[-6:]:
            if m["role"] in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_message})
        return self._call_llm(messages, provider, temperature=0.5)

    # ------------------------------------------------------------------
    # Plan parser
    # ------------------------------------------------------------------

    def _parse_json_plan(self, raw: str) -> dict:
        """Extract JSON from model output even if wrapped in markdown."""
        text = raw.strip()
        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.M)
        text = re.sub(r"```\s*$", "", text, flags=re.M)
        text = text.strip()
        # Find first {...} block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {"intent": "chitchat"}

    # ------------------------------------------------------------------
    # Execute plan → fetch data from store
    # ------------------------------------------------------------------

    def _execute_plan(self, intent: str, plan: dict) -> str:
        div = plan.get("division")
        day = plan.get("day")
        time_slot = plan.get("time_slot")
        subject = plan.get("subject")
        professor = plan.get("professor")
        class_type = plan.get("class_type")
        room = plan.get("room")
        entry_id = plan.get("entry_id")

        if intent == "query_timetable":
            records = self.store.query(
                division=div, day=day, time_slot=time_slot,
                subject=subject, professor=professor,
                class_type=class_type, room=room, limit=20,
            )
            if not records:
                return "No matching classes found."
            return self.store.format_records(records, compact=True)

        if intent == "get_day_schedule":
            return self.store.get_day_overview(day or "Monday", div, class_type)

        if intent == "get_filtered_schedule":
            return self.store.get_filtered_schedule(
                division=div, day=day, class_type=class_type, subject=subject)

        if intent == "get_professor_schedule":
            if not professor:
                return "Please specify a professor name."
            if hasattr(self.store, "format_professor_schedule"):
                return self.store.format_professor_schedule(professor)
            records = self.store.get_professor_schedule(professor)
            return self.store.format_records(records, compact=True) if records else f"No classes found for '{professor}'."

        if intent == "get_division_timetable":
            if not div:
                return "Please specify a division."
            records = self.store.get_division_schedule(div)
            return self.store.format_records(records, compact=True) if records else f"No timetable found for {div}."

        if intent == "who_teaches_at":
            if not div or not time_slot:
                return "Please specify division and time slot."
            return self.store.answer_faculty_at_time(div, time_slot, day)

        if intent == "list_divisions":
            return "Available divisions: " + ", ".join(self.store.divisions)

        if intent == "get_timetable_summary":
            return str(self.store.get_summary())

        if intent == "find_class":
            records = self.store.find_entries(
                division=div, day=day, time_slot=time_slot,
                subject=subject, professor=professor, class_type=class_type, limit=15,
            )
            if not records:
                return "No entries found."
            return self.store.format_entries_with_ids(records)

        if intent == "add_class":
            if not all([professor, day, time_slot, div, subject]):
                return "Missing required fields: professor, day, time_slot, division, subject."
            entry = self.store.add_class(
                professor=professor, day=day, time_slot=time_slot,
                division=div, subject=subject,
                room=room or "", class_type=class_type or "Theory",
            )
            eid = int(self.store.df["_id"].max())
            return format_edit_result(self.store, {"success": True, "entry": entry, "entry_id": eid}, "add")

        if intent == "update_class":
            new_fields = {
                k: plan[k] for k in ("new_professor", "new_day", "new_time_slot",
                                      "new_division", "new_subject", "new_room", "new_type")
                if plan.get(k)
            }
            result = self.store.update_class(
                entry_id=entry_id, division=div, day=day,
                time_slot=time_slot, subject=subject, professor=professor,
                **new_fields,
            )
            return format_edit_result(self.store, result, "update")

        if intent == "delete_class":
            result = self.store.delete_class(
                entry_id=entry_id, division=div, day=day,
                time_slot=time_slot, subject=subject, professor=professor,
            )
            return format_edit_result(self.store, result, "delete")

        if intent == "replace_subject":
            old_subj = plan.get("old_subject")
            new_subj = plan.get("new_subject_replace") or plan.get("new_subject")
            if not old_subj or not new_subj:
                return "Please specify the old and new subject names."
            result = self.store.replace_subject(
                old_subject=old_subj, new_subject=new_subj,
                division=div, day=day,
            )
            return format_edit_result(self.store, result, "replace")

        return "I'm not sure how to handle that request."

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    def _fallback_chat(self, user_msg: str) -> str:
        msg = user_msg.lower().strip()
        if not msg:
            return (
                "Ask me about your timetable or edit it directly:\n"
                "- *Find CE2 Friday labs*\n"
                "- *Add class AD1 Monday 10:00 am - 11:00 am, subject AP, professor Dr. X, room AC 301*\n"
                "- *Update id 93 room to AC 401*\n"
                "- *Delete id 113*"
            )

        edit_reply = handle_edit_command(self.store, user_msg)
        if edit_reply:
            return edit_reply

        prof_query = _extract_professor_query(user_msg)
        if prof_query and not re.search(r"\b(add|delete|update|change|replace|find)\b", msg):
            if hasattr(self.store, "format_professor_schedule"):
                return self.store.format_professor_schedule(prof_query)
            records = self.store.get_professor_schedule(prof_query)
            return self.store.format_records(records, compact=True) if records else f"No classes for '{prof_query}'."

        div_match = re.search(r"\b(ad[123]|ce[123]|et[123]|el|it[123]|me[12])\b", msg, re.I)
        division = div_match.group(1).upper() if div_match else None
        days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
        day = next((d.capitalize() for d in days if d in msg), None)
        time_str = _extract_time(user_msg)

        if "division" in msg and not division:
            return "Available divisions: " + ", ".join(self.store.divisions)
        if "summary" in msg or "overview" in msg:
            return str(self.store.get_summary())
        if division and time_str and _asks_faculty(msg):
            return self.store.answer_faculty_at_time(division, time_str, day)
        if division and time_str:
            records = self.store.query(division=division, day=day, time_slot=time_str, limit=10)
            return self.store.format_records(records, compact=True) if records else f"No classes for {division} at {time_str}."
        class_type = _extract_class_type(user_msg)
        if division and day:
            if class_type:
                return self.store.get_filtered_schedule(division=division, day=day, class_type=class_type)
            return self.store.get_day_overview(day, division)
        if division and _wants_full_timetable(msg):
            return self.store.format_records(self.store.get_division_schedule(division), compact=True)
        if division:
            return (
                f"I found division **{division}**. Try:\n"
                f"- *Who teaches {division} at 10:00 am?*\n"
                f"- *Find entries {division} Friday*\n"
                f"- *Replace {division} BET with AP*"
            )
        return (
            "**Commands you can use:**\n"
            "- *Find CE2 Friday labs*\n"
            "- *Add class AD1 Monday 10:00 am - 11:00 am, subject AP, professor Dr. X, room AC 301, type Theory*\n"
            "- *Update id 93 room to AC 401*\n"
            "- *Change CE2 Monday BET room to AC 502*\n"
            "- *Delete id 113*\n"
            "- *Replace CE2 BET with AP*"
        )

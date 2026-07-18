"""Timetable chatbot — Ollama LLM with rule-based fallback."""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

from timetable import TimetableStore
from edit_parser import handle_edit_command, is_edit_command, format_edit_result, format_replace_preview

import os

logger = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"
GROQ_MODEL = "llama-3.2-3b-preview"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

EXTRACT_SYSTEM = """You are a college timetable assistant. Your ONLY job is to read the user's message and output a JSON action plan.

The timetable has these divisions: AD1, AD2, AD3, CE1, CE2, CE3, ET1, ET2, ET3, EL, IT1, IT2, IT3, ME1, ME2.
Days: Monday, Tuesday, Wednesday, Thursday, Friday.
Class types: Theory, Lab, Tutorial, Practical.

{subject_list}

For `professor`, extract the exact name as written by the user. Do not attempt to correct spelling. If not provided, output null.

INTENT SELECTION GUIDE (pick the BEST match):
- "get_professor_schedule" — ANY question about a professor's classes, schedule, or when/where they teach.
  Examples: "does bochare sir have class on tuesday", "when does kolambe mam teach", "show me sharma sir's timetable", "bochare tuesday lectures"
- "query_timetable" — General search with multiple filters (division + subject, day + type, etc.)
  Examples: "CE2 labs on friday", "physics classes", "what's in room AC 301"
- "get_day_schedule" — Show everything on a specific day (optionally for a division).
  Examples: "what's on monday", "CE1 thursday schedule", "show friday"
- "get_division_timetable" — Show full timetable for a division.
  Examples: "show CE2 timetable", "full schedule for IT1"
- "get_filtered_schedule" — Filtered view (by type, subject, etc.).
  Examples: "all labs for CE2", "theory classes on wednesday"
- "who_teaches_at" — ONLY when asking who is teaching at a SPECIFIC division + time.
  Examples: "who teaches CE2 at 10 am on monday" (requires division AND time_slot)
- "get_timetable_summary" — Overview statistics.
  Examples: "how many classes total", "summary", "overview"
- "find_class" — Search with entry IDs shown.
- "chitchat" — Greetings, thanks, jokes, unrelated questions.
  Examples: "hi", "thanks", "what's the weather"

CONVERSATION CONTEXT:
You will receive conversation history. Use it to resolve references:
- Pronouns: "he", "she", "his", "her", "they", "them", "that professor" → resolve professor from prior messages
- "same day", "and for CE1?" → inherit division/day from prior context
- "what about Physics" → NEW subject query, CLEAR professor (set null)
- "what about Monday" → KEEP division, change day
- Only inherit fields the user does NOT explicitly change.

UNDERSTANDING CASUAL LANGUAGE:
- "sir", "mam", "madam", "teacher" → the word before it is the professor's name. "bochare sir" → professor: "bochare"
- "lecture", "class", "period" → means Theory unless "lab" or "tutorial" is said
- "free period", "any gaps", "off" → query_timetable to check what's NOT scheduled
- "after lunch", "afternoon" → time after 1:00 pm
- "morning" → before 12:00 pm
- Division names may be messy: "ce 2" → "CE2", "i.t. 1" → "IT1", "ad-3" → "AD3"
- Misspellings: try your best to match against the professor/subject lists above

IMPORTANT: When someone asks about a professor ("does X sir teach...", "X mam schedule", "when does X have class"), ALWAYS use intent "get_professor_schedule" with the professor's name. Do NOT use "who_teaches_at" — that intent is ONLY for "who teaches [division] at [time]".

Respond with ONLY valid JSON — no prose, no markdown fences:

{{
  "intent": "<intent from list above>",
  "division": "<division or null>",
  "day": "<day or null>",
  "time_slot": "<time slot string or null>",
  "subject": "<natural subject name — 'Physics', 'Math', 'Chemistry', etc. System does partial matching. null if not relevant>",
  "professor": "<professor name/partial name or null>",
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
  "old_subject": "<for replace_subject or null>",
  "new_subject_replace": "<for replace_subject or null>"
}}

Rules:
- When the user names a subject, use the natural name. "Physics" matches "AP (Applied Physics)", "Math" matches "M-I (Engineering Mathematics I)".
- Normalize divisions: "CE 2" → "CE2", "it1" → "IT1".
- "labs" without other context → set class_type to "Lab".
- "tomorrow", "today" → leave day as null.
- For chitchat (greetings, thanks, off-topic) → intent: "chitchat"."""

ANSWER_SYSTEM = """You are a warm, friendly college timetable assistant.

Your job: Write ONLY a short 1-2 sentence introduction to the timetable data below.
Do NOT list, repeat, summarize, or reformat any of the actual timetable entries.
The entries will be shown separately — you are just writing the intro line.

Examples of good intros:
- "Here's what I found for Prof. Bochare on Tuesday! 📅"
- "Yep, CE2 has a few labs on Friday! Here they are:"
- "I couldn't find any classes matching that — maybe try a different day or check the spelling? 🤔"
- "Looks like a busy morning for AD1! Here's the schedule:"

Rules:
- Keep it SHORT — one or two sentences max
- Be warm and conversational, like a friendly senior student
- Use emoji sparingly (0-1 per message)
- NEVER abbreviate professor names. If you mention a name from the data, use the exact full name shown.
- If the data says "no classes found" or "not found", be helpful and suggest what they could try
- NEVER mention specific times, rooms, subjects, or professor names UNLESS they are in the data below
- Just write the intro, nothing else"""


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

def detect_groq() -> dict:
    """Return {'available': bool, 'api_key_set': bool}"""
    import streamlit as st
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            pass
    return {"available": bool(api_key), "api_key_set": bool(api_key)}

def _groq_chat(messages: list[dict], temperature: float = 0.2, timeout: int = 60) -> str:
    """Call Groq API and return the assistant content string."""
    import streamlit as st
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets.get("GROQ_API_KEY")
        except Exception:
            pass
            
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not found.")
        
    body = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }
    
    req = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except urllib.error.URLError as e:
        if hasattr(e, 'read'):
            err_data = e.read().decode('utf-8')
            raise RuntimeError(f"Groq API error: {err_data}") from e
        raise RuntimeError(f"Groq not reachable: {e}") from e


def _is_affirmative(msg: str) -> bool:
    return bool(re.match(r"^\s*(yes|yep|yeah|yup|y|confirm|confirmed|do it|go ahead|ok|okay)\b", msg, re.I))


def _is_negative(msg: str) -> bool:
    return bool(re.match(r"^\s*(no|nope|nah|n|cancel|stop|never\s*mind|nevermind)\b", msg, re.I))


def _looks_like_no_data(text: str) -> bool:
    """True for the data layer's deterministic 'nothing found / need more info'
    messages. These should be relayed to the user as-is, never handed to the
    LLM for 'natural' phrasing — that's exactly the step where a small local
    model tends to fill the gap with fabricated specifics instead of just
    repeating "not found"."""
    t = text.strip().lower()
    no_data_prefixes = (
        "no matching classes found",
        "no classes found",
        "no timetable found",
        "no entries found",
        "no classes matching",
        "please specify",
        "i couldn't find a matching entry",
        "i'm not sure how to handle",
        "multiple entries match",
        "multiple matches",
    )
    return t.startswith(no_data_prefixes)


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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_status(self) -> dict:
        self._ollama_status = detect_ollama()
        self._groq_status = detect_groq()
        return self.get_status()

    def get_status(self) -> dict:
        if self._ollama_status is None:
            self._ollama_status = detect_ollama()
        if self._groq_status is None:
            self._groq_status = detect_groq()
            
        active_provider = "offline"
        if self.provider == "groq" and self._groq_status["available"]:
            active_provider = "groq"
        elif self.provider == "ollama" and self._ollama_status["available"]:
            active_provider = "ollama"
        elif self.provider == "auto":
            if self._ollama_status["available"]:
                active_provider = "ollama"
            elif self._groq_status["available"]:
                active_provider = "groq"
                
        return {
            "ollama": self._ollama_status,
            "groq": self._groq_status,
            "active_provider": active_provider
        }

    def is_ai_available(self) -> bool:
        return self.get_status()["active_provider"] != "offline"

    def provider_label(self) -> str:
        status = self.get_status()
        active = status["active_provider"]
        if active == "ollama":
            return f"Ollama · {self.model}"
        elif active == "groq":
            return f"Groq · {GROQ_MODEL}"
        return "Rule-based (offline)"

    def refresh_status(self):
        self._ollama_status = detect_ollama()
        self._groq_status = detect_groq()

    def chat(
        self,
        user_message: str,
        history: list[dict] | None = None,
        pending_confirmation: dict | None = None,
    ) -> tuple[str, dict | None]:
        """Process one chat turn.

        Returns (reply_text, pending_confirmation). The caller (e.g. app.py)
        must store `pending_confirmation` and pass it back on the *next* call,
        so a delete/replace can require an explicit yes/no before it happens.
        """
        # ── A confirmation is awaiting a reply — handle that first ──────────
        if pending_confirmation:
            if _is_affirmative(user_message):
                return self._execute_pending(pending_confirmation), None
            if _is_negative(user_message):
                return "Okay, cancelled — nothing was changed.", None
            reminder = (
                "I still need a yes or no on this before doing anything else:\n\n"
                f"{pending_confirmation.get('preview', 'the pending change')}"
            )
            return reminder, pending_confirmation

        if is_edit_command(user_message):
            edit_reply = handle_edit_command(self.store, user_message)
            if edit_reply is not None:
                if isinstance(edit_reply, dict):
                    return edit_reply["text"], edit_reply["pending"]
                return edit_reply, None

        status = self.get_status()
        active = status["active_provider"]

        if active != "offline":
            try:
                return self._chat_llm(user_message, history or [], active)
            except Exception as exc:
                logger.exception("Falling back to offline mode after %s error: %s", active, exc)
                fallback_text, fallback_pending = self._fallback_chat(user_message)
                note = "_I couldn't reach the AI model just now, so here's my best offline answer:_\n\n"
                return note + fallback_text, fallback_pending

        return self._fallback_chat(user_message)

    def _execute_pending(self, pending: dict) -> str:
        """Actually carry out a previously-previewed delete/replace."""
        action = pending.get("action")
        params = pending.get("params", {})
        if action == "delete":
            result = self.store.delete_class(**params)
            return format_edit_result(self.store, result, "delete")
        if action == "replace":
            result = self.store.replace_subject(**params)
            return format_edit_result(self.store, result, "replace")
        return "I lost track of what we were confirming — could you try that request again?"

    # ------------------------------------------------------------------
    # LLM two-phase chat
    # ------------------------------------------------------------------

    def _call_llm(self, messages: list[dict], provider: str, temperature: float = 0.2) -> str:
        if provider == "groq":
            return _groq_chat(messages, temperature=temperature)
        else:
            return _ollama_chat(self.model, messages, temperature=temperature)

    def _chat_llm(self, user_message: str, history: list[dict], provider: str) -> tuple[str, dict | None]:
        # ── Phase 1: extract intent + entities ──────────────────────────
        # Build dynamic system prompt with actual subject/professor data
        unique_subjects = list(set(
            re.sub(r'\s*(Tutorial|Lab).*', '', s).strip()
            for s in self.store.subjects
            if 'Batch' not in s and 'CS:' not in s
        ))
        subject_list = "Available subjects in the timetable:\n" + ", ".join(sorted(unique_subjects)[:30])
        
        system_prompt = EXTRACT_SYSTEM.format(
            subject_list=subject_list
        )
        
        extract_messages = [{"role": "system", "content": system_prompt}]
        # Provide recent history as context (last 4 turns)
        for m in history[-8:]:
            if m["role"] in ("user", "assistant"):
                extract_messages.append({"role": m["role"], "content": m["content"]})
        extract_messages.append({"role": "user", "content": user_message})

        raw = self._call_llm(extract_messages, provider, temperature=0.0)
        plan = self._parse_json_plan(raw)
        
        with open("last_plan.json", "w", encoding="utf-8") as f:
            json.dump({"raw": raw, "plan": plan}, f, indent=2)
            
        logger.info("Phase 1 plan for %r: %s", user_message, plan)
        intent = plan.get("intent", "chitchat")

        # Chitchat — just ask the model to reply directly
        if intent == "chitchat":
            return self._llm_direct(user_message, history, provider), None

        # Destructive actions require an explicit yes/no before touching data.
        if intent == "delete_class":
            return self._preview_delete_intent(plan)
        if intent == "replace_subject":
            return self._preview_replace_intent(plan)

        # ── Phase 2: fetch data ──────────────────────────────────────────
        data_text = self._execute_plan(intent, plan)
        logger.info("Phase 2 retrieved data for %r:\n%s", user_message, data_text)

        # If the data layer says "not found", still let the LLM phrase it naturally
        # so responses feel human. Only bypass for truly empty/error results.
        if data_text.strip() == "":
            return "I couldn't find anything matching that — could you rephrase or give me more details? 🤔", None

        # ── Phase 3: generate natural INTRO only ──────────────────────────
        # The LLM writes ONLY a brief intro sentence. We pass ONLY the retrieved
        # data to prevent the LLM from trying to "correct" typos in the user's prompt.
        answer_messages = [{"role": "system", "content": ANSWER_SYSTEM}]
        answer_messages.append({"role": "user", "content": (
            f"[Retrieved timetable data for this question:]\n{data_text}\n\n"
            "Write ONLY a short intro sentence. Do NOT list the data."
        )})
        raw_intro = self._call_llm(answer_messages, provider, temperature=0.3).strip()
        
        # Enforce the 1-line rule strictly: throw away any hallucinated lists
        intro = raw_intro.split("\n")[0].strip()
        
        # Combine: LLM intro + raw data (never rewritten by LLM)
        return f"{intro}\n\n{data_text}", None

    def _preview_delete_intent(self, plan: dict) -> tuple[str, dict | None]:
        """Resolve a delete_class intent to a specific entry and ask for confirmation."""
        params = {
            "entry_id": plan.get("entry_id"),
            "division": plan.get("division"),
            "day": plan.get("day"),
            "time_slot": plan.get("time_slot"),
            "subject": plan.get("subject"),
            "professor": plan.get("professor"),
            "class_type": plan.get("class_type"),
        }
        params = {k: v for k, v in params.items() if v not in (None, "")}
        preview = self.store.resolve_for_delete(**params)
        if preview["status"] == "not_found":
            return "I couldn't find a matching entry to delete. Try including a division, day, subject, or the entry ID.", None
        if preview["status"] == "ambiguous":
            text = "Multiple entries match that description — please specify an ID:\n" + \
                self.store.format_entries_with_ids(preview["matches"])
            return text, None
        e = preview["entry"]
        text = (
            f"⚠️ This will **delete** [ID {e['entry_id']}]: {e['day']} {e['time_slot']} | "
            f"{e['division']} | {e['subject']} | {e['professor']} | Room {e['room']} ({e['type']}).\n\n"
            "Reply **yes** to confirm or **no** to cancel."
        )
        pending = {"action": "delete", "params": {"entry_id": e["entry_id"]}, "preview": text}
        return text, pending

    def _preview_replace_intent(self, plan: dict) -> tuple[str, dict | None]:
        """Resolve a replace_subject intent to specific entries and ask for confirmation."""
        old_subj = plan.get("old_subject")
        new_subj = plan.get("new_subject_replace") or plan.get("new_subject")
        if not old_subj or not new_subj:
            return "Please specify both the current subject and what to replace it with.", None
        div = plan.get("division")
        day = plan.get("day")
        preview = self.store.resolve_for_replace(old_subj, new_subj, div, day)
        if preview["status"] == "not_found":
            hint = f"'{old_subj}'" + (f" in {div}" if div else "")
            return f"No classes matching {hint}.", None
        entries = preview["entries"]
        text = (
            f"⚠️ This will **replace {len(entries)} class(es)** as shown below:\n\n"
            f"{format_replace_preview(entries)}\n\n"
            "Reply **yes** to confirm or **no** to cancel."
        )
        pending = {
            "action": "replace",
            "params": {"old_subject": old_subj, "new_subject": new_subj, "division": div, "day": day},
            "preview": text,
        }
        return text, pending

    def _llm_direct(self, user_message: str, history: list[dict], provider: str) -> str:
        """For chitchat / meta questions — reply without timetable data."""
        messages = [
            {"role": "system", "content": (
                "You are a warm, friendly college timetable assistant. "
                "Chat naturally like a helpful senior student. Use casual language, "
                "be encouraging, and add a touch of personality. If someone greets you, "
                "greet them back warmly and let them know you're here to help with their timetable. "
                "Keep responses short and natural — don't be formal or robotic."
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
                plan = json.loads(m.group(0))
                for k, v in list(plan.items()):
                    if isinstance(v, str) and v.strip().lower() == "null":
                        plan[k] = None
                return plan
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
                return self.store.format_professor_schedule(
                    professor, day=day, division=div, class_type=class_type, time_slot=time_slot
                )
            records = self.store.get_professor_schedule(
                professor, day=day, division=div, class_type=class_type, time_slot=time_slot
            )
            return self.store.format_records(records, compact=True) if records else f"No classes found for '{professor}'."

        if intent == "get_division_timetable":
            if not div:
                return "Please specify a division."
            records = self.store.get_division_schedule(div)
            return self.store.format_records(records, compact=True) if records else f"No timetable found for {div}."

        if intent == "who_teaches_at":
            # If we have professor but no div/time_slot, this was misclassified — fall through to query_timetable
            if professor and (not div or not time_slot):
                records = self.store.query(
                    professor=professor, day=day, division=div,
                    class_type=class_type, time_slot=time_slot, limit=20,
                )
                if records:
                    return self.store.format_records(records, compact=True)
                return f"No classes found for '{professor}'" + (f" on {day}" if day else "") + "."
            if not div or not time_slot:
                # Try a general query with whatever we have
                records = self.store.query(
                    division=div, day=day, time_slot=time_slot,
                    professor=professor, class_type=class_type, limit=20,
                )
                if records:
                    return self.store.format_records(records, compact=True)
                return "I need a bit more info — which division and time slot are you asking about?"
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

        # Note: delete_class and replace_subject are intercepted earlier in
        # _chat_llm (via _preview_delete_intent / _preview_replace_intent) so
        # they can be confirmed before anything is changed — they never reach
        # this point.

        return "I'm not sure how to handle that request."

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    def _fallback_chat(self, user_msg: str) -> tuple[str, dict | None]:
        msg = user_msg.lower().strip()
        if not msg:
            return (
                "Ask me about your timetable or edit it directly:\n"
                "- *Find CE2 Friday labs*\n"
                "- *Add class AD1 Monday 10:00 am - 11:00 am, subject AP, professor Dr. X, room AC 301*\n"
                "- *Update id 93 room to AC 401*\n"
                "- *Delete id 113*"
            ), None

        edit_reply = handle_edit_command(self.store, user_msg)
        if edit_reply is not None:
            if isinstance(edit_reply, dict):
                return edit_reply["text"], edit_reply["pending"]
            return edit_reply, None

        div_match = re.search(r"\b(ad[123]|ce[123]|et[123]|el|it[123]|me[12])\b", msg, re.I)
        division = div_match.group(1).upper() if div_match else None
        days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
        day = next((d.capitalize() for d in days if d in msg), None)

        prof_query = _extract_professor_query(user_msg)
        if prof_query and not re.search(r"\b(add|delete|update|change|replace|find)\b", msg):
            if hasattr(self.store, "format_professor_schedule"):
                return self.store.format_professor_schedule(prof_query, day=day, division=division), None
            records = self.store.get_professor_schedule(prof_query, day=day, division=division)
            text = self.store.format_records(records, compact=True) if records else f"No classes for '{prof_query}'."
            return text, None
        time_str = _extract_time(user_msg)

        if "division" in msg and not division:
            return "Available divisions: " + ", ".join(self.store.divisions), None
        if "summary" in msg or "overview" in msg:
            return str(self.store.get_summary()), None
        if division and time_str and _asks_faculty(msg):
            return self.store.answer_faculty_at_time(division, time_str, day), None
        if division and time_str:
            records = self.store.query(division=division, day=day, time_slot=time_str, limit=10)
            text = self.store.format_records(records, compact=True) if records else f"No classes for {division} at {time_str}."
            return text, None
        class_type = _extract_class_type(user_msg)
        if division and day:
            if class_type:
                return self.store.get_filtered_schedule(division=division, day=day, class_type=class_type), None
            return self.store.get_day_overview(day, division), None
        if division and _wants_full_timetable(msg):
            return self.store.format_records(self.store.get_division_schedule(division), compact=True), None
        if division:
            return (
                f"I found division **{division}**. Try:\n"
                f"- *Who teaches {division} at 10:00 am?*\n"
                f"- *Find entries {division} Friday*\n"
                f"- *Replace {division} BET with AP*"
            ), None
        return (
            "**Commands you can use:**\n"
            "- *Find CE2 Friday labs*\n"
            "- *Add class AD1 Monday 10:00 am - 11:00 am, subject AP, professor Dr. X, room AC 301, type Theory*\n"
            "- *Update id 93 room to AC 401*\n"
            "- *Change CE2 Monday BET room to AC 502*\n"
            "- *Delete id 113*\n"
            "- *Replace CE2 BET with AP*"
        ), None
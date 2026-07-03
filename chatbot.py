"""AI chatbot with OpenAI (GPT) and Google Gemini (REST) support."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from timetable import TimetableStore
from edit_parser import handle_edit_command, is_edit_command, format_edit_result

SYSTEM_PROMPT = """You are a friendly college timetable assistant.

CRITICAL RULES:
1. Use tools to look up schedule data — never guess.
2. After receiving tool results, write a SHORT direct answer. Do NOT dump the full raw listing unless user asks for all slots/classes of someone.
3. Answer ONLY what the user asked.
4. For professor name queries, use partial names (e.g. 'Kolambe' matches 'Ms. N. D. Kolambe').
5. Only show a full weekly timetable when the user explicitly asks for "full timetable".
6. When user asks for labs/tutorials/theory/practicals, ALWAYS pass class_type filter.
7. Do NOT include Theory when user asked for Labs, or vice versa.
8. EDITING: You CAN add, update, and delete timetable entries via tools. Changes save to CSV immediately.
9. Before update/delete, use find_class if the entry is ambiguous. Confirm what changed after edits.
10. Class type field is: Theory, Lab, Tutorial, or Practical.

Divisions: AD1-3, CE1-3, ET1-3, EL, IT1-3, ME1-2."""

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "query_timetable",
        "description": "Search classes with filters. Use time_slot for a specific period.",
        "parameters": {
            "type": "object",
            "properties": {
                "division": {"type": "string"}, "day": {"type": "string"},
                "time_slot": {"type": "string"}, "subject": {"type": "string"},
                "professor": {"type": "string", "description": "Partial name ok e.g. Kolambe"},
                "class_type": {"type": "string", "enum": ["Theory", "Lab", "Tutorial", "Practical"]},
                "room": {"type": "string"}, "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "who_teaches_at",
        "description": "Faculty teaching a division at a specific time.",
        "parameters": {
            "type": "object",
            "properties": {
                "division": {"type": "string"}, "time_slot": {"type": "string"}, "day": {"type": "string"},
            },
            "required": ["division", "time_slot"],
        },
    },
    {
        "name": "get_day_schedule",
        "description": "Schedule for one day. Pass class_type when user asks for labs/tutorials/theory only.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {"type": "string"},
                "division": {"type": "string"},
                "class_type": {"type": "string", "enum": ["Theory", "Lab", "Tutorial", "Practical"]},
            },
            "required": ["day"],
        },
    },
    {
        "name": "get_filtered_schedule",
        "description": "Best for 'all labs of CE2 on Friday' — filter by division, day, class type, subject.",
        "parameters": {
            "type": "object",
            "properties": {
                "division": {"type": "string"},
                "day": {"type": "string"},
                "class_type": {"type": "string", "enum": ["Theory", "Lab", "Tutorial", "Practical"]},
                "subject": {"type": "string"},
            },
        },
    },
    {
        "name": "get_division_timetable",
        "description": "Full weekly timetable only when user wants entire week.",
        "parameters": {
            "type": "object",
            "properties": {"division": {"type": "string"}},
            "required": ["division"],
        },
    },
    {
        "name": "get_professor_schedule",
        "description": "All classes for a professor. Use for 'all slots of X' questions. Partial names ok.",
        "parameters": {
            "type": "object",
            "properties": {"professor": {"type": "string"}},
            "required": ["professor"],
        },
    },

    {
        "name": "find_class",
        "description": "Find entries with entry_id for editing/deleting. Use before update or delete if unsure.",
        "parameters": {
            "type": "object",
            "properties": {
                "division": {"type": "string"}, "day": {"type": "string"},
                "time_slot": {"type": "string"}, "subject": {"type": "string"},
                "professor": {"type": "string"}, "class_type": {"type": "string", "enum": ["Theory", "Lab", "Tutorial", "Practical"]},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "add_class",
        "description": "Add a new class to the timetable and save.",
        "parameters": {
            "type": "object",
            "properties": {
                "professor": {"type": "string"}, "day": {"type": "string"},
                "time_slot": {"type": "string"}, "division": {"type": "string"},
                "subject": {"type": "string"}, "room": {"type": "string"},
                "class_type": {"type": "string", "enum": ["Theory", "Lab", "Tutorial", "Practical"]},
            },
            "required": ["professor", "day", "time_slot", "division", "subject"],
        },
    },
    {
        "name": "update_class",
        "description": "Update an existing class. Pass entry_id OR search fields (division, day, time_slot, subject).",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "integer"},
                "division": {"type": "string"}, "day": {"type": "string"},
                "time_slot": {"type": "string"}, "subject": {"type": "string"}, "professor": {"type": "string"},
                "new_professor": {"type": "string"}, "new_day": {"type": "string"},
                "new_time_slot": {"type": "string"}, "new_division": {"type": "string"},
                "new_subject": {"type": "string"}, "new_room": {"type": "string"},
                "new_type": {"type": "string", "enum": ["Theory", "Lab", "Tutorial", "Practical"]},
            },
        },
    },
    {
        "name": "replace_subject",
        "description": "Replace all classes of one subject with another in a division e.g. replace BET with AP in CE2.",
        "parameters": {
            "type": "object",
            "properties": {
                "division": {"type": "string"},
                "old_subject": {"type": "string", "description": "Subject to replace e.g. BET"},
                "new_subject": {"type": "string", "description": "New subject e.g. AP"},
                "day": {"type": "string"},
            },
            "required": ["old_subject", "new_subject"],
        },
    },
    {
        "name": "delete_class",
        "description": "Delete a class from the timetable. Pass entry_id OR search fields to identify it.",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "integer"},
                "division": {"type": "string"}, "day": {"type": "string"},
                "time_slot": {"type": "string"}, "subject": {"type": "string"}, "professor": {"type": "string"},
            },
        },
    },
    {
        "name": "list_divisions",
        "description": "List all divisions.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_timetable_summary",
        "description": "Overview stats.",
        "parameters": {"type": "object", "properties": {}},
    },
]

OPENAI_TOOLS = [{"type": "function", "function": tool} for tool in TOOL_DEFINITIONS]
GEMINI_TOOLS = [{"functionDeclarations": TOOL_DEFINITIONS}]
SYNTHESIS_HINT = (
    "Summarize the tool results in a clear, concise answer. "
    "Do not paste raw data dumps unless the user asked for all slots/classes."
)


def detect_provider() -> str | None:
    preferred = os.getenv("LLM_PROVIDER", "auto").lower()
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    if preferred == "openai" and has_openai:
        return "openai"
    if preferred in ("gemini", "google") and has_gemini:
        return "gemini"
    if preferred == "auto":
        if has_gemini:
            return "gemini"
        if has_openai:
            return "openai"
    return None


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

def _extract_replace(msg: str):
    m = re.search(
        r"replace\s+(?:(ad[123]|ce[123]|et[123]|el|it[123]|me[12])\s+)?"
        r"(\w+)\s+(?:class(?:es)?|subject)?\s+with\s+(\w+)\s*(?:class(?:es)?|subject)?",
        msg, re.I,
    )
    if m:
        return {
            "division": m.group(1).upper() if m.group(1) else None,
            "old_subject": m.group(2),
            "new_subject": m.group(3),
        }
    m = re.search(
        r"replace\s+(\w+)\s+with\s+(\w+)\s+in\s+(ad[123]|ce[123]|et[123]|el|it[123]|me[12])",
        msg, re.I,
    )
    if m:
        return {"old_subject": m.group(1), "new_subject": m.group(2), "division": m.group(3).upper()}
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


class TimetableChatbot:
    def __init__(self, store: TimetableStore | None = None, provider: str | None = None):
        self.store = store or TimetableStore()
        self.provider = provider or detect_provider()
        self._openai_client = None

    def provider_label(self) -> str:
        if self.provider == "openai":
            return f"GPT ({os.getenv('OPENAI_MODEL', 'gpt-4o-mini')})"
        if self.provider == "gemini":
            return f"Gemini ({os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')})"
        return "Rule-based (no API key)"

    def _run_tool(self, name: str, args: dict, as_json: bool = True) -> str:
        if name == "who_teaches_at":
            text = self.store.answer_faculty_at_time(args["division"], args["time_slot"], args.get("day"))
            payload = {"answer": text, "matches": self.store.query(
                division=args["division"], day=args.get("day"), time_slot=args["time_slot"], limit=10)}
            return json.dumps(payload, default=str) if as_json else text

        if name == "query_timetable":
            records = self.store.query(
                division=args.get("division"), day=args.get("day"), time_slot=args.get("time_slot"),
                subject=args.get("subject"), professor=args.get("professor"),
                class_type=args.get("class_type"), room=args.get("room"), limit=args.get("limit", 15),
            )
            total = self.store.count(
                division=args.get("division"), day=args.get("day"), time_slot=args.get("time_slot"),
                subject=args.get("subject"), professor=args.get("professor"), class_type=args.get("class_type"),
            )
            return json.dumps({"matches": records, "total": total, "shown": len(records)}, default=str) if as_json else self.store.format_records(records, compact=True)

        if name == "get_day_schedule":
            text = self.store.get_day_overview(
                args["day"], args.get("division"), args.get("class_type"))
            return json.dumps({"schedule": text}) if as_json else text

        if name == "get_filtered_schedule":
            text = self.store.get_filtered_schedule(
                division=args.get("division"), day=args.get("day"),
                class_type=args.get("class_type"), subject=args.get("subject"))
            return json.dumps({"schedule": text}) if as_json else text

        if name == "get_division_timetable":
            records = self.store.get_division_schedule(args["division"])
            return json.dumps({"matches": records, "total": len(records)}, default=str) if as_json else self.store.format_records(records, compact=True)

        if name == "get_professor_schedule":
            prof = args["professor"]
            if hasattr(self.store, "format_professor_schedule"):
                text = self.store.format_professor_schedule(prof)
            else:
                records = self.store.get_professor_schedule(prof)
                text = self.store.format_records(records, compact=True) if records else f"No classes for {prof}."
            records = self.store.get_professor_schedule(args["professor"])
            return json.dumps({"answer": text, "matches": records, "total": len(records)}, default=str) if as_json else text


        if name == "find_class":
            records = self.store.find_entries(
                division=args.get("division"), day=args.get("day"),
                time_slot=args.get("time_slot"), subject=args.get("subject"),
                professor=args.get("professor"), class_type=args.get("class_type"),
                limit=args.get("limit", 15),
            )
            text = self.store.format_entries_with_ids(records)
            payload = {"matches": records, "total": len(records), "listing": text}
            return json.dumps(payload, default=str) if as_json else text

        if name == "add_class":
            entry = self.store.add_class(
                professor=args["professor"], day=args["day"], time_slot=args["time_slot"],
                division=args["division"], subject=args["subject"],
                room=args.get("room", ""), class_type=args.get("class_type", "Theory"),
            )
            eid = int(self.store.df["_id"].max())
            entry["entry_id"] = eid
            payload = {"success": True, "entry": entry, "entry_id": eid}
            return json.dumps(payload, default=str) if as_json else format_edit_result(self.store, payload, "add")

        if name == "update_class":
            new_fields = {k: v for k, v in args.items() if k.startswith("new_") and v is not None}
            result = self.store.update_class(
                entry_id=args.get("entry_id"), division=args.get("division"), day=args.get("day"),
                time_slot=args.get("time_slot"), subject=args.get("subject"), professor=args.get("professor"),
                **new_fields,
            )
            return json.dumps(result, default=str) if as_json else format_edit_result(self.store, result, "update")

        if name == "replace_subject":
            result = self.store.replace_subject(
                old_subject=args["old_subject"], new_subject=args["new_subject"],
                division=args.get("division"), day=args.get("day"),
            )
            if as_json:
                return json.dumps(result, default=str)
            if not result.get("success"):
                return result.get("error", "Replace failed.")
            lines = [f"Replaced **{result['count']}** class(es):"]
            for e in result.get("updated", []):
                lines.append(
                    f"- [ID {e['entry_id']}] {e['day']} {e['time_slot']} | {e['division']} | "
                    f"{e['subject']} ({e['type']})"
                )
            return "\n".join(lines)

        if name == "delete_class":
            result = self.store.delete_class(
                entry_id=args.get("entry_id"), division=args.get("division"), day=args.get("day"),
                time_slot=args.get("time_slot"), subject=args.get("subject"), professor=args.get("professor"),
            )
            return json.dumps(result, default=str) if as_json else format_edit_result(self.store, result, "delete")

        if name == "list_divisions":
            return json.dumps({"divisions": self.store.divisions}) if as_json else "Available divisions: " + ", ".join(self.store.divisions)

        if name == "get_timetable_summary":
            return json.dumps(self.store.get_summary()) if as_json else str(self.store.get_summary())

        return json.dumps({"error": f"Unknown tool: {name}"})

    def chat(self, user_message: str, history: list[dict] | None = None) -> str:
        if is_edit_command(user_message):
            edit_reply = handle_edit_command(self.store, user_message)
            if edit_reply:
                return edit_reply
        messages = list(history or [])
        messages.append({"role": "user", "content": user_message})
        try:
            if self.provider == "openai":
                return self._chat_openai(messages)
            if self.provider == "gemini":
                return self._chat_gemini_rest(messages)
        except Exception as exc:
            fallback = self._fallback_chat(user_message)
            err = str(exc)
            if fallback and not fallback.startswith("**Tip:**") and "Try:" not in fallback[-80:]:
                note = "*Gemini quota exceeded — used offline mode.*" if "429" in err or "quota" in err.lower() else f"*(AI error — offline mode: {exc})*"
                if "429" in err or "quota" in err.lower():
                    note += " Wait a few minutes, or switch to **OpenAI** in the sidebar."
                return f"{fallback}\n\n{note}"
            if "429" in err or "quota" in err.lower():
                return (
                    "**Gemini quota exceeded** (free tier limit).\n\n"
                    "Options:\n"
                    "1. Wait a few minutes and retry\n"
                    "2. Switch provider to **OpenAI** in the sidebar\n"
                    "3. Get a new key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)"
                )
            raise
        return self._fallback_chat(user_message)

    def _gemini_generate(self, api_key: str, model: str, contents: list, use_tools: bool = True) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
        }
        if use_tools:
            body["tools"] = GEMINI_TOOLS
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API error {e.code}: {detail}") from e

    def _chat_gemini_rest(self, messages: list[dict]) -> str:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("No Gemini API key set")
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        contents: list[dict] = []
        for m in messages[:-1]:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        contents.append({"role": "user", "parts": [{"text": messages[-1]["content"]}]})

        used_tools = False
        for _ in range(6):
            data = self._gemini_generate(api_key, model, contents, use_tools=True)
            candidates = data.get("candidates") or []
            if not candidates:
                raise RuntimeError(data.get("error", {}).get("message", "No response from Gemini"))
            parts = candidates[0].get("content", {}).get("parts", [])
            fn_calls = [p for p in parts if "functionCall" in p]

            if not fn_calls:
                text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
                if used_tools and (not text or self._looks_like_dump(text)):
                    contents.append({"role": "model", "parts": parts})
                    contents.append({"role": "user", "parts": [{"text": SYNTHESIS_HINT}]})
                    data = self._gemini_generate(api_key, model, contents, use_tools=False)
                    parts = data["candidates"][0]["content"]["parts"]
                    text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
                return text or "No answer found."

            used_tools = True
            contents.append({"role": "model", "parts": parts})
            fn_parts = []
            for p in fn_calls:
                fc = p["functionCall"]
                args = dict(fc.get("args") or {})
                fn_parts.append({
                    "functionResponse": {
                        "name": fc["name"],
                        "response": {"result": self._run_tool(fc["name"], args)},
                    }
                })
            contents.append({"role": "user", "parts": fn_parts})

        contents.append({"role": "user", "parts": [{"text": SYNTHESIS_HINT}]})
        data = self._gemini_generate(api_key, model, contents, use_tools=False)
        parts = data["candidates"][0]["content"]["parts"]
        return "\n".join(p.get("text", "") for p in parts if p.get("text")).strip() or "Could you rephrase that?"

    def _chat_openai(self, messages: list[dict]) -> str:
        if self._openai_client is None:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        used_tools = False
        for _ in range(6):
            response = self._openai_client.chat.completions.create(
                model=model, messages=api_messages, tools=OPENAI_TOOLS, tool_choice="auto")
            msg = response.choices[0].message
            if msg.tool_calls:
                used_tools = True
                api_messages.append(msg)
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments or "{}")
                    api_messages.append({"role": "tool", "tool_call_id": tc.id, "content": self._run_tool(tc.function.name, args)})
            else:
                text = msg.content or ""
                if used_tools and self._looks_like_dump(text):
                    return self._synthesize_openai(api_messages, model)
                return text or "I could not generate a response."
        return self._synthesize_openai(api_messages, model) if used_tools else "Could you rephrase that?"

    def _synthesize_openai(self, api_messages: list, model: str) -> str:
        api_messages.append({"role": "user", "content": SYNTHESIS_HINT})
        response = self._openai_client.chat.completions.create(model=model, messages=api_messages)
        return response.choices[0].message.content or "No answer found."

    def _looks_like_dump(self, text: str) -> bool:
        return text.count("•") + text.count("|") >= 3 or len(text) > 800

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
            return self._run_tool("list_divisions", {}, as_json=False)
        if "summary" in msg or "overview" in msg:
            return self._run_tool("get_timetable_summary", {}, as_json=False)
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
            "**Edit via chat** (no API key needed):\n"
            "- *Find CE2 Friday labs*\n"
            "- *Add class AD1 Monday 10:00 am - 11:00 am, subject AP, professor Dr. X, room AC 301, type Theory*\n"
            "- *Update id 93 room to AC 401*\n"
            "- *Change CE2 Monday BET room to AC 502*\n"
            "- *Delete id 113*\n"
            "- *Replace CE2 BET with AP*"
        )

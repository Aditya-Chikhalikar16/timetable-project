"""Parse natural-language edit commands for the timetable chatbot."""
from __future__ import annotations

import re

DIVISION_RE = r"\b(ad[123]|ce[123]|et[123]|el|it[123]|me[12])\b"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def _capday(d: str) -> str:
    return d.capitalize()


def parse_context(msg: str) -> dict:
    ctx: dict = {}
    m = re.search(DIVISION_RE, msg, re.I)
    if m:
        ctx["division"] = m.group(1).upper()
    for d in DAYS:
        if re.search(rf"\b{d}\b", msg, re.I):
            ctx["day"] = _capday(d)
            break
    tm = re.search(
        r"(\d{1,2}:?\d{0,2}\s*(?:am|pm))\s*(?:-|to)\s*(\d{1,2}:?\d{0,2}\s*(?:am|pm))",
        msg, re.I,
    )
    if tm:
        ctx["time_slot"] = f"{tm.group(1).strip()} - {tm.group(2).strip()}"
    else:
        tm = re.search(r"(\d{1,2}:?\d{0,2}\s*(?:am|pm))", msg, re.I)
        if tm:
            t = tm.group(1).strip()
            if ":" not in t:
                t = re.sub(r"(\d{1,2})\s*(am|pm)", r"\1:00 \2", t, flags=re.I)
            ctx["time_slot"] = t
    if re.search(r"\b(labs?|laboratory)\b", msg, re.I):
        ctx["class_type"] = "Lab"
    elif re.search(r"\b(tutorials?|tut)\b", msg, re.I):
        ctx["class_type"] = "Tutorial"
    elif re.search(r"\b(practicals?)\b", msg, re.I):
        ctx["class_type"] = "Practical"
    elif re.search(r"\b(theory|lectures?)\b", msg, re.I):
        ctx["class_type"] = "Theory"
    return ctx


def _field(msg: str, pattern: str) -> str | None:
    m = re.search(pattern, msg, re.I)
    return m.group(1).strip().rstrip(".,!?") if m else None


def parse_replace(msg: str) -> dict | None:
    m = re.search(
        rf"replace\s+(?:(?P<div>{DIVISION_RE})\s+)?(?P<old>\w+)\s+"
        r"(?:class(?:es)?|subject)?\s*with\s+(?P<new>\w+)\s*(?:class(?:es)?|subject)?",
        msg, re.I,
    )
    if m:
        return {
            "division": m.group("div").upper() if m.group("div") else None,
            "old_subject": m.group("old"),
            "new_subject": m.group("new"),
        }
    m = re.search(
        rf"replace\s+(?P<old>\w+)\s+with\s+(?P<new>\w+)\s+in\s+(?P<div>{DIVISION_RE})",
        msg, re.I,
    )
    if m:
        return {
            "old_subject": m.group("old"),
            "new_subject": m.group("new"),
            "division": m.group("div").upper(),
        }
    return None


def parse_add(msg: str) -> dict | None:
    if not re.search(r"\b(add|create|insert)\b", msg, re.I):
        return None
    if not re.search(r"\b(class|entry|slot|lecture|lab|tutorial|add)\b", msg, re.I):
        if not (_field(msg, r"professor\s+") and _field(msg, r"subject\s+")):
            return None
    ctx = parse_context(msg)
    professor = _field(msg, r"professor\s+([^,]+?)(?:\s*,\s*|\s+room\b|\s+subject\b|\s+type\b|$)")
    subject = _field(msg, r"subject\s+([^,]+?)(?:\s*,\s*|\s+room\b|\s+professor\b|\s+type\b|$)")
    room = _field(msg, r"room\s+([^,]+?)(?:\s*,\s*|\s+subject\b|\s+professor\b|\s+type\b|$)")
    if not professor or not subject:
        return None
    if not ctx.get("division") or not ctx.get("day") or not ctx.get("time_slot"):
        return None
    return {
        "professor": professor,
        "day": ctx["day"],
        "time_slot": ctx["time_slot"],
        "division": ctx["division"],
        "subject": subject,
        "room": room or "",
        "class_type": ctx.get("class_type", "Theory"),
    }


def parse_field_changes(msg: str) -> dict:
    changes: dict = {}
    mapping = [
        (r"\b(?:new\s+)?professor\s+to\s+([^,\n]+)", "new_professor"),
        (r"\bprofessor\s+to\s+([^,\n]+)", "new_professor"),
        (r"\broom\s+to\s+([^,\n]+)", "new_room"),
        (r"\bsubject\s+to\s+([^,\n]+)", "new_subject"),
        (r"\bdivision\s+to\s+(" + DIVISION_RE + r")", "new_division"),
        (r"\bday\s+to\s+(monday|tuesday|wednesday|thursday|friday)", "new_day"),
        (r"\b(?:time|slot)\s+to\s+([\d:apm\s\-]+)", "new_time_slot"),
        (r"\btype\s+to\s+(theory|lab|tutorial|practical)", "new_type"),
        (r"\bmove\s+to\s+(monday|tuesday|wednesday|thursday|friday)", "new_day"),
    ]
    for pat, key in mapping:
        val = _field(msg, pat)
        if val:
            if key == "new_day":
                val = _capday(val)
            if key == "new_type":
                val = val.capitalize()
            if key == "new_division":
                val = val.upper()
            changes[key] = val.strip()
    tm = re.search(
        r"move\s+to\s+(\d{1,2}:?\d{0,2}\s*(?:am|pm))\s*(?:-|to)\s*(\d{1,2}:?\d{0,2}\s*(?:am|pm))",
        msg, re.I,
    )
    if tm:
        changes["new_time_slot"] = f"{tm.group(1).strip()} - {tm.group(2).strip()}"
    return changes


def parse_update(msg: str) -> dict | None:
    if parse_replace(msg):
        return None
    if not re.search(r"\b(update|change|edit|modify|move|reschedule|set)\b", msg, re.I):
        return None
    changes = parse_field_changes(msg)
    m = re.search(r"\b(?:update|edit|change|modify)\s+(?:entry\s+)?id\s+(\d+)", msg, re.I)
    if m:
        cmd = {"entry_id": int(m.group(1))}
        cmd.update(changes)
        return cmd if changes else cmd
    m = re.search(r"\bid\s+(\d+)\b.*\b(?:to|room|professor|subject|day|time)", msg, re.I)
    if m and changes:
        return {"entry_id": int(m.group(1)), **changes}
    ctx = parse_context(msg)
    if changes and (ctx.get("division") or ctx.get("day") or ctx.get("time_slot")):
        cmd = {k: v for k, v in ctx.items() if k != "class_type"}
        subj = _field(msg, r"\b(AP|BET|FPL|M-I|EG|ICC|AC|BXT|FAI|GM|PLB|YM|CS)\b")
        if subj:
            cmd["subject"] = subj
        prof = _field(msg, r"(?:for|by)\s+([A-Z][^,\n]+)")
        if prof:
            cmd["professor"] = prof
        cmd.update(changes)
        return cmd
    if changes and "entry_id" not in changes:
        return None
    return None


def parse_delete(msg: str) -> dict | None:
    if not re.search(r"\b(delete|remove)\b", msg, re.I):
        return None
    m = re.search(r"\b(?:delete|remove)\s+(?:entry\s+)?id\s+(\d+)", msg, re.I)
    if m:
        return {"entry_id": int(m.group(1))}
    m = re.search(r"\b(?:delete|remove)\s+id\s+(\d+)", msg, re.I)
    if m:
        return {"entry_id": int(m.group(1))}
    ctx = parse_context(msg)
    cmd = {k: v for k, v in ctx.items() if k in ("division", "day", "time_slot", "class_type")}
    subj = _field(msg, r"\b(AP|BET|FPL|M-I|EG|ICC|AC|BXT|FAI|GM|PLB|YM|CS)\b")
    if subj:
        cmd["subject"] = subj
    prof = _field(msg, r"(?:for|by)\s+(Mr\.|Ms\.|Mrs\.|Dr\.)\s+[^,\n]+")
    if prof:
        cmd["professor"] = prof
    return cmd if len(cmd) >= 2 else None


def parse_find(msg: str) -> dict | None:
    if not re.search(r"\b(find|list|show)\b", msg, re.I):
        return None
    ctx = parse_context(msg)
    if re.search(r"\b(entry|entries|class|classes|id)\b", msg, re.I):
        return ctx
    if ctx.get("division"):
        return ctx
    return None


def is_edit_command(msg: str) -> bool:
    return bool(
        parse_add(msg) or parse_update(msg) or parse_delete(msg)
        or parse_replace(msg) or parse_find(msg)
        or re.search(r"\b(add|delete|remove|update|change|edit|replace|find)\b", msg, re.I)
    )


def format_edit_result(store, result: dict, action: str) -> str:
    if not result.get("success"):
        err = result.get("error", f"{action} failed.")
        if result.get("matches"):
            err += "\n\nMatching entries:\n" + store.format_entries_with_ids(result["matches"])
        return err
    if action == "add":
        e = result.get("entry", {})
        eid = result.get("entry_id") or e.get("entry_id", "?")
        return (
            f"**Added** [ID {eid}]: {e.get('day')} {e.get('time_slot')} | "
            f"{e.get('division')} | {e.get('subject')} | {e.get('professor')} | "
            f"Room {e.get('room')} ({e.get('type')})"
        )
    if action == "update":
        e = result.get("entry", {})
        return (
            f"**Updated** [ID {e['entry_id']}]: {e['day']} {e['time_slot']} | "
            f"{e['division']} | {e['subject']} | {e['professor']} | "
            f"Room {e['room']} ({e['type']})"
        )
    if action == "delete":
        d = result.get("deleted", {})
        return (
            f"**Deleted** [ID {d['entry_id']}]: {d['day']} {d['time_slot']} | "
            f"{d['division']} | {d['subject']} | {d['professor']}"
        )
    if action == "replace":
        lines = [f"**Replaced {result['count']} class(es):**"]
        for e in result.get("updated", []):
            lines.append(
                f"- [ID {e['entry_id']}] {e['day']} {e['time_slot']} | {e['division']} | "
                f"{e['subject']} ({e['type']})"
            )
        return "\n".join(lines)
    return str(result)


def handle_edit_command(store, msg: str) -> str | None:
    """Try to handle an edit command offline. Returns response or None."""
    rep = parse_replace(msg)
    if rep:
        ctx = parse_context(msg)
        if ctx.get("division") and not rep.get("division"):
            rep["division"] = ctx["division"]
        if ctx.get("day"):
            rep["day"] = ctx["day"]
        result = store.replace_subject(**rep)
        return format_edit_result(store, result, "replace")

    add = parse_add(msg)
    if add:
        entry = store.add_class(**add)
        eid = int(store.df["_id"].max())
        return format_edit_result(store, {"success": True, "entry": entry, "entry_id": eid}, "add")

    upd = parse_update(msg)
    if upd:
        changes = {k: v for k, v in upd.items() if k.startswith("new_")}
        lookup = {k: v for k, v in upd.items() if not k.startswith("new_") and k != "entry_id"}
        eid = upd.get("entry_id")
        result = store.update_class(entry_id=eid, **lookup, **changes)
        return format_edit_result(store, result, "update")

    dele = parse_delete(msg)
    if dele:
        result = store.delete_class(**dele)
        return format_edit_result(store, result, "delete")

    find = parse_find(msg)
    if find:
        records = store.find_entries(
            division=find.get("division"), day=find.get("day"),
            time_slot=find.get("time_slot"), class_type=find.get("class_type"),
            limit=20,
        )
        if records:
            return "**Entries found:**\n" + store.format_entries_with_ids(records)
        return "No entries found. Try adding division, day, or class type."

    return None

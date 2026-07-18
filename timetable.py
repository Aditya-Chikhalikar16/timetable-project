"""Timetable data layer."""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd

DATA_PATH = Path(__file__).parent / "data" / "timetable_data.csv"
DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
COLUMNS = ["professor", "day", "time_slot", "division", "subject", "room", "type"]

def _parse_clock(text: str) -> tuple[int, int] | None:
    text = text.strip().lower().replace(".", "")
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3) or ""
    if ap == "pm" and h != 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    elif not ap and h <= 7:
        h += 12
    return (h, mi)

def _slot_start(slot: str) -> tuple[int, int] | None:
    m = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)", slot.lower())
    if not m:
        return None
    return _parse_clock(f"{m.group(1)}:{m.group(2)}{m.group(3)}")

def _slot_sort_key(slot: str) -> tuple:
    start = _slot_start(slot)
    return start if start else (99, 99)

def _times_match(query_time: str, slot: str) -> bool:
    q = _parse_clock(query_time)
    s = _slot_start(slot)
    return q is not None and s is not None and q == s

class TimetableStore:
    def __init__(self, csv_path=None):
        self.csv_path = Path(csv_path) if csv_path else DATA_PATH
        self.reload()

    def reload(self):
        self.df = pd.read_csv(self.csv_path)
        for col in COLUMNS:
            if col in self.df.columns:
                self.df[col] = self.df[col].astype(str).str.strip()
        self.df["_id"] = range(len(self.df))

    def save(self):
        self.df.drop(columns=["_id"], errors="ignore").to_csv(self.csv_path, index=False)

    @property
    def divisions(self):
        return sorted(self.df["division"].unique().tolist())

    @property
    def days(self):
        present = set(self.df["day"].unique())
        return [d for d in DAYS_ORDER if d in present]

    @property
    def subjects(self):
        return sorted(self.df["subject"].unique().tolist())

    @property
    def professors(self):
        return sorted(self.df["professor"].unique().tolist())

    @property
    def types(self):
        return sorted(self.df["type"].unique().tolist())

    def find_professors(self, query: str) -> list[str]:
        """Fuzzy match e.g. 'kolambe' or 'nikita kolambe' -> Ms. N. D. Kolambe, with typo tolerance."""
        import difflib
        q_words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2 and w not in ('sir', 'mam', 'madam', 'prof', 'dr')]
        if not q_words:
            return []
        scored = []
        for prof in self.professors:
            p_words = [w for w in re.split(r"\W+", prof.lower()) if len(w) > 2 and w not in ('sir', 'mam', 'madam', 'prof', 'dr')]
            total_score = 0
            for qw in q_words:
                best_match = 0
                for pw in p_words:
                    ratio = difflib.SequenceMatcher(None, qw, pw).ratio()
                    if ratio > best_match:
                        best_match = ratio
                if best_match >= 0.7:  # Typo tolerance
                    total_score += best_match
            if total_score > 0:
                scored.append((total_score, prof))
        if not scored:
            return []
        scored.sort(key=lambda x: -x[0])
        best = scored[0][0]
        return [p for s, p in scored if s >= best - 0.1]

    def find_subjects(self, query: str) -> list[str]:
        """Fuzzy match subject names with typo tolerance."""
        import difflib
        q_words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2 and w not in ('lecture', 'lectures', 'class', 'classes', 'schedule', 'timetable')]
        if not q_words:
            return []
        scored = []
        for subj in self.subjects:
            p_words = [w for w in re.split(r"\W+", subj.lower()) if len(w) > 2]
            total_score = 0
            for qw in q_words:
                best_match = 0
                for pw in p_words:
                    ratio = difflib.SequenceMatcher(None, qw, pw).ratio()
                    if ratio > best_match:
                        best_match = ratio
                if best_match >= 0.75:
                    total_score += best_match
            if total_score > 0:
                scored.append((total_score, subj))
        if not scored:
            return []
        scored.sort(key=lambda x: -x[0])
        best = scored[0][0]
        return [p for s, p in scored if s >= best - 0.1]

    def _apply_filters(self, division=None, day=None, subject=None, professor=None,
                       class_type=None, room=None, time_slot=None):
        df = self.df.copy()
        if division:
            if division.upper() in [d.upper() for d in self.divisions]:
                df = df[df["division"].str.upper() == division.upper()]
        if day and not df.empty:
            if day.lower() in [d.lower() for d in self.days]:
                df = df[df["day"].str.lower() == day.lower()]
        if subject and not df.empty:
            skip_subject = False
            if room:
                # Heuristic 1: room="AC 501", subject="AC (Applied Chemistry)"
                room_prefix_match = re.match(r'([A-Za-z]+)', room)
                if room_prefix_match:
                    rp = room_prefix_match.group(1).lower()
                    if subject.lower().startswith(rp):
                        skip_subject = True
                
                # Heuristic 2: subject="AC", room="501"
                if re.match(r'^\d+[A-Za-z]?$', str(room).strip()):
                    if len(subject) <= 4 and re.match(r'^[A-Za-z]+$', subject.strip()):
                        room = f"{subject.strip()} {room.strip()}"
                        skip_subject = True

            if not skip_subject:
                mask = df["subject"].str.contains(re.escape(subject), case=False, na=False)
                if not mask.any():
                    names = self.find_subjects(subject)
                    if names:
                        mask = df["subject"].isin(names)
                    else:
                        mask = pd.Series([True] * len(df), index=df.index)
                df = df[mask]
        if professor and not df.empty:
            mask = df["professor"].str.contains(re.escape(professor), case=False, na=False)
            if not mask.any():
                names = self.find_professors(professor)
                if names:
                    mask = df["professor"].isin(names)
            df = df[mask]
        if class_type and not df.empty:
            ct_lower = class_type.lower()
            match_type = None
            if "lecture" in ct_lower or "theory" in ct_lower:
                match_type = "theory"
            elif "lab" in ct_lower:
                match_type = "lab"
            elif "prac" in ct_lower:
                match_type = "practical"
            elif "tut" in ct_lower:
                match_type = "tutorial"
            if match_type:
                df = df[df["type"].str.lower().str.contains(match_type, na=False)]
        if room and not df.empty:
            ignore_rooms = {"room", "class", "lecture", "hall", "lab"}
            if room.lower() not in ignore_rooms:
                norm_room = re.sub(r'[\W_]+', '', room.lower())
                if norm_room:
                    mask = df["room"].astype(str).apply(lambda x: norm_room in re.sub(r'[\W_]+', '', x.lower()))
                    df = df[mask]
        if time_slot and not df.empty:
            df = df[df["time_slot"].apply(lambda s: _times_match(time_slot, s))]
        
        if df.empty:
            return df
        return df.sort_values(["day", "time_slot", "division"])

    def query(self, division=None, day=None, subject=None, professor=None,
              class_type=None, room=None, time_slot=None, limit=50):
        df = self._apply_filters(division, day, subject, professor, class_type, room, time_slot)
        return df.head(limit).drop(columns=["_id"], errors="ignore").to_dict(orient="records")

    def count(self, division=None, day=None, subject=None, professor=None,
              class_type=None, time_slot=None):
        return len(self._apply_filters(division, day, subject, professor, class_type, time_slot=time_slot))

    def get_division_schedule(self, division, day=None):
        return self.query(division=division, day=day, limit=100)

    def get_professor_schedule(self, professor, day=None, division=None, class_type=None, time_slot=None):
        return self.query(
            professor=professor, day=day, division=division,
            class_type=class_type, time_slot=time_slot, limit=100,
        )

    def format_professor_schedule(self, professor_query: str, day=None, division=None,
                                  class_type=None, time_slot=None) -> str:
        records = self.get_professor_schedule(
            professor_query, day=day, division=division, class_type=class_type, time_slot=time_slot
        )
        scope_parts = [p for p in (day, division, class_type) if p]
        scope = f" on {' / '.join(scope_parts)}" if scope_parts else ""
        if not records:
            return f"No classes found for '{professor_query}'{scope}."
        names = self.find_professors(professor_query)
        header = names[0] if len(names) == 1 else ", ".join(names)
        lines = [f"**Schedule for {header}{scope}** ({len(records)} classes):\n"]
        for r in records:
            lines.append(
                f"- **{r['day']}** {r['time_slot']} | {r['division']} | {r['subject']} | Room {r['room']} ({r['type']})"
            )
        return "\n".join(lines)

    def get_summary(self):
        return {
            "total_classes": len(self.df),
            "divisions": self.divisions,
            "days": self.days,
            "class_types": self.types,
            "unique_subjects": len(self.subjects),
            "unique_professors": len(self.professors),
        }


    def format_schedule_grouped(self, records, title=None):
        if not records:
            return "No matching classes found."
        lines = [title] if title else []
        by_slot = {}
        for r in records:
            by_slot.setdefault(r["time_slot"], []).append(r)
        for slot in sorted(by_slot.keys(), key=_slot_sort_key):
            slot_records = by_slot[slot]
            by_subject = {}
            for r in slot_records:
                key = (r["subject"], r["type"], r["room"])
                by_subject.setdefault(key, []).append(r["professor"])
            for (subject, ctype, room), profs in by_subject.items():
                prof_list = ", ".join(dict.fromkeys(profs))
                lines.append(
                    f"\n**{slot}** — {subject} ({ctype})\n"
                    f"  Faculty: {prof_list} | Room: {room}"
                )
        return "\n".join(lines) if lines else "No matching classes found."

    def get_filtered_schedule(self, division=None, day=None, class_type=None, subject=None, professor=None):
        records = self.query(
            division=division, day=day, class_type=class_type, subject=subject, professor=professor, limit=100
        )
        parts = []
        if class_type:
            parts.append(f"{class_type}s")
        if subject:
            parts.append(subject)
        if professor:
            parts.append(professor)
        if division:
            parts.append(division)
        if day:
            parts.append(f"on {day}")
        label = " ".join(parts) or "Results"
        title = f"**{label}** ({len(records)} found):"
        return self.format_schedule_grouped(records, title=title)

    def get_day_overview(self, day, division=None, class_type=None):
        records = self.query(division=division, day=day, class_type=class_type, limit=100)
        if not records:
            label = day + (f" ({division})" if division else "")
            if class_type:
                label += f" — {class_type} only"
            return f"No classes found for {label}."
        title = f"**{day}**" + (f" ({division})" if division else "")
        if class_type:
            title += f" — {class_type} only"
        title += f" ({len(records)} classes):"
        return self.format_schedule_grouped(records, title=title)

    def format_records(self, records, compact=False):
        if not records:
            return "No matching classes found."
        if compact:
            return "\n".join(
                f"- {r['day']} {r['time_slot']}: {r['professor']} — {r['subject']} ({r['type']}, {r['room']})"
                for r in records
            )
        return "\n".join(
            f"• {r['day']} {r['time_slot']} | {r['division']} | {r['subject']} | {r['professor']} | {r['room']} | {r['type']}"
            for r in records
        )

    def answer_faculty_at_time(self, division, time_slot, day=None):
        records = self.query(division=division, day=day, time_slot=time_slot, limit=20)
        if not records:
            where = f"{division} at {time_slot}"
            if day:
                where += f" on {day}"
            return f"No classes found for {where}."
        label = f"**{division}** at **{time_slot}**"
        if day:
            label += f" on **{day}**"
        by_day: dict[str, list] = {}
        for r in records:
            by_day.setdefault(r["day"], []).append(r)
        lines = [f"Faculty teaching {label}:\n"]
        for d in sorted(by_day.keys(), key=lambda x: DAYS_ORDER.index(x) if x in DAYS_ORDER else 99):
            slot_records = by_day[d]
            slot = slot_records[0]["time_slot"]
            profs = []
            seen = set()
            for r in slot_records:
                if r["professor"] not in seen:
                    seen.add(r["professor"])
                    profs.append(f"**{r['professor']}** ({r['subject']}, {r['type']}, Room {r['room']})")
            lines.append(f"- **{d}** ({slot}): " + "; ".join(profs))
        if not day and len(by_day) > 1:
            lines.append("\n*This slot occurs on multiple days — specify a day if you need one.*")
        return "\n".join(lines)

    def pivot_grid(self, division):
        df = self._apply_filters(division=division)
        slots = sorted(df["time_slot"].unique(), key=_slot_sort_key)
        days = [d for d in self.days if d in df["day"].values]
        grid = {day: {} for day in days}
        for _, row in df.iterrows():
            grid[row["day"]][row["time_slot"]] = f"{row['subject']}\n{row['professor']}\n{row['room']}"
        result = pd.DataFrame(index=slots, columns=days)
        for day in days:
            for slot in slots:
                result.at[slot, day] = grid[day].get(slot, "")
        return result


    def find_entries(self, division=None, day=None, time_slot=None, subject=None,
                     professor=None, class_type=None, limit=20):
        df = self._apply_filters(division, day, subject, professor, class_type, time_slot=time_slot)
        out = []
        for _, row in df.head(limit).iterrows():
            rec = {k: row[k] for k in COLUMNS}
            rec["entry_id"] = int(row["_id"])
            out.append(rec)
        return out

    def format_entries_with_ids(self, records):
        if not records:
            return "No matching entries."
        lines = []
        for r in records:
            eid = r.get("entry_id", "?")
            lines.append(
                f"- [ID {eid}] {r['day']} {r['time_slot']} | {r['division']} | "
                f"{r['subject']} | {r['professor']} | {r['room']} ({r['type']})"
            )
        return "\n".join(lines)

    def add_class(self, professor, day, time_slot, division, subject, room, class_type="Theory"):
        entry = self.add_entry(
            professor=professor, day=day, time_slot=time_slot, division=division,
            subject=subject, room=room, type=class_type,
        )
        self.save()
        return entry

    def _resolve_entry_id(self, entry_id=None, division=None, day=None, time_slot=None,
                          subject=None, professor=None, class_type=None):
        if entry_id is not None:
            if not self.df[self.df["_id"] == entry_id].empty:
                return int(entry_id)
            return None
        matches = self.find_entries(division, day, time_slot, subject, professor, class_type, limit=5)
        if len(matches) == 1:
            return matches[0]["entry_id"]
        return matches

    def update_class(self, entry_id=None, division=None, day=None, time_slot=None,
                     subject=None, professor=None, **changes):
        resolved = self._resolve_entry_id(entry_id, division, day, time_slot, subject, professor)
        if isinstance(resolved, list):
            if not resolved:
                return {"success": False, "error": "No matching entry found.", "matches": []}
            return {"success": False, "error": "Multiple matches — specify entry_id or more details.",
                    "matches": resolved}
        field_map = {
            "new_professor": "professor", "new_day": "day", "new_time_slot": "time_slot",
            "new_division": "division", "new_subject": "subject", "new_room": "room",
            "new_type": "type", "professor": "professor", "day": "day", "time_slot": "time_slot",
            "division": "division", "subject": "subject", "room": "room", "type": "type",
            "class_type": "type",
        }
        updates = {}
        for k, v in changes.items():
            if v is None or v == "":
                continue
            col = field_map.get(k, k)
            if col in COLUMNS:
                updates[col] = v
        if not updates:
            return {"success": False, "error": "No fields to update."}
        if not self.update_entry(resolved, **updates):
            return {"success": False, "error": f"Entry ID {resolved} not found."}
        self.save()
        row = self.df[self.df["_id"] == resolved].iloc[0]
        entry = {c: row[c] for c in COLUMNS}
        entry["entry_id"] = int(resolved)
        return {"success": True, "entry": entry}


    def canonical_subject(self, abbrev, class_type="Theory", subject_pool=None):
        """Look up the existing full subject name for an abbreviation.

        `subject_pool` lets a caller pass a fixed snapshot of subjects to search
        (e.g. taken before a bulk update begins) instead of the live, possibly
        already-partially-mutated `self.subjects` — otherwise a multi-row
        replace can have an earlier row's new name get picked up as the
        "existing" canonical match for a later row.
        """
        ab = abbrev.upper().strip()
        ab_pattern = re.escape(ab)
        pool = self.subjects if subject_pool is None else subject_pool
        if class_type == "Tutorial":
            for s in pool:
                if s.upper().startswith(ab) and "Tutorial" in s:
                    return s
            return f"{abbrev.upper()} Tutorial" if len(abbrev) <= 4 else f"{abbrev} Tutorial"
        if class_type == "Lab":
            for s in pool:
                # Word-boundary match, not bare substring containment — otherwise
                # a short code like "CS" would match inside an unrelated word
                # like "PHYSICS" and silently rename the wrong subject.
                if re.search(rf"\b{ab_pattern}\b", s.upper()) and "Lab" in s:
                    return s
            return abbrev
        for s in pool:
            su = s.upper()
            if su.startswith(ab + " (") or su.startswith(ab + "("):
                return s
        for s in pool:
            if re.search(rf"\b{ab_pattern}\b", s.upper()) and "Lab" not in s and "Tutorial" not in s:
                return s
        return abbrev

    def _resolved_replacement_name(self, entry, old_subject, new_subject, subject_pool=None):
        """Work out the actual subject string a given entry will be renamed to."""
        if entry["type"] == "Lab":
            # Only replace the leading subject code (e.g. "AP" in "AP (Applied Physics) Lab"),
            # not any matching substring inside the description (e.g. "Ap" in "Applied").
            new_name = re.sub(
                rf"^{re.escape(old_subject)}\b", new_subject, entry["subject"], count=1, flags=re.I
            )
            if new_name == entry["subject"]:
                new_name = self.canonical_subject(new_subject, "Lab", subject_pool=subject_pool)
        elif entry["type"] == "Tutorial":
            new_name = self.canonical_subject(new_subject, "Tutorial", subject_pool=subject_pool)
        else:
            new_name = self.canonical_subject(new_subject, entry["type"], subject_pool=subject_pool)
        return new_name

    def resolve_for_replace(self, old_subject, new_subject, division=None, day=None):
        """Preview what a replace_subject call would do, without changing any data."""
        entries = self.find_entries(division=division, subject=old_subject, day=day, limit=50)
        if not entries:
            return {"status": "not_found"}
        # Snapshot subjects once so multi-row previews are all resolved against
        # the same starting state, not against each other's proposed renames.
        subject_pool = list(self.subjects)
        preview = []
        for e in entries:
            preview.append({
                **e,
                "resolved_new_subject": self._resolved_replacement_name(
                    e, old_subject, new_subject, subject_pool=subject_pool
                ),
            })
        return {"status": "ok", "entries": preview}

    def replace_subject(self, old_subject, new_subject, division=None, day=None):
        entries = self.find_entries(
            division=division, subject=old_subject, day=day, limit=50
        )
        if not entries:
            hint = f"'{old_subject}'"
            if division:
                hint += f" in {division}"
            return {"success": False, "error": f"No classes matching {hint}.", "matches": []}
        # Snapshot subjects once so a bulk replace resolves every row against the
        # same starting state — otherwise renaming row 1 could get picked up as
        # the "existing" canonical name when resolving row 2, and so on.
        subject_pool = list(self.subjects)
        updated = []
        for e in entries:
            new_name = self._resolved_replacement_name(e, old_subject, new_subject, subject_pool=subject_pool)
            result = self.update_class(entry_id=e["entry_id"], new_subject=new_name)
            if result.get("success"):
                updated.append(result["entry"])
        if not updated:
            return {"success": False, "error": "Update failed for all matches."}
        return {"success": True, "count": len(updated), "updated": updated}


    def resolve_for_delete(self, entry_id=None, division=None, day=None, time_slot=None,
                           subject=None, professor=None, class_type=None):
        """Preview what a delete_class call would remove, without changing any data."""
        resolved = self._resolve_entry_id(entry_id, division, day, time_slot, subject, professor, class_type)
        if isinstance(resolved, list):
            if not resolved:
                return {"status": "not_found"}
            return {"status": "ambiguous", "matches": resolved}
        row = self.df[self.df["_id"] == resolved]
        if row.empty:
            return {"status": "not_found"}
        entry = {c: row.iloc[0][c] for c in COLUMNS}
        entry["entry_id"] = int(resolved)
        return {"status": "ok", "entry": entry}

    def delete_class(self, entry_id=None, division=None, day=None, time_slot=None,
                     subject=None, professor=None, class_type=None):
        resolved = self._resolve_entry_id(entry_id, division, day, time_slot, subject, professor, class_type)
        if isinstance(resolved, list):
            if not resolved:
                return {"success": False, "error": "No matching entry found.", "matches": []}
            return {"success": False, "error": "Multiple matches — specify entry_id or more details.",
                    "matches": resolved}
        row = self.df[self.df["_id"] == resolved]
        if row.empty:
            return {"success": False, "error": f"Entry ID {resolved} not found."}
        deleted = {c: row.iloc[0][c] for c in COLUMNS}
        deleted["entry_id"] = int(resolved)
        if not self.delete_entry(resolved):
            return {"success": False, "error": "Delete failed."}
        self.save()
        return {"success": True, "deleted": deleted}


    def update_entry(self, entry_id, **kwargs):
        mask = self.df["_id"] == entry_id
        if not mask.any():
            return False
        for key, val in kwargs.items():
            if key in COLUMNS and val is not None:
                self.df.loc[mask, key] = str(val).strip()
        return True

    def add_entry(self, **kwargs):
        row = {col: kwargs.get(col, "") for col in COLUMNS}
        row["_id"] = int(self.df["_id"].max()) + 1 if len(self.df) else 0
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        return {k: row[k] for k in COLUMNS}

    def delete_entry(self, entry_id):
        before = len(self.df)
        self.df = self.df[self.df["_id"] != entry_id].reset_index(drop=True)
        self.df["_id"] = range(len(self.df))
        return len(self.df) < before

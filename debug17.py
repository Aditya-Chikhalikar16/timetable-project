import difflib
import re

def find_subjects(query: str, all_subjs: list[str]) -> list[str]:
    q_words = [w for w in re.split(r'\W+', query.lower()) if len(w) > 2 and w not in ('lecture', 'lectures', 'class', 'classes', 'schedule', 'timetable')]
    if not q_words:
        return []
    scored = []
    for subj in all_subjs:
        p_words = [w for w in re.split(r'\W+', subj.lower()) if len(w) > 2]
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

subjs = ["AP (Applied Physics)", "Mathematics I", "BET (Basics of Electrical Technology)", "CS:B Lab"]
print(find_subjects("Lectures by Ms. S.A Upasani Mam", subjs))

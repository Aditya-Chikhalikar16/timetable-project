import difflib
import re

def find_professors(query: str, all_profs: list[str]) -> list[str]:
    # Clean up query
    q_words = [w for w in re.split(r'\W+', query.lower()) if len(w) > 2 and w not in ('sir', 'mam', 'madam', 'prof', 'dr')]
    if not q_words:
        return []
        
    scored = []
    for prof in all_profs:
        # Clean up prof name
        p_words = [w for w in re.split(r'\W+', prof.lower()) if len(w) > 2 and w not in ('sir', 'mam', 'madam', 'prof', 'dr')]
        
        # Maximize match for each query word against any prof word
        total_score = 0
        for qw in q_words:
            best_match = 0
            for pw in p_words:
                ratio = difflib.SequenceMatcher(None, qw, pw).ratio()
                if ratio > best_match:
                    best_match = ratio
            if best_match >= 0.7:  # Typo tolerance threshold
                total_score += best_match
                
        if total_score > 0:
            scored.append((total_score, prof))
            
    if not scored:
        return []
        
    scored.sort(key=lambda x: -x[0])
    best = scored[0][0]
    return [p for s, p in scored if s >= best - 0.1]  # Return top matches within 10% of best

profs = ["Dr. K. S. Dhabekar", "Ms. S. A. Upasani", "Dr. K. N. Handore"]
print(find_professors("Upasni Mam", profs))
print(find_professors("dhabekar sir", profs))
print(find_professors("Ms. S.A Upasani mam", profs))

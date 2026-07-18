import re
professors = ["Dr. K. S. Dhabekar", "Dr. T. D. Gadekar", "Dr. D. P. Sali"]
query = "Dr.Dhabekar"
tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
scored = []
for prof in professors:
    nl = prof.lower()
    score = sum(1 for t in tokens if t in nl)
    if score > 0:
        scored.append((score, prof))
print(f"Tokens: {tokens}")
print(f"Scored: {scored}")
if scored:
    scored.sort(key=lambda x: (-x[0], x[1]))
    best = scored[0][0]
    best_profs = [p for s, p in scored if s == best]
    print(f"Best: {best_profs}")

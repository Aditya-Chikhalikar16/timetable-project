import re

subject = "AC"
room = "501"

skip_subject = False

# First heuristic: room="AC 501", subject="AC (Applied Chemistry)"
if room:
    room_prefix_match = re.match(r'([A-Za-z]+)', room)
    if room_prefix_match:
        rp = room_prefix_match.group(1).lower()
        if subject.lower().startswith(rp):
            skip_subject = True

# Second heuristic: subject="AC", room="501"
if room and subject:
    # If room is just numbers and subject is just a short prefix (e.g. AC or MB)
    if re.match(r'^\d+[A-Za-z]?$', str(room).strip()):
        if len(subject) <= 4 and re.match(r'^[A-Za-z]+$', subject.strip()):
            # Reconstruct the room
            print(f"Reconstructing room from subject '{subject}' and room '{room}'")
            room = f"{subject.strip()} {room.strip()}"
            skip_subject = True

print(f"Result: room='{room}', skip_subject={skip_subject}")

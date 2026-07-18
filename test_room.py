import re

room = "MB 207A, 207B"
rooms = [re.sub(r'[\W_]+', '', r.lower()) for r in room.split(',')]
print(rooms)

import pandas as pd
import json
import re

df = pd.read_csv('data/timetable_data.csv')

# Get all unique normalized rooms
rooms = set()
for r in df['room'].dropna().unique():
    parts = re.split(r'[,/]', str(r))
    for p in parts:
        clean = p.strip()
        if clean and clean.lower() not in ('lab', 'room', 'class'):
            norm_r = re.sub(r'[\W_]+', '', clean.lower())
            if norm_r:
                rooms.add(norm_r)

days = df['day'].dropna().unique()

print(f"Checking {len(rooms)} unique normalized rooms across {len(days)} days...")

free_rooms_by_day = {day: [] for day in days}

for day in days:
    day_df = df[df['day'] == day]
    for norm_r in rooms:
        # Check if the room appears in any class on this day
        mask = day_df['room'].astype(str).apply(lambda x: norm_r in re.sub(r'[\W_]+', '', x.lower()))
        if not mask.any():
            free_rooms_by_day[day].append(norm_r)

for day, free_rooms in free_rooms_by_day.items():
    if free_rooms:
        print(f"\nRooms completely free on {day}:")
        for r in sorted(free_rooms):
            print(f" - {r}")


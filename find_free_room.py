import pandas as pd
import json

df = pd.read_csv('data/timetable_data.csv')

# Get all unique rooms (cleaning them up a bit to avoid duplicates like 'AC 501' vs 'AC501')
rooms = set()
for r in df['room'].dropna().unique():
    # some rooms are listed as "MB 604/611 / MB 407B, MB 408B"
    # let's split by commas and slashes to get individual rooms
    import re
    parts = re.split(r'[,/]', str(r))
    for p in parts:
        clean = p.strip()
        if clean and clean.lower() not in ('lab', 'room', 'class'):
            rooms.add(clean)

days = df['day'].dropna().unique()

print(f"Checking {len(rooms)} unique rooms across {len(days)} days...")

free_rooms_by_day = {day: [] for day in days}

for day in days:
    day_df = df[df['day'] == day]
    for room in rooms:
        # Check if the room appears in any class on this day
        mask = day_df['room'].str.contains(re.escape(room), na=False, case=False)
        if not mask.any():
            free_rooms_by_day[day].append(room)

for day, free_rooms in free_rooms_by_day.items():
    if free_rooms:
        print(f"\nRooms completely free on {day}:")
        # Print first 5 to avoid spam
        for r in sorted(free_rooms)[:5]:
            print(f" - {r}")
        if len(free_rooms) > 5:
            print(f"   ... and {len(free_rooms) - 5} more")


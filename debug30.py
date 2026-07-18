from timetable import TimetableStore
store = TimetableStore()
# Simulate query with hallucinated subject from room prefix
records = store.query(day="Monday", subject="AC (Applied Chemistry)", room="AC 501")
print(f"Records found: {len(records)}")
for r in records:
    print(r)

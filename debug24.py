from timetable import TimetableStore
store = TimetableStore()
# Simulate query with new prompt extraction
records = store.query(day="Monday", room="AC 501")
print(f"Records found: {len(records)}")
for r in records:
    print(r)

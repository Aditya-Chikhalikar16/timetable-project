from timetable import TimetableStore
store = TimetableStore()
# Simulate query 3:
records = store.query(day="Monday", subject="AC", room="AC 501")
print(f"Records found: {len(records)}")
for r in records:
    print(r)

from timetable import TimetableStore
store = TimetableStore()
# Simulate query 4:
records = store.query(day="Monday", subject="AC", room="501")
print(f"Records found: {len(records)}")
for r in records:
    print(r)

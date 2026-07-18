from timetable import TimetableStore
store = TimetableStore()
records = store.query(day="Monday", subject="AC", room="501")
print(f"Records found: {len(records)}")
for r in records:
    print(r)

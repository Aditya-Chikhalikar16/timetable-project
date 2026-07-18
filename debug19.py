from timetable import TimetableStore
store = TimetableStore()
# Simulate query 2:
records = store.query(division="CE2", day="Tuesday", subject="Lectures by Ms. S.A Upasani Mam", professor="Upasani Mam")
print(f"Records found: {len(records)}")
for r in records:
    print(r)

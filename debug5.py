from timetable import TimetableStore
s = TimetableStore()
print("Handore Monday:", len(s.query(professor="Dr. K. N. Handore", day="Monday")))

from timetable import TimetableStore
s = TimetableStore()
print("Total profs:", len(s.professors))
print("First 20 profs:", s.professors[:20])
print("Is Dhabekar in first 20?", any("Dhabekar" in p for p in s.professors[:20]))

from timetable import TimetableStore
store = TimetableStore()
# Test 1: subject = 'lectures'
print("Test 1 (subject='lectures'):", len(store.query(professor="dr.dhabekar", day="monday", subject="lectures")))
# Test 2: class_type = 'lectures'
print("Test 2 (class_type='lectures'):", len(store.query(professor="dr.dhabekar", day="monday", class_type="lectures")))
# Test 3: division = 'lectures'
print("Test 3 (division='lectures'):", len(store.query(professor="dr.dhabekar", day="monday", division="lectures")))

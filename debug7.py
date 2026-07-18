from timetable import TimetableStore
store = TimetableStore()
print("Starting...")
try:
    store._apply_filters(
        division='null', day='Monday', subject='null', 
        professor='Dr. K. N. Handore', class_type='Theory', room='null', time_slot='null'
    )
    print("Done without error")
except Exception as e:
    import traceback
    traceback.print_exc()

from timetable import TimetableStore
store = TimetableStore()
df = store.df.copy()
df = df[df["room"].str.contains("null", case=False, na=False)]
print("Shape after room:", df.shape)
print("Columns:", df.columns)
df = df[df["time_slot"].apply(lambda s: False)]
print("Shape after time_slot:", df.shape)
print("Columns:", df.columns)
df.sort_values(["day", "time_slot", "division"])
print("Sort successful")

import pandas as pd
df = pd.DataFrame(columns=["day", "time_slot", "division"])
df = df[df["day"] == "Monday"]
print(df.sort_values(["day", "time_slot", "division"]))

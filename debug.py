import json
from chatbot import TimetableChatbot, EXTRACT_SYSTEM
cb = TimetableChatbot(provider="ollama")
# Replace {subject_list} and {professor_list} in EXTRACT_SYSTEM
sys_prompt = EXTRACT_SYSTEM.format(
    subject_list="Subjects: AP",
    professor_list="Professors: Dr. K. S. Dhabekar"
)

messages = [
    {"role": "system", "content": sys_prompt},
    {"role": "user", "content": "lectures by dr.dhabekar on monday"}
]
try:
    plan = cb._parse_json_plan(cb._call_llm(messages, provider="ollama", temperature=0.0))
    print(f"PLAN: {json.dumps(plan, indent=2)}")
    
    # Let's run it through _apply_filters
    df = cb.store._apply_filters(
        division=plan.get("division"),
        day=plan.get("day"),
        subject=plan.get("subject"),
        professor=plan.get("professor"),
        class_type=plan.get("class_type"),
        room=plan.get("room"),
        time_slot=plan.get("time_slot")
    )
    print(f"RESULT COUNT: {len(df)}")
    if len(df) == 0:
        print("Empty! Let's debug filters.")
        # Debug each step
        df = cb.store.df.copy()
        if plan.get("professor"):
            prof = plan["professor"]
            names = cb.store.find_professors(prof)
            print(f"Professor '{prof}' -> matched: {names}")
            
except Exception as e:
    import traceback
    traceback.print_exc()

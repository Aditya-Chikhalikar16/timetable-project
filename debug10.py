from chatbot import EXTRACT_SYSTEM, TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
sys_prompt = EXTRACT_SYSTEM.format(subject_list="AP", professor_list="Dr. K. S. Dhabekar")
try:
    plan = cb._parse_json_plan(cb._call_llm([{'role': 'system', 'content': sys_prompt}, {'role': 'user', 'content': 'lectures by dr.dhabekar on monday'}], provider='ollama', temperature=0.0))
    print(f"PLAN: {plan}")
    df = cb.store._apply_filters(
        division=plan.get("division"), day=plan.get("day"), subject=plan.get("subject"),
        professor=plan.get("professor"), class_type=plan.get("class_type"), room=plan.get("room"),
        time_slot=plan.get("time_slot")
    )
    print(f"LEN: {len(df)}")
except Exception as e:
    import traceback
    traceback.print_exc()

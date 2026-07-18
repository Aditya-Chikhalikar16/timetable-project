from timetable import TimetableStore
from chatbot import TimetableChatbot
cb = TimetableChatbot(provider='ollama')
import json
print('Starting extraction...')
sys_prompt = cb.extract_system_prompt if hasattr(cb, 'extract_system_prompt') else cb._chat_llm.__code__.co_consts[0]
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
    print(f"Error: {e}")

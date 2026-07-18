from chatbot import EXTRACT_SYSTEM, TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
sys_prompt = EXTRACT_SYSTEM.format(subject_list="AP")
history = [
    {"role": "user", "content": "lectures by dr.dhabekar on monday"},
]
try:
    plan = cb._parse_json_plan(cb._call_llm([{'role': 'system', 'content': sys_prompt}] + history, provider='ollama', temperature=0.0))
    print(f"PLAN: {plan}")
except Exception as e:
    import traceback
    traceback.print_exc()

from chatbot import TimetableChatbot, EXTRACT_SYSTEM
import json
cb = TimetableChatbot(provider='ollama')
prompt = EXTRACT_SYSTEM.format(subject_list="") + "\nIMPORTANT: Room names often start with AC or MB. Do NOT extract 'AC' or 'MB' as a subject if it is just part of a room name."
history = [
    {"role": "user", "content": "is AC 501 occupied on monday"},
]
try:
    plan = cb._parse_json_plan(cb._call_llm([{'role': 'system', 'content': prompt}] + history, provider='ollama', temperature=0.0, format_json=True))
    print(f"PLAN: {plan}")
except Exception as e:
    import traceback
    traceback.print_exc()

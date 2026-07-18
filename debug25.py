from chatbot import TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
history = [
    {"role": "user", "content": "is AC 501 occupied on monday"},
]
try:
    plan_raw = cb._call_llm(cb._build_extract_messages(history, "is AC 501 occupied on monday"), provider='ollama', temperature=0.0, format_json=True)
    plan = cb._parse_json_plan(plan_raw)
    print(f"PLAN: {plan}")
except Exception as e:
    import traceback
    traceback.print_exc()

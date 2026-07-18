from chatbot import EXTRACT_SYSTEM, TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
sys_prompt = EXTRACT_SYSTEM.format(subject_list="AP", professor_list="Dr. K. S. Dhabekar")
history = [
    {"role": "user", "content": "lectures by dr.dhabekar on monday"},
    {"role": "assistant", "content": "It seems I couldn't find any classes matching your search criteria - can you try checking another day or double-checking the spelling?\n\nNo matching classes found."},
    {"role": "user", "content": "didnt you just fixed it"},
    {"role": "assistant", "content": "My apologies! I know exactly what happened here..."},
    {"role": "user", "content": "lectures by dr.dhabekar on monday"},
    {"role": "assistant", "content": "It seems I couldn't find any classes matching your search criteria - can you try checking another day or double-checking the spelling?\n\nNo matching classes found."},
    {"role": "user", "content": "ready to accept defeat bro?lol"},
    {"role": "user", "content": "lectures by dr.dhabekar on monday"},
]
try:
    plan = cb._parse_json_plan(cb._call_llm([{'role': 'system', 'content': sys_prompt}] + history, provider='ollama', temperature=0.0))
    print(f"PLAN: {plan}")
except Exception as e:
    import traceback
    traceback.print_exc()

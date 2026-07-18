from chatbot import TimetableChatbot, EXTRACT_SYSTEM
cb = TimetableChatbot(provider='ollama')
import json

subject_list = "Available subjects in the timetable:\nAC (Applied Chemistry), AP (Applied Physics), BET (Basics of Electrical Technology)"
system_prompt = EXTRACT_SYSTEM.format(subject_list=subject_list)
messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": "is AC 501 occupied on monday"}]

raw = cb._call_llm(messages, provider='ollama', temperature=0.0, format_json=True)
print("RAW OUTPUT FROM LLM:")
print(raw)

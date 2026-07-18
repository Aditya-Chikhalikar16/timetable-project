from chatbot import TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
history = [{"role": "user", "content": "is AC 501 occupied on monday"}]
try:
    messages = cb._build_extract_messages(history, "is AC 501 occupied on monday")
    raw = cb._call_llm(messages, provider='ollama', temperature=0.0, format_json=True)
    print("RAW OUTPUT FROM LLM:")
    print(raw)
except Exception as e:
    import traceback
    traceback.print_exc()

from chatbot import TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
history = [
    {"role": "user", "content": "is AC 501 occupied on monday"},
]
try:
    resp, plan = cb._chat_llm("is AC 501 occupied on monday", history, provider='ollama')
    print(f"PLAN: {plan}")
    print(f"RESP: {resp}")
except Exception as e:
    import traceback
    traceback.print_exc()

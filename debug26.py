from chatbot import TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
history = [
    {"role": "user", "content": "is AC 501 occupied on monday"},
]
try:
    plan = cb._chat_llm("is AC 501 occupied on monday", history, provider='ollama')[1]
    print(f"PLAN: {plan}")
except Exception as e:
    import traceback
    traceback.print_exc()

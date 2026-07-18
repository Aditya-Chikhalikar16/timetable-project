from chatbot import TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
history = []
resp, plan = cb._chat_llm("Give me all the lab sessions of Gadekar Sir throughout the week", history, provider='ollama')
print("PLAN:", json.dumps(plan, indent=2))
with open("resp.txt", "w", encoding="utf-8") as f:
    f.write(resp)

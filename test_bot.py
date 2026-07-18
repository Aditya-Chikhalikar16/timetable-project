import json
from chatbot import TimetableChatbot
cb = TimetableChatbot()
messages = [
    {"role": "system", "content": cb._chat_llm.__code__.co_consts[0] if hasattr(cb._chat_llm.__code__, "co_consts") else "No sys prompt"},
    {"role": "user", "content": "lectures by dr.dhabekar on monday"}
]
res = cb._call_llm(messages, provider="ollama")
print(res)

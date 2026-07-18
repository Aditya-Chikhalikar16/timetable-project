from chatbot import TimetableChatbot
cb = TimetableChatbot(provider='ollama')
history = [{"role": "user", "content": "is AC 303 occupied on tuesday"}]
resp, plan = cb._chat_llm("is AC 303 occupied on tuesday", history, provider='ollama')
with open("resp.txt", "w", encoding="utf-8") as f:
    f.write(resp)

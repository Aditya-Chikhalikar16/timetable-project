from chatbot import TimetableChatbot
cb = TimetableChatbot(provider='ollama')
history = [{"role": "user", "content": "is AC 303 occupied on tuesday"}]
try:
    resp, plan = cb._chat_llm("is AC 303 occupied on tuesday", history, provider='ollama')
    print("PLAN:", plan)
    print("RESP:", resp.encode('utf-8').decode('utf-8'))
except Exception as e:
    import traceback
    traceback.print_exc()

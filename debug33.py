from chatbot import TimetableChatbot
cb = TimetableChatbot(provider='ollama')
history = [{"role": "user", "content": "what classroom is free on tuesday"}]
try:
    resp, plan = cb._chat_llm("what classroom is free on tuesday", history, provider='ollama')
    print("PLAN:", plan)
    print("RESP:", resp)
except Exception as e:
    import traceback
    traceback.print_exc()

from chatbot import TimetableChatbot
cb = TimetableChatbot(provider="ollama")
reply, pending = cb.chat("lectures by dr.dhabekar on monday", [])
print("REPLY:", reply)

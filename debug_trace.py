import json
import logging
from chatbot import TimetableChatbot
logging.basicConfig(level=logging.INFO)
cb = TimetableChatbot(provider="ollama")
try:
    reply, pending = cb.chat("lectures by dr.dhabekar on monday", [])
    print("REPLY:", reply)
except Exception as e:
    import traceback
    traceback.print_exc()

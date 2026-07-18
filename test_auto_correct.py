from chatbot import TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
plan = {
    "intent": "get_filtered_schedule",
    "division": "Gadekar",
    "class_type": "Lab"
}
resp = cb._execute_plan(plan["intent"], plan)
print(resp)

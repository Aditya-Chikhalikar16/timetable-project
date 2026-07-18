from chatbot import TimetableChatbot
import json
cb = TimetableChatbot(provider='ollama')
plan = {
    "intent": "get_filtered_schedule",
    "division": "Gadekar",
    "class_type": "Lab"
}
resp = cb._execute_plan(plan["intent"], plan)

# Simulate what chat_llm does with an empty result
if resp.strip() == "" or "No matching classes found" in resp:
    print("I checked the timetable, but I couldn't find any classes matching your request.")
else:
    print(resp)

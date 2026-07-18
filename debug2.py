import json
from chatbot import TimetableChatbot, EXTRACT_SYSTEM
cb = TimetableChatbot(provider="ollama")
sys_prompt = EXTRACT_SYSTEM.format(
    subject_list="Subjects: AP",
    professor_list="Professors: Dr. K. S. Dhabekar"
)

messages = [
    {"role": "system", "content": sys_prompt},
    {"role": "user", "content": "now what lectures avhad mam have on friday"},
    {"role": "assistant", "content": "**Schedule for Ms. P. T. Avhad on Friday** (1 classes):\n- Friday 12:45 pm - 13:45 pm: Ms. P. T. Avhad — AP:B Lab / EEL-1 Batch A,C (Lab, MB 601/MB 605 / MB 207B)"},
    {"role": "user", "content": "lectures by dr.dhabekar on monday"}
]
try:
    plan = cb._parse_json_plan(cb._call_llm(messages, provider="ollama", temperature=0.0))
    print(f"PLAN: {json.dumps(plan, indent=2)}")
except Exception as e:
    import traceback
    traceback.print_exc()

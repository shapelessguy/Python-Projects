import os
import json
bot_ai_path = os.path.dirname(__file__)
with open(os.path.join(bot_ai_path, 'genai.json'), 'r') as file:
    genai_token = json.load(file)['token']
import google.generativeai as genai
genai.configure(api_key=genai_token)
model = genai.GenerativeModel("gemini-2.0-flash")

chat = model.start_chat(history=[{'role': 'user', 'parts': "you tell me something"}])
response = chat.send_message('''
How does google work?
                             
''', stream=False, generation_config={"max_output_tokens": 1000}).text.strip()
print(response)
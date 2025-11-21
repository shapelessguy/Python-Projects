import os
import json
main_folder_path = os.path.dirname(__file__)
with open(os.path.join(main_folder_path, 'ds_ai.json'), 'r') as file:
    genai_token = json.load(file)['token']
from openai import OpenAI
# import google.generativeai as genai

# genai.configure(api_key=genai_token)

# model = genai.GenerativeModel("gemini-2.0-flash")
# chat = model.start_chat(
#     history=[
#         {"role": "user", "parts": "Hello"},
#         {"role": "model", "parts": "Great to meet you. What would you like to know?"},
#     ]
# )
# response = chat.send_message("I have 2 dogs in my house.", stream=False)
# print("||", response.text.strip(), "||")
# # response = chat.send_message("How many paws are in my house?")
# # print(response.text)
# # response = model.generate_content("Write a story about a magic backpack in 3 sentences.", stream=True)
# # for chunk in response:
# #     sys.stdout.write(repr(chunk.text))


client = OpenAI(api_key=genai_token, base_url="https://api.deepseek.com")

stream = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello, tell me something unusual"},
    ],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)

print("\n--- Done ---")

stream = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello, tell me something unusual"},
    ],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)

print("\n--- Done ---")
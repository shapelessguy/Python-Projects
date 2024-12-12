import google.generativeai as genai
import os
import sys
genai.configure(api_key='AIzaSyCsziciA-yFtNlSMbCdqfy87nDJ8ozNO74')

model = genai.GenerativeModel("gemini-1.5-flash")
chat = model.start_chat(
    history=[
        {"role": "user", "parts": "Hello"},
        {"role": "model", "parts": "Great to meet you. What would you like to know?"},
    ],
    generation_config=genai.types.GenerationConfig(
        candidate_count=1,
        stop_sequences=["x"],
        max_output_tokens=20,
        temperature=1.0,
    ),
)
response = chat.send_message("I have 2 dogs in my house.", stream=True)
for chunk in response:
    sys.stdout.write(chunk.text)
# response = chat.send_message("How many paws are in my house?")
# print(response.text)
# response = model.generate_content("Write a story about a magic backpack in 3 sentences.", stream=True)
# for chunk in response:
#     sys.stdout.write(repr(chunk.text))
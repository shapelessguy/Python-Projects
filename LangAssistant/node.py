import os
import json
import time
from message import Message
main_folder_path = os.path.dirname(__file__)
with open(os.path.join(main_folder_path, 'ds_ai.json'), 'r') as file:
    genai_token = json.load(file)['token']
from openai import OpenAI


NATIVE_LANGUAGE = "English"
TARGET_LANGUAGE = "German"
TARGET_LEVEL = "B1"


class Node:
    id: str = ""
    system_prompt: str = ""
    accept_kw: str = ""
    connected_nodes: list = []

    def __init__(self):
        pass

    def start_processing(self, input: Message):
        # print("Processing node: ", self.__class__.__name__)
        output = self.__process(input)
        if len(self.connected_nodes) == 1:
            return self.connected_nodes[0]().start_processing(output)
        elif len(self.connected_nodes) > 1:
            for n in self.connected_nodes:
                if n().accept_kw == output.query:
                    return n().start_processing(output)
        else:
            return output
    
    def preprocess(self, input: Message):
        return input
    
    def process(self, input: Message):
        return input
    
    def postprocess(self, output: Message):
        return output
    
    def __process(self, input: Message):
        input = self.preprocess(input)
        output = self.process(input)
        return self.postprocess(output)

    def askLLM(self, messages):
        client = OpenAI(api_key=genai_token, base_url="https://api.deepseek.com")
        stream = client.chat.completions.create(
            model="deepseek-chat",
            messages = messages,
            stream=True
        )

        final = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                final += chunk.choices[0].delta.content
        return final

    def getNextAgent(self, system_prompt, connected_nodes):
        next_hops_txt = "\n".join([f"{n().accept_kw}: {n().description}" for n in connected_nodes])
        system_prompt = system_prompt.replace(f"%%ACCEPTABLE_KW%%", next_hops_txt)
        if len(connected_nodes) > 1:
            acceptable_kw = [n().accept_kw for n in connected_nodes]
            system_prompt += f"Remember, you can answer with just one of these keyword: {acceptable_kw}"

        client = OpenAI(api_key=genai_token, base_url="https://api.deepseek.com")
        stream = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system_prompt}],
            stream=True
        )

        final = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                final += chunk.choices[0].delta.content
        return final

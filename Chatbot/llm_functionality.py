import re
import time
import requests
import pyttsx3


class State:

    def __init__(self) -> None:
        self.is_waiting = False
        self.is_speaking = False
    
    def set_waiting(self, waiting):
        if self.is_waiting and not waiting:
            self.send('END_WAITING')
            print('End waiting.')
        elif not self.is_waiting and waiting:
            self.send('START_WAITING')
            print('Start waiting.')
        self.is_waiting = waiting

    def set_speaking(self, speaking):
        if self.is_speaking and not speaking:
            self.send('END_SPEAKING')
            print('End speaking.')
        elif not self.is_speaking and speaking:
            self.send('START_SPEAKING')
            print('Start speaking.')
        self.is_speaking = speaking
    
    def speak(self, audio):
        short_aknowledgement = audio.lower() in ['ok', 'ok.']

        if not short_aknowledgement:
            self.set_speaking(True)

        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        engine.setProperty('voice', voices[2].id)
        engine.say(audio)
        engine.runAndWait()

        if not short_aknowledgement:
            self.set_speaking(False)

    def send(self, command):
        url = "http://localhost:8080/"
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        requests.post(url, data=command, headers=headers)


class LLM:

    def __init__(self, state) -> None:
        self.state = state

        from dotenv import dotenv_values
        from openai import OpenAI
        self.client = OpenAI(api_key=dotenv_values(".env")['OPENAI_KEY'])
        self.system_prompt = None
        with open('prompts.txt', 'r', encoding='utf-8') as file:
            prompts = file.read().split('------------------------------------------')
            for prompt in prompts:
                split_prompt = prompt.split('\n')
                header = split_prompt[0]
                body = '\n'.join(split_prompt[1:])
                if header == 'SYSTEM_PROMPT':
                    self.system_prompt = body
    
    def process_text(self, text):
        print(f'SENT: {text}')
        completion = self.client.chat.completions.create(
            model="gpt-3.5-turbo-0125",
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": text}
            ]
        )
        reply = completion.choices[0].message.content
        commands = re.findall(r'\|([^|]+)\|', reply)
        if len(commands) > 0:
            for i in range(len(commands)):
                command = commands[i]
                print(f'COMMAND {command}')
                if self.state is not None:
                    self.state.send(command)
                if i < len(commands) - 1:
                    time.sleep(0.6)
        else:
            print(f'REPLY: {reply}')
            if self.state is not None:
                self.state.speak(reply)


if __name__ == '__main__':
    llm = LLM(None)
    llm.process_text('turn on the TV and turn off the UV lights also')

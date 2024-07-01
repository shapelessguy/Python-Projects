import copy
import datetime
import multiprocessing
import os
import re
import time
import traceback
import requests
import pyttsx3

main_folder = os.path.dirname(__file__)


class SpeechManager:
    def __init__(self):
        self.proc = None

    def speaking(self, audio_text):
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        if len(voices) > 2:
            engine.setProperty('voice', voices[2].id)
        engine.say(audio_text)
        engine.runAndWait()

    def start_speaking(self, audio_text, timeout=None):
        self.proc = multiprocessing.Process(target=self.speaking, args=(audio_text,))
        self.proc.start()
        self.proc.join(timeout)

    def stop_speaking(self):
        if self.proc and self.proc.is_alive():
            self.proc.terminate()
            self.proc.join()
            print("Speech process terminated on demand.")


class State:

    def __init__(self, speech_manager: SpeechManager) -> None:
        self.is_waiting = False
        self.is_thinking = False
        self.is_speaking = False
        self.speech_manager = speech_manager
    
    def set_waiting(self, waiting):
        if self.is_waiting and not waiting:
            self.send('END_WAITING')
            print('End waiting.')
        elif not self.is_waiting and waiting:
            self.send('START_WAITING')
            print('Start waiting.')
        self.is_waiting = waiting
    
    def set_thinking(self, thinking):
        if self.is_thinking and not thinking:
            self.send('END_THINKING')
            print('End thinking.')
        elif not self.is_thinking and thinking:
            self.send('START_THINKING')
            print('Start thinking.')
        self.is_thinking = thinking

    def set_speaking(self, speaking):
        if self.is_speaking and not speaking:
            self.send('END_SPEAKING')
            print('End speaking.')
        elif not self.is_speaking and speaking:
            self.send('START_SPEAKING')
            print('Start speaking.')
        self.is_speaking = speaking

    def set_error(self, error):
        if error:
            self.send('START_ERROR')
            print('Starting error.')
        else:
            self.send('END_ERROR')
            print('Ending error.')
    
    def speak(self, audio_text):
        short_aknowledgement = audio_text.lower().strip() in ['ok', 'ok.']

        self.set_speaking(True)
        if short_aknowledgement:
            time.sleep(1)
        
        self.speech_manager.start_speaking(audio_text, timeout=60)
        self.speech_manager.stop_speaking()

        self.set_speaking(False)

    def send(self, command):
        try:
            url = "http://localhost:8080/"
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            requests.post(url, data=command, headers=headers, timeout=0.3)
        except:
            print('Issue while sending data to CyanSystemManager')


def get_reply(llm, model: str, messages_, new_chat=True):
    messages = copy.deepcopy(messages_)
    try:
        for msg in messages:
            msg['content'] = msg['content'].replace('{{time}}', datetime.datetime.now().strftime("%d-%m-%yT%H:%M:00"))
        if model == Model.Gemini:
            if new_chat:
                chat = llm.google_client.start_chat()
                text = f'These are the specifications of your role: {messages[0]["content"]}.\n CHAT STARTED.\n\n'
                for msg in messages[1:]:
                    text += f'{msg["role"]}: {msg["content"]}\n'
            else:
                text = f'{messages[-1]["role"]}: {messages[-1]["content"]}\n'

            text_response = []
            responses = chat.send_message(text, stream=True)
            for chunk in responses:
                text_response.append(chunk.text)
            reply = "".join(text_response)
        else:
            completion = llm.openai_client.chat.completions.create(model=model, messages=messages)
            reply = completion.choices[0].message.content
        return reply
    except:
        print('Exception during response generation.')
    return ""


class Model:
    ChatGPT3 = 'gpt-3.5-turbo-0125'
    ChatGPT4 = 'gpt-4-0613'
    Gemini = 'gemini-1'

class Expert:
    def __init__(self, llm, model) -> None:
        print(f'Start chatting with {self.__class__.__name__}')
        self.system_prompt = llm.all_prompts[self.__class__.__name__]
        self.model = model
        self.llm = llm

    def chat(self, history):
        pass

class CalendarExpert(Expert):
    def __init__(self, llm, model) -> None:
        super().__init__(llm, model)
    
    def chat(self, history):
        history[0] = {"role": "system", "content": self.system_prompt}
        if self.llm.state is not None:
            self.llm.state.set_thinking(True)
        reply = get_reply(self.llm, self.model, history)
        if self.llm.state is not None:
            self.llm.state.set_thinking(True)
            
        print('Reply:', reply)
        
        if self.llm.state is not None:
            self.llm.state.speak(reply)


class LLM:

    def __init__(self, state: State) -> None:
        self.state = state

        from dotenv import dotenv_values
        from openai import OpenAI
        self.openai_client = OpenAI(api_key=dotenv_values(os.path.join(main_folder, '.env'))['OPENAI_KEY'])

        import vertexai
        from vertexai.generative_models import GenerativeModel, ChatSession
        vertexai.init(project="ip-manager42", location="us-central1")
        self.google_client = GenerativeModel("gemini-1.0-pro")
        
        self.all_prompts = {}
        with open(os.path.join(main_folder, 'prompts.txt'), 'r', encoding='utf-8') as file:
            prompts = file.read().split('------------------------------------------\n')
            for prompt in prompts:
                split_prompt = prompt.split('\n')
                header = split_prompt[0]
                body = '\n'.join(split_prompt[1:])
                self.all_prompts[header] = body
    
    def process_text(self, text, model):
        print(f'SENT: {text}')
        messages=[
            {"role": "system", "content": self.all_prompts['SYSTEM_PROMPT']},
            {"role": "user", "content": text}
        ]
        
        reply = get_reply(self, model, messages)
        commands = re.findall(r'\|([^|]+)\|', reply)
        return reply, commands, messages, model
    
    def take_action(self, reply, commands, messages, model):
        if len(commands) > 0:
            for i in range(len(commands)):
                command = commands[i]
                print(f'COMMAND {command}')
                if self.state is not None:
                    self.state.send(command)
                if command == 'CALENDAR':
                    self.new_session(expert=CalendarExpert(self, model), history=messages)
                if i < len(commands) - 1:
                    time.sleep(0.6)
        else:
            print(f'REPLY: {reply}')
            if self.state is not None:
                self.state.speak(reply)
    
    def new_session(self, expert: Expert, history: list[dict]):
        expert.chat(history)


if __name__ == '__main__':
    llm = LLM(None)
    reply, commands, _, _ = llm.process_text('turn on the TV and then turn off the UV lights.', Model.Gemini)

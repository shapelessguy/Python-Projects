from node import Node, NATIVE_LANGUAGE, TARGET_LANGUAGE
from agents.output import Output
from message import Message

STYLE: str = '''
Reply in few lines, don't be logorroic!
'''

SYSTEM_PROMPT: str = f'''
You are a general purpose agent used by the user to help him learning {TARGET_LANGUAGE}.
Native language of the user is {NATIVE_LANGUAGE} so, generally explain things in {NATIVE_LANGUAGE}.
In the chat above you will see the previous exchanges between the user and the previous agents he interacted with, you included.
Based on the chat, reply to the user accordingly.
The functionalities of the system you are part of are:
- translating sentences from {NATIVE_LANGUAGE} to {TARGET_LANGUAGE};
- translating sentences from {TARGET_LANGUAGE} to {NATIVE_LANGUAGE};
- translating words from {NATIVE_LANGUAGE} to {TARGET_LANGUAGE};
- reply generic questions regarding the language.
{STYLE}
'''

class GeneralQuestion(Node):
    system_prompt = SYSTEM_PROMPT
    accept_kw = "general_question"
    description = "This agent is used to answer questions that are unrelated."
    connected_nodes = [Output]

    def process(self, input: Message):
        messages=[
            {"role": "system", "content": self.system_prompt},
            *input.history.get_list()
        ]
        output_text = self.askLLM(messages)
        return Message(output_text, intent=GeneralQuestion, from_="assistant", history=input.history)
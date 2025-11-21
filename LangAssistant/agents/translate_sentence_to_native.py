from node import Node, NATIVE_LANGUAGE, TARGET_LANGUAGE, TARGET_LEVEL
from agents.error_logger import ErrorLogger
from message import Message

STYLE: str = '''
While proposing a new sentence, don't lose too much time in being polite or anything. Be as quick as possible.
'''

SYSTEM_PROMPT: str = f'''
You are an agent that proposes sentences in {TARGET_LANGUAGE} and the user has to translate them in {NATIVE_LANGUAGE}.
In the chat above you will see the previous exchanges between the user and the previous agents he interacted with, you included.
Based on the chat, realize if you have to invent a new sentence that the user will have to translate, or if you have to answer (and then propose a new sentence).
The language level of the user is {TARGET_LEVEL}.
{STYLE}
'''

class TranslateSentenceToNative(Node):
    system_prompt = SYSTEM_PROMPT
    accept_kw = "translate_sentence_to_native"
    description = "This agent is used to create exercises regarding sentence translations. " \
        f"The virtual assistant proposes a sentence in {TARGET_LANGUAGE} and the user has to translate into {NATIVE_LANGUAGE}."
    connected_nodes = [ErrorLogger]

    def process(self, input: Message):
        messages=[
            {"role": "system", "content": self.system_prompt},
            *input.history.get_list(last=4)
        ]
        output_text = self.askLLM(messages)
        return Message(output_text, intent=TranslateSentenceToNative, from_="assistant", history=input.history)

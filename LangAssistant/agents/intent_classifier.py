from node import Node
from message import Message
from agents.translate_sentence_from_native import TranslateSentenceFromNative
from agents.translate_sentence_to_native import TranslateSentenceToNative
from agents.translate_word_from_native import TranslateWordFromNative
from agents.translate_word_to_native import TranslateWordToNative
from agents.general_question import GeneralQuestion

SYSTEM_PROMPT: str = f'''
You are an agent that indicates which indicates the intent of the following prompt from the user:
------------------
%%PROMPT%%
------------------

Based on this prompt, answer using ONLY one word, indicating if the intent of the user is one of the above intents:
%%ACCEPTABLE_KW%%

Take also into consideration that previously, the intent of the user was "%%PREVIOUS_INTENT%%"
Last messages:
%%LAST_MESSAGES%%
'''

class IntentClassifier(Node):
    system_prompt = SYSTEM_PROMPT
    accept_kw = ""
    description = ""
    connected_nodes = [TranslateSentenceFromNative, TranslateSentenceToNative, TranslateWordFromNative, TranslateWordToNative, GeneralQuestion]

    def process(self, input: Message):
        valid = False
        system_prompt = self.system_prompt.replace(f"%%PROMPT%%", input.query).replace(f"%%PREVIOUS_INTENT%%", input.intent().accept_kw)
        last_msg_txt = "\n".join([f"From {m.from_}: {m.query}" for m in input.history if not m.hidden][-4:])
        system_prompt = system_prompt.replace(f"%%LAST_MESSAGES%%", last_msg_txt)
        while not valid:
            output_text = self.getNextAgent(system_prompt, self.connected_nodes)
            print("----------------------------->", output_text)
            for n in self.connected_nodes:
                if output_text.startswith(n().accept_kw):
                    valid = True
                    intent = n

        return Message(output_text, intent=intent, from_="assistant", history=input.history, hidden=True)

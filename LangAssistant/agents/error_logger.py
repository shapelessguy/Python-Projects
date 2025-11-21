from node import Node
from message import Message
from agents.output import Output

STYLE: str = '''
The way you log them is by returning in the reply a list of errors in the following format {"intended_word": "error_type"}.
For example if the user had to translate "The boy has a big skateboard" into
"Il ragazzo ha un grande skateboard" but the translation was "La bambino aveva un grande scateboard",
you have to report the following message:
------ Start message
{"la": "declination"}
{"ragazzo": "meaning"}
{"ha": "conjucation"}
{"skateboard": "spelling"}
------ End message
Your reply will be parsed and stored, therefore always respect the simple format. Signal ONLY the obvious errors! Only 1 error if possible, maximum 2 if really necessary.
'''

SYSTEM_PROMPT: str = f'''
You are an error logger agent. Your role is to look into the last message between user and assistant, assess which type of errors the user made.
error_types are the following [meaning, declination, conjucation, spelling].
{STYLE}
'''

class ErrorLogger(Node):
    system_prompt = SYSTEM_PROMPT
    accept_kw = ""
    connected_nodes = [Output]

    def process(self, input: Message):
        messages=[
            {"role": "system", "content": self.system_prompt},
            *input.history.get_list(last=2)
        ]
        wrong = False
        if wrong:
            output_text = self.askLLM(messages)
            errors = output_text.split("\n")
            for er in errors:
                print("            Err -> ", er)
        return input

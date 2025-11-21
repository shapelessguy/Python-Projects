import os
import inspect
import importlib
from pathlib import Path
from message import Message, History
from agents.general_question import GeneralQuestion
from agents.translate_sentence_to_native import TranslateSentenceToNative

package_name = "agents"
package_path = Path(os.path.dirname(__file__)).joinpath("agents")

agents = {}

for filename in os.listdir(package_path):
    if filename.endswith(".py") and filename != "__init__.py":
        module_name = f"{package_name}.{filename[:-3]}"
        module = importlib.import_module(module_name)
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module_name:
                agents[name] = obj


input_agent = agents["Input"]()
history = History()
messages = [
    Message(query="Hi!", intent=GeneralQuestion, from_="user", history=history),
    Message(query="Hi! I'm here to help you learn your favourite language. What would you like to do today?", intent=GeneralQuestion, from_="assistant", history=history)
]

first_msg = "Let's start with sentence translation to English, shall we?"
while True:
    if not first_msg:
        user_request = input("")
    else:
        user_request = first_msg
        first_msg = ""
    message = Message(query=user_request, intent=messages[-1].intent, from_="user", history=messages[-1].history)
    output = input_agent.start_processing(message)
    print(output.query)

from node import Node
from message import Message
from agents.intent_classifier import IntentClassifier

class Input(Node):
    system_prompt = ""
    accept_kw = ""
    connected_nodes = [IntentClassifier]

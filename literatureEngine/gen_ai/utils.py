import os
import re
import tiktoken
import hashlib


MODELS_PATH = os.path.join(os.path.dirname(__file__), "models")
CACHE_FOLDER_PATH = os.path.join(os.path.dirname(__file__), "cache")


def query_to_hash(query: str, algo="sha1", length=24):
    h = hashlib.new(algo)
    h.update(query.encode("utf-8"))
    return h.hexdigest()[:length]


def count_tokens(text):
    encoder = tiktoken.get_encoding("cl100k_base")
    if len(text) < 1000:
        return len(encoder.encode(text))
    else:
        return int(len(text) / 4)


def construct_prompt(prompt_structure, request_content):
    pattern = r'{{(.*?)}}'
    matches = re.findall(pattern, prompt_structure)
    variables = {}
    for x in matches:
        value = request_content["profile"]
        for k in x.split("."):
            value = value.get(k, None) if type(value) is dict else None
            if value is None:
                break
        variables[x] = "" if value is None else value
    
    prompt = prompt_structure
    for k, v in variables.items():
        prompt = prompt.replace("{{" + k + "}}", str(v))
    return prompt

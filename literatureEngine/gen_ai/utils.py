import os
import tiktoken
import hashlib


MODELS_PATH = os.path.join(os.path.dirname(__file__), "models")


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

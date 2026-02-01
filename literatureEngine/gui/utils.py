import traceback
import difflib
import re
import hashlib
import unicodedata
from utils import pprint


class OpClass:
    def __init__(self):
        pass

    def start(self, signal, args):
        # Executed by a worker thread
        pass

    def end(self, signal, args):
        # Executed by the main thread
        pass


class Operation:
    def __init__(self, signal, op_class: OpClass, args: dict):
        self.signal = signal
        self.op_class = op_class()
        self.op_class_name = op_class.__name__
        self.args = args
    
    def start(self):
        try:
            self.op_class.start(self.signal, self.args)
        except:
            pprint(traceback.format_exc())
    
    def end(self):
        try:
            self.op_class.end(self.signal, self.args)
        except:
            pprint(traceback.format_exc())


def matching_string(string: str, collection: list[str]):
    result = None
    matches = difflib.get_close_matches(string, collection, n=1, cutoff=0.8)
    if len(matches):
        result = matches[0]
    return result


def query_to_hash(query: str, algo="sha1", length=12):
    h = hashlib.new(algo)
    h.update(query.encode("utf-8"))
    return h.hexdigest()[:length]


def normalize_name(name: str, max_length: int = 150):
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'[^\w\s.-]', '_', name)
    name = re.sub(r'[\s_]+', '_', name)
    name = name.strip('._')
    if max_length and len(name) > max_length:
        name = name[:max_length].rstrip('._')
    return name


def create_paper_id(title, doi, year):
    return query_to_hash(normalize_name(title) + doi + str(year))

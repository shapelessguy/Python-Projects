
class History(list):
    def __init__(self):
        pass

    def get_list(self, last=None):
        out = []
        for m in self:
            if not m.hidden:
                out.append({"role": m.from_, "content": m.query})
        if last:
            out = out[-last:]
        return out


class Message:
    query: str = ""
    intent = None
    from_ = ""
    history = []
    hidden = False

    def __init__(self, query: str, intent, from_: str, history: History, hidden: bool = False):
        self.query = query
        self.intent = intent
        self.from_ = from_
        self.history = history
        self.hidden = hidden
        history.append(self)

    def __str__(self):
        result = f"Query: {self.query}\nIntent: {self.intent}"
        return result
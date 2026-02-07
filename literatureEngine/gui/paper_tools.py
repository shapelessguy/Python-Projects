

class References(list):

    def __init__(self, signal):
        self.signal = signal
        self.extend([x["_id"] for x in signal.mongo.fetch_refs_by_context(signal.cur_review, signal.cur_context, ["_id"])])
        self.view = []
    
    def get_attributes(self, attributes: list[str]):
        ui_manager = self.signal.ui_manager
        raw_papers = ui_manager.signal.mongo.fetch_ref_by_ids(ui_manager.signal.cur_review, self.view, attributes)
        return raw_papers

    def apply_filters(self, filter_functs: list):
        self.view = []
        for v in self:
            include_ = True
            for f in filter_functs:
                if not f(v):
                    include_ = False
                    break
            if include_:
                self.view.append(v)
    
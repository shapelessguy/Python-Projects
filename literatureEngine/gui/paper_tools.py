

attr_functions = [
    {"name": "title", "attribute": "title", "default": ""},
    {"name": "year", "attribute": "year", "default": 0},
    {"name": "abstract", "attribute": "abstract", "default": ""},
]


def make_accessor(self, attribute, default):
    def accessor(default=default):
        self.__required_attr__.add(attribute)
        return self.attributes.get(attribute, default)
    return accessor


class Paper:
    __required_attr__ = set()

    def __init__(self, ref_id, attributes={}):
        self.ref_id = ref_id
        self.attributes = attributes
        if len(self.attributes):
            self.setup()
    
    def setup(self):
        for function in attr_functions:
            setattr(self, function["name"], make_accessor(self, function["attribute"], function["default"]))

    
def are_valid_formulas(formulas: list[str]):
    dummy_paper = Paper("dummy")
    dummy_paper.setup()
    for f in formulas:
        try:
            exec(f, {"paper": dummy_paper})
        except Exception as e:
            print(f"Bad formula: {f}\n{e}")
            return False
    return True


class References(list):

    def __init__(self, signal):
        self.signal = signal
        self.extend([Paper(x["_id"]) for x in signal.mongo.fetch_refs_by_context(signal.cur_review, signal.cur_context, ["_id"])])
        self.view = []
        self.last_filters = []
    
    def get_attributes(self, attributes: list[str]):
        ui_manager = self.signal.ui_manager
        raw_papers = ui_manager.signal.mongo.fetch_ref_by_ids(ui_manager.signal.cur_review, [x.ref_id for x in self.view], attributes)
        return raw_papers
        

    def apply_filters(self, filters: list = None):
        if filters is None:
            filters = self.last_filters
        dummy_paper = Paper("dummy")
        dummy_paper.setup()
        dummy_paper.__required_attr__ = set()

        # filters.append({"formula": "'LLM' in paper.abstract()"})
        for f in filters:
            formula = f["formula"]
            try:
                exec(formula, {"paper": dummy_paper})
            except Exception as e:
                continue

        attributes_to_compute = dummy_paper.__required_attr__
        attributes_to_compute.add("_id")
        collection = [Paper(x["_id"], x) for x in self.signal.mongo.fetch_refs_by_context(self.signal.cur_review, self.signal.cur_context, attributes_to_compute)]
            
        self.view = []
        for v in collection:
            include_ = True
            for f in filters:
                formula = f["formula"]
                try:
                    if not eval(formula, {"paper": v}):
                        include_ = False
                        break
                except Exception as e:
                    include_ = False
                    break
            if include_:
                v.attributes = {}
                self.view.append(v)
        self.last_filters = filters
    
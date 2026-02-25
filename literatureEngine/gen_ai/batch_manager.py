import os
import time
import threading
import requests
import inspect
import importlib
import json
from pathlib import Path
from gen_ai.model import Model
from datetime import datetime, timezone
from pymongo import MongoClient, errors
from pymongo.errors import DuplicateKeyError
from bson.objectid import ObjectId
from gen_ai.model import JobStatus, ErrorMsg, ErrorType
from gen_ai.utils import count_tokens, query_to_hash, MODELS_PATH
CONTENT_TAG = "__X__"


class Directives:
    def __init__(self, request, to_be_computed, to_be_copied, to_be_updated, to_be_dropped):
        self.request = request
        self.to_be_computed = to_be_computed
        self.to_be_copied = to_be_copied
        self.to_be_updated = to_be_updated
        self.to_be_dropped = to_be_dropped
        self.to_be_computed_tokens = self.get_input_tokens_count(self.to_be_computed)
        self.to_be_updated_tokens = self.get_input_tokens_count(self.to_be_updated)
        self.pricing = request.model.pricing
    
    def get_input_tokens_count(self, req_ids: set[str]):
        input_tokens_count = 0
        for content in self.request.contents:
            if content["request"]["request_id"] in req_ids:
                input_tokens_count += count_tokens(self.request.prompt_structure.replace(CONTENT_TAG, content["request"]["text"]))
        return input_tokens_count
    
    def estimate_costs(self, expected_output_tokens_per_request: int):
        tot_requests = len(self.to_be_computed)
        tot_input_tokens = self.to_be_computed_tokens
        if self.request.update:
            tot_requests += len(self.to_be_updated)
            tot_input_tokens += self.to_be_updated_tokens
        tot_max_output_tokens = self.request.generationConfig["maxOutputTokens"] * tot_requests
        expected_tot_output_tokens = min(expected_output_tokens_per_request, self.request.generationConfig["maxOutputTokens"]) * tot_requests

        multiplier = (1 if not self.request.batch else 0.5) / 10**6
        input_cost = tot_input_tokens * self.pricing["input"] * multiplier
        estimated_output_cost = (tot_input_tokens * self.pricing["input"] + expected_tot_output_tokens * self.pricing["output"]) * multiplier
        max_output_cost = (tot_input_tokens * self.pricing["input"] + tot_max_output_tokens * self.pricing["output"]) * multiplier
        return {
            "#requests": tot_requests,
            "input_tokens": tot_input_tokens,
            "max_output_tokens": tot_max_output_tokens,
            "update": self.request.update,
            "expectedOutputTokensPerRequest": expected_output_tokens_per_request,
            "modelInfo": {
                "modelFamily": self.request.model.__bases__[0].__name__,
                "modelName": self.request.model.__name__,
                "batchMode": self.request.batch,
                "pricing": {k: (v * (1 if not self.request.batch else 0.5)) for k, v in self.pricing.items()}
            },
            "requestInfo": {
                "#toBeComputed": len(self.to_be_computed),
                "#alreadyComputedByOtherTask": len(self.to_be_copied),
                "#toBeUpdated": len(self.to_be_updated),
                "#alreadyComputed": len(self.to_be_dropped),
            },
            "costs": {
                "inputCostUsd": input_cost,
                "outputCostUsd": estimated_output_cost,
                "maxOutputCostUsd": max_output_cost,
                "inputCostEur": input_cost / self.request.eur_usd_rate,
                "outputCostEur": estimated_output_cost / self.request.eur_usd_rate,
                "maxOutputCostEur": max_output_cost / self.request.eur_usd_rate,
            },
        }
    
    def __str__(self):
        output = ""
        output += f"To be computed: {self.to_be_computed}\n"
        output += f"To be copied: {self.to_be_copied}\n"
        output += f"To be updated: {self.to_be_updated}\n"
        output += f"To be dropped: {self.to_be_dropped}\n"
        output += f"Input tokens for reqs to be computed: {self.to_be_computed_tokens}\n"
        output += f"Input tokens for reqs to be updated: {self.to_be_updated_tokens}\n"
        output += f"Pricing: {self.pricing}\n"
        return output


def collect_all_model_classes():
    if not os.path.exists(MODELS_PATH):
        raise Exception("Model path not found!")
    folder = Path(MODELS_PATH).resolve()
    model_classes = {}

    for filepath in folder.glob("*.py"):
        if filepath.name == "__init__.py":
            continue
        spec = importlib.util.spec_from_file_location(filepath.stem, str(filepath))
        if spec is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"Failed to load {filepath.name}: {e}")
            continue
        
        class_name = None
        for _, attr_value in inspect.getmembers(module, inspect.isclass):
            if hasattr(attr_value, "__bases__") and attr_value.__bases__[0] == Model:
                class_name = attr_value
                model_classes[class_name] = set()
                break
        for _, attr_value in inspect.getmembers(module, inspect.isclass):
            if hasattr(attr_value, "__bases__") and attr_value.__bases__[0] == class_name:
                model_classes[class_name].add(attr_value)
    return model_classes


def resolve_model(model_class, model_name):
    model = None
    for n, v in collect_all_model_classes().items():
        for m in v:
            if n.__name__ == model_class and m.__name__ == model_name:
                model = m
                break
    if not model:
        raise Exception(f"Model {model_class}.{model_name} not recognized.")
    return model


class Request:
    def __init__(self, from_entry: dict={}, model: Model=None, generationConfig: dict={}, task_id: str="",
                 prompt_structure: str="", req_content_list: list[str]=[], contents: list[dict]=[], batch: bool=False, update: bool=False):
        self.sanitized = False
        self.eur_usd_rate = 1
        if from_entry:
            self.req_id = from_entry["_id"]
            self.model = resolve_model(from_entry["model_info"]["modelFamily"], from_entry["model_info"]["modelName"])
            self.price_usd = from_entry["priceUSD"]
            self.price_eur = from_entry["priceEUR"]
            self.date = from_entry["date"]
            self.operational = from_entry["model_info"]["operational"]
            self.generationConfig = from_entry["generationConfig"]
            self.task_id = from_entry["taskId"]
            self.prompt_structure = from_entry["promptStructure"]
            self.request_hash = from_entry["requestHash"]
            self.contents = from_entry["contents"]
            self.batch = from_entry["batch"]
            self.update = from_entry["update"]
            self.status = from_entry["status"]
        else:
            self.req_id = None
            self.model = model
            self.price_usd = 0
            self.price_eur = 0
            self.date = datetime.now(timezone.utc)
            self.operational = {}
            self.generationConfig = generationConfig
            self.task_id = task_id
            self.prompt_structure = prompt_structure
            self.request_hash = query_to_hash(prompt_structure + self.model.__name__ + json.dumps(self.generationConfig))
            self.contents = [
                {
                    "request": {"request_id": query_to_hash(text), "text": text},
                    "response": {}}
                for text in req_content_list
            ] if not contents else contents
            self.batch = batch
            self.update = update
            self.status = JobStatus.JOB_STATE_CREATED
    
    # def clone(self):
    #     request = Request(model=self.model, generationConfig=self.generationConfig, task_id=self.task_id, prompt_structure=self.prompt_structure,
    #                       contents=[x for x in self.contents], batch=self.batch, update=self.update)
    #     request.req_id = self.req_id
    #     request.price_eur = self.price_usd
    #     request.price_eur = self.price_usd
    #     request.date = self.date
    #     request.operational = self.operational
    #     request.request_hash = self.request_hash
    #     request.status = self.status
    #     return request
    
    def get_full_requests(self):
        return [self.prompt_structure.replace(CONTENT_TAG, content["request"]["text"]) for content in self.contents if not len(content["response"])]
    
    def create_record(self):
        entry = {
            "_id": self.req_id,
            "model_info": {
                "modelFamily": self.model.__bases__[0].__name__,
                "modelName": self.model.__name__,
                "operational": self.operational
            },
            "priceUSD": self.price_usd,
            "priceEUR": self.price_eur,
            "date": self.date,
            "taskId": self.task_id,
            "generationConfig": self.generationConfig,
            "promptStructure": self.prompt_structure,
            "requestHash": self.request_hash,
            "status": self.status,
            "batch": self.batch,
            "update": self.update,
            "contents": self.contents
        }
        return entry


class BatchManager:
    def __init__(self, ip, port, username, password, db_name, collection_name):
        self.eur_usd_rate = 1
        try:
            self.eur_usd_rate = requests.get("https://api.frankfurter.app/latest", params={"from": "EUR", "to": "USD"}).json()["rates"]["USD"]
        except:
            pass
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.db_name = db_name
        self.collection_name = collection_name
        self.connection_url = f"mongodb://{self.username}:{self.password}@{self.ip}:{self.port}/?authSource=admin" \
            if (username and password) else f"mongodb://{self.ip}:{self.port}"
        self.client = None
        self.instant_requests: list[ObjectId] = []
        self.batch_requests: list[ObjectId] = []
        self.on_background = False
        self.interrupt_backgroud_flag = False
        self.close_flag = False
        self.start_background_flag = False
        self.__registered_cb_on_instant__ = None
        self.__registered_cb_on_batch__ = None
        self.connect()
        self.load_initial_state()
        # self.cancel_instant_requests()
        self.start_background()
        threading.Thread(target=self.background_task, daemon=True).start()

    def connect(self):
        try:
            self.client = MongoClient(self.connection_url, serverSelectionTimeoutMS=400)
            self.client.admin.command('ping')
            print(f'BatchManager connected to MongoDB')
        except errors.ServerSelectionTimeoutError:
            self.connected = False
            print("Could not connect to MongoDB. Server not available.")
        else:
            self.connected = True
    
    def register_instant_callback(self, function):
        self.__registered_cb_on_instant__ = function
    
    def register_batch_callback(self, function):
        self.__registered_cb_on_batch__ = function
    
    def close(self):
        self.close_flag = True
    
    def load_initial_state(self):
        coll = self.client[self.db_name][self.collection_name]
        results = coll.find({ "status": {"$in": [
            JobStatus.JOB_STATE_CREATED,
            JobStatus.JOB_STATE_PENDING,
            JobStatus.JOB_STATE_RUNNING
        ]}}, {"_id": 1, "batch": 1})
        for r in results:
            if r["batch"]:
                self.batch_requests.append(r["_id"])
            else:
                self.instant_requests.append(r["_id"])

    def get_instant_requests(self):
        coll = self.client[self.db_name][self.collection_name]
        return list(coll.find({ "_id": {"$in": self.instant_requests}}))
    
    def create_request_entry(self, request_entry):
        coll = self.client[self.db_name][self.collection_name]
        while True:
            request_entry["_id"] = ObjectId()
            try:
                coll.insert_one(request_entry)
                return request_entry
            except DuplicateKeyError:
                continue

    def update_request_entry(self, request_entry):
        coll = self.client[self.db_name][self.collection_name]
        coll.find_one_and_update({"_id": request_entry["_id"]}, {"$set": request_entry}, upsert=True)

    def get_request_entry(self, _id):
        coll = self.client[self.db_name][self.collection_name]
        return coll.find_one({"_id": _id})

    def get_content_by_query(self, req_ids: set[str], query: dict):
        coll = self.client[self.db_name][self.collection_name]
        contents = {content["request"]["request_id"]: content
                    for doc in coll.find(query) for content in doc["contents"] if content["request"]["request_id"] in req_ids and content["response"] != {}}
        return contents

    def delete_content_by_query(self, req_ids: set[str], query: dict):
        coll = self.client[self.db_name][self.collection_name]
        base_filter = {
            **query,
            "contents.request.request_id": {"$in": list(req_ids)}
        }
        update = {
            "$pull": {
                "contents": {
                    "request.request_id": {"$in": list(req_ids)}
                }
            }
        }
        coll.update_many(filter=base_filter, update=update)

    def get_req_id_by_query(self, req_ids: set[str], query: dict):
        coll = self.client[self.db_name][self.collection_name]
        pipeline = [
            {"$match": {
                **query
            }},
            {"$unwind": "$contents"},
            {"$group": {
                "_id": None,
                "req_ids": {"$addToSet": "$contents.request.request_id"}
            }}
        ]
        result = coll.aggregate(pipeline)
        doc = next(result, None)
        stored_req_ids = set(doc["req_ids"]) if doc else set()
        fresh_ids = {rid for rid in req_ids if rid not in stored_req_ids}
        computed_ids = {rid for rid in req_ids if rid in stored_req_ids}
        return fresh_ids, computed_ids

    def get_directives(self, request: Request):
        # Request_id configurations:
        # new_task - new_prompt = request should be computed
        # new_task - computed_prompt = request has been already computed under a different task
        # computed_task - new_prompt = request has been already computed for the current task but under a different prompt signature
        # computed_task - computed_prompt = request has been already computed
        req_ids = {content["request"]["request_id"] for content in request.contents}
        if len(req_ids) != len(request.contents):
            raise Exception("Duplicated content in the request!")
        states = [
            JobStatus.JOB_STATE_CREATED,
            JobStatus.JOB_STATE_PENDING,
            JobStatus.JOB_STATE_RUNNING,
            JobStatus.JOB_STATE_SUCCEEDED
        ] 
        new_task, computed_task = self.get_req_id_by_query(req_ids, {"taskId": request.task_id, "status": {"$in": states}})
        new_prompt, computed_prompt = self.get_req_id_by_query(req_ids, {"requestHash": request.request_hash, "status": {"$in": states}})
        _, computed_totally = self.get_req_id_by_query(req_ids, {"taskId": request.task_id, "requestHash": request.request_hash, "status": {"$in": states}})
        to_be_computed, to_be_copied, to_be_updated, to_be_dropped = set(), set(), set(), set()
        for req_id in req_ids:
            if req_id in new_task and req_id in new_prompt:
                to_be_computed.add(req_id)
            elif (req_id in new_task and req_id in computed_prompt) or (req_id in computed_task and req_id in computed_prompt and req_id not in computed_totally):
                to_be_copied.add(req_id)
            elif req_id in computed_task and req_id in new_prompt:
                to_be_updated.add(req_id)
            elif req_id in computed_totally:
                to_be_dropped.add(req_id)
        return Directives(request, to_be_computed, to_be_copied, to_be_updated, to_be_dropped)

    def sanitize_request_content(self, directives: Directives):
        request: Request = directives.request
        request.contents = [content for content in request.contents if content["request"]["request_id"] not in directives.to_be_dropped]
        if not directives.request.update:
            request.contents = [content for content in request.contents if content["request"]["request_id"] not in directives.to_be_updated]
        else:
            states = [
                JobStatus.JOB_STATE_CREATED,
                JobStatus.JOB_STATE_PENDING,
                JobStatus.JOB_STATE_RUNNING,
                JobStatus.JOB_STATE_SUCCEEDED
            ]
            self.delete_content_by_query(directives.to_be_updated, {"taskId": request.task_id, "status": {"$in": states}})
        
        states = [
            JobStatus.JOB_STATE_CREATED,
            JobStatus.JOB_STATE_PENDING,
            JobStatus.JOB_STATE_RUNNING,
            JobStatus.JOB_STATE_CANCELLED,
            JobStatus.JOB_STATE_SUCCEEDED
        ]
        source_contents = self.get_content_by_query(directives.to_be_copied, {"requestHash": request.request_hash, "status": {"$in": states}})
        request.contents = [source_contents.get(content["request"]["request_id"], content) for content in request.contents]
        final_req_ids = set()
        final_contents = []
        for content in request.contents:
            if content["request"]["request_id"] not in final_req_ids:
                final_contents.append(content)
                final_req_ids.add(content["request"]["request_id"])
        request.contents = final_contents
        request.sanitized = True  # This flag is important as a sanity check is mandatory!
        request.eur_usd_rate = self.eur_usd_rate
        directives = self.get_directives(request)
        return request
    
    def interrupt_background(self):
        self.interrupt_backgroud_flag = True
        while self.on_background:
            time.sleep(0.05)
        self.interrupt_backgroud_flag = False
    
    def start_background(self):
        while self.on_background:
            time.sleep(0.05)
        self.start_background_flag = True

    def send_request(self, directives: Directives):
        """
        Send a request to the provider.
        
        Returns:
            - message (ErrorMsg|None):
                - ErrorMsg (NO_REQUEST|INITIALIZATION|SIMPLE_REQUEST) if an error occurred
                - None if requests have been sent
        """
        self.interrupt_background()
        sanitized_request = self.sanitize_request_content(directives)
        
        if len(sanitized_request.contents) == 0:
            self.start_background()
            return ErrorMsg(ErrorType.NO_REQUEST)

        if not sanitized_request.batch:
            model = sanitized_request.model()
            if not model.is_initialized():
                self.start_background()
                err = ErrorMsg(ErrorType.INITIALIZATION, model.init_err)
                print(err)
                return err
            stored_request = Request(from_entry=self.create_request_entry(sanitized_request.create_record()))
            self.instant_requests.append(stored_request.req_id)
        else:
            full_requests = sanitized_request.get_full_requests()
            status, message = sanitized_request.model().send_batch(sanitized_request, full_requests)
            if status == JobStatus.JOB_STATE_SUCCEEDED:
                sanitized_request.operational = message
                stored_request = Request(from_entry=self.create_request_entry(sanitized_request.create_record()))
                self.batch_requests.append(stored_request.req_id)
        self.start_background()
    
    def cancel_instant_requests(self):
        self.interrupt_background()
        self.__cancel_instant_requests__()
        self.start_background()
    
    def __cancel_instant_requests__(self):
        requests_ = self.get_instant_requests()[::-1]
        for i in range(len(requests_) - 1, -1, -1):
            request = Request(from_entry=requests_[i])
            request.status = JobStatus.JOB_STATE_CANCELLED
            self.update_request_entry(request.create_record())
            self.instant_requests.pop(0)

    def __compute_next_instant__(self):
        """
        Computes the next instant request.
        
        Returns:
            - Data (dict):
                - request (Request): Request object
                - content (dict): Content in form of a dict of the current generated request
                - computed (int): Current number of elements computed
                - tot_count (int): Current number of elements to be computed + already computed
                OR
                - None if error occurred
            - ErrorMsg (INITIALIZATION|SIMPLE_REQUEST) if an error occurred. None otherwise
        """
        requests_ = self.get_instant_requests()[::-1]
        tot_count = sum([len(req["contents"]) for req in requests_])
        computed_count = sum([len([1 for content in req["contents"] if content["response"] != {}]) for req in requests_])

        next_request_text = None
        next_content = None
        request = None

        for i in range(len(requests_) - 1, -1, -1):
            request = Request(from_entry=requests_[i])
            request.eur_usd_rate = self.eur_usd_rate
            for content in request.contents:
                if content["response"] == {}:
                    next_request_text = content["request"]["text"]
                    next_content = content
                    break
            if next_request_text is not None:
                break
            else:
                request.status = JobStatus.JOB_STATE_SUCCEEDED
                self.update_request_entry(request.create_record())
                self.instant_requests.pop(0)
        
        try:
            if next_request_text is not None:
                next_req_text = request.prompt_structure.replace(CONTENT_TAG, next_request_text)
                status, data, error = request.model().send_simple_request(request, next_req_text)
                if status == JobStatus.JOB_STATE_SUCCEEDED:
                    response = data
                    next_content["response"] = response
                    if computed_count + 1 == tot_count:
                        request.status = JobStatus.JOB_STATE_SUCCEEDED
                        self.instant_requests.pop(0)
                    self.update_request_entry(request.create_record())
                    return {"request": request, "content": next_content, "computed": computed_count + 1, "tot_count": tot_count}, None
                else:
                    return None, error
            return None, ErrorMsg(ErrorType.NO_REQUEST)
        except Exception as e:
            return None, ErrorMsg(ErrorType.UNKNOWN, e)

    def __fetch_batch_at__(self, index):
        """
        Fetches the batch request at a specified index.
        
        Returns:
            Data (dict):
                - request (Request): Batch request just computed or None if an error occurred.
                OR None if an error occurred
            - ErrorMsg (INITIALIZATION|BATCH_PARSING|BATCH_NOT_READY) if an error occurred, None otherwise
        """
        if not len(self.batch_requests):
            return None, ErrorMsg(ErrorType.NO_REQUEST)
        if index >= len(self.batch_requests) or index < 0:
            return None, ErrorMsg(ErrorType.NO_REQUEST)
        
        coll = self.client[self.db_name][self.collection_name]
        batch_request = Request(from_entry=coll.find_one({ "_id": self.batch_requests[index]}))
        batch_request.eur_usd_rate = self.eur_usd_rate
        try:
            status, data, error = batch_request.model().fetch_batch_results(batch_request)
            if status != batch_request.status:
                batch_request.status = status
                if status != JobStatus.JOB_STATE_SUCCEEDED:
                    self.update_request_entry(batch_request.create_record())
            
            if status in [JobStatus.JOB_STATE_CANCELLED, JobStatus.JOB_STATE_EXPIRED, JobStatus.JOB_STATE_FAILED, JobStatus.JOB_STATE_SUCCEEDED]:
                responses = data
                self.batch_requests.pop(index)
                if status == JobStatus.JOB_STATE_SUCCEEDED:
                    if len(batch_request.contents) != len(responses):
                        batch_request.status = JobStatus.JOB_STATE_FAILED
                    else:
                        for content, response in zip(batch_request.contents, responses):
                            content["response"] = response
                    self.update_request_entry(batch_request.create_record())

            return ({"request": batch_request}, None) if status == JobStatus.JOB_STATE_SUCCEEDED else (None, error)
        except Exception as e:
            return None, ErrorMsg(ErrorType.UNKNOWN, e)
    
    def wait(self, sec: int):
        for _ in range(int(20 * sec)):
            if self.interrupt_backgroud_flag or self.close_flag:
                return
            time.sleep(0.05)

    def background_task(self):
        POLLING_INTERVAL = 5
        backoff_values = [0, 0.1, 0.5, 2, 5]
        delay_idx = {"instant": 0}
        print("Monitoring AI requests...")
        while not self.close_flag:
            self.on_background = True
            self.start_background_flag = False
            while not self.interrupt_backgroud_flag and not self.close_flag:
                while len(self.instant_requests) and not self.interrupt_backgroud_flag and not self.close_flag:
                    instant_data, errorMsg = self.__compute_next_instant__()
                    if not errorMsg:
                        if self.__registered_cb_on_instant__:
                            try:
                                self.__registered_cb_on_instant__(*list(instant_data.values()))
                            except:
                                print(f"Error while processing callback {self.__registered_cb_on_instant__.__name__}")
                    else:
                        delay_idx["instant"] = min(delay_idx["instant"] + 1, len(backoff_values) - 1)
                        self.wait(backoff_values[delay_idx["instant"]])
                for i in range(len(self.batch_requests)-1, -1, -1):
                    if self.interrupt_backgroud_flag or self.close_flag:
                        break
                    batch_id = self.batch_requests[i]
                    if batch_id not in delay_idx:
                        delay_idx[batch_id] = 0
                    batch_data, errorMsg = self.__fetch_batch_at__(i)
                    if errorMsg is None:
                        if self.__registered_cb_on_batch__:
                            try:
                                self.__registered_cb_on_batch__(*list(batch_data.values()))
                            except:
                                print(f"Error while processing callback {self.__registered_cb_on_batch__.__name__}")
                    elif errorMsg.error_type not in {ErrorType.BATCH_NOT_READY}:
                        delay_idx[batch_id] = min(delay_idx[batch_id] + 1, len(backoff_values) - 1)
                        print(errorMsg)
                        self.wait(backoff_values[delay_idx[batch_id]])

                for _ in range(10 * POLLING_INTERVAL):
                    if len(self.instant_requests) or self.interrupt_backgroud_flag or self.close_flag:
                        break
                    time.sleep(0.1)
            self.on_background = False

            while not self.start_background_flag and not self.close_flag:
                time.sleep(0.1)


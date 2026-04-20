import os
import time
import threading
import requests
import inspect
import importlib
import json
import shutil
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from gen_ai.model import Model
from datetime import datetime, timezone
from pymongo import MongoClient, errors, IndexModel
from pymongo.errors import DuplicateKeyError
from bson.objectid import ObjectId
from gen_ai import models
from gen_ai.models import local
from gen_ai.model import JobStatus, ErrorMsg, ErrorType
from gen_ai.utils import count_tokens, query_to_hash, construct_prompt, MODELS_PATH, CACHE_FOLDER_PATH
DEFAULT_CONTENT_TAG = "DEFAULT_CONTENT_TAG"
DEFAULT_API_KEY = "000000000000000000"


class Directives:
    def __init__(self, request, bm, to_be_computed, to_be_copied, to_be_updated, to_be_dropped):
        self.request = request
        self.bm = bm
        self.to_be_computed = to_be_computed
        self.to_be_copied = to_be_copied
        self.to_be_updated = to_be_updated
        self.to_be_dropped = to_be_dropped
        self.to_be_computed_tokens = self.get_input_tokens_count(self.to_be_computed)
        self.to_be_updated_tokens = self.get_input_tokens_count(self.to_be_updated)
        self.pricing = request.model.pricing
        self.total_computed_costs = {}
    
    def get_input_tokens_count(self, profile_ids: set[str]):
        input_tokens_count = 0
        dupl_ids = set()
        for content in self.request.contents:
            if content["request"]["profile_id"] in profile_ids and content["request"]["profile_id"] not in dupl_ids:
                dupl_ids.add(content["request"]["profile_id"])
                input_tokens_count += count_tokens(construct_prompt(self.request.prompt_structure, content["request"]))
        return input_tokens_count
    
    def estimate_costs(self, expected_output_tokens_per_request: int = None):
        tot_requests = len(self.to_be_computed)
        tot_input_tokens = self.to_be_computed_tokens
        if self.request.update:
            tot_requests += len(self.to_be_updated)
            tot_input_tokens += self.to_be_updated_tokens
        tot_max_output_tokens = self.request.gen_config["maxOutputTokens"] * tot_requests
        if expected_output_tokens_per_request is None:
            expected_output_tokens_per_request = int(self.request.gen_config["maxOutputTokens"] / 2)
        expected_tot_output_tokens = min(expected_output_tokens_per_request, self.request.gen_config["maxOutputTokens"]) * tot_requests

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
                "total_spent": self.total_computed_costs,
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


def get_model_modules():
    if not os.path.exists(MODELS_PATH):
        raise Exception("Model path not found!")
    folder = Path(MODELS_PATH).resolve()

    modules = set()
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
        modules.add(module)
    return modules


def collect_all_model_classes():
    model_classes = {}
    for module in get_model_modules():
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


def resolve_model(module="_", model_class="_", model_name="_"):
    model = None
    for n, v in collect_all_model_classes().items():
        for m in v:
            if (n.__name__ == model_class if model_class != "_" else n.__module__ == module) and m.__name__ == model_name:
                model = m
                break
    return model


def resolve_model_class(model_class):
    for module in get_model_modules():
        if module.__name__ == model_class:
            return module


def get_model_fullname(model: Model):
    return model.__bases__[0].__name__ + "." + model.__name__


def is_valid_profile(profiles):
    if not isinstance(profiles, dict) and not isinstance(profiles, str):
        return False
    
    if isinstance(profiles, dict):
        for key, value in profiles.items():
            if not isinstance(key, str) and not isinstance(key, int):
                return False
            return is_valid_profile(value)
    
    return True


def verify_inputs(task_id, prompt_structure, profiles, chat, stream, batch, update):
    assert type(task_id) is str or type(task_id) is ObjectId
    assert type(prompt_structure) is str
    assert isinstance(profiles, Iterable) or type(profiles) is str
    if type(profiles) in [dict, str]:
        assert is_valid_profile(profiles)
    elif isinstance(profiles, Iterable):
        assert all(isinstance(x, str) for x in profiles) or all(is_valid_profile(x) for x in profiles)

    assert type(chat) is bool
    assert type(stream) is bool
    assert type(batch) is bool
    assert type(update) is bool
    if chat and (batch or update):
        raise Exception("Chat mode is incompatible with 'batch' and 'update' flags.")
    if chat and (isinstance(profiles, Iterable) and len(profiles) > 1):
        raise Exception("Chat mode is incompatible with multiple contents.")
    if not chat and stream:
        raise Exception("Streaming is allowed only in chat mode.")


def sanitize_model_genConfig(model, gen_config):
    assert model is None or type(model) is str or model.__bases__[0].__bases__[0] is Model
    assert type(gen_config) is dict
    model = model if model else local.gemma3
    model = resolve_model(**{k: m for k, m in zip(("module", "model_name"), model.split(".")[-2:])}) if type(model) == str else model
    if not model:
        raise Exception(f"Model not recognized.")
    if "maxOutputTokens" not in gen_config:
        gen_config["maxOutputTokens"] = 4000
    return model, gen_config


class Request:
    def __init__(self, from_entry: dict={}, model: Model|str=None, gen_config: dict={}, task_id: ObjectId|str="",
                 prompt_structure: str="", profiles: dict | list[str] | list[dict] | str="", contents: list[dict]=[],
                 chat: bool=False, stream: bool=False, batch: bool=False, update: bool=False):
        self.directives: Directives = None
        self.eur_usd_rate = 1
        if from_entry:
            self.req_id = from_entry["_id"]
            self.model = resolve_model(model_class=from_entry["model_info"]["modelFamily"], model_name=from_entry["model_info"]["modelName"])
            if not self.model:
                raise Exception(f'Model {from_entry["model_info"]["modelFamily"]}.{from_entry["model_info"]["modelName"]} not recognized.')
            self.price_usd = from_entry["priceUSD"]
            self.price_eur = from_entry["priceEUR"]
            self.date = from_entry["date"]
            self.operational = from_entry["model_info"]["operational"]
            self.gen_config = from_entry["generationConfig"]
            self.task_id = from_entry["taskId"]
            self.prompt_structure = from_entry["promptStructure"]
            self.request_hash = from_entry["requestHash"]
            self.contents = from_entry["contents"]
            self.chat = from_entry["chat"]
            self.stream = from_entry["stream"]
            self.batch = from_entry["batch"]
            self.update = from_entry["update"]
            self.status = from_entry["status"]
            self.cancellation_requested = from_entry["cancellationRequested"]
        else:
            task_id = task_id if task_id else ObjectId()
            prompt_structure = prompt_structure if prompt_structure else ("{{" + DEFAULT_CONTENT_TAG + "}}")

            verify_inputs(task_id, prompt_structure, profiles, chat, stream, batch, update)
            self.model, self.gen_config = sanitize_model_genConfig(model, gen_config)
            self.req_id = None
            self.price_usd = 0
            self.price_eur = 0
            self.date = datetime.now(timezone.utc)
            self.operational = {}
            self.task_id = task_id
            self.prompt_structure = prompt_structure
            self.request_hash = ObjectId(query_to_hash(prompt_structure + get_model_fullname(model) + json.dumps(self.gen_config))) if not chat else None
            if type(profiles) is str:
                profiles = [{"tag": 0, "content_vars": {DEFAULT_CONTENT_TAG: profiles}}]
            elif type(profiles) is dict:
                profiles = [{"tag": tag, "content_vars": x} for tag, x in profiles.items()]
            elif isinstance(profiles, Iterable):
                profiles = [{"tag": i, "content_vars": (x if type(x) is dict else {DEFAULT_CONTENT_TAG: x})} for i, x in enumerate(profiles)]
            else:
                raise Exception("Unknown input format.")

            additional_body = {
                "modelFamily": self.model.__bases__[0].__name__,
                "modelName": self.model.__name__,
                "generationConfig": self.gen_config
            } if chat else {}
            self.contents = [
                {
                    "request": {
                        "profile_id": query_to_hash(json.dumps(profile["content_vars"])) if not chat else 0,
                        "profile_tag": profile["tag"],
                        "profile": profile["content_vars"],
                        **additional_body
                    },
                    "response": {}
                }
                for profile in profiles
            ] if not contents else contents
            self.chat = chat
            self.stream = stream
            self.batch = batch
            self.update = update
            self.status = JobStatus.JOB_STATE_CREATED
            self.cancellation_requested = False
    
    def get_full_requests(self):
        return {content["request"]["profile_id"]: construct_prompt(self.prompt_structure, content["request"])
                for content in self.contents if not len(content["response"])}
    
    def is_complete(self):
        return all([content["response"] != {} for content in self.contents])

    def get_directives(self, bm):
        # Request_id configurations:
        # new_task - new_prompt = request should be computed
        # new_task - computed_prompt = request has been already computed under a different task
        # computed_task - new_prompt = request has been already computed for the current task but under a different prompt signature
        # computed_task - computed_prompt = request has been already computed
        profile_ids = {content["request"]["profile_id"] for content in self.contents}
        
        if self.chat:
            assert len(profile_ids) < 2
            to_be_computed, to_be_copied, to_be_updated, to_be_dropped = profile_ids, set(), set(), set()
        else:
            states = [
                JobStatus.JOB_STATE_CREATED,
                JobStatus.JOB_STATE_PENDING,
                JobStatus.JOB_STATE_RUNNING,
                JobStatus.JOB_STATE_SUCCEEDED
            ] 
            new_task, computed_task = bm.__get_profile_id_by_query__(profile_ids, {"taskId": self.task_id, "status": {"$in": states}, "chat": False})
            new_prompt, computed_prompt = bm.__get_profile_id_by_query__(profile_ids, {"requestHash": self.request_hash, "status": {"$in": states}, "chat": False})
            _, computed_totally = bm.__get_profile_id_by_query__(profile_ids, {"taskId": self.task_id, "requestHash": self.request_hash, "status": {"$in": states}, "chat": False})
            to_be_computed, to_be_copied, to_be_updated, to_be_dropped = set(), set(), set(), set()
            for profile_id in profile_ids:
                if profile_id in new_task and profile_id in new_prompt:
                    to_be_computed.add(profile_id)
                elif (profile_id in new_task and profile_id in computed_prompt) or (profile_id in computed_task and profile_id in computed_prompt and profile_id not in computed_totally):
                    to_be_copied.add(profile_id)
                elif profile_id in computed_task and profile_id in new_prompt:
                    to_be_updated.add(profile_id)
                elif profile_id in computed_totally:
                    to_be_dropped.add(profile_id)
        directives = Directives(self, bm, to_be_computed, to_be_copied, to_be_updated, to_be_dropped)
        directives.total_computed_costs = bm.get_consumption()
        self.directives = directives
    
    def estimate_costs(self, expected_output_tokens_per_request: int=None):
        if not self.directives:
            raise Exception("Directives needed: did you forget to call 'request.get_directives(BatchManager)'?")
        return self.directives.estimate_costs(expected_output_tokens_per_request)
    
    def send_request(self):
        if not self.directives:
            raise Exception("Directives needed: did you forget to call 'request.get_directives(BatchManager)'?")
        return self.directives.bm.send_request(self)

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
            "chat": self.chat,
            "stream": self.stream,
            "batch": self.batch,
            "update": self.update,
            "date": self.date,
            "taskId": self.task_id,
            "requestHash": self.request_hash,
            "promptStructure": self.prompt_structure,
            "contents": self.contents,
            "generationConfig": self.gen_config,
            "status": self.status,
            "cancellationRequested": self.cancellation_requested,
        }
        return entry


class BatchManager:
    def __init__(self, ip: str, port: int|str, db_name: str, username: str = "", password: str = "", api_keys: dict = {}, space: str|None=None,
                 cb_on_complete = None, cb_on_stream = None):
        self.__api_keys = {}
        self.set_api_keys(api_keys)

        self.eur_usd_rate = 1
        try:
            self.eur_usd_rate = requests.get("https://api.frankfurter.app/latest", params={"from": "EUR", "to": "USD"}).json()["rates"]["USD"]
        except:
            pass
        
        assert type(ip) is str and len(ip)
        assert (type(port) is str and len(port)) or type(port) is int
        assert type(db_name) is str and len(db_name)
        assert type(username) is str
        assert type(password) is str
        assert type(space) is str or space is None
        self.__ip = ip
        self.__port = port
        self.__username = username
        self.__password = password
        self.__db_name = db_name
        self.__space = space
        self.__connection_url = f"mongodb://{self.__username}:{self.__password}@{self.__ip}:{self.__port}/?authSource=admin" \
            if (username and password) else f"mongodb://{self.__ip}:{self.__port}"
        self.__client = None
        self.__chat_requests: list[ObjectId]
        self.__instant_requests: list[ObjectId]
        self.__batch_requests: list[ObjectId]
        self.__on_background = False
        self.__interrupt_backgroud_flag = True
        self.__close_flag = False
        self.__start_background_flag = False
        self.__registered_cb_on_chat__ = None
        self.__registered_cb_on_instant__ = None
        self.__registered_cb_on_batch__ = None
        self.__registered_cb_on_complete__ = cb_on_complete
        self.__registered_cb_on_stream__ = cb_on_stream
        self.__clear_cache_folder()
        self.__connect()
        threading.Thread(target=self.__background_task, daemon=True).start()
        if space:
            self.set_space(space)
    
    def __clear_cache_folder(self):
        folder = CACHE_FOLDER_PATH
        if not os.path.exists(folder):
            os.mkdir(folder)
        for item in os.listdir(folder):
            path = os.path.join(folder, item)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception as e:
                print(f"Failed to delete {path}: {e}")

    def __connect(self):
        try:
            self.__client = MongoClient(self.__connection_url, serverSelectionTimeoutMS=400)
            self.__client.admin.command('ping')
            print(f'BatchManager connected to MongoDB')
        except errors.ServerSelectionTimeoutError:
            self.connected = False
            print("Could not connect to MongoDB. Server not available.")
        else:
            self.connected = True
    
    def __get_collection(self):
        if not self.__space:
            raise Exception("You have to set a space for this operation.")
        return self.__client[self.__db_name][self.__space]
    
    def __get_api_key(self, model: Model):
        return self.__api_keys.get(model.__module__.split(".")[-1], DEFAULT_API_KEY)
    
    def __load_initial_state(self):
        self.__chat_requests: list[ObjectId] = []
        self.__instant_requests: list[ObjectId] = []
        self.__batch_requests: list[ObjectId] = []
        self.__get_collection().create_indexes([
            IndexModel("status"),
            IndexModel("requestHash"),
            IndexModel("chat"),
            IndexModel("taskId")
        ])
        results = self.__get_collection().find({ "status": {"$in": [
            JobStatus.JOB_STATE_CREATED,
            JobStatus.JOB_STATE_PENDING,
            JobStatus.JOB_STATE_RUNNING
        ]}}, {"_id": 1, "batch": 1, "chat": 1})
        for r in results:
            if r["batch"]:
                self.__batch_requests.append(r["_id"])
            else:
                if r["chat"]:
                    self.__chat_requests.append(r["_id"])
                else:
                    self.__instant_requests.append(r["_id"])
    
    def __create_request_entry(self, request_entry):
        while True:
            request_entry["_id"] = ObjectId()
            try:
                self.__get_collection().insert_one(request_entry)
                return request_entry
            except DuplicateKeyError:
                continue

    def __update_request_entry(self, request_entry):
        self.__get_collection().find_one_and_update({"_id": request_entry["_id"]}, {"$set": request_entry}, upsert=True)

    def __get_content_by_query(self, profile_ids: set[str], query: dict):
        contents = {content["request"]["profile_id"]: content
                    for doc in self.__get_collection().find(query)
                    for content in doc["contents"]
                    if content["request"]["profile_id"] in profile_ids and content["response"] != {}}
        return contents

    def __delete_content_by_query(self, profile_ids: set[str], query: dict):
        base_filter = {
            **query,
            "contents.request.profile_id": {"$in": list(profile_ids)}
        }
        update = {
            "$pull": {
                "contents": {
                    "request.profile_id": {"$in": list(profile_ids)}
                }
            }
        }
        self.__get_collection().update_many(filter=base_filter, update=update)

    def __get_profile_id_by_query__(self, profile_ids: set[str], query: dict):
        pipeline = [
            {"$match": {
                **query
            }},
            {"$unwind": "$contents"},
            {"$group": {
                "_id": None,
                "profile_ids": {"$addToSet": "$contents.request.profile_id"}
            }}
        ]
        result = self.__get_collection().aggregate(pipeline)
        doc = next(result, None)
        stored_profile_ids = set(doc["profile_ids"]) if doc else set()
        fresh_ids = {rid for rid in profile_ids if rid not in stored_profile_ids}
        computed_ids = {rid for rid in profile_ids if rid in stored_profile_ids}
        return fresh_ids, computed_ids

    def __sanitize_request_content(self, directives: Directives):
        request: Request = directives.request
        request.contents = [content for content in request.contents if content["request"]["profile_id"] not in directives.to_be_dropped]
        if not directives.request.update:
            request.contents = [content for content in request.contents if content["request"]["profile_id"] not in directives.to_be_updated]
        
        states = [
            JobStatus.JOB_STATE_CREATED,
            JobStatus.JOB_STATE_PENDING,
            JobStatus.JOB_STATE_RUNNING,
            JobStatus.JOB_STATE_CANCELLED,
            JobStatus.JOB_STATE_SUCCEEDED
        ]
        source_contents = self.__get_content_by_query(directives.to_be_copied, {"requestHash": request.request_hash, "status": {"$in": states}, "chat": False})
        request.contents = [source_contents.get(content["request"]["profile_id"], content) for content in request.contents]
        return request

    def __finalize_request_content(self, request: Request):
        final_contents = []
        for content in request.contents:
            full_req_hash = ObjectId(query_to_hash(construct_prompt(request.prompt_structure, content["request"])))
            content["request"]["full_request_hash"] = full_req_hash
            final_contents.append(content)
        request.contents = final_contents
        return request
    
    def __interrupt_background(self):
        self.__interrupt_backgroud_flag = True
        while self.__on_background:
            time.sleep(0.05)
        self.__interrupt_backgroud_flag = False
    
    def __start_background(self):
        self.__interrupt_background()
        while self.__on_background:
            time.sleep(0.05)
        if self.__space:
            self.__start_background_flag = True

    def __on_complete(self, request: Request):
        if self.__registered_cb_on_complete__:
            try:
                self.__registered_cb_on_complete__(request)
            except:
                import traceback
                print(traceback.format_exc())
                pass
        else:
            print("no callback")
    
    def __cancel_instant_requests(self):
        requests_ = list(self.__get_collection().find({ "_id": {"$in": self.__instant_requests}}))[::-1]
        for i in range(len(requests_) - 1, -1, -1):
            request = Request(from_entry=requests_[i])
            request.cancellation_requested = True
            request.status = JobStatus.JOB_STATE_CANCELLED
            self.__update_request_entry(request.create_record())
            self.__instant_requests.pop(0)
    
    def __handle_simple_requests(self, req_ids: list[ObjectId], chat=False):
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
        requests_ = list(self.__get_collection().find({ "_id": {"$in": req_ids}}))[::-1]
        tot_count = sum([len(req["contents"]) for req in requests_])
        computed_count = sum([len([1 for content in req["contents"] if content["response"] != {}]) for req in requests_])

        cur_content = None
        request = None

        for i in range(len(requests_) - 1, -1, -1):
            try:
                request = Request(from_entry=requests_[i])
            except:
                req_ids.pop(0)
                continue
            request.eur_usd_rate = self.eur_usd_rate
            for content in request.contents:
                if content["response"] == {}:
                    cur_content = content
                    break
            if cur_content is not None:
                break
            else:
                request.status = JobStatus.JOB_STATE_SUCCEEDED
                self.__update_request_entry(request.create_record())
                self.__on_complete(request)
                req_ids.pop(0)

        try:
            if cur_content is not None:
                next_req_text = construct_prompt(request.prompt_structure, cur_content["request"])
                model = request.model if not chat else resolve_model(model_class=cur_content["request"]["modelFamily"], model_name=cur_content["request"]["modelName"])
                if not model:
                    raise Exception(f'Model {cur_content["request"]["modelFamily"]}.{cur_content["request"]["modelName"]} not recognized.')
                model_instance = model(self.__get_api_key(request.model))
                if not model_instance.is_initialized():
                    return None, ErrorMsg(ErrorType.INITIALIZATION, model_instance.init_err)
                
                if request.stream:
                    data, error = model_instance.stream_request(request, next_req_text, self.__registered_cb_on_stream__)
                else:
                    data, error = model_instance.send_simple_request(request, next_req_text)
                
                if not error:
                    response = data
                    computed = 0
                    for content in request.contents:
                        if cur_content["request"]["profile_id"] == content["request"]["profile_id"]:
                            computed += 1
                            content["response"] = response
                    self.__update_request_entry(request.create_record())
                    return {"request": request, "content": cur_content, "computed": computed_count + computed, "tot_count": tot_count}, None
                else:
                    return None, error
            return None, ErrorMsg(ErrorType.NO_REQUEST)
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            return None, ErrorMsg(ErrorType.UNKNOWN, e)

    def __fetch_batch_at(self, index):
        """
        Fetches the batch request at a specified index.
        
        Returns:
            Data (dict):
                - request (Request): Batch request just computed or None if an error occurred.
                OR None if an error occurred
            - ErrorMsg (INITIALIZATION|BATCH_PARSING|BATCH_NOT_READY) if an error occurred, None otherwise
        """
        if not len(self.__batch_requests):
            return None, ErrorMsg(ErrorType.NO_REQUEST)
        if index >= len(self.__batch_requests) or index < 0:
            return None, ErrorMsg(ErrorType.NO_REQUEST)
        
        try:
            batch_request = Request(from_entry=self.__get_collection().find_one({ "_id": self.__batch_requests[index]}))
        except Exception as e:
            self.__batch_requests.pop(index)
            return None, ErrorMsg(ErrorType.UNKNOWN, e)
        batch_request.eur_usd_rate = self.eur_usd_rate
        
        if batch_request.is_complete():
            batch_request.status = JobStatus.JOB_STATE_SUCCEEDED
            self.__batch_requests.pop(index)
            self.__on_complete(batch_request)
            self.__update_request_entry(batch_request.create_record())
            return {"request": batch_request}, None
        try:
            model_instance = batch_request.model(self.__get_api_key(batch_request.model))
            if not model_instance.is_initialized():
                return None, ErrorMsg(ErrorType.INITIALIZATION, model_instance.init_err)
            job_status, data, error = model_instance.fetch_batch_results(batch_request)
            if job_status != batch_request.status:
                batch_request.status = job_status
                if job_status != JobStatus.JOB_STATE_SUCCEEDED:
                    self.__update_request_entry(batch_request.create_record())
            
            if job_status in [JobStatus.JOB_STATE_CANCELLED, JobStatus.JOB_STATE_EXPIRED, JobStatus.JOB_STATE_FAILED, JobStatus.JOB_STATE_SUCCEEDED]:
                responses = data
                self.__batch_requests.pop(index)
                if job_status == JobStatus.JOB_STATE_SUCCEEDED:
                    for content in batch_request.contents:
                        response = responses.get(content["request"]["profile_id"], None)
                        if response:
                            content["response"] = response
                    self.__on_complete(batch_request)
                    self.__update_request_entry(batch_request.create_record())

            return ({"request": batch_request}, None) if job_status == JobStatus.JOB_STATE_SUCCEEDED else (None, error)
        except Exception as e:
            return None, ErrorMsg(ErrorType.UNKNOWN, e)
    
    def __wait(self, sec: int):
        for _ in range(int(20 * sec)):
            if self.__interrupt_backgroud_flag or self.__close_flag:
                return
            time.sleep(0.05)

    def __background_task(self):
        POLLING_INTERVAL = 5
        backoff_values = [0, 0.1, 0.5, 2, 5]
        delay_idx = {"chat": 0, "instant": 0}
        print("Monitoring AI requests...")
        while not self.__close_flag:
            self.__on_background = True
            self.__start_background_flag = False
            while not self.__interrupt_backgroud_flag and not self.__close_flag:
                while len(self.__chat_requests) and not self.__interrupt_backgroud_flag and not self.__close_flag:
                    instant_data, errorMsg = self.__handle_simple_requests(self.__chat_requests, chat=True)
                    if not errorMsg:
                        if self.__registered_cb_on_chat__:
                            try:
                                self.__registered_cb_on_chat__(*list(instant_data.values()))
                            except:
                                print(f"Error while processing callback {self.__registered_cb_on_chat__.__name__}")
                    elif errorMsg.error_type not in {ErrorType.NO_REQUEST}:
                        delay_idx["chat"] = min(delay_idx["chat"] + 1, len(backoff_values) - 1)
                        self.__wait(backoff_values[delay_idx["chat"]])
                while len(self.__instant_requests) and not len(self.__chat_requests) and not self.__interrupt_backgroud_flag and not self.__close_flag:
                    instant_data, errorMsg = self.__handle_simple_requests(self.__instant_requests, chat=False)
                    if not errorMsg:
                        if self.__registered_cb_on_instant__:
                            try:
                                self.__registered_cb_on_instant__(*list(instant_data.values()))
                            except:
                                print(f"Error while processing callback {self.__registered_cb_on_instant__.__name__}")
                    elif errorMsg.error_type not in {ErrorType.NO_REQUEST}:
                        print(errorMsg)
                        delay_idx["instant"] = min(delay_idx["instant"] + 1, len(backoff_values) - 1)
                        self.__wait(backoff_values[delay_idx["instant"]])
                for i in range(len(self.__batch_requests)-1, -1, -1):
                    if len(self.__chat_requests) or self.__interrupt_backgroud_flag or self.__close_flag:
                        break
                    batch_data, errorMsg = self.__fetch_batch_at(i)
                    if errorMsg is None:
                        if self.__registered_cb_on_batch__:
                            try:
                                self.__registered_cb_on_batch__(*list(batch_data.values()))
                            except:
                                print(f"Error while processing callback {self.__registered_cb_on_batch__.__name__}")
                    elif errorMsg.error_type not in {ErrorType.BATCH_NOT_READY}:
                        print(errorMsg)

                for _ in range(10 * POLLING_INTERVAL):
                    if len(self.__chat_requests) or len(self.__instant_requests) or self.__interrupt_backgroud_flag or self.__close_flag:
                        break
                    time.sleep(0.1)
            self.__on_background = False

            while not self.__start_background_flag and not self.__close_flag:
                time.sleep(0.1)
    
    # ------------------------------------------------------------------------------------------------------------
    
    def get_consumption(self):
        coll = self.__get_collection()
        computation_price_aggr = list(coll.aggregate([
            {"$match": {"chat": {"$ne": True}}},
            {
                "$group": {
                    "_id": {
                        "family": "$model_info.modelFamily",
                        "name": "$model_info.modelName"
                    },
                    "usd": {"$sum": "$priceUSD"},
                    "eur": {"$sum": "$priceEUR"}
                }
            }
        ]))
        computation_price_chats = list(coll.aggregate([
            {"$match": {"chat": True}},
            {
                "$group": {
                    "_id": None,
                    "usd": {"$sum": "$priceUSD"},
                    "eur": {"$sum": "$priceEUR"}
                }
            }
        ]))
        computed_costs = {
            "chats": {
                "usd": computation_price_chats[0]["usd"] if len(computation_price_chats) else 0,
                "eur": computation_price_chats[0]["eur"] if len(computation_price_chats) else 0
            },
            "parallel": {}
        }
        parallel = {x["_id"]["family"]: [] for x in computation_price_aggr}
        for k in parallel:
            for x in computation_price_aggr:
                if x["_id"]["family"] == k:
                    parallel[k] = {x["_id"]["name"]: {"usd": x["usd"], "eur": x["eur"]}}
        computed_costs["parallel"] = parallel
        return computed_costs

    def set_space(self, space: str):
        self.__interrupt_background()
        assert type(space) is str or space is None
        self.__space = space
        self.__load_initial_state()
        self.__start_background()
    
    def set_api_keys(self, api_keys: dict[str|Model, str]):
        clean_api_keys = {}
        assert type(api_keys) is dict
        for model_family, api_key in api_keys.items():
            assert type(model_family) is str or (hasattr(model_family, "__package__") and model_family.__package__ == models.__name__)
            if type(model_family) is str:
                model_family = model_family.split(".")[-1]
                model_family = resolve_model_class(model_family)
                assert model_family is not None
            assert type(api_key) is str
            clean_api_keys[model_family.__name__.split(".")[-1]] = api_key
        self.__api_keys = clean_api_keys
    
    def get_active_api_keys(self):
        api_keys = {}

        def check_model(class_):
            module_name = class_.__module__
            api_key = self.__api_keys.get(module_name)
            if not api_key:
                return module_name, False
            try:
                model = class_(api_key)
                return module_name, model.is_initialized()
            except:
                return module_name, False

        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_module = {
                executor.submit(check_model, cls): cls.__module__
                for cls in collect_all_model_classes()
            }
            for future in as_completed(future_to_module):
                module_name, initialized = future.result()
                api_keys[module_name] = initialized
        return api_keys
    
    def register_instant_callback(self, function):
        self.__registered_cb_on_instant__ = function
    
    def register_batch_callback(self, function):
        self.__registered_cb_on_batch__ = function
    
    def register_on_complete_callback(self, function):
        self.__registered_cb_on_complete__ = function
    
    def register_on_stream_callback(self, function):
        self.__registered_cb_on_stream__ = function
    
    def close(self):
        self.__close_flag = True
    
    def create_chat(self, model: Model | str=None, gen_config: dict={}, task_id: ObjectId | str=""):
        request = Request(model=model, gen_config=gen_config, task_id=task_id, profiles=[], chat=True)
        request.status = JobStatus.JOB_STATE_RUNNING
        chat_obj = self.__get_collection().find_one({"chat": True, "taskId": task_id})
        if chat_obj:
            return ErrorMsg(ErrorType.NO_REQUEST)
        return Request(from_entry=self.__create_request_entry(request.create_record()))
    
    def send_chat(self, task_id: ObjectId|str, message: dict|str, stream: bool=False, model: Model | str=None, gen_config: dict={}):
        assert type(message) in [dict, str]
        chat_obj = self.__get_collection().find_one({"chat": True, "taskId": task_id})
        if not chat_obj:
            return None, ErrorMsg(ErrorType.CHAT_NOT_FOUND)
        request = Request(from_entry=chat_obj)
        model_, gen_config_ = sanitize_model_genConfig(model, gen_config)
        if model:
            request.model = model_
        if gen_config == {}:
            request.gen_config = gen_config_

        additional_body = {
            "modelFamily": request.model.__bases__[0].__name__,
            "modelName": request.model.__name__,
            "generationConfig": request.gen_config
        }
        new_content = {
            "request": {
                "profile_id": len(request.contents),
                "profile": {DEFAULT_CONTENT_TAG: message},
                **additional_body
            },
            "response": {}
        }
        request.contents = [new_content]
        request.status = JobStatus.JOB_STATE_RUNNING
        request.stream = stream
        request.get_directives(self)
        return self.send_request(request)
    
    def create_single_request(self, model: Model|str=None, gen_config: dict={}, task_id: ObjectId|str="",
                              prompt_structure: str="", message: dict | str="", update: bool=False):
        assert type(message) in [dict, str]
        request = Request(model=model, gen_config=gen_config, task_id=task_id, prompt_structure=prompt_structure, profiles=message, update=update)
        request.get_directives(self)
        return request
    
    def create_bucket_requests(self, model: Model|str=None, gen_config: dict={}, task_id: ObjectId|str="",
                               prompt_structure: str="", profiles: dict | list[str] | list[dict] | str="", batch: bool=False, update: bool=False):
        request = Request(model=model, gen_config=gen_config, task_id=task_id, prompt_structure=prompt_structure, profiles=profiles, batch=batch, update=update)
        request.get_directives(self)
        return request

    def send_request(self, request: Request):
        """
        Send a request to the provider.
        
        Returns:
            - Sanitized request (Request) if no error occurred, None otherwise.
            - message (ErrorMsg|None):
                - ErrorMsg (NO_REQUEST|INITIALIZATION|SIMPLE_REQUEST) if an error occurred
                - None if requests have been sent
        """
        self.__interrupt_background()
        sanitized_request = request if request.chat else self.__sanitize_request_content(request.directives)
        sanitized_request = self.__finalize_request_content(request)
        sanitized_request.eur_usd_rate = self.eur_usd_rate
        
        if not sanitized_request.chat and len(sanitized_request.contents) == 0:
            self.__start_background()
            return sanitized_request, ErrorMsg(ErrorType.NO_REQUEST)

        error = None
        if len(sanitized_request.get_full_requests()) == 0:
            stored_request = Request(from_entry=self.__create_request_entry(sanitized_request.create_record()))
            reqs = self.__batch_requests if stored_request.batch else self.__instant_requests
            reqs.append(stored_request.req_id)
        else:
            model_instance = sanitized_request.model(self.__get_api_key(request.model))
            if not model_instance.is_initialized():
                stored_request = sanitized_request
                error = ErrorMsg(ErrorType.INITIALIZATION, model_instance.init_err)
            else:
                if not sanitized_request.batch:
                    chat_obj = None
                    if sanitized_request.chat:
                        chat_obj = self.__get_collection().find_one({"chat": True, "taskId": sanitized_request.task_id})
                        if chat_obj:
                            chat_request = Request(from_entry=chat_obj)
                            stored_request = sanitized_request
                            stored_request.status = JobStatus.JOB_STATE_CREATED
                            stored_request.req_id = chat_request.req_id
                            stored_request.contents[0]["request"]["profile_id"] = len(chat_request.contents)
                            stored_request.contents = chat_request.contents + stored_request.contents
                            self.__update_request_entry(stored_request.create_record())
                        else:
                            stored_request = Request(from_entry=self.__create_request_entry(sanitized_request.create_record()))
                        self.__chat_requests.append(stored_request.req_id)
                    else:
                        stored_request = Request(from_entry=self.__create_request_entry(sanitized_request.create_record()))
                        self.__instant_requests.append(stored_request.req_id)
                else:
                    artifacts = model_instance.send_batch(sanitized_request)
                    if type(artifacts) is dict:
                        sanitized_request.operational = artifacts
                        stored_request = Request(from_entry=self.__create_request_entry(sanitized_request.create_record()))
                        self.__batch_requests.append(stored_request.req_id)
                    else:
                        stored_request = sanitized_request
                        error = artifacts

        if error is None:
            states = [
                    JobStatus.JOB_STATE_CREATED,
                    JobStatus.JOB_STATE_PENDING,
                    JobStatus.JOB_STATE_RUNNING,
                    JobStatus.JOB_STATE_SUCCEEDED
                ]
            self.__delete_content_by_query(request.directives.to_be_updated, {"taskId": request.directives.request.task_id, "status": {"$in": states}, "chat": False})
        else:
            print(error)
        self.__start_background()
        return (stored_request, None) if not error else (None, error)
    
    def cancel_request(self, request_id: ObjectId):
        entry = self.__get_collection().find_one({ "_id": request_id})
        if not entry:
            return ErrorMsg(ErrorType.BATCH_CANCEL, "Id for the request not found")
        self.__interrupt_background()
        request = Request(from_entry=entry)
        
        if request.batch:
            model_instance = request.model(self.__get_api_key(request.model))
            if not model_instance.is_initialized():
                self.__start_background()
                return ErrorMsg(ErrorType.INITIALIZATION, model_instance.init_err)
            error = model_instance.cancel_batch(request)
            if not error:
                request.cancellation_requested = True
                self.__update_request_entry(request.create_record())
            else:
                return error
        else:
            if request.status != JobStatus.JOB_STATE_SUCCEEDED:
                request.cancellation_requested = True
                request.status == JobStatus.JOB_STATE_CANCELLED
                for i in range(len(self.__instant_requests)):
                    if self.__instant_requests[i] == request.req_id:
                        self.__instant_requests.pop(i)
                        break
            self.__update_request_entry(request.create_record())
        self.__start_background()
        return None
    
    def cancel_instant_requests(self):
        self.__interrupt_background()
        self.__cancel_instant_requests()
        self.__start_background()


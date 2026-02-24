import gen_ai.models
from datetime import datetime, timezone
from pymongo import MongoClient, errors
from bson.objectid import ObjectId
from gen_ai.models import ModelClass
from utils import query_to_hash
from bson import json_util
CONTENT_TAG = "__X__"


class JobStatus:
    JOB_STATE_FAILED = 'JOB_STATE_FAILED'
    JOB_STATE_CANCELLED = 'JOB_STATE_CANCELLED'
    JOB_STATE_EXPIRED = 'JOB_STATE_EXPIRED'

    JOB_STATE_SUCCEEDED = 'JOB_STATE_SUCCEEDED'
    JOB_STATE_RUNNING = 'JOB_STATE_RUNNING'
    JOB_STATE_CREATED = 'JOB_STATE_CREATED'


class Directives:
    def __init__(self, request, to_be_computed, to_be_copied, to_be_updated, to_be_dropped):
        self.request = request
        self.to_be_computed = to_be_computed
        self.to_be_copied = to_be_copied
        self.to_be_updated = to_be_updated
        self.to_be_dropped = to_be_dropped
    
    def __str__(self):
        output = ""
        output += f"To be computed: {self.to_be_computed}\n"
        output += f"To be copied: {self.to_be_copied}\n"
        output += f"To be updated: {self.to_be_updated}\n"
        output += f"To be dropped: {self.to_be_dropped}\n"
        return output



class Request:
    def __init__(self, from_entry: dict={}, model_class: ModelClass=None, model_name: str="", generationConfig: dict={}, task_id: str="",
                 prompt_structure: str="", req_content_list: list[str]=[], contents: list[dict]=[], instant: bool=False):
        self.adjusted = False
        if from_entry:
            self.req_id = from_entry["_id"]
            self.model_class = getattr(gen_ai.models, from_entry["model_info"]["modelClass"])
            self.model_name = from_entry["model_info"]["modelName"]
            self.date = from_entry["date"],
            self.operational = from_entry["model_info"]["operational"]
            self.generationConfig = from_entry["generationConfig"]
            self.task_id = from_entry["taskId"]
            self.prompt_structure = from_entry["promptStructure"]
            self.prompt_structure_hash = from_entry["promptStructureHash"]
            self.contents = from_entry["contents"]
            self.instant = from_entry["instant"]
            self.status = from_entry["status"]
        else:
            self.req_id = ObjectId()
            self.model_class = model_class
            self.model_name = model_name
            self.date = datetime.now(timezone.utc)
            self.operational = {}
            self.generationConfig = generationConfig
            self.task_id = task_id
            self.prompt_structure = prompt_structure
            self.prompt_structure_hash = query_to_hash(prompt_structure)
            self.contents = [
                {
                    "request": {"request_id": query_to_hash(text), "text": text},
                    "response": {}}
                for text in req_content_list
            ] if not contents else contents
            self.instant = instant
            self.status = JobStatus.JOB_STATE_CREATED
    
    def clone(self):
        return Request(model_class=self.model_class, model_name=self.model_name, generationConfig=self.generationConfig,
                       task_id=self.task_id, prompt_structure=self.prompt_structure, contents=self.contents, instant=self.instant)
    
    def get_full_requests(self):
        return [self.prompt_structure.replace(CONTENT_TAG, content["request"]["text"]) for content in self.contents if not len(content["response"])]
    
    def create_record(self):
        entry = {
            "_id": self.req_id,
            "model_info": {
                "modelClass": self.model_class.__name__,
                "modelName": self.model_name,
                "operational": self.operational
            },
            "date": self.date,
            "taskId": self.task_id,
            "generationConfig": self.generationConfig,
            "promptStructure": self.prompt_structure,
            "promptStructureHash": self.prompt_structure_hash,
            "status": self.status,
            "instant": self.instant,
            "contents": self.contents
        }
        return entry



class BatchManager:
    def __init__(self, ip, port, username, password, db_name, collection_name):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.db_name = db_name
        self.collection_name = collection_name
        self.connection_url = f"mongodb://{self.username}:{self.password}@{self.ip}:{self.port}/?authSource=admin" \
            if (username and password) else f"mongodb://{self.ip}:{self.port}"
        self.client = None
        self.connect()

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
    
    def create_request_entry(self, request_entry):
        coll = self.client[self.db_name][self.collection_name]
        coll.find_one_and_update(
            {"_id": request_entry["_id"]},
            {"$set": request_entry},
            upsert=True,
        )
        return request_entry["_id"]
    
    def get_request_entry(self, _id):
        coll = self.client[self.db_name][self.collection_name]
        return coll.find_one({"_id": _id})
    
    def get_req_id_by_query(self, req_ids: set[str], query: dict):
        coll = self.client[self.db_name][self.collection_name]
        pipeline = [
            {"$match": {
                **query,
                "status": {"$in": [
                    JobStatus.JOB_STATE_CREATED,
                    JobStatus.JOB_STATE_RUNNING,
                    JobStatus.JOB_STATE_SUCCEEDED
                ]}
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
    
    def get_content_by_query(self, req_ids: set[str], query: dict):
        coll = self.client[self.db_name][self.collection_name]
        contents = {content["request"]["request_id"]: content
                    for doc in coll.find(query) if doc["status"] in [JobStatus.JOB_STATE_CREATED, JobStatus.JOB_STATE_RUNNING, JobStatus.JOB_STATE_SUCCEEDED]
                    for content in doc["contents"] if content["request"]["request_id"] in req_ids}
        return contents
    
    def delete_content_by_query(self, req_ids: set[str], query: dict):
        coll = self.client[self.db_name][self.collection_name]
        base_filter = {
            **query,
            "status": {
                "$in": [
                    JobStatus.JOB_STATE_CREATED,
                    JobStatus.JOB_STATE_RUNNING,
                    JobStatus.JOB_STATE_SUCCEEDED
                ]
            },
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
    
    def get_directives(self, request: Request):
        # Request_id configurations:
        # new_task - new_prompt = request should be computed
        # new_task - computed_prompt = request has been already computed under a different task
        # computed_task - new_prompt = request has been already computed for the current task but under a different prompt signature
        # computed_task - computed_prompt = request has been already computed
        req_ids = {content["request"]["request_id"] for content in request.contents}
        new_task, computed_task = self.get_req_id_by_query(req_ids, {"taskId": request.task_id})
        new_prompt, computed_prompt = self.get_req_id_by_query(req_ids, {"promptStructureHash": request.prompt_structure_hash})
        _, computed_totally = self.get_req_id_by_query(req_ids, {"taskId": request.task_id, "promptStructureHash": request.prompt_structure_hash})
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

    def request_preview(self, directives: Directives, update=False):
        request: Request = directives.request.clone()
        request.contents = [content for content in request.contents if content["request"]["request_id"] not in directives.to_be_dropped]
        if not update:
            request.contents = [content for content in request.contents if content["request"]["request_id"] not in directives.to_be_updated]
        else:
            self.delete_content_by_query(directives.to_be_updated, {"taskId": request.task_id})
        source_contents = self.get_content_by_query(directives.to_be_copied, {"promptStructureHash": request.prompt_structure_hash})
        request.contents = [source_contents.get(content["request"]["request_id"], content) for content in request.contents]
        request.adjusted = True
        return request
    
    def send_request(self, directives: Directives, adjusted_request: Request=None, update=False):
        if not adjusted_request:
            adjusted_request = self.request_preview(directives, update)
        elif not adjusted_request.adjusted:
            raise Exception("Request must be previewed first!")
        if len(adjusted_request.contents) == 0:
            return
        _id = self.create_request_entry(adjusted_request.create_record())


        adjusted_request = Request(from_entry=self.get_request_entry(_id))
        model = adjusted_request.model_class(adjusted_request.model_name)
        model.send_request(adjusted_request)

import os
import gridfs
import hashlib
import tempfile
import platform
import subprocess
from gui.utils import pprint, create_paper_id
from pymongo import MongoClient, errors, ReturnDocument
from bson.objectid import ObjectId


def calculate_hash(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


class MongoDB:
    connected = True

    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.client = None
        self.db_name = "LiteratureReview"
    
    def connect(self):
        try:
            connection_url = f"mongodb://mongodb:mongodb@{self.ip}:{self.port}/?authSource=admin"
            self.client = MongoClient(connection_url, serverSelectionTimeoutMS=400)
            self.client.admin.command('ping')
            self.fetch_collections()
            pprint(f'Connected to MongoDB')
        except errors.ServerSelectionTimeoutError:
            self.connected = False
            pprint("Could not connect to MongoDB. Server not available.")
        else:
            self.connected = True
    
    def fetch_collections(self):
        return [x for x in self.client[self.db_name].list_collection_names() if x not in ["fs.files", "fs.chunks"] and not x.startswith("__all_papers__")]
    
    def fetch_user_pdf_ids(self, collection_name: str, container_name: str):
        db = self.client[self.db_name]
        doc = db[collection_name].find_one(
            {"containers.name": container_name},
            {"containers.$": 1}
        )
        if doc and "containers" in doc:
            return doc["containers"][0]["user_pdf_ids"]
        return []
    
    def fetch_user_pdf_md(self, user_pdf_id):
        user_pdf_id = ObjectId(user_pdf_id)
        db = self.client[self.db_name]
        return db["fs.files"].find_one({"_id": user_pdf_id})
    
    def fetch_user_pdf_mds(self, collection_name: str, container_name: str):
        ids = self.fetch_user_pdf_ids(collection_name, container_name)
        db = self.client[self.db_name]
        if not ids:
            return []
        db = self.client[self.db_name]
        cursor = db["fs.files"].find({"_id": {"$in": ids}})
        return [doc for doc in cursor]
    
    def fetch_containers(self, collection_name: str):
        db = self.client[self.db_name]
        doc = db[collection_name].find_one({})
        if doc and "containers" in doc:
            return list(doc["containers"])
        return []
    
    def fetch_contexts(self, collection_name: str):
        db = self.client[self.db_name]
        doc = db[collection_name].find_one({})
        if doc and "contexts" in doc:
            return list(doc["contexts"])
        return []
    
    def add_query(self, collection_name: str, context_name: str, query_info: dict):
        db = self.client[self.db_name]
        coll = db[collection_name]
        query_str = query_info["query"]

        coll.update_one(
            {"contexts.name": context_name},
            {"$set": {
                "contexts.$[ctx].queries.$[qry]": query_info
            }},
            array_filters=[
                {"ctx.name": context_name},
                {"qry.query": query_str}
            ],
            upsert=True
        )
    
    def remove_query(self, collection_name: str, context_name: str, query: str):
        db = self.client[self.db_name]
        db[collection_name].update_one({"contexts.name": context_name}, {"$pull": {"contexts.$.queries": {"query": query}}})
    
    def fetch_performed_queries(self, collection_name: str, context_name: str):
        db = self.client[self.db_name]
        doc = db[collection_name].find_one({"contexts.name": context_name}, {"contexts.$": 1})
        if not doc or "contexts" not in doc or len(doc["contexts"]) == 0:
            return []
        return doc["contexts"][0].get("queries", [])
    
    def fetch_refs_by_context(self, collection_name: str, context_name: str, include_keys=None):
        db = self.client[self.db_name]
        doc = db[collection_name].find_one({"contexts.name": context_name}, {"contexts.$": 1})
        if doc and "contexts" in doc:
            references = doc["contexts"][0].get("references", [])
            target_libraries = doc["contexts"][0].get("target_libraries", [])
        else:
            references, target_libraries = [], []
        if not len(target_libraries) and not len(references):
            return []
    
        containers_cursor = db[collection_name].aggregate([
            {"$unwind": "$containers"},
            {"$match": {"containers._id": {"$in": target_libraries}}},
            {"$project": {"user_pdf_ids": "$containers.user_pdf_ids"}}
        ])
        user_pdf_ids = [pdf for c in containers_cursor for pdf in c["user_pdf_ids"]]

        query = {"$or": [{"file_id": {"$in": user_pdf_ids}}, {"_id": {"$in": references}}]}
        projection = include_keys if include_keys is not None else None
        papers_cursor = db[f"__all_papers__:{collection_name}"].find(query, projection)
        papers = list(papers_cursor)
        return papers
    
    def fetch_ref_by_id(self, collection_name: str, _id: str):
        db = self.client[self.db_name]
        paper = db[f"__all_papers__:{collection_name}"].find_one({"_id": ObjectId(_id)})
        return paper
    
    def fetch_ref_by_ids(self, collection_name: str, _id_list: list[str], include_keys=None):
        db = self.client[self.db_name]
        id_list = [ObjectId(x) for x in _id_list]
        projection = include_keys if include_keys is not None else None
        papers = db[f"__all_papers__:{collection_name}"].find({"_id": {"$in": id_list}}, projection)
        return list(papers)
    
    def get_missing_dois_from_context(self, collection_name: str, context_name: str, doi_list: list[str]):
        db = self.client[self.db_name]
        doc = db[collection_name].find_one({"contexts.name": context_name}, {"contexts.$": 1})

        if not doc or "contexts" not in doc or not doc["contexts"]:
            return doi_list

        ref_ids = doc["contexts"][0].get("references", [])
        if not ref_ids:
            return list(doi_list)
        
        papers_coll = db[f"__all_papers__:{collection_name}"]
        existing_dois = [p["doi"] for p in papers_coll.find({"_id": {"$in": ref_ids}}, projection={"doi": 1, "_id": 0}) if "doi" in p]
        existing_set = set(existing_dois)
        missing = [doi for doi in doi_list if doi not in existing_set]
        
        return missing
        
    
    def open_pdf(self, file_id):
        
        db = self.client[self.db_name]
        fs = gridfs.GridFS(db)
        
        try:
            grid_out = fs.get(ObjectId(file_id))
            pdf_data = grid_out.read()
            filename = grid_out.filename
        except Exception as e:
            pprint(f"Error fetching from GridFS: {e}")
            return

        temp_dir = tempfile.gettempdir()
        filename_ = f"{file_id}_{filename}"
        temp_path = os.path.join(temp_dir, filename_)
        
        try:
            if not os.path.exists(temp_path):
                with open(temp_path, "wb") as f:
                    f.write(pdf_data)
        except Exception as e:
            pprint(f"Error writing file")
            return

        if platform.system() == "Darwin":
            subprocess.call(("open", temp_path))
        elif platform.system() == "Windows":
            os.startfile(temp_path)
        else:
            subprocess.call(("xdg-open", temp_path))
    
    def create_collection(self, collection_name: str):
        if collection_name in ["fs.files", "fs.chunks"]:
            return
        db = self.client[self.db_name]
        db.create_collection(collection_name)
        db[collection_name].insert_one({"containers": []})
    
    def create_container(self, collection_name: str, container_name: str):
        db = self.client[self.db_name]
        new_item = {
            "_id": ObjectId(),
            "name": container_name,
            "user_pdf_ids": []
        }
        db[collection_name].update_one({}, {"$push": {"containers": new_item}}, upsert=True)
    
    def edit_container(self, collection_name: str, old_container_name: str, container_name: str):
        db = self.client[self.db_name]
        db[collection_name].update_one({ "containers.name": old_container_name }, { "$set": {"containers.$.name": container_name }})
    
    def create_context(self, collection_name: str, context_name: str, container_ids: list):
        db = self.client[self.db_name]
        new_item = {
            "name": context_name,
            "target_libraries": container_ids,
            "references": []
        }
        db[collection_name].update_one({}, {"$push": {"contexts": new_item}}, upsert=True)
    
    def edit_context(self, collection_name: str, old_context_name: str, context_name: str, container_ids: list):
        db = self.client[self.db_name]
        db[collection_name].update_one({ "contexts.name": old_context_name },
            { "$set": {
                "contexts.$.name": context_name,
                "contexts.$.target_libraries": container_ids
            }}
        )
    
    def delete_collection(self, collection_name: str):
        db = self.client[self.db_name]
        if collection_name in db.list_collection_names():
            db[collection_name].drop()
    
    def delete_container(self, collection_name: str, container_name: str):
        db = self.client[self.db_name]
        coll = db[collection_name]
        doc = coll.find_one({"containers.name": container_name}, {"containers.$": 1})
        if not doc or "containers" not in doc:
            return False

        container_id = doc["containers"][0]["_id"]
        coll.update_one({}, {"$pull": {"containers": {"_id": container_id}}})
        coll.update_one({}, {"$pull": {"contexts.$[].target_libraries": container_id}})
    
    def delete_context(self, collection_name: str, context_name: str):
        db = self.client[self.db_name]
        coll = db[collection_name]
        coll.update_one({}, {"$pull": {"contexts": {"name": context_name}}})
    
    def delete_user_pdf_ref(self, collection_name: str, container_name: str, file_id):
        db = self.client[self.db_name]
        db[collection_name].update_one(
            {"containers.name": container_name},
            {"$pull": {"containers.$.user_pdf_ids": file_id}}
        )
    
    def save_user_pdf(self, collection_name: str, container_name: str, filepath: str):
        db = self.client[self.db_name]
        fs = gridfs.GridFS(db)

        file_hash = calculate_hash(filepath)
        filename = os.path.basename(filepath)
        existing_file = db["fs.files"].find_one({"metadata.hash": file_hash})

        if existing_file:
            pprint("File already exists in database. Linking existing ID.")
            file_id = existing_file["_id"]
        else:
            with open(filepath, "rb") as f:
                metadata = {"hash": file_hash}
                file_id = fs.put(f, filename=filename, metadata=metadata)

        db[collection_name].update_one(
            {"containers.name": container_name},
            {"$addToSet": {"containers.$.user_pdf_ids": file_id}}
        )
        return db["fs.files"].find_one({"metadata.hash": file_hash})
    
    def add_paper(self, collection_name: str, paper: dict, fs_id: str = None, overwrite: bool = False):
        db = self.client[self.db_name]
        coll = db[f"__all_papers__:{collection_name}"]

        paper["paperId"] = create_paper_id(paper.get("title", ""), paper.get("file_id", ""), paper.get("year", 2025))
        fs_id = ObjectId(paper["file_id"]) if paper.get("file_id", None) else fs_id
        if fs_id:
            paper["paperId"] = create_paper_id(paper.get("title", ""), fs_id, paper.get("year", 2025))
            paper["file_id"] = fs_id
        
        existing = coll.find_one({"paperId": paper["paperId"]}, projection={"_id": 1})
        if existing and not overwrite:
            return existing["_id"]

        if "_id" in paper:
            del paper["_id"]
        found_paper = coll.find_one_and_update(
            {"paperId": paper["paperId"]},
            {"$set": paper},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return found_paper["_id"]
    
    def add_paperIds_to_context(self, collection_name: str, context_name: str, paper_id_list: list):
        db = self.client[self.db_name]
        db[collection_name].update_one({ "contexts.name": context_name },
            { "$addToSet": {"contexts.$.references": {"$each": paper_id_list}}}
        )
    
    def remove_paper(self, collection_name: str, paper_id: ObjectId):
        db = self.client[self.db_name]
        result = db[f"__all_papers__:{collection_name}"].delete_one({"_id": ObjectId(paper_id)})
        return result.deleted_count > 0
    
    def get_paper_by_fs_id(self, collection_name: str, fs_id: str):
        db = self.client[self.db_name]
        coll = db[f"__all_papers__:{collection_name}"]
        paper = coll.find_one({"file_id": fs_id})
        return paper
    
    def get_papers_by_fs_ids(self, collection_name: str, fs_ids: list[str]):
        db = self.client[self.db_name]
        coll = db[f"__all_papers__:{collection_name}"]
        papers = list(coll.find({"file_id": {"$in": fs_ids}}))
        return papers

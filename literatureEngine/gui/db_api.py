import re
import sys
import os
import gridfs
import hashlib
import tempfile
import platform
import subprocess
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
            print(f'Connected to MongoDB')
        except errors.ServerSelectionTimeoutError:
            self.connected = False
            print("Could not connect to MongoDB. Server not available.")
        else:
            self.connected = True
    
    def fetch_collections(self):
        return [x for x in self.client[self.db_name].list_collection_names() if x not in ["fs.files", "fs.chunks"] and not x.startswith("__all_papers__")]
    
    def fetch_containers(self, collection_name: str):
        db = self.client[self.db_name]
        doc = db[collection_name].find_one({})
        if doc and "containers" in doc:
            return [item["container_name"] for item in doc["containers"]]
        return []
    
    def fetch_user_pdf_ids(self, collection_name: str, container_name: str):
        db = self.client[self.db_name]
        doc = db[collection_name].find_one(
            {"containers.container_name": container_name},
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
            return [item["container_name"] for item in doc["containers"]]
        return []
    
    def open_pdf(self, file_id):
        
        db = self.client[self.db_name]
        fs = gridfs.GridFS(db)
        
        try:
            grid_out = fs.get(file_id)
            pdf_data = grid_out.read()
            filename = grid_out.filename
        except Exception as e:
            print(f"Error fetching from GridFS: {e}")
            return

        temp_dir = tempfile.gettempdir()
        filename_ = f"{file_id}_{filename}"
        temp_path = os.path.join(temp_dir, filename_)
        
        try:
            if not os.path.exists(temp_path):
                with open(temp_path, "wb") as f:
                    f.write(pdf_data)
        except Exception as e:
            print(f"Error writing file")
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
            "container_name": container_name,
            "paper_ids": [],
            "user_pdf_ids": [],
            "gathered_pdf_ids": []
        }
        db[collection_name].update_one({}, {"$push": {"containers": new_item}}, upsert=True)
    
    def delete_collection(self, collection_name: str):
        db = self.client[self.db_name]
        if collection_name in db.list_collection_names():
            db[collection_name].drop()
    
    def delete_container(self, collection_name: str, container_name: str):
        db = self.client[self.db_name]
        action = {"$pull": {"containers": {"container_name": container_name}}}
        return db[collection_name].update_one({}, action)
    
    def delete_user_pdf_ref(self, collection_name: str, container_name: str, file_id):
        db = self.client[self.db_name]
        db[collection_name].update_one(
            {"containers.container_name": container_name},
            {"$pull": {"containers.$.user_pdf_ids": file_id}}
        )
    
    def save_user_pdf(self, collection_name: str, container_name: str, filepath: str):
        db = self.client[self.db_name]
        fs = gridfs.GridFS(db)

        file_hash = calculate_hash(filepath)
        filename = os.path.basename(filepath)
        existing_file = db["fs.files"].find_one({"metadata.hash": file_hash})

        if existing_file:
            print("File already exists in database. Linking existing ID.")
            file_id = existing_file["_id"]
        else:
            with open(filepath, "rb") as f:
                metadata = {"hash": file_hash}
                file_id = fs.put(f, filename=filename, metadata=metadata)

        db[collection_name].update_one(
            {"containers.container_name": container_name},
            {"$addToSet": {"containers.$.user_pdf_ids": file_id}}
        )
        return db["fs.files"].find_one({"metadata.hash": file_hash})
    
    def add_paper(self, collection_name: str, paper: dict, fs_id: str = None):
        db = self.client[self.db_name]
        coll = db[f"__all_papers__:{collection_name}"]
        target_id = paper.get("paperId")

        to_update = {}
        if fs_id:
            to_update["file_id"] = fs_id
        
        update_ops = {"$set": to_update}
        update_ops["$set"].update(paper)

        found_paper = coll.find_one_and_update(
            {"paperId": target_id}, 
            update_ops, 
            upsert=True, 
            return_document=ReturnDocument.AFTER
        )
        return found_paper["_id"]
    
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
    
    # def create_instance(self, box_id: str='', profile: str=''):
    #     """
    #     Create a new database instance for the specified box and profile.

    #     Parameters:
    #     -------------
    #     box_id: str
    #         The ID of the box to connect.
    #     profile: str
    #         The profile name associated with the box.

    #     Returns:
    #     -------------
    #     MongoDB or None
    #         The MongoDB instance, or None if an error occurs.
    #     """
    #     global BOX_ID, PROFILE
    #     box_id = box_id if box_id != '' else BOX_ID
    #     profile = profile if profile != '' else PROFILE
    #     if box_id == '' or profile == '':
    #         return
    #     self.namespace = f'Box{box_id}_profile{profile}'
    #     self.box_id = box_id
    #     self.profile = profile
    #     BOX_ID = self.box_id
    #     PROFILE = self.profile
    #     if self.client is None:
    #         self.connect(self.sainsor_db_port)
    #     try:
    #         db = self.client['SaiNSOR']
    #         instance = db[self.namespace]
    #         self.sainsor_node_collection = instance[self.collections['sainsor_node']]
    #         self.session_collection = instance[self.collections['session']]
    #         self.config_collection = instance[self.collections['config']]
    #         self.recording_phases_collection = instance[self.collections['recording_phases']]
    #         self.rosbag_collection = instance[self.collections['rosbag']]
    #         self.msg_types_collection = instance[self.collections['msg_types']]
    #         self.topics_collection = instance[self.collections['topics']]
    #         # Check connection by attempting to find a document
    #         self.session_collection.find_one()
            
    #         self.msg_types = {}
    #         for e in self.msg_types_collection.find():
    #             self.msg_types[e['name']] = {k: v for k, v in e.items() if k not in ['name']}
    #         return self
    #     except errors.PyMongoError as e:
    #         print(f"An error occurred: {e}")
    #         return None
    
    # def delete_collection(self, box_id: str, profile: str, collection_name: str):
    #     """
    #     Delete a specific collection for the specified box and profile.

    #     Parameters:
    #     -------------
    #     box_id: str
    #         The ID of the box.
    #     profile: str
    #         The profile name associated with the box.
    #     collection_name: str
    #         The name of the collection to delete.

    #     Returns:
    #     -------------
    #     bool
    #         True if the collection is deleted successfully, False otherwise.
    #     """
    #     if collection_name not in self.collections:
    #         print(f"Collection {collection_name} not recognized.")
    #         return
    #     if self.client is None:
    #         self.connect(self.sainsor_db_port)
    #     try:
    #         db = self.client['SaiNSOR']
    #         instance_name = f'Box{box_id}_profile{profile}'
    #         instance = db[instance_name]
    #         collection = instance[self.collections[collection_name]]
    #         collection.delete_many({})
    #         db.drop_collection(collection_name)
    #         print(f"All data for collection {collection_name} has been deleted.")
    #         return True
    #     except errors.PyMongoError as e:
    #         print(f"An error occurred: {e}")
    #         return False
    
    # def delete_all_collections(self, box_id: str, profile: str):
    #     """
    #     Delete all collections for the specified box and profile.

    #     Parameters:
    #     -------------
    #     box_id: str
    #         The ID of the box.
    #     profile: str
    #         The profile name associated with the box.

    #     Returns:
    #     -------------
    #     bool
    #         True if all collections are deleted successfully, False otherwise.
    #     """
    #     if self.client is None:
    #         self.connect(self.sainsor_db_port)
    #     try:
    #         db = self.client['SaiNSOR']
    #         instance_name = f'Box{box_id}_profile{profile}'
    #         instance = db[instance_name]
    #         for collection_name in self.collections:
    #             collection = instance[self.collections[collection_name]]
    #             collection.delete_many({})
    #             db.drop_collection(instance_name + '_' + self.collections[collection_name])
    #         print(f"All data and collections for instance {instance_name} has been deleted.")
    #         return True
    #     except errors.PyMongoError as e:
    #         print(f"An error occurred: {e}")
    #         return False
        
    # def search_all_collections(self):
    #     """
    #     Search for all collections that match the SaiNSOR naming pattern.

    #     Returns:
    #     -------------
    #     list
    #         A list of matching collection names.
    #     """
    #     db = self.client['SaiNSOR']
    #     pattern = re.compile(r"^Box\w+_profile\w+")
    #     matching_collections = []
    #     try:
    #         collections = db.list_collection_names()
    #         matching_collections = [col for col in collections if pattern.match(col)]
    #     except errors.PyMongoError as e:
    #         print(f"An error occurred while listing collections: {e}")
    #     return matching_collections

    # def get_sainsor_nodes(self):
    #     """
    #     Retrieve all SaiNSOR nodes from the database.

    #     Returns:
    #     -------------
    #     pymongo.cursor.Cursor
    #         A cursor object for iterating through the SaiNSOR nodes.
    #     """
    #     sainsors = []
    #     for s in self.sainsor_node_collection.find():
    #         if version_compatible(s['version'], GUI_DB_RANGE):
    #             sainsors.append(s)
    #     return sainsors

    # def get_session_by_id(self, id):
    #     """
    #     Retrieve a session by its ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId/str
    #         The ID of the session.

    #     Returns:
    #     -------------
    #     dict or None
    #         The session document, or None if not found.
    #     """
    #     return self.session_collection.find_one({'_id': ObjectId(id)})

    # def get_session_by_session_id(self, id):
    #     """
    #     Retrieve a session by its session-ID.

    #     Parameters:
    #     -------------
    #     id: str
    #         The local ID of the session.

    #     Returns:
    #     -------------
    #     dict or None
    #         The session document, or None if not found.
    #     """
    #     return self.session_collection.find_one({'session_id': id})

    # def get_sainsor_node_by_id(self, id):
    #     """
    #     Retrieve a SaiNSOR node by its ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId/str
    #         The ID of the SaiNSOR node.

    #     Returns:
    #     -------------
    #     dict or None
    #         The node document, or None if not found.
    #     """
    #     return self.sainsor_node_collection.find_one({'_id': ObjectId(id)})

    # def get_config_by_id(self, id):
    #     """
    #     Retrieve a configuration by its ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId/str
    #         The ID of the configuration.

    #     Returns:
    #     -------------
    #     dict or None
    #         The configuration document, or None if not found.
    #     """
    #     return self.config_collection.find_one({'_id': ObjectId(id)})
    
    # def get_rec_phase_by_id(self, id):
    #     """
    #     Retrieve a recording phase by its ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId/str
    #         The ID of the recording phase.

    #     Returns:
    #     -------------
    #     dict or None
    #         The recording phase document, or None if not found.
    #     """
    #     return self.recording_phases_collection.find_one({'_id': ObjectId(id)})

    # def get_topic_by_id(self, id):
    #     """
    #     Retrieve a topic by its ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId/str
    #         The ID of the topic.

    #     Returns:
    #     -------------
    #     dict or None
    #         The topic document, or None if not found.
    #     """
    #     return self.topics_collection.find_one({'_id': ObjectId(id)})

    # def get_topic_by_rosbag_id(self, rosbag_id):
    #     """
    #     Retrieve a topic by its relative rosbag's ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId/str
    #         The ID of the rosbag.

    #     Returns:
    #     -------------
    #     dict or None
    #         The topic document, or None if not found.
    #     """
    #     rosbag = self.rosbag_collection.find_one({'_id': ObjectId(rosbag_id)})
    #     if rosbag is None:
    #         return None
    #     return self.topics_collection.find_one({'_id': rosbag['topic_ref']})

    # def get_rp_by_rosbag_id(self, rosbag_id):
    #     """
    #     Retrieve a recording_phase by its relative rosbag's ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId/str
    #         The ID of the rosbag.

    #     Returns:
    #     -------------
    #     dict or None
    #         The recording_phase document, or None if not found.
    #     """
    #     rosbag = self.rosbag_collection.find_one({'_id': ObjectId(rosbag_id)})
    #     if rosbag is None:
    #         return None
    #     config = self.config_collection.find_one({'_id': rosbag['config_ref']})
    #     if config is None:
    #         return None
    #     return self.recording_phases_collection.find_one({'_id': config['rec_phase_ref']})
    
    # def get_msg_types(self):
    #     """
    #     Retrieve all message types in the database.

    #     Returns:
    #     -------------
    #     dict
    #         A dictionary of message types and their associated fields.
    #     """
    #     types = {}
    #     for e in self.msg_types_collection.find():
    #         types[e['name']] = {k: v for k, v in e.items() if k not in ['name']}
    #     return types
    
    # def get_topics(self):
    #     """
    #     Retrieve all topics in the database.

    #     Returns:
    #     -------------
    #     pymongo.cursor.Cursor
    #         A cursor object for iterating through the topics.
    #     """
    #     return [t for t in self.topics_collection.find()]

    # def get_sessions(self, names=(), resolve=True):
    #     """
    #     Retrieve session information for specified session names.

    #     Parameters:
    #     -------------
    #     names: tuple, optional
    #         A tuple of session names to search for (default is an empty tuple).
    #     resolve: bool, optional
    #         A flag to allow recursive search within the indexed sessions (default is True).

    #     Returns:
    #     -------------
    #     list
    #         A list of session documents or an empty list if none found.
    #     """
    #     try:
    #         if len(names) == 0:
    #             sessions = [s for s in self.session_collection.find({'closing_time': {'$exists': True, '$ne': None}})]
    #             return Sessions(self, [s for s in sessions if version_compatible(s['version'], GUI_DB_RANGE)], resolve)
    #         else:
    #             return Sessions(self, [s for name in names for s in self.session_collection.find_one({'session_id': name})
    #                                    if version_compatible(s['version'], GUI_DB_RANGE)], resolve)
    #     except:
    #         return Sessions(self, [], True)
    
    # def get_rosbags_by_ids(self, ids=[]):
    #     """
    #     Retrieves ROS bags that match the provided IDs.

    #     Parameters:
    #     -------------
    #         ids (list): A list of IDs to match against the 'session_id' field.

    #     Returns:
    #     -------------
    #         list: A list of matching ROS bag documents.
    #     """
    #     try:
    #         if not ids:
    #             return []
    #         query = {'_id': {'$in': [ObjectId(x) for x in ids]}}
    #         matching_rosbags = list(self.rosbag_collection.find(query))
    #         return matching_rosbags
    #     except Exception as e:
    #         return []
    
    # def get_rosbags(self, sessions=[]):
    #     """
    #     Retrieve rosbags associated with specific sessions.

    #     Parameters:
    #     -------------
    #     sessions: list or str
    #         A list of sessions (or just the name of one) to filter rosbags.

    #     Returns:
    #     -------------
    #     list[dict]
    #         A list of rosbags that match the provided sessions.
    #     """
        
    #     if not isinstance(sessions, list) and not isinstance(sessions, tuple) and not isinstance(sessions, set):
    #         sessions = [sessions]

    #     session_ids = [x['_id'] for x in sessions]
    #     rec_phases_refs = list(self.recording_phases_collection.find({"session_ref": {"$in": session_ids}}, {"_id": 1}))
    #     rec_phase_ids = [x['_id'] for x in rec_phases_refs]
    #     config_refs = list(self.config_collection.find({"rec_phase_ref": {"$in": rec_phase_ids}}, {"_id": 1}))
    #     config_ids = [x['_id'] for x in config_refs]
    #     bags = list(self.rosbag_collection.find({"config_ref": {"$in": config_ids}}))
    #     return bags

    # def get_rosbags_full_structure(self, sessions):
    #     """
    #     Retrieve a hierarchical tree structure of the sessions.

    #     Parameters:
    #     -------------
    #     sessions: list or str
    #         A list of sessions (or just the name of one) to filter rosbags.

    #     Returns:
    #     -------------
    #     list[dict]
    #         A hierarchical tree structure representing the relationships between sessions, 
    #         recording phases, configurations, bags, etc. The structure is as follows:
    #             [
    #                 {
    #                     '_id': <session_id>,
    #                     'rec_phase': {
    #                         '_id': <rec_phase_id>,
    #                         'config': {
    #                             '_id': <config_id>,
    #                             'bags': [
    #                                 {...},  # Bag 1
    #                                 {...},  # Bag 2
    #                                 ...
    #                             ]
    #                         }
    #                     }
    #                 },
    #                 ...
    #             ]
    #     """
        
    #     if not isinstance(sessions, list) and not isinstance(sessions, tuple) and not isinstance(sessions, set):
    #         sessions = [sessions]
        
    #     def join(table1, table2, key1, new_key):
    #         for i in range(len(table1)):
    #             t1 = table1[i]
    #             for j in range(len(table2)):
    #                 t2 = table2[j]
    #                 if t1[key1] == t2['_id']:
    #                     del t1[key1]
    #                     t2c = t2.copy()
    #                     t2c['_id'] = str(t2c['_id'])
    #                     t1[new_key] = t2c
    #                     break
    #         return [x for x in table1 if new_key in x]
        
    #     def join_reverted(table1, table2, key1, new_key):
    #         for i in range(len(table1)):
    #             t1 = table1[i]
    #             for j in range(len(table2)):
    #                 t2 = table2[j]
    #                 if t1[key1] == t2['_id']:
    #                     del t1[key1]
    #                     t1c = t1.copy()
    #                     t1c['_id'] = str(t1c['_id'])
    #                     t2[new_key] = t2.get(new_key, []) + [t1c]
    #                     break
    #         return [x for x in table2 if new_key in x]

    #     session_ids = [x['_id'] for x in sessions]
    #     rec_phases_refs = list(self.recording_phases_collection.find({"session_ref": {"$in": session_ids}, "closing_time": {"$ne": None}}))
    #     rec_phase_ids = [x['_id'] for x in rec_phases_refs]
    #     config_refs = list(self.config_collection.find({"rec_phase_ref": {"$in": rec_phase_ids}}))
    #     config_ids = [x['_id'] for x in config_refs]
    #     bags = list(self.rosbag_collection.find({"config_ref": {"$in": config_ids}}, {"md_dependencies": 0}))
    #     topics_ids = list(set([x['topic_ref'] for x in bags]))
    #     topics_refs = list(self.topics_collection.find({"_id": {"$in": topics_ids}}))
    #     sainsor_node_ids = list(set([x['sainsor_node_ref'] for x in topics_refs]))
    #     msg_type_ids = list(set([x['msg_type_ref'] for x in topics_refs]))
    #     sainsor_node_refs = list(self.sainsor_node_collection.find({"_id": {"$in": sainsor_node_ids}}))
    #     msg_type_refs = list(self.msg_types_collection.find({"_id": {"$in": msg_type_ids}}))
    #     topics_refs = join(topics_refs, sainsor_node_refs, 'sainsor_node_ref', 'sainsor_node')
    #     topics_refs = join(topics_refs, msg_type_refs, 'msg_type_ref', 'msg_type')
    #     bags = join(bags, topics_refs, 'topic_ref', 'topic')
    #     config_refs = join_reverted(bags, config_refs, 'config_ref', 'bags')
    #     rec_phases_refs = join_reverted(config_refs, rec_phases_refs, 'rec_phase_ref', 'configs')
    #     sessions = join_reverted(rec_phases_refs, sessions, 'session_ref', 'rec_phases')
    #     for s in sessions:
    #         s['_id'] = str(s['_id'])
    #     return sessions
    
    # def delete_rosbag(self, id):
    #     """
    #     Delete a rosbag by its ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId/str
    #         The ID of the rosbag to delete.

    #     Returns:
    #     -------------
    #     tuple
    #         The URI of the rosbag, the session reference, and the configuration reference.
    #     """
    #     rosbag = self.rosbag_collection.find_one({'_id': ObjectId(id)})
    #     self.rosbag_collection.delete_one({'_id': ObjectId(id)})
    #     if rosbag is None:
    #         return None, None, None
    #     config = [x for x in self.config_collection.find() if x['_id'] == rosbag['config_ref']][0]
    #     rec_phase = [x for x in self.recording_phases_collection.find() if x['_id'] == config['rec_phase_ref']][0]
    #     return rosbag['uri'], rec_phase['session_ref'], rosbag['config_ref']
    
    # def delete_session(self, id):
    #     """
    #     Delete a session by its ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId
    #         The ID of the session to delete.
    #     """
    #     self.session_collection.delete_one({'_id': ObjectId(id)})
    
    # def delete_configuration(self, id):
    #     """
    #     Delete a configuration by its ID.

    #     Parameters:
    #     -------------
    #     id: ObjectId
    #         The ID of the configuration to delete.
    #     """
    #     self.config_collection.delete_one({'_id': ObjectId(id)})

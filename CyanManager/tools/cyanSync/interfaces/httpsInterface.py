import sys
import os
import asyncio
import base64
import uuid
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils import *
from interfaces.https_server.ws_manager import WebSocketManager
from https_client import FileBuilder, pprint


SHORT_TIMEOUT = 3.0
LONG_TIMEOUT = 10.0


class HTTPSInterface(Interface):
    root = ""
    local_root = ""
    folder_map = {}

    def __init__(self, local_id, interface_id, signal, args):
        self.ws_manager: WebSocketManager
        super().__init__(local_id, interface_id, signal)
        for k, v in args.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def device_connected(self):
        future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].list_clients(), self.signal["loop"])
        return self.interface_id in future.result(timeout=SHORT_TIMEOUT)

    def parse_device_info(self):
        data = {"request": "parse_device_info"}
        future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, SHORT_TIMEOUT), self.signal["loop"])
        try:
            return future.result(timeout=SHORT_TIMEOUT)["reply"]
        except Exception as e:
            pprint(f"HTTPS request failed on 'parse_device_info': {e}")
            return None
    
    def get_memory_consumption(self):
        data = {"request": "get_memory_consumption", "root": self.root}
        future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, SHORT_TIMEOUT), self.signal["loop"])
        try:
            reply = future.result(timeout=SHORT_TIMEOUT)["reply"]
            return reply
        except Exception as e:
            pprint(f"HTTPS request failed on 'get_memory_consumption': {e}")
            return None

    def get_remote_files(self, signal, remote_path, files, remote_root):
        data = {"request": "list_remote_files", "path": remote_path.get_unix_path()}
        future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, SHORT_TIMEOUT), self.signal["loop"])
        try:
            files_ = future.result(timeout=SHORT_TIMEOUT)["reply"]
            files_to_add = []
            for f in files_:
                if signal["kill"]:
                    return []
                full_path, date, size = f
                date = datetime.fromisoformat(date)
                full_filename = CPath(full_path).relative_to(CPath(signal['interface'].root))
                local_path = full_filename.prepend(signal['interface'].local_root)
                remote_path = full_filename.prepend(signal['interface'].root)
                files_to_add.append((full_filename, local_path, remote_path, date, True, int(size)))
            return files_to_add
        except Exception as e:
            pprint(f"HTTPS request failed on 'get_remote_files': {e}")
            return []

    def get_remote_sync_md(self, remote_path):
        data = {"request": "get_full_remote_sync_md", "path": remote_path.get_unix_path()}
        future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, SHORT_TIMEOUT), self.signal["loop"])
        try:
            self.full_remote_md = future.result(timeout=SHORT_TIMEOUT)["reply"]
            result = self.full_remote_md.get(self.share_id(), {})
            return result
        except Exception as e:
            pprint(f"HTTPS request failed on 'get_remote_sync_md': {e}")
            return None

    def delete_file_from_remote(self, remote_path):
        try:
            data = {"request": "delete_file_from_remote", "path": remote_path.get_unix_path()}
            future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, SHORT_TIMEOUT), self.signal["loop"])
            return future.result(timeout=SHORT_TIMEOUT)["reply"]
        except Exception as e:
            pprint(f"HTTPS request failed on 'delete_file_from_remote': {e}")
            return 1

    current_fb = None
    def copy_file_to_local(self, local_path, remote_path):
        src = remote_path.get_unix_path()
        dst = local_path.get_unix_path()

        try:
            data = {"request": "copy_file_to_local", "from_path": src}
            future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, SHORT_TIMEOUT), self.signal["loop"])
            reply = future.result(timeout=SHORT_TIMEOUT)["reply"]
            current_fb = FileBuilder(dst, reply["last_modified"], reply["file_id"], reply["tot_chunks"])
            for i in range(current_fb.tot_chunks):
                pprint(f"getting chunk {i+1}/{current_fb.tot_chunks}: {current_fb.to_path}")
                data = {"request": "get_file_chunk", "from_path": src, "index": i}
                future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, LONG_TIMEOUT), self.signal["loop"])
                chunk = future.result(timeout=LONG_TIMEOUT)["reply"]
                if chunk == 1:
                    raise Exception("Bad file transfer")
                current_fb.add_part(chunk)
            current_fb.close()
            return 0
        except Exception as e:
            pprint(f"HTTPS request failed on 'copy_file_to_local': {e}")
            return 1
        

    def copy_file_to_remote(self, local_path, remote_path):
        src = local_path.get_unix_path()
        dst = remote_path.get_unix_path()

        st = os.stat(src)
        last_modified = datetime.fromtimestamp(st.st_mtime).isoformat()
        
        CHUNK_SIZE = 256 * 1024
        file_size = os.path.getsize(src)
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        file_id = uuid.uuid4().hex

        try:
            with open(src, "rb") as f:
                data = {"request": "copy_file_to_remote", "to_path": dst, "last_modified": last_modified, "file_id": file_id, "tot_chunks": total_chunks}
                for chunk_index in range(total_chunks):
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    encoded = base64.b64encode(chunk).decode("ascii")
                    chunk_data = {**data, "index": chunk_index, "encoded": encoded}
                    future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, chunk_data, SHORT_TIMEOUT), self.signal["loop"])
                    future.result(timeout=5.0)["reply"]
            return 0
        except Exception as e:
            pprint(f"HTTPS request failed on 'move_file_from_remote_to_remote': {e}")
            return 1

    def move_file_from_remote_to_remote(self, remote_path, dest_path):
        src = remote_path.get_unix_path()
        dst = dest_path.get_unix_path()
        
        try:
            data = {"request": "move_file_from_remote_to_remote", "from_path": src, "to_path": dst}
            future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, SHORT_TIMEOUT), self.signal["loop"])
            return future.result(timeout=5.0)["reply"]
        except Exception as e:
            pprint(f"HTTPS request failed on 'move_file_from_remote_to_remote': {e}")
            return None
import sys
import os
import asyncio
import time
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils import *
from interfaces.https_server.ws_manager import WebSocketManager


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
        return self.interface_id in future.result(timeout=1.0)

    def parse_device_info(self):
        data = {"request": "parse_device_info"}
        future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, 1), self.signal["loop"])
        try:
            return future.result(timeout=1.0)["reply"]
        except Exception:
            return None
    
    def get_memory_consumption(self):
        data = {"request": "get_memory_consumption", "root": self.root}
        future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, 1), self.signal["loop"])
        try:
            reply = future.result(timeout=1.0)["reply"]
            return reply
        except Exception:
            return None

    def get_remote_files(self, signal, remote_path, files, remote_root):
        data = {"request": "list_remote_files", "path": remote_path.get_unix_path()}
        future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, 1), self.signal["loop"])
        try:
            files_ = future.result(timeout=10.0)["reply"]
            files_to_add = []
            for f in files_:
                full_path, date, size = f
                date = datetime.fromisoformat(date)
                full_filename = CPath(full_path).relative_to(CPath(signal['interface'].root))
                local_path = full_filename.prepend(signal['interface'].local_root)
                remote_path = full_filename.prepend(signal['interface'].root)
                files_to_add.append((full_filename, local_path, remote_path, date, True, int(size)))
            return files_to_add
        except Exception:
            return None

    def get_remote_sync_md(self, remote_path):
        data = {"request": "get_full_remote_sync_md", "path": remote_path.get_unix_path()}
        future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, 1), self.signal["loop"])
        try:
            self.full_remote_md = future.result(timeout=1.0)["reply"]
            result = self.full_remote_md.get(self.share_id(), {})
            return result
        except Exception:
            return None

    def delete_file_from_remote(self, remote_path):
        try:
            data = {"request": "delete_file_from_remote", "path": remote_path.get_unix_path()}
            future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, 1), self.signal["loop"])
            return future.result(timeout=1.0)["reply"]
        except Exception:
            return None

    def copy_file_to_local(self, local_path, remote_path):
        src = local_path.get_unix_path()
        dst = remote_path.get_unix_path()

        try:
            data = {"request": "copy_file_to_local", "from_path": dst}
            future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, 1), self.signal["loop"])
            last_modified_iso = future.result(timeout=1.0)["reply"]
            date = datetime.fromisoformat(last_modified_iso)
            self.signal["ws_manager"].save_to = {"path": src, "last_modified": date}
            for _ in range(100):
                if self.signal["kill"] or self.signal["ws_manager"].save_to is None:
                    break
                time.sleep(0.1)
        except Exception:
            return None
        

    def copy_file_to_remote(self, local_path, remote_path):
        src = local_path.get_unix_path()
        dst = remote_path.get_unix_path()

        st = os.stat(src)
        last_modified = datetime.fromtimestamp(st.st_mtime).isoformat()

        try:
            data = {"request": "copy_file_to_remote", "to_path": dst, "last_modified": last_modified}
            future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, 1), self.signal["loop"])
            future.result(timeout=1.0)["reply"]
        except Exception:
            return None

        try:
            with open(src, "rb") as f:
                data = f.read()
            future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, 1), self.signal["loop"])
            return 0
        except Exception:
            return None

    def move_file_from_remote_to_remote(self, remote_path, dest_path):
        src = remote_path.get_unix_path()
        dst = dest_path.get_unix_path()
        
        try:
            data = {"request": "move_file_from_remote_to_remote", "from_path": src, "to_path": dst}
            future = asyncio.run_coroutine_threadsafe(self.signal["ws_manager"].send_to_client(self.interface_id, data, 1), self.signal["loop"])
            return future.result(timeout=1.0)["reply"]
        except Exception:
            return None
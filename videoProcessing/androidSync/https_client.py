import asyncio
import ssl
import json
import os
import time
import uuid
import base64
import platform
import shutil
import socket
import sys
import websockets
import psutil
from pathlib import Path
from datetime import datetime


SYNC_MD_FILE = ".syncmd.json"
TEMP_EXT = ".synctmp"
DEVICE_ID = ""
URL = ""
current_fb = None


def check_if_process_already_running(script_name, last_arg):
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            proc_name = proc.info["name"].lower()
            if not proc_name.startswith("python"):
                continue
            cmdline = proc.info.get("cmdline") or []
            if not cmdline:
                continue
            if any(script_name in part for part in cmdline) and cmdline[-1] == last_arg:
                processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if len(processes) > 2:
        print(f"SyncAndroid already running on the same configuration:")
        for proc in processes:
            print(" ".join(proc.info["cmdline"]) + f" -> {proc.pid}")
        return True
    return False


class FileBuilder:
    def __init__(self, to_path, last_modified, file_id, tot_chunks, file_size=0):
        self.to_path = to_path
        os.makedirs(os.path.dirname(to_path), exist_ok=True)
        self.last_modified = datetime.fromisoformat(last_modified).timestamp()
        self.file_id = file_id
        self.file_size = file_size
        self.tot_chunks = tot_chunks
    
    def add_part(self, encoded):
        chunk = base64.b64decode(encoded)
        with open(self.to_path + TEMP_EXT, "ab") as f:
            f.write(chunk)
    
    def get_chunk(self, index):
        CHUNK_SIZE = 256 * 1024
        offset = index * CHUNK_SIZE
        if offset >= self.file_size:
            raise ValueError("Chunk index out of range")

        retries = 5
        for _ in range(retries):
            try:
                with open(self.to_path, "rb") as f:
                    f.seek(offset)
                    chunk = f.read(CHUNK_SIZE)
                return base64.b64encode(chunk).decode("ascii")
            except:
                time.sleep(0.05)
        return 1
    
    def close(self):
        shutil.move(self.to_path + TEMP_EXT, self.to_path)
        os.utime(self.to_path, (self.last_modified, self.last_modified))


def parse_device_info():
    machine = platform.machine()
    processor = platform.processor()

    return (
        f"Machine: {machine} - "
        f"Processor: {processor}"
    )


def get_memory_consumption(root):
    usage = shutil.disk_usage(root)

    total = usage.total
    used = usage.used
    percent = f"{int((used / total) * 100)}%"

    return used, total, percent


def list_remote_files(path):
    files_to_add = []
    for root_, _, files in os.walk(path):
        for name in files:
            full_path = os.path.join(root_, name)
            st = os.stat(full_path)
            size = st.st_size
            date = datetime.fromtimestamp(st.st_mtime).isoformat()
            files_to_add.append([full_path, date, size])
    return files_to_add


def get_full_remote_sync_md(remote_path):
    md_path = os.path.join(remote_path, SYNC_MD_FILE)
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    result = {}
    if os.path.exists(md_path):
        try:
            with open(md_path, "r", encoding="utf-8") as file:
                result = json.load(file)
        except:
            result = {}
    return result


def delete_file_from_remote(remote_path):
    if os.path.exists(remote_path):
        try:
            os.remove(remote_path)
        except:
            return 1
    return 0


def copy_file_to_local(remote_path):
    global current_fb
    st = os.stat(remote_path)
    last_modified = datetime.fromtimestamp(st.st_mtime).isoformat()
    CHUNK_SIZE = 256 * 1024
    file_size = os.path.getsize(remote_path)
    total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    file_id = uuid.uuid4().hex
    data = {"last_modified": last_modified, "file_id": file_id, "tot_chunks": total_chunks}
    current_fb = FileBuilder(remote_path, last_modified, file_id, total_chunks, file_size=file_size)
    return data


def get_file_chunk(remote_path, index):
    global current_fb
    if not current_fb or current_fb.to_path != remote_path:
        return
    return current_fb.get_chunk(index)


def copy_file_to_remote(to_path, last_modified, file_id, index, tot_chunks, encoded):
    global current_fb
    if index == 0:
        current_fb = FileBuilder(to_path, last_modified, file_id, tot_chunks)
    current_fb.add_part(encoded)
    if index == tot_chunks - 1:
        current_fb.close()
        current_fb = None
    return 0


def move_file_from_remote_to_remote(src_path, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        shutil.move(src_path, dest_path)
    except:
        return 1
    return 0


async def receive_messages(ws):
    """Continuously receive server messages."""
    try:
        async for data in ws:
            reply = None
            arg_lst = []
            try:
                data_json = json.loads(data)
                for arg in ["path", "from_path", "to_path"]:
                    value = data_json.get(arg, None)
                    if value is not None:
                        arg_lst.append(f"{arg}: {value}")
                if data_json.get("request") == "parse_device_info":
                    reply = parse_device_info()
                elif data_json.get("request") == "get_memory_consumption":
                    reply = get_memory_consumption(data_json.get("root"))
                elif data_json.get("request") == "list_remote_files":
                    reply = list_remote_files(data_json.get("path"))
                elif data_json.get("request") == "get_full_remote_sync_md":
                    reply = get_full_remote_sync_md(data_json.get("path"))
                elif data_json.get("request") == "delete_file_from_remote":
                    reply = delete_file_from_remote(data_json.get("path"))
                elif data_json.get("request") == "copy_file_to_local":
                    reply = copy_file_to_local(data_json.get("from_path"))
                elif data_json.get("request") == "get_file_chunk":
                    reply = get_file_chunk(data_json.get("from_path"), data_json.get("index"))
                elif data_json.get("request") == "copy_file_to_remote":
                    args = ("to_path", "last_modified", "file_id", "index", "tot_chunks", "encoded")
                    reply = copy_file_to_remote(**{k: data_json.get(k) for k in args})
                elif data_json.get("request") == "move_file_from_remote_to_remote":
                    reply = move_file_from_remote_to_remote(data_json.get("from_path"), data_json.get("to_path"))
            except:
                pass
            
            if reply is not None:
                arg_str = " -> " + ", ".join(arg_lst) if len(arg_lst) else ""
                print(f"{data_json.get('request')!r:<{30}}{arg_str}")
                struct_data = json.dumps({"request_id": data_json["request_id"], "reply": reply})
                await ws.send(struct_data)
    except websockets.ConnectionClosed:
        print("Connection closed by server")


async def connect_and_run(url, ssl_context):
    while True:
        try:
            async with websockets.connect(
                f"wss://{url}",
                ssl=ssl_context,
                additional_headers={"X-Client-Name": DEVICE_ID},
                max_size=None,
                max_queue=None) as ws:
                print("Connected to server")
                await asyncio.gather(receive_messages(ws))

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            print("Connection error:", e)
            await asyncio.sleep(5)


async def main():
    global DEVICE_ID, URL
    DEVICE_ID = sys.argv[1]
    if check_if_process_already_running(Path(__file__).stem + ".py", DEVICE_ID):
        sys.exit(1)
    url = f"{socket.gethostbyname('cyanroomserver.duckdns.org')}:443"
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    await connect_and_run(url, ssl_context)


if __name__ == "__main__":
    asyncio.run(main())

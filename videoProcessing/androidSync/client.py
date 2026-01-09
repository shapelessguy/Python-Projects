import asyncio
import ssl
import websockets
import json
import os
import stat
import platform
import shutil
import socket
from datetime import datetime

SYNC_MD_FILE = ".syncmd.json"
SERVER_PORT = 10001
DEVICE_ID = "DLR"
HOSTNAME = socket.gethostbyname("cyanroomserver.duckdns.org")
HOSTNAME = "localhost"
url = f"{HOSTNAME}:{SERVER_PORT}"

ssl_context = ssl.SSLContext()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
pending_op = None


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
    global pending_op
    st = os.stat(remote_path)
    last_modified = datetime.fromtimestamp(st.st_mtime).isoformat()
    pending_op = {"op": "copy_file_to_local", "from_path": remote_path}
    return last_modified

def copy_file_to_remote(remote_path, last_modified):
    global pending_op
    pending_op = {"op": "copy_file_to_remote", "to_path": remote_path, "last_modified": last_modified}
    return 0

def move_file_from_remote_to_remote(src_path, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        shutil.move(src_path, dest_path)
    except:
        return 1
    return 0

def manage_data(data):
    global pending_op
    if not pending_op:
        return

    if pending_op["op"] == "copy_file_to_remote":
        filepath = pending_op["to_path"]
        last_modified = pending_op["last_modified"]
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        print("Writing on:", filepath)
        
        try:
            with open(filepath, "wb") as f:
                f.write(data)
        except:
            try:
                if os.name == "nt" and os.path.exists(filepath):
                    os.chmod(filepath, stat.S_IWRITE)
                    os.system(f'attrib -H -S "{filepath}"')
                with open(filepath, "wb") as f:
                    f.write(data)
            except:
                pass

        timestamp = datetime.fromisoformat(last_modified).timestamp()
        os.utime(filepath, (timestamp, timestamp))
        pending_op = None

async def send_file(ws, filepath):
    print("Sending from:", filepath)
    try:
        with open(filepath, "rb") as f:
            data = f.read()
            await ws.send(data)
    except:
        pass

async def receive_messages(ws):
    """Continuously receive server messages."""
    try:
        async for data in ws:
            reply = None
            try:
                data_json = json.loads(data)
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
                elif data_json.get("request") == "copy_file_to_remote":
                    reply = copy_file_to_remote(data_json.get("to_path"), data_json.get("last_modified"))
                elif data_json.get("request") == "move_file_from_remote_to_remote":
                    reply = move_file_from_remote_to_remote(data_json.get("from_path"), data_json.get("to_path"))
                else:
                    manage_data(data)
            except:
                manage_data(data)
            
            if reply is not None:
                print(f"replied to {data_json.get('request')}")
                await ws.send(json.dumps({"request_id": data_json["request_id"], "reply": reply}))
            
            if pending_op and pending_op["op"] == "copy_file_to_local":
                await send_file(ws, pending_op["from_path"])
    except websockets.ConnectionClosed:
        print("Connection closed by server")


async def connect_and_run(url, ssl_context):
    while True:
        try:
            async with websockets.connect(f"wss://{url}", ssl=ssl_context, additional_headers={"X-Client-Name": DEVICE_ID}) as ws:
                print("Connected to server")
                await asyncio.gather(receive_messages(ws))

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            print("Connection error:", e)
            await asyncio.sleep(5)

async def main():
    await connect_and_run(url, ssl_context)

if __name__ == "__main__":
    asyncio.run(main())

# async def send_file(file_path: str):
#     """Send a file over WSS with its filename first."""
#     filename = os.path.basename(file_path)

#     for _ in range(100):
#         try:
#             async with websockets.connect(f"wss://{url}", ssl=ssl_context) as ws:
#                 # Send filename first as JSON
#                 await ws.send(json.dumps({"filename": filename}))
                
#                 # Send file content as binary
#                 with open(file_path, "rb") as f:
#                     data = f.read()
#                 await ws.send(data)
                
#                 # Receive server confirmation
#                 reply = await ws.recv()
#                 print(f"Server reply: {reply}")
#         except Exception as e:
#             print("Miss:", e)
#         time.sleep(5)

# if __name__ == "__main__":
#     file_path = r"C:\Users\cian_cl\Documents\DLR documents\cv.pdf"
#     asyncio.run(send_file(file_path))

import asyncio
import json
import websockets
import uuid
import os
import stat


class WebSocketManager:
    def __init__(self):
        self._clients = {}
        self._lock = asyncio.Lock()
        self._pending = {}
        self.save_to = None

    async def register(self, ws, client_name: str):
        async with self._lock:
            self._clients[ws] = client_name

    async def unregister(self, ws):
        async with self._lock:
            self._clients.pop(ws, None)

    async def send(self, ws, message: dict):
        if ws.closed:
            return
        await ws.send(json.dumps(message))

    async def broadcast(self, message: dict):
        dead = []
        async with self._lock:
            for ws in self._clients:
                try:
                    await ws.send(json.dumps(message))
                except websockets.ConnectionClosed:
                    dead.append(ws)

            for ws in dead:
                self._clients.pop(ws, None)

    async def client_count(self):
        async with self._lock:
            return len(self._clients)

    async def list_clients(self):
        async with self._lock:
            return list(self._clients.values())

    async def send_to_client(self, client_name: str, message: any, timeout: float) -> bool:
        request_id = uuid.uuid4().hex
        if type(message) == dict:
            message["request_id"] = request_id
            message = json.dumps(message)

        fut = asyncio.get_running_loop().create_future()
        self._pending[request_id] = fut

        async with self._lock:
            for ws, name in self._clients.items():
                if name == client_name:
                    await ws.send(message)
                    break
            else:
                self._pending.pop(request_id, None)
                return None
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(request_id, None)

    def save_file(self, data):
        if self.save_to is not None:
            filepath = self.save_to["path"]
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
            timestamp = self.save_to["last_modified"].timestamp()
            os.utime(filepath, (timestamp, timestamp))
            self.save_to = None

    async def handle_response(self, message: any):
        try:
            data = json.loads(message)
            request_id = data.get("request_id")
            if request_id in self._pending:
                self._pending[request_id].set_result(data)
            else:
                self.save_file(message)
        except:
            self.save_file(message)


import asyncio
import ssl
import socket
import websockets
import json
import sys
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import aiohttp

port = 12312
client = sys.argv[1] if len(sys.argv) > 1 else "default_llm_client"
target = "llm_provider"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
pending = {}
ws_connection = None

async def handle_llm_instruct(ws, sender, content, request_id):
    print(f"sender={sender}, request_id={request_id}")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://autoreq.dlr.de/litellm/v1/chat/completions",
            headers={"Authorization": "Bearer autoreq-admin", "Content-Type": "application/json"},
            json=content
        ) as resp:
            result = await resp.json()

    await ws.send(json.dumps({
        "llm_instruct": {"sender": client, "content": result, "request_id": request_id},
        "target": sender,
        "request_id": request_id
    }))
    
async def listen(ws):
    async for message in ws:
        data = json.loads(message)
        request_id = data.get("request_id")
        sender = data.get("sender")
        content = data.get("content")

        if request_id in pending:
            pending[request_id].set_result(data)
        elif sender and content and request_id:
            await handle_llm_instruct(ws, sender, content, request_id)
        else:
            print(f"Received: {message}")

async def connect():
    global ws_connection
    while True:
        try:
            ip = socket.gethostbyname("cyanroomserver.duckdns.org")
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            headers = {"X-Client-Name": client}
            async with websockets.connect(f"wss://{ip}", ssl=ssl_ctx, additional_headers=headers) as ws:
                ws_connection = ws
                print("Connected!")
                await listen(ws)
        except Exception as e:
            ws_connection = None
            print(f"Connection lost: {e}, retrying in 5 seconds...")
            await asyncio.sleep(5)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    if ws_connection is None:
        return JSONResponse({"error": "not connected"}, status_code=503)

    body = await request.body()
    request_id = str(uuid.uuid4())
    future = asyncio.get_running_loop().create_future()
    pending[request_id] = future

    await ws_connection.send(json.dumps({
        "llm_instruct": {
            "sender": client,
            "method": request.method,
            "path": path,
            "content": json.loads(body) if body else {},
            "request_id": request_id
        },
        "target": target,
        "request_id": request_id
    }))

    try:
        result = await asyncio.wait_for(future, timeout=30)
        return JSONResponse(result.get("content", {}))
    except asyncio.TimeoutError:
        return JSONResponse({"error": "timeout"}, status_code=504)
    finally:
        pending.pop(request_id, None)

async def main():
    asyncio.create_task(connect())
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()

asyncio.run(main())
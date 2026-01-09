import asyncio
import ssl
import websockets
import os
import json

PORT = 443

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(certfile=os.path.join(os.path.dirname(__file__), "cert.pem"), keyfile=os.path.join(os.path.dirname(__file__), "key.pem"))
signal = None


async def handle(ws):
    global signal
    client_name = ws.request.headers.get("X-Client-Name")
    await signal['ws_manager'].register(ws, client_name)
    print(f"Client {client_name} connected")

    try:
        async for message in ws:
            await signal['ws_manager'].handle_response(message)

    except websockets.ConnectionClosed:
        pass
    finally:
        await signal['ws_manager'].unregister(ws)
        print("Client disconnected")


async def run_server(signal_):
    global signal
    signal = signal_
    stop_event = signal["kill_server"]
    async with websockets.serve(
        handle,
        "0.0.0.0",
        PORT,
        ssl=ssl_context,
        max_size=None,
        max_queue=None,
        read_limit=2**20,
        write_limit=2**20
    ):
        print(f"WSS server listening on port {PORT}")
        await stop_event.wait()

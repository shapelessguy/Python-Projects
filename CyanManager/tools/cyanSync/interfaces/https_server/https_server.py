import ssl
import websockets
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from https_client import pprint

PORT = 443

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(certfile=os.path.join(os.path.dirname(__file__), "cert.pem"), keyfile=os.path.join(os.path.dirname(__file__), "key.pem"))
signal = None


async def handle(ws):
    global signal
    client_name = ws.request.headers.get("X-Client-Name")
    await signal['ws_manager'].register(ws, client_name)
    pprint(f"Client {client_name} connected")

    try:
        async for message in ws:
            await signal['ws_manager'].handle_response(message)

    except websockets.ConnectionClosed:
        await signal['ws_manager'].unregister(ws)
        pprint(f"Client {client_name} disconnected")
    except:
        import traceback
        print(traceback.format_exc())


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
        ping_interval=None,
        ping_timeout=None,
    ):
        pprint(f"WSS server listening on port {PORT}")
        await stop_event.wait()

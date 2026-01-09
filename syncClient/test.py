import asyncio
import ssl
import websockets
import os
import json

PORT = 10001
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(certfile=os.path.join(os.path.dirname(__file__), "cert.pem"), keyfile=os.path.join(os.path.dirname(__file__), "key.pem"))

async def handle(websocket):
    print("Client connected")
    filename = None
    try:
        async for message in websocket:
            if isinstance(message, str):
                # Try to parse a JSON message for filename
                try:
                    info = json.loads(message)
                    filename = info.get("filename")
                    print(f"Client says filename: {filename}")
                except json.JSONDecodeError:
                    print(f"Received text: {message}")
            else:
                # Binary message = file content
                if not filename:
                    filename = "uploaded_ws_file"
                filepath = os.path.join(UPLOAD_DIR, filename)
                with open(filepath, "wb") as f:
                    f.write(message)
                await websocket.send(b"OK")
                print(f"Saved file {filepath}")
                filename = None  # reset for next file
    except websockets.ConnectionClosedOK:
        print("Client disconnected gracefully")
    except Exception as e:
        print("Connection handler failed:", e)

# Main server loop
async def main():
    # Use async with + serve_forever like the example you provided
    async with websockets.serve(
        handle, "0.0.0.0", PORT, ssl=ssl_context
    ) as server:
        print(f"WSS server listening on port {PORT}")
        await server.serve_forever()  # runs indefinitely

asyncio.run(main())

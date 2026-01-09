import asyncio
import ssl
import websockets
import json
import os
import time
import socket


# Server URL
url = f"{socket.gethostbyname("cyanroomserver.duckdns.org")}:443"

# Disable certificate verification for testing
ssl_context = ssl.SSLContext()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

async def send_file(file_path: str):
    """Send a file over WSS with its filename first."""
    filename = os.path.basename(file_path)

    for _ in range(100):
        try:
            async with websockets.connect(f"wss://{url}", ssl=ssl_context) as ws:
                # Send filename first as JSON
                await ws.send(json.dumps({"filename": filename}))
                
                # Send file content as binary
                with open(file_path, "rb") as f:
                    data = f.read()
                await ws.send(data)
                
                # Receive server confirmation
                reply = await ws.recv()
                print(f"Server reply: {reply}")
        except:
            print("Miss")
        time.sleep(5)

if __name__ == "__main__":
    file_path = r"C:\Users\cian_cl\Documents\DLR documents\cv.pdf"
    asyncio.run(send_file(file_path))

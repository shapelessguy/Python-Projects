"""Run the API on the port from secrets.json:  python -m api   (from the project root)"""
import uvicorn

from api.config import API_PORT, HOST

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=HOST,
        port=API_PORT,
        reload=True,
        reload_includes=["*.py", "secrets.json"],
        # A restart (a reload, above) waits for the requests still open to
        # finish — and every open page keeps one open for up to 25 s on
        # purpose (api/longpoll.py). Cut them after 2 s instead: the pages
        # simply ask again.
        timeout_graceful_shutdown=2,
    )

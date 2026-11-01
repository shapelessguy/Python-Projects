"""Run the API on the port from config.json:  python -m api   (from the project root)"""
import uvicorn

from api.config import API_PORT, HOST

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=HOST,
        port=API_PORT,
        reload=True,
        # Only the project is watched: a users.json moved elsewhere by
        # config.json's USERS_FILE takes a restart to pick up an edit, since
        # watching its folder would watch everything under it as well.
        reload_includes=["*.py", "config.json", "secrets.json", "users.json"],
        # A restart (a reload, above) waits for the requests still open to
        # finish — and every open page keeps one open for up to 25 s on
        # purpose (api/longpoll.py). Cut them after 2 s instead: the pages
        # simply ask again.
        timeout_graceful_shutdown=2,
    )

"""Run the API on the port from .env:  python -m api   (from the project root)"""
import uvicorn

from api.config import API_PORT, HOST

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=HOST,
        port=API_PORT,
        reload=True,
        reload_includes=["*.py", "users.json", ".env"],
    )

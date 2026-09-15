"""Food service — a plug-and-play router module.

Contract picked up by ``api/main.py`` auto-discovery:
  * ``router``        — mounted under its own /api prefix
  * ``VERSION_NAMES`` — keys it contributes to GET /api/version + X-*-Version
  * ``init()``        — create its own storage (own SQLite file + image dir)
  * ``versions(user)``— that user's current counter(s), merged into GET /api/version

Every row and every image is scoped to the authenticated user; nothing here
touches the diary schema.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.auth import require_user
from api.services import food

router = APIRouter(prefix="/api/food", tags=["food"])

VERSION_NAMES = ["food"]
PANEL = "food"  # gates the whole router behind permissions.visibility -- see api/auth.py


def init() -> None:
    food.init_db()


def versions(user: str | None) -> dict[str, int]:
    return {"food": food.version(user)} if user else {"food": 0}


# ── models ───────────────────────────────────────────────────────────────
class DishIn(BaseModel):
    name: str = Field(min_length=1)
    category: str = ""
    rating: int = 0
    image_url: str | None = None
    url: str = ""


class DishPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    rating: int | None = None
    image_url: str | None = None
    url: str | None = None
    instructions: str | None = None  # manual edit from the Instructions modal
    ingredients: str | None = None  # manual edit from the Ingredients modal (JSON text)


# ── dishes ───────────────────────────────────────────────────────────────
@router.get("/dishes")
async def list_dishes(user: str = Depends(require_user)):
    return await run_in_threadpool(food.get_all, user)


@router.post("/dishes")
async def create_dish(body: DishIn, user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(
            food.create_dish, user, body.name, body.category, body.rating, body.image_url, body.url
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # image download / network
        raise HTTPException(502, f"could not save dish image: {e}")


@router.patch("/dishes/{dish_id}")
async def patch_dish(dish_id: int, body: DishPatch, user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(
            food.update_dish, user, dish_id, body.model_dump(exclude_unset=True)
        )
    except KeyError:
        raise HTTPException(404, f"no dish {dish_id}")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(502, f"could not update dish: {e}")


@router.delete("/dishes/{dish_id}")
async def delete_dish(dish_id: int, user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(food.delete_dish, user, dish_id)
    except KeyError:
        raise HTTPException(404, f"no dish {dish_id}")


# ── image search (server-side proxy; the serper key never reaches clients) ─
@router.get("/image-search")
async def image_search(
    q: str = Query(..., min_length=1),
    num: int = Query(60, ge=1, le=100),
    _user: str = Depends(require_user),
):
    try:
        return {"images": await run_in_threadpool(food.search_images, q, num)}
    except Exception as e:
        raise HTTPException(502, f"image search failed: {e}")


# ── serve stored dish images (shared catalogue; auth enforced at include) ─
@router.get("/images/{name}")
def get_image(name: str):
    path = food.image_path(name)
    if path is None:
        raise HTTPException(404, "no such image")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800, immutable"})

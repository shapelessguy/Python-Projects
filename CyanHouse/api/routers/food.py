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
    image_url: str | None = None  # picked from the image search, downloaded
    image_data: str | None = None  # uploaded: a data: URL
    url: str = ""
    lang: str = "en"  # the language name and category are written in


class DishPatch(BaseModel):
    name: str | None = None
    category: str | None = None
    rating: int | None = None
    image_url: str | None = None  # picked from the image search, downloaded
    image_data: str | None = None  # uploaded: a data: URL
    url: str | None = None
    instructions: str | None = None  # manual edit from the Instructions modal
    lang: str | None = None  # the language name / category / instructions are written in (default "en")
    # The facts, from the dish view (food._fact_changes); null clears one.
    prep_min: int | None = None
    cook_min: int | None = None
    total_min: int | None = None
    difficulty: str | None = None
    ingredients: str | None = None  # manual edit from the Ingredients modal (JSON text)


# ── dishes ───────────────────────────────────────────────────────────────
@router.get("/dishes")
async def list_dishes(user: str = Depends(require_user)):
    return await run_in_threadpool(food.get_all, user)


@router.post("/dishes")
async def create_dish(body: DishIn, user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(
            food.create_dish, user, body.name, body.category, body.rating, body.image_url, body.url,
            body.lang, body.image_data,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    except food.TranslationError as e:
        raise HTTPException(502, str(e))
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
    except food.TranslationError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        raise HTTPException(502, f"could not update dish: {e}")


@router.post("/dishes/{dish_id}/import")
async def import_recipe(dish_id: int, user: str = Depends(require_user)):
    """Import (again) the recipe the dish links to: its ingredients,
    instructions and facts, on a job of its own (food_import.py)."""
    try:
        return await run_in_threadpool(food.import_recipe, user, dish_id)
    except KeyError:
        raise HTTPException(404, f"no dish {dish_id}")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/dishes/{dish_id}")
async def delete_dish(dish_id: int, user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(food.delete_dish, user, dish_id)
    except KeyError:
        raise HTTPException(404, f"no dish {dish_id}")


# ── the ingredient list ────────────────────────────────────────────────────
class Conversion(BaseModel):
    """a_qty a_unit = b_qty b_unit, between two of mass, volume and pieces."""
    a_qty: float
    a_unit: str
    b_qty: float
    b_unit: str


class IngredientPatch(BaseModel):
    name: str | None = None
    # All of its conversions, replacing what it had ([] clears them).
    conversions: list[Conversion] | None = None


@router.patch("/ingredients/{ingredient_id}")
async def patch_ingredient(ingredient_id: int, body: IngredientPatch, user: str = Depends(require_user)):
    """Rename an ingredient (into another one, merging them), or set its
    conversions."""
    convs = None if body.conversions is None else [c.model_dump() for c in body.conversions]
    try:
        return await run_in_threadpool(food.update_ingredient, user, ingredient_id, body.name, convs)
    except food.IngredientError as e:
        raise HTTPException(e.status_code, str(e))


@router.delete("/ingredients/{ingredient_id}")
async def delete_ingredient(ingredient_id: int, user: str = Depends(require_user)):
    try:
        return await run_in_threadpool(food.delete_ingredient, user, ingredient_id)
    except food.IngredientError as e:
        raise HTTPException(e.status_code, str(e))


# ── the grocery list (which dishes are on it is the client's) ─────────────
class GroceryIn(BaseModel):
    items: dict[int, float]  # dish id -> how much of it, in its yield's unit


@router.post("/grocery")
async def grocery(body: GroceryIn, _user: str = Depends(require_user)):
    return {"lines": await run_in_threadpool(food.grocery, body.items)}


# ── recipe pages: GialloZafferano search, a picked page fetched and kept ──
@router.get("/recipe-search")
async def recipe_search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1, le=50),
    _user: str = Depends(require_user),
):
    try:
        return await run_in_threadpool(food.recipe_search, q, page)
    except Exception as e:
        raise HTTPException(502, f"recipe search failed: {e}")


class RecipePageIn(BaseModel):
    url: str = Field(min_length=1)


@router.post("/recipe-page")
async def recipe_page(body: RecipePageIn, _user: str = Depends(require_user)):
    """Fetch a recipe page and keep it (HTML and schema.org metadata); what
    it says comes back for the dish form."""
    try:
        return {"recipe": await run_in_threadpool(food.fetch_recipe_page, body.url)}
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(502, f"could not fetch the recipe: {e}")


@router.get("/recipe-page")
async def get_recipe_page(url: str = Query(..., min_length=1), _user: str = Depends(require_user)):
    """A recipe page as kept (fetched now if it isn't yet): what it says, and
    its preparation -- the recipe viewer."""
    try:
        return await run_in_threadpool(food.recipe_page, url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(502, f"could not fetch the recipe: {e}")


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

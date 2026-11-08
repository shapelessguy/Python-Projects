"""Finance — Personal's Finance tab: categories, forecasts and payments, all
per user. Self-contained module: own DB, own per-user counter — see
api/services/finance.py for the model.

Contract picked up by ``api/main.py`` auto-discovery:
  * ``router``        — mounted under /api/finance. GET / is the snapshot
                        (its version, categories, forecasts, every payment);
                        every change replies with the same snapshot.
  * ``VERSION_NAMES`` — "finance", per user
  * ``init()``        — creates the schema and starts the daily job below

Daily job (a daemon thread, so a reload simply ends it): once at start, then
every day at DAILY_AT — after the ECB publishes, around 16:00 CET — it writes
the forecasts' payments that have come due and fetches the missing EUR/USD
rates. Both remember where they stopped, so an extra run writes nothing twice.
"""
import threading
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_user
from api.models import FinanceCategoryBody, FinanceOrderBody, FinanceExecutedBody, FinanceForecastBody
from api.services import finance

router = APIRouter(prefix="/api/finance", tags=["finance"])

VERSION_NAMES = ["finance"]
PANEL = "personal"  # gates the whole router behind permissions.visibility -- see api/auth.py

DAILY_AT = "17:00"



def init() -> None:
    finance.init_db()
    threading.Thread(target=_daily_loop, name="finance-daily", daemon=True).start()


def versions(user: str | None) -> dict[str, int]:
    if not user:
        return {"finance": 0}
    with finance.connect() as conn:
        return {"finance": finance.version(conn, user)}


def _seconds_until(hhmm: str) -> float:
    now = datetime.now()
    h, m = map(int, hhmm.split(":"))
    at = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if at <= now:
        at += timedelta(days=1)
    return (at - now).total_seconds()


def _daily_loop() -> None:
    while True:
        try:
            with finance.connect() as conn:
                finance.run_forecasts(conn)
        except Exception as e:
            print(f"[finance] forecasts run failed: {e!r}")
        try:
            finance.update_fx()
        except Exception as e:   # offline: the next run catches up
            print(f"[finance] fx update failed: {e!r}")
        time.sleep(_seconds_until(DAILY_AT))


# ── endpoints ──────────────────────────────────────────────────────────────
def _snapshot(conn, user: str) -> dict:
    return {
        # The finance counter this reflects: the client skips the refetch
        # its own change's bump would otherwise cause.
        "version": finance.version(conn, user),
        "categories": finance.list_categories(conn, user),
        "forecasts": finance.list_forecasts(conn, user),
        "executed": finance.list_executed(conn, user),
    }


def _change(user: str, fn, *args) -> dict:
    """Run one change, then reply with the snapshot."""
    try:
        with finance.connect() as conn:
            fn(conn, user, *args)
            return _snapshot(conn, user)
    except finance.FinanceError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


def _fields(body) -> dict:
    return body.model_dump(exclude_unset=True)


@router.get("")
def get_snapshot(user: str = Depends(require_user)):
    with finance.connect() as conn:
        return _snapshot(conn, user)


@router.post("/categories")
def create_category(body: FinanceCategoryBody, user: str = Depends(require_user)):
    return _change(user, finance.create_category, _fields(body))


@router.put("/categories/order")
def order_categories(body: FinanceOrderBody, user: str = Depends(require_user)):
    return _change(user, finance.move_categories, body.parent_id, body.ids)


@router.patch("/categories/{cat_id}")
def patch_category(cat_id: int, body: FinanceCategoryBody, user: str = Depends(require_user)):
    return _change(user, finance.update_category, cat_id, _fields(body))


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, user: str = Depends(require_user)):
    return _change(user, finance.delete_category, cat_id)


@router.post("/forecasts")
def create_forecast(body: FinanceForecastBody, user: str = Depends(require_user)):
    return _change(user, finance.create_forecast, _fields(body))


@router.patch("/forecasts/{row_id}")
def patch_forecast(row_id: int, body: FinanceForecastBody, user: str = Depends(require_user)):
    return _change(user, finance.update_forecast, row_id, _fields(body))


@router.delete("/forecasts/{row_id}")
def delete_forecast(row_id: int, user: str = Depends(require_user)):
    return _change(user, finance.delete_forecast, row_id)


@router.post("/executed")
def create_executed(body: FinanceExecutedBody, user: str = Depends(require_user)):
    return _change(user, finance.create_executed, _fields(body))


@router.patch("/executed/{row_id}")
def patch_executed(row_id: int, body: FinanceExecutedBody, user: str = Depends(require_user)):
    return _change(user, finance.update_executed, row_id, _fields(body))


@router.delete("/executed/{row_id}")
def delete_executed(row_id: int, user: str = Depends(require_user)):
    return _change(user, finance.delete_executed, row_id)

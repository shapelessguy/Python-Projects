"""Stocks -- the Environment panel's Stocks tab, on the Tradegate store.

Contract picked up by ``api/main.py`` auto-discovery:
  * ``router``        — mounted under /api/stocks
  * ``VERSION_NAMES`` — "stocks", per user: moves when one of *their* stocks
                        gets new ticks or its history, or their list changes.
                        Each stock in GET /api/stocks also carries its own
                        `rev`, moved only by its own ticks or history, so a
                        page asks just for the new part of the charts that
                        changed (GET /series with `since`).
  * ``init()``        — starts the two background jobs below

Background jobs (daemon threads, so a reload simply ends them):
  * the tick recorder (api/services/tradegate.py) -- every watched ISIN,
    every 30 s in trading hours. If another recorder holds the folder (one
    started from the CLI), this one waits and takes over when it stops.
  * the daily history (api/services/tradegate_history.py) -- once at start
    (a no-op for a stock already current) and every evening at HISTORY_AT.
    A stock just added gets its history at once, in its own thread.

Portfolio (/api/stocks/portfolio): the user's buys and sells, each at the
price per share given with it (or its day's close), and what they come to --
now and on every trading day since the first: average cost, realised and
unrealised profit, tax on the net profit at the user's rate. It has its own
endpoints so a page showing only the charts never asks for it.

Every read is scoped to what the user watches or holds (tradegate_store).
"""
import bisect
import threading
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.auth import require_user
from api.services import tradegate, tradegate_history
from api.services import tradegate_store as store

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

VERSION_NAMES = ["stocks"]
PANEL = "environment"  # gates the whole router behind permissions.visibility -- see api/auth.py

HISTORY_AT = "22:30"

# In-process counters: the recorder runs in this process, so nothing else
# needs to see them. A restart starts again from 0, which reads as a change.
# They are read by every held /api/version request twice a second, so the
# watchlists they need are kept here too rather than asked of the DB.
_version_lock = threading.Lock()
_history_lock = threading.Lock()   # one onvista download at a time
_loading: set[str] = set()         # ISINs whose first history download is running
_revs: dict[str, int] = {}         # per ISIN: moves with its new ticks / history
_user_versions: dict[str, int] = {}
_lists: dict[str, set[str]] | None = None   # user -> ISINs watched or held, loaded on first use


def _watchlists() -> dict[str, set[str]]:
    global _lists
    if _lists is None:
        _lists = store.followed()
    return _lists


def _forget_lists() -> None:
    """A list or a portfolio changed: load them again when next needed."""
    global _lists
    with _version_lock:
        _lists = None


def _bump(isins=(), users=()) -> None:
    """Stocks that changed (their rev moves, and so does every watcher's
    counter) and/or users whose list changed."""
    isins = set(isins)
    with _version_lock:
        for isin in isins:
            _revs[isin] = _revs.get(isin, 0) + 1
        moved = set(users) | {u for u, own in _watchlists().items() if own & isins}
        for user in moved:
            _user_versions[user] = _user_versions.get(user, 0) + 1


def versions(user: str | None) -> dict[str, int]:
    return {"stocks": _user_versions.get(user, 0) if user else 0}


def init() -> None:
    store.db()   # create the schema before the first request
    threading.Thread(target=_record, name="tradegate-recorder", daemon=True).start()
    threading.Thread(target=_history_loop, name="tradegate-history", daemon=True).start()


def _record() -> None:
    told = False
    while True:
        try:
            tradegate.run(on_trades=_bump)
        except tradegate.RecorderBusy as e:
            if not told:
                print(f"[stocks] {e} Waiting for it to stop.")
                told = True
        except Exception as e:
            print(f"[stocks] recorder stopped: {e!r}; restarting in 60 s")
        time.sleep(60)


def _update_history(isins) -> None:
    for isin in isins:
        with _history_lock:
            try:
                tradegate_history.update(isin)
            except Exception as e:   # keep going with the others
                print(f"[stocks] history {isin}: {e!r}")
    _bump(isins)


def _seconds_until(hhmm: str) -> float:
    now = datetime.now()
    h, m = map(int, hhmm.split(":"))
    at = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if at <= now:
        at += timedelta(days=1)
    return (at - now).total_seconds()


def _history_loop() -> None:
    while True:
        try:
            _update_history(store.all_watched())
        except Exception as e:
            print(f"[stocks] history run failed: {e!r}")
        time.sleep(_seconds_until(HISTORY_AT))


def _backfill(isin: str) -> None:
    try:
        _update_history([isin])
    finally:
        _loading.discard(isin)
        _bump([isin])


# ── endpoints ────────────────────────────────────────────────────────────
class StockIn(BaseModel):
    isin: str


class OrderIn(BaseModel):
    isins: list[str]


@router.get("")
def list_stocks(user: str = Depends(require_user)):
    stocks = store.summaries(user)
    for s in stocks:
        s["loading"] = s["isin"] in _loading
        s["rev"] = _revs.get(s["isin"], 0)
    return {"today": date.today().isoformat(), "stocks": stocks}


def _isin(raw: str) -> str:
    try:
        return store.normalise_isin(raw)
    except ValueError:
        raise HTTPException(422, f"not an ISIN: {raw.strip()}")


async def _watch(user: str, isin: str) -> dict:
    """Onto the user's list, its history downloaded if nobody had it yet."""
    # Check it is traded on Tradegate before it goes on any list.
    try:
        info = await run_in_threadpool(tradegate_history.lookup, isin)
    except LookupError:
        raise HTTPException(404, f"{isin} is not listed on Tradegate")
    except Exception as e:
        raise HTTPException(502, f"could not look up {isin}: {e}")
    store.watch(user, [isin])
    _forget_lists()
    if store.last_daily_date(isin) is None and isin not in _loading:
        _loading.add(isin)
        threading.Thread(target=_backfill, args=(isin,), name=f"history-{isin}", daemon=True).start()
    return info


@router.post("")
async def add_stock(body: StockIn, user: str = Depends(require_user)):
    isin = _isin(body.isin)
    info = await _watch(user, isin)
    _bump(users=[user])
    return {"isin": isin, "name": info.get("name") or isin}


@router.put("/order")
def reorder(body: OrderIn, user: str = Depends(require_user)):
    """The user's stocks in this order: the list, the charts and the picker."""
    try:
        store.reorder(user, body.isins)
    except ValueError as e:
        raise HTTPException(422, str(e))
    _bump(users=[user])
    return {}


@router.delete("/{isin}")
def remove_stock(isin: str, user: str = Depends(require_user)):
    """Off this user's list; the market data stays -- and keeps being collected
    while anyone watches or holds it."""
    store.unwatch(user, [_isin(isin)])
    _forget_lists()
    _bump(users=[user])
    return {}


def _num(v):
    """A number as short as JSON can say it: 33644.0 -> 33644, 516.70000001 -> 516.7."""
    if v is None:
        return None
    v = round(v, 4)
    return int(v) if v == int(v) else v


@router.get("/series")
def series(
    isins: str = Query(..., description="comma-separated ISINs"),
    start: str = Query("", description="daily only"),
    end: str = Query("", description="daily only"),
    resample: str = Query("daily", pattern="^(ticks|daily)$"),
    since: str = Query("", description="ticks: ISIN:last_trade_id,... -- only the trades after it"),
    user: str = Depends(require_user),
):
    """Only what a chart draws, and only the part the client lacks.

    `daily`: one bar per day from start to end (dates, inclusive), today's
    being the current price -- {index: [date], close, volume}. The client
    keeps what it has and asks for just the days it is missing, or for
    today alone to follow the price; weeks it sums itself.

    `ticks`: today's trades -- {day, time: ["HH:MM:SS.mmm"], close, volume,
    last_id}; with `since` only those after the trade id the client holds,
    which it appends."""
    cursors = dict(c.split(":", 1) for c in since.split(",") if ":" in c)
    out = {}
    for isin in (i.strip().upper() for i in isins.split(",") if i.strip()):
        if resample == "ticks":
            cursor = cursors.get(isin, "")
            after = int(cursor) if cursor.isdigit() else 0
            rows = store.read_ticks(user, isin, after)
            out[isin] = {"day": date.today().isoformat(),
                         "time": [r[1][11:] for r in rows],
                         "close": [_num(r[2]) for r in rows],
                         "volume": [_num(r[3]) for r in rows],
                         "last_id": rows[-1][0] if rows else after}
        else:
            bars = store.read_bars(user, isin, start or None, end or None)
            out[isin] = {"index": [b["date"] for b in bars],
                         "close": [_num(b["close"]) for b in bars],
                         "volume": [_num(b["volume"]) for b in bars]}
    return {"series": out}


# ── portfolio ────────────────────────────────────────────────────────────
class TransactionIn(BaseModel):
    isin: str
    date: str
    shares: float        # > 0 bought, < 0 sold
    amount: float | None = None  # paid / received for all the shares; None: at the day's close


class TaxIn(BaseModel):
    tax_rate: float


def _close_on(bars: list[dict], day: str):
    """The close of `day`, or of the last trading day before it."""
    k = bisect.bisect_right([b["date"] for b in bars], day)
    return bars[k - 1]["close"] if k else None


def _apply(h: dict, shares: float, p: float) -> None:
    """One transaction on a holding, at average cost."""
    if shares > 0:
        h["cost"] += p * shares
    elif h["shares"] > 0:
        avg = h["cost"] / h["shares"]
        h["realised"] += -shares * (p - avg)
        h["cost"] += shares * avg
    h["shares"] += shares


def _history(rows: list[dict], bars: dict, rate: float) -> dict:
    """Every trading day from the first transaction on: what the portfolio was
    worth at that day's closes, and what it had made. Transactions count from
    their day (a weekend's from the Monday)."""
    days = sorted({b["date"] for i in bars for b in bars[i]} | {r["date"] for r in rows})
    days = [d for d in days if d >= rows[0]["date"]] if rows else []
    keys = ("value", "invested", "realised", "unrealised", "profit", "tax", "net")
    out = {"index": [], **{k: [] for k in keys}}
    held: dict[str, dict] = {}
    # Each stock's close as of the day, walked forward with the days (one
    # pass over its bars, not a search per day).
    close: dict[str, float] = {}
    at = {i: 0 for i in bars}
    k = 0
    for d in days:
        while k < len(rows) and rows[k]["date"] <= d:
            r = rows[k]
            _apply(held.setdefault(r["isin"], {"shares": 0.0, "cost": 0.0, "realised": 0.0}),
                   r["shares"], r["price"])
            k += 1
        for i, b in bars.items():
            while at[i] < len(b) and b[at[i]]["date"] <= d:
                close[i] = b[at[i]]["close"]
                at[i] += 1
        if not any(i in close for i in held):
            continue   # a weekend before the first bar
        value = sum(h["shares"] * (close.get(i) or 0) for i, h in held.items())
        invested = sum(h["cost"] for h in held.values())
        realised = sum(h["realised"] for h in held.values())
        profit = realised + value - invested
        tax = max(profit, 0.0) * rate / 100
        out["index"].append(d)
        for key, v in zip(keys, (value, invested, realised, value - invested, profit, tax, profit - tax)):
            out[key].append(_num(round(v, 2)))
    return out


@router.get("/portfolio")
def portfolio(user: str = Depends(require_user)):
    """Transactions at their price (or their day's close), holdings at average
    cost, the totals, and their `history` day by day. A stock whose history is
    not there yet has no closes, and is left out of the totals (`incomplete`)."""
    rows = store.transactions(user)
    rate = store.tax_rate(user)
    bars = {}
    for isin in {r["isin"] for r in rows}:
        first = min(r["date"] for r in rows if r["isin"] == isin)
        start = (date.fromisoformat(first) - timedelta(days=14)).isoformat()
        bars[isin] = store.read_bars(user, isin, start)
    held: dict[str, dict] = {}
    unpriced = set()
    for r in rows:
        r["exact"] = r["price"] is not None
        p = r["price"] if r["exact"] else _close_on(bars[r["isin"]], r["date"])
        r["price"] = p
        h = held.setdefault(r["isin"], {"isin": r["isin"], "name": r["name"], "shares": 0.0,
                                        "cost": 0.0, "realised": 0.0})
        if p is None or not bars[r["isin"]]:
            unpriced.add(r["isin"])
            h["shares"] += r["shares"]
        else:
            _apply(h, r["shares"], p)
    holdings = []
    totals = {"invested": 0.0, "value": 0.0, "realised": 0.0, "unrealised": 0.0}
    for h in held.values():
        last = bars[h["isin"]][-1]["close"] if bars[h["isin"]] else None
        if abs(h["shares"]) < 1e-9:
            h["shares"] = h["cost"] = 0.0
        if h["isin"] in unpriced:
            holdings.append({**h, "shares": _num(h["shares"]), "cost": None, "realised": None,
                             "last": _num(last), "value": None, "unrealised": None})
            continue
        value = h["shares"] * last
        totals["invested"] += h["cost"]
        totals["value"] += value
        totals["realised"] += h["realised"]
        totals["unrealised"] += value - h["cost"]
        holdings.append({"isin": h["isin"], "name": h["name"], "shares": _num(h["shares"]),
                         "cost": _num(h["cost"]), "last": _num(last), "value": _num(value),
                         "realised": _num(h["realised"]), "unrealised": _num(value - h["cost"])})
    # Held first, biggest first; the ones sold off at the end.
    holdings.sort(key=lambda h: (not h["shares"], -(h["value"] or 0)))
    profit = totals["realised"] + totals["unrealised"]
    tax = max(profit, 0.0) * rate / 100
    history = _history([r for r in rows if r["isin"] not in unpriced],
                       {i: b for i, b in bars.items() if i not in unpriced}, rate)
    for r in rows:
        r["amount"] = _num(r["price"] * abs(r["shares"])) if r["price"] is not None else None
        r["price"] = _num(r["price"])
    return {
        "tax_rate": rate,
        "transactions": rows[::-1],   # newest first
        "holdings": holdings,
        "totals": {**{k: _num(v) for k, v in totals.items()},
                   "profit": _num(profit), "tax": _num(tax), "net": _num(profit - tax)},
        "history": history,
        "incomplete": bool(unpriced),
    }


async def _checked(body: "TransactionIn", user: str) -> tuple[str, str, float | None]:
    """The transaction's ISIN, day and price per share, once it makes sense.
    A stock neither watched nor held yet goes onto the watchlist first, so
    its chart -- and its prices -- get downloaded."""
    isin = _isin(body.isin)
    try:
        day = date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(422, f"not a date: {body.date}")
    if day > date.today():
        raise HTTPException(422, "that date is in the future")
    if not body.shares:
        raise HTTPException(422, "no shares")
    if body.amount is not None and body.amount <= 0:
        raise HTTPException(422, "the amount must be above 0")
    each = body.amount / abs(body.shares) if body.amount is not None else None
    if isin not in _watchlists().get(user, set()):
        await _watch(user, isin)
    return isin, day.isoformat(), each


@router.post("/portfolio")
async def add_transaction(body: TransactionIn, user: str = Depends(require_user)):
    isin, day, each = await _checked(body, user)
    try:
        store.add_transaction(user, isin, day, body.shares, each)
    except ValueError as e:
        raise HTTPException(422, str(e))
    _forget_lists()
    _bump(users=[user])
    return {}


@router.put("/portfolio/{tid}")
async def update_transaction(tid: int, body: TransactionIn, user: str = Depends(require_user)):
    isin, day, each = await _checked(body, user)
    try:
        if not store.update_transaction(user, tid, isin, day, body.shares, each):
            raise HTTPException(404, "no such transaction")
    except ValueError as e:
        raise HTTPException(422, str(e))
    _forget_lists()
    _bump(users=[user])
    return {}


@router.delete("/portfolio/{tid}")
def delete_transaction(tid: int, user: str = Depends(require_user)):
    try:
        if not store.delete_transaction(user, tid):
            raise HTTPException(404, "no such transaction")
    except ValueError as e:
        raise HTTPException(422, str(e))
    _forget_lists()
    _bump(users=[user])
    return {}


@router.put("/portfolio/tax")
def set_tax(body: TaxIn, user: str = Depends(require_user)):
    if not 0 <= body.tax_rate <= 100:
        raise HTTPException(422, "the tax rate is a percentage, 0 to 100")
    store.set_tax_rate(user, body.tax_rate)
    _bump(users=[user])
    return {}

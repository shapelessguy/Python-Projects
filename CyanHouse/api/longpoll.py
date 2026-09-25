"""Held requests: answer when something changed, not on every ask.

A client that polled once a second to learn whether anything changed now
asks once, with `since` set to the tag of what it already has, and the
request is held until the answer's tag differs, or `wait` seconds pass,
whichever comes first. A change reaches it as fast as before; a client
with nothing new costs one request every `wait` seconds instead of one a
second. Without `since` (an old client, a first ask) it answers at once,
as it always did.

The tag travels in the X-Tag header, so the body is what it always was.
While a request is held the server looks every CHECK seconds — in
process, which is cheap — and stops early if the client goes away.
"""
import asyncio
import hashlib
import json
import time
from typing import Any, Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

CHECK = 0.5
MAX_WAIT = 30.0


def tag(value: Any) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


async def hold(request: Request, read: Callable[[], Awaitable[Any]],
               since: str | None, wait: float, check: float = CHECK) -> JSONResponse:
    """`read()` the current value until its tag is not `since`, or `wait`
    seconds are up; answer with it and its tag."""
    deadline = time.monotonic() + max(0.0, min(wait, MAX_WAIT))
    while True:
        value = await read()
        t = tag(value)
        if not since or t != since or time.monotonic() >= deadline or await request.is_disconnected():
            return JSONResponse(value, headers={"X-Tag": t})
        await asyncio.sleep(check)

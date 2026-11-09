#!/usr/bin/env python3
"""One-off import of the categorised bank movements (movements_categorized.csv:
";"-separated, decimal points, UTF-8; columns data;importo;descrizione;banca;
from;to;tags) into one user's Finance payments.

  - from / to are category names the user already has; an unknown or
    ambiguous name stops the import before anything is written.
  - importo is always positive: one EUR payment, one "from" line and one
    "to" line of that amount. tags (","-separated) become the payment's tags.
  - No reason: the bank's text stays out of the app.
  - The MoneyGuard import already covers the payments up to its last date:
    a row up to then whose amount the user already has within 6 days is
    skipped as a duplicate.

A copy of the database is kept next to it first.

    python -m scripts.import_movements /mnt/earth/EARTH/movements_categorized.csv cian_cl
"""
import csv
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal

from api.config import FINANCE_DB
from api.services import finance


def main(path: str, user: str) -> None:
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))

    finance.init_db()
    with finance.connect() as conn:
        names = Counter(n for (n,) in conn.execute(
            "SELECT name FROM finance_categories WHERE username = ?", (user,)))
        wanted = {r[side] for r in rows for side in ("from", "to")}
        if bad := sorted(n for n in wanted if names[n] != 1):
            sys.exit(f"unknown or ambiguous categories: {bad}")
        ids = dict(conn.execute("SELECT name, id FROM finance_categories WHERE username = ?", (user,)))

        last = conn.execute("SELECT MAX(date) FROM finance_executed WHERE username = ?",
                            (user,)).fetchone()[0] or ""
        have = [(date.fromisoformat(d), a) for d, a in conn.execute(
            "SELECT e.date, MAX(l.amount_cents) FROM finance_executed e "
            "JOIN finance_executed_lines l ON l.executed_id = e.id "
            "WHERE e.username = ? AND e.date <= ? GROUP BY e.id", (user, last))]

        backup = f"{FINANCE_DB}.before-movements-{datetime.now():%Y%m%d-%H%M%S}"
        with sqlite3.connect(backup) as dest:
            conn.backup(dest)

        done = skipped = 0
        for r in rows:
            amount = int(Decimal(r["importo"]) * 100)
            day = date.fromisoformat(r["data"])
            if r["data"] <= last and any(a == amount and abs(d - day) <= timedelta(days=6)
                                         for d, a in have):
                skipped += 1
                continue
            finance.create_executed(conn, user, {
                "date": r["data"],
                "currency": "EUR",
                "lines": [{"side": "from", "category_id": ids[r["from"]], "amount_cents": amount},
                          {"side": "to", "category_id": ids[r["to"]], "amount_cents": amount}],
                "tags": [t for t in r["tags"].split(",") if t],
            })
            done += 1

        tags = conn.execute("SELECT COUNT(*) FROM finance_tags WHERE username = ?", (user,)).fetchone()[0]
    print(f"{done} payments, {skipped} duplicates skipped, {tags} tags now; backup at {backup}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

#!/usr/bin/env python3
"""One-off import of a MoneyGuard export (Moneyguard.csv: ";"-separated,
decimal commas, UTF-8 with BOM) into one user's Finance.

  - Methods (Portafogli, Fineco, ...) become categories of kind "account";
    every other Category becomes a plain category (all at the top level).
  - Expense: from its Method to its Category. Income: from its Category to
    its Method. Transfer: the other way round from how it reads — "Method
    PostePay, Category to Portafogli" is money from Portafogli into PostePay
    (a card topped up from the wallet, then spent). Amounts in euros, from
    the Amount column.
  - Tags (";"-separated) become the payment's tags.
  - Notes and zero-amount rows are skipped.

Refuses a user who already has categories or payments. A copy of the
database is kept next to it first.

    python -m scripts.import_moneyguard /mnt/earth/EARTH/Moneyguard.csv cian_cl
"""
import csv
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal

from api.config import FINANCE_DB
from api.services import finance


def cents(text: str) -> int:
    return int(Decimal(text.replace(",", ".")) * 100)


def main(path: str, user: str) -> None:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))
    skipped = Counter()
    kept = []
    for r in rows:
        if r["Type"] == "Note":
            skipped["note"] += 1
        elif cents(r["Amount"]) == 0:
            skipped["zero"] += 1
        else:
            kept.append(r)

    accounts = sorted({r["Method"] for r in kept})
    others = sorted({r["Category"] for r in kept if r["Type"] != "Transfer"})
    for r in kept:
        if r["Type"] == "Transfer" and r["Category"].removeprefix("to ") not in accounts:
            sys.exit(f"transfer to an unknown account: {r}")

    finance.init_db()
    with finance.connect() as conn:
        if conn.execute("SELECT EXISTS(SELECT 1 FROM finance_categories WHERE username = ?) "
                        "OR EXISTS(SELECT 1 FROM finance_executed WHERE username = ?)",
                        (user, user)).fetchone()[0]:
            sys.exit(f"{user} already has Finance data: nothing imported")
        backup = f"{FINANCE_DB}.before-moneyguard-{datetime.now():%Y%m%d-%H%M%S}"
        with sqlite3.connect(backup) as dest:
            conn.backup(dest)

        ids = {}
        for name in accounts:
            ids[name] = finance.create_category(conn, user, {"name": name, "kind": "account"})["id"]
        for name in others:
            ids[name] = finance.create_category(conn, user, {"name": name})["id"]

        for r in kept:
            src, dst = {
                "Expense": (r["Method"], r["Category"]),
                "Income": (r["Category"], r["Method"]),
                "Transfer": (r["Category"].removeprefix("to "), r["Method"]),
            }[r["Type"]]
            amount = cents(r["Amount"])
            finance.create_executed(conn, user, {
                "date": r["Date"][:10],
                "currency": "EUR",
                "lines": [{"side": "from", "category_id": ids[src], "amount_cents": amount},
                          {"side": "to", "category_id": ids[dst], "amount_cents": amount}],
                "tags": r["Tags"].split(";"),
            })

        tags = conn.execute("SELECT COUNT(*) FROM finance_tags WHERE username = ?", (user,)).fetchone()[0]
    print(f"{len(kept)} payments, {len(accounts)} accounts, {len(others)} categories, {tags} tags "
          f"(skipped: {dict(skipped)}); backup at {backup}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

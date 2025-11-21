#!/usr/bin/env python3
"""Identify parlay markets by name heuristics and write a filtered CSV.

Heuristics:
1) Question/slug/ticker contains "parlay" (case-insensitive)
2) Question contains "nothing ever happens" (case-insensitive)
3) Question matches any in a curated allowlist (case-insensitive match)

Defaults:
    Input: markets.csv
    Output: processed/parlay_markets_manual.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable, List, Dict, Set


ALLOWLIST = {
    "Fed decisions (Sep-Dec)",
    "Fed decisions (Oct-Jan)",
    "Nothing Ever Happens: November",
    "Nothing Ever Happens: Russia Edition",
    "Progressive Cities Parlay",
    "Nothing Ever Happens: AI Edition",
    "Fed decisions (Dec-Mar)",
    "Nothing Ever Happens: Military Edition",
    "Nothing Ever Happens: Jerome Powell Edition",
    "Google Trends Parlay",
    "Token Launch Party Parlay",
    "Nothing Ever Happens: Airdrops Edition",
    "Nothing Ever Happens: World Leader Out Edition",
    "Nothing Ever Happens: Conspiracy Edition",
    "Largest Democratic Margin of Victory",
    "Tech Release Parlay",
    "Nothing Ever Happens: Taylor Swift Edition",
    "Zohran Mamdani Parlay",
    "Trump's Christmas Wishlist Parlay",
    "Trump meets Xi, Putin, and Kim by December 31?",
    "Panick in the White House",
    "Trump Crypto Pardon Parlay",
    "Nothing Ever Happens: MrBeast Edition",
    "Nothing Ever Happens: Natural Disaster Edition",
    "Nothing Ever Happens: Trump Pardon Edition",
}

# Additional slug-level allowlist (case-insensitive)
ALLOWLIST_SLUGS = {
    "will-the-fed-cut-cut-cut-in-2025-796",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Identify parlay markets by name heuristics.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("markets.csv"),
        help="Input markets CSV (default: markets.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("processed/parlay_markets_manual.csv"),
        help="Output CSV path (default: processed/parlay_markets_manual.csv)",
    )
    return parser.parse_args()


def is_parlay_row(row: Dict[str, str], allowlist_ci: Set[str]) -> bool:
    q = (row.get("question") or "").strip()
    slug = (row.get("market_slug") or "").strip()
    ticker = (row.get("ticker") or "").strip()
    blob = " ".join([q, slug, ticker]).lower()

    if "parlay" in blob:
        return True
    if "nothing ever happens" in blob:
        return True
    if q.lower() in allowlist_ci:
        return True
    if slug.lower() in ALLOWLIST_SLUGS:
        return True
    return False


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows


def write_rows(rows: Iterable[Dict[str, str]], fieldnames: List[str], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    rows = load_rows(args.input)
    allowlist_ci = {name.lower() for name in ALLOWLIST}

    seen_ids = set()
    filtered: List[Dict[str, str]] = []
    for row in rows:
        if not is_parlay_row(row, allowlist_ci):
            continue
        mid = row.get("id")
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        filtered.append(row)

    if not filtered:
        print("No parlay-like markets found with current heuristics.")
        return 0

    fieldnames = list(rows[0].keys())
    write_rows(filtered, fieldnames, args.output)
    print(f"Wrote {len(filtered)} parlay-like markets to {args.output}")
    print(f"Heuristics: 'parlay' in text, 'nothing ever happens', or allowlist ({len(ALLOWLIST)} items).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

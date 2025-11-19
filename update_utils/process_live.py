import csv
import io
import os
import subprocess
import sys
import warnings
from collections import deque
from itertools import islice
from pathlib import Path

import pandas as pd
import polars as pl

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poly_utils.utils import get_markets  # noqa: E402

CHUNK_SIZE = int(os.environ.get("PROCESS_LIVE_CHUNK_SIZE", "500000"))
GOLDSKY_FILE = "goldsky/orderFilled.csv"
PROCESSED_FILE = "processed/trades.csv"


def get_processed_df(df: pl.DataFrame) -> pl.DataFrame:
    markets_df = get_markets()
    markets_df = markets_df.rename({'id': 'market_id'})

    markets_long = (
        markets_df
        .select(["market_id", "token1", "token2"])
        .melt(
            id_vars="market_id",
            value_vars=["token1", "token2"],
            variable_name="side",
            value_name="asset_id",
        )
    )

    df = df.with_columns(
        pl.when(pl.col("makerAssetId") != "0")
        .then(pl.col("makerAssetId"))
        .otherwise(pl.col("takerAssetId"))
        .alias("nonusdc_asset_id")
    )

    df = df.join(
        markets_long,
        left_on="nonusdc_asset_id",
        right_on="asset_id",
        how="left",
    )

    df = df.with_columns([
        pl.when(pl.col("makerAssetId") == "0").then(pl.lit("USDC")).otherwise(pl.col("side")).alias("makerAsset"),
        pl.when(pl.col("takerAssetId") == "0").then(pl.lit("USDC")).otherwise(pl.col("side")).alias("takerAsset"),
        pl.col("market_id"),
    ])

    df = df[['timestamp', 'market_id', 'maker', 'makerAsset', 'makerAmountFilled', 'taker', 'takerAsset', 'takerAmountFilled', 'transactionHash']]

    df = df.with_columns([
        (pl.col("makerAmountFilled") / 10**6).alias("makerAmountFilled"),
        (pl.col("takerAmountFilled") / 10**6).alias("takerAmountFilled"),
    ])

    df = df.with_columns([
        pl.when(pl.col("takerAsset") == "USDC").then(pl.lit("BUY")).otherwise(pl.lit("SELL")).alias("taker_direction"),
        pl.when(pl.col("takerAsset") == "USDC").then(pl.lit("SELL")).otherwise(pl.lit("BUY")).alias("maker_direction"),
    ])

    df = df.with_columns([
        pl.when(pl.col("makerAsset") != "USDC").then(pl.col("makerAsset")).otherwise(pl.col("takerAsset")).alias("nonusdc_side"),
        pl.when(pl.col("takerAsset") == "USDC").then(pl.col("takerAmountFilled")).otherwise(pl.col("makerAmountFilled")).alias("usd_amount"),
        pl.when(pl.col("takerAsset") != "USDC").then(pl.col("takerAmountFilled")).otherwise(pl.col("makerAmountFilled")).alias("token_amount"),
        pl.when(pl.col("takerAsset") == "USDC")
        .then(pl.col("takerAmountFilled") / pl.col("makerAmountFilled"))
        .otherwise(pl.col("makerAmountFilled") / pl.col("takerAmountFilled"))
        .cast(pl.Float64)
        .alias("price"),
    ])

    df = df[['timestamp', 'market_id', 'maker', 'taker', 'nonusdc_side', 'maker_direction', 'taker_direction', 'price', 'usd_amount', 'token_amount', 'transactionHash']]
    return df


def count_data_rows(path: str) -> int:
    """Count data rows (excluding header) quickly."""
    if not os.path.exists(path):
        return 0

    newline_count = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            newline_count += chunk.count(b"\n")

    return max(0, newline_count - 1)


def skip_lines(handle, n: int) -> None:
    """Advance file handle by n lines efficiently."""
    if n <= 0:
        return
    deque(islice(handle, n), maxlen=0)


def process_live() -> None:
    print("=" * 60)
    print("🔄 Processing Live Trades")
    print("=" * 60)

    last_processed = {}
    processed_rows = 0

    if os.path.exists(PROCESSED_FILE):
        print(f"✓ Found existing processed file: {PROCESSED_FILE}")
        processed_rows = count_data_rows(PROCESSED_FILE)
        result = subprocess.run(['tail', '-n', '20', PROCESSED_FILE], capture_output=True, text=True)
        lines = [line for line in result.stdout.splitlines() if line.strip()]

        parsed = None
        for line in reversed(lines):
            reader = csv.reader([line])
            row = next(reader, [])
            if len(row) == 11:
                parsed = row
                break

        if not parsed:
            raise RuntimeError(
                "Could not find a valid row in processed/trades.csv. The file may be corrupted; "
                "please re-generate it (remove the file and rerun process_live)."
            )

        last_processed['timestamp'] = pd.to_datetime(parsed[0])
        last_processed['transactionHash'] = parsed[-1]
        last_processed['maker'] = parsed[2]
        last_processed['taker'] = parsed[3]

        print(f"📍 Resuming from: {last_processed['timestamp']}")
        print(f"   Last hash: {last_processed['transactionHash'][:16]}...")
    else:
        print("⚠ No existing processed file found - processing from beginning")

    print(f"\n📂 Reading: {GOLDSKY_FILE}")

    schema_overrides = {
        "takerAssetId": pl.Utf8,
        "makerAssetId": pl.Utf8,
    }

    if not os.path.exists(GOLDSKY_FILE):
        raise FileNotFoundError(f"{GOLDSKY_FILE} not found. Run update_goldsky first.")

    processed_path = Path(PROCESSED_FILE)
    if not processed_path.parent.exists():
        processed_path.parent.mkdir(parents=True, exist_ok=True)

    total_appended = 0
    chunk_idx = 0

    with open(GOLDSKY_FILE, "r") as source:
        header = source.readline()
        if processed_rows:
            print(f"⏩ Skipping {processed_rows:,} already processed rows from Goldsky dump")
            skip_lines(source, processed_rows)

        while True:
            lines = list(islice(source, CHUNK_SIZE))
            if not lines:
                break

            chunk_idx += 1
            buffer = io.StringIO()
            buffer.write(header)
            buffer.writelines(lines)
            buffer.seek(0)

            chunk_df = pl.read_csv(buffer, schema_overrides=schema_overrides)
            buffer.close()

            chunk_df = chunk_df.with_columns(
                pl.from_epoch(pl.col('timestamp'), time_unit='s').alias('timestamp')
            )

            processed_chunk = get_processed_df(chunk_df)

            file_exists = processed_path.exists()
            include_header = not file_exists and total_appended == 0

            with open(PROCESSED_FILE, "a") as out_f:
                processed_chunk.write_csv(out_f, include_header=include_header)

            total_appended += len(processed_chunk)
            last_ts = processed_chunk[-1, "timestamp"]
            print(f"✓ Chunk {chunk_idx}: wrote {len(processed_chunk):,} rows (total appended {total_appended:,}, last ts {last_ts})")

    print("=" * 60)
    print("✅ Processing complete!")
    print("=" * 60)


if __name__ == "__main__":
    process_live()

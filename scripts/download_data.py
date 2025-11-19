#!/usr/bin/env python3
"""Download Polymarket data from cloud storage.

This script downloads pre-processed data files for Jupyter notebook analysis.
No authentication or setup required - data is publicly accessible!

Usage:
    python download_data.py

    # Or download specific files only:
    python download_data.py --files markets
    python download_data.py --files trades
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from tqdm import tqdm


# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Public Supabase Storage URLs (no authentication needed!)
BASE_URL = "https://hgzttvjqhfepdnngsrhs.supabase.co/storage/v1/object/public/polymarket-data"

FILES_TO_DOWNLOAD = {
    'markets': {
        'url': f'{BASE_URL}/markets.csv',
        'path': PROJECT_ROOT / 'markets.csv',
        'description': 'Market metadata (170K+ markets)'
    },
    'trades': {
        'url': f'{BASE_URL}/latest_10000000_trades.parquet',
        'path': PROJECT_ROOT / 'processed' / 'latest_10000000_trades.parquet',
        'description': 'Latest 10M trades (~7 days of data)'
    },
    'metadata': {
        'url': f'{BASE_URL}/metadata.json',
        'path': PROJECT_ROOT / 'data_metadata.json',
        'description': 'Update timestamps and data info'
    }
}


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Download Polymarket data from cloud storage (public, no auth needed)'
    )
    parser.add_argument(
        '--files',
        nargs='+',
        choices=['markets', 'trades', 'metadata', 'all'],
        default=['all'],
        help='Files to download (default: all)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-download even if files exist'
    )
    return parser.parse_args()


def download_file(url: str, destination: Path, description: str, force: bool = False) -> bool:
    """Download a file from URL with progress bar.

    Args:
        url: URL to download from
        destination: Local file path to save to
        description: Description for progress display
        force: Force download even if file exists

    Returns:
        True if downloaded successfully, False otherwise
    """
    # Create parent directory
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Check if file exists
    if destination.exists() and not force:
        size_mb = destination.stat().st_size / (1024 * 1024)
        print(f"   ℹ️  File exists: {destination.name} ({size_mb:.1f} MB)")
        print(f"      Use --force to re-download")
        return True

    print(f"📥 Downloading: {description}")
    print(f"   From: {url}")
    print(f"   To:   {destination}")

    try:
        # Stream download with progress bar
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        # Download with progress bar
        with open(destination, 'wb') as f, tqdm(
            desc=destination.name,
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
        ) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))

        size_mb = destination.stat().st_size / (1024 * 1024)
        print(f"✅ Downloaded: {destination.name} ({size_mb:.1f} MB)\n")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Download failed: {e}\n")
        # Clean up partial download
        if destination.exists():
            destination.unlink()
        return False


def main():
    """Download data from cloud storage."""
    args = parse_args()

    print("="*80)
    print("📥 POLYMARKET DATA DOWNLOADER")
    print("="*80)
    print("Downloading from public cloud storage (no authentication required)")
    print()

    # Determine what to download
    if 'all' in args.files:
        files_to_get = ['markets', 'trades', 'metadata']
    else:
        files_to_get = [f for f in args.files if f != 'all']

    print(f"📦 Files to download: {', '.join(files_to_get)}")
    print()

    # Download each file
    success_count = 0
    total_size = 0

    for i, file_key in enumerate(files_to_get, 1):
        file_info = FILES_TO_DOWNLOAD[file_key]

        print(f"[{i}/{len(files_to_get)}]")
        success = download_file(
            url=file_info['url'],
            destination=file_info['path'],
            description=file_info['description'],
            force=args.force
        )

        if success:
            success_count += 1
            if file_info['path'].exists():
                total_size += file_info['path'].stat().st_size / (1024 * 1024)

    # Show metadata if downloaded
    metadata_path = PROJECT_ROOT / 'data_metadata.json'
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            print("="*80)
            print("📊 DATA INFORMATION")
            print("="*80)

            trades_info = metadata.get('files', {}).get('trades', {})
            if trades_info:
                print(f"Trades:       {trades_info.get('num_trades', 'N/A'):,}")
                date_range = trades_info.get('date_range', {})
                if date_range:
                    print(f"Date range:   {date_range.get('start', 'N/A')} to {date_range.get('end', 'N/A')}")

            last_updated = metadata.get('last_updated', 'N/A')
            print(f"Last updated: {last_updated}")
            print()
        except Exception:
            pass

    # Summary
    print("="*80)
    print("✅ DOWNLOAD COMPLETE")
    print("="*80)
    print(f"Files downloaded: {success_count}/{len(files_to_get)}")
    print(f"Total size:       {total_size:.1f} MB")
    print()
    print("🎉 Ready to analyze!")
    print("   Run: jupyter notebook notebooks/")
    print()
    print("📓 Available notebooks:")
    print("   • polymarket_analytics.ipynb - General analytics functions")
    print("   • top_traders_market_analysis.ipynb - Top traders analysis")
    print("   • single_trader_analysis.ipynb - Individual trader deep dive")

    return 0 if success_count == len(files_to_get) else 1


if __name__ == '__main__':
    sys.exit(main())

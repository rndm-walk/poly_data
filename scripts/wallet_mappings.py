#!/usr/bin/env python3
"""
Wallet Mappings Module - Single source of truth for proxy-to-main wallet mappings.

Loads wallet mapping data from parlay_user_volume_notes.csv and provides
structured access to wallet relationships, sources, and metadata.

Notation in CSV:
- (CEX, ...) or (Bridge, ...) → funding source
- (0xADDRESS) → confirmed main wallet
- (0xADDRESS?) → uncertain main wallet
- (0xADDRESS)(need) → main wallet that needs transaction fetch
- (0xADDRESS?)(need) → uncertain main wallet that needs fetch
"""

import csv
import re
from pathlib import Path
from typing import Dict, Optional


def parse_notes(notes: str) -> Dict:
    """
    Parse notes from CSV to extract wallet mapping information.

    Args:
        notes: The notes string from the CSV (e.g., "(0xABC...)(need)" or "(CEX, Binance)")

    Returns:
        Dictionary with parsed information:
        - main_wallet: str (if present)
        - uncertain: bool (if main wallet has "?" marker)
        - needs_fetch: bool (if marked with "(need)")
        - source: str (if CEX/Bridge/etc.)
    """
    result = {}

    notes = notes.strip()

    # Check for wallet address pattern first: (0xADDRESS?) or (0xADDRESS)
    # Pattern: (0x followed by 40 hex chars, optional ?)
    wallet_pattern = r'\(0x[a-fA-F0-9]{40}(\?)?\)'
    wallet_match = re.search(wallet_pattern, notes)

    if wallet_match:
        wallet_str = wallet_match.group(0)
        # Extract the address
        address = wallet_str[1:-1]  # Remove parentheses

        # Check if uncertain (ends with ?)
        if address.endswith("?"):
            result["uncertain"] = True
            address = address[:-1]  # Remove the ?
        else:
            result["uncertain"] = False

        result["main_wallet"] = address.lower()

    # Check if it's a source annotation (CEX, Bridge, etc.)
    # Only if we didn't find a wallet address
    elif notes.startswith("(") and notes.endswith(")"):
        # Extract source info - remove outer parentheses
        source = notes[1:-1]
        result["source"] = source

    # Check if needs fetch
    if "(need)" in notes:
        result["needs_fetch"] = True
    else:
        result["needs_fetch"] = False

    return result


def load_wallet_mappings(csv_path: Optional[Path] = None) -> Dict[str, Dict]:
    """
    Load wallet mappings from CSV file.

    Args:
        csv_path: Path to the CSV file. If None, uses default location.

    Returns:
        Dictionary mapping proxy wallet addresses to their metadata:
        {
            "0xproxy_address": {
                "volume": float,
                "main_wallet": "0xmain_address",  # if available
                "uncertain": bool,                 # if main wallet is uncertain
                "needs_fetch": bool,               # if needs transaction fetch
                "source": str                      # if CEX/Bridge/etc.
            }
        }
    """
    if csv_path is None:
        # Default to project root / processed / parlay_user_volume_notes.csv
        csv_path = Path(__file__).parent.parent / "processed" / "parlay_user_volume_notes.csv"

    mappings = {}

    with open(csv_path, 'r') as f:
        # Skip header
        next(f)

        for line in f:
            line = line.strip()
            if not line:
                continue

            # Split only on first comma (address,total_usd)
            # This handles commas inside notes like "(CEX, Binance)"
            parts = line.split(',', 1)
            if len(parts) != 2:
                continue

            address = parts[0].strip().lower()
            total_usd_str = parts[1].strip()

            # Extract volume (first part before any parentheses or spaces)
            volume_match = re.match(r'^([\d.]+)', total_usd_str)
            if volume_match:
                volume = float(volume_match.group(1))
            else:
                continue  # Skip rows without valid volume

            # Parse notes (everything after the volume)
            # Match from first ( to last ) to get full notes including (need)
            notes_match = re.search(r'\(.*\)', total_usd_str)
            notes = notes_match.group(0) if notes_match else ""

            # Build mapping entry
            entry = {"volume": volume}

            if notes:
                parsed = parse_notes(notes)
                entry.update(parsed)

            mappings[address] = entry

    return mappings


def get_main_wallet(proxy_address: str, mappings: Optional[Dict] = None) -> Optional[str]:
    """
    Get the main wallet address for a proxy wallet.

    Args:
        proxy_address: The proxy wallet address
        mappings: Pre-loaded mappings dict. If None, will load from CSV.

    Returns:
        Main wallet address if available, None otherwise
    """
    if mappings is None:
        mappings = load_wallet_mappings()

    proxy_address = proxy_address.lower()
    wallet_info = mappings.get(proxy_address, {})

    return wallet_info.get("main_wallet")


def get_funding_source(proxy_address: str, mappings: Optional[Dict] = None) -> Optional[str]:
    """
    Get the funding source for a proxy wallet (e.g., "CEX, Binance").

    Args:
        proxy_address: The proxy wallet address
        mappings: Pre-loaded mappings dict. If None, will load from CSV.

    Returns:
        Funding source string if available, None otherwise
    """
    if mappings is None:
        mappings = load_wallet_mappings()

    proxy_address = proxy_address.lower()
    wallet_info = mappings.get(proxy_address, {})

    return wallet_info.get("source")


def needs_transaction_fetch(proxy_address: str, mappings: Optional[Dict] = None) -> bool:
    """
    Check if a proxy wallet needs transaction fetching.

    Args:
        proxy_address: The proxy wallet address
        mappings: Pre-loaded mappings dict. If None, will load from CSV.

    Returns:
        True if needs fetch, False otherwise
    """
    if mappings is None:
        mappings = load_wallet_mappings()

    proxy_address = proxy_address.lower()
    wallet_info = mappings.get(proxy_address, {})

    return wallet_info.get("needs_fetch", False)


def is_uncertain(proxy_address: str, mappings: Optional[Dict] = None) -> bool:
    """
    Check if the main wallet mapping is uncertain.

    Args:
        proxy_address: The proxy wallet address
        mappings: Pre-loaded mappings dict. If None, will load from CSV.

    Returns:
        True if uncertain, False otherwise
    """
    if mappings is None:
        mappings = load_wallet_mappings()

    proxy_address = proxy_address.lower()
    wallet_info = mappings.get(proxy_address, {})

    return wallet_info.get("uncertain", False)


# Legacy compatibility - expose as WALLET_MAPPINGS constant
WALLET_MAPPINGS = load_wallet_mappings()


if __name__ == "__main__":
    # Test the parser
    print("Loading wallet mappings from CSV...")
    mappings = load_wallet_mappings()

    print(f"\n✓ Loaded {len(mappings)} wallet mappings\n")

    # Show some examples
    print("="*80)
    print("SAMPLE MAPPINGS")
    print("="*80)

    for i, (address, info) in enumerate(list(mappings.items())[:10], 1):
        print(f"\n{i}. {address}")
        print(f"   Volume: ${info['volume']:,.2f}")

        if "main_wallet" in info:
            uncertainty = " (uncertain)" if info.get("uncertain") else ""
            needs_fetch = " [needs fetch]" if info.get("needs_fetch") else ""
            print(f"   Main Wallet: {info['main_wallet']}{uncertainty}{needs_fetch}")

        if "source" in info:
            print(f"   Source: {info['source']}")

    # Show wallets that need fetching
    needs_fetch = [(addr, info) for addr, info in mappings.items() if info.get("needs_fetch")]
    print(f"\n{'='*80}")
    print(f"WALLETS NEEDING TRANSACTION FETCH: {len(needs_fetch)}")
    print("="*80)

    for addr, info in needs_fetch[:5]:
        uncertainty = " (uncertain)" if info.get("uncertain") else ""
        print(f"  • {addr[:10]}...{addr[-8:]}: {info.get('main_wallet', 'N/A')}{uncertainty}")

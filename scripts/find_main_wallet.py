#!/usr/bin/env python3
"""
Find the main wallet connected to a Polymarket proxy wallet by analyzing USDC transactions.

This script:
1. Fetches all USDC (ERC-20) token transfers for a given proxy wallet
2. Analyzes transfer patterns to identify the main wallet
3. Looks for funding patterns, withdrawal patterns, and transaction frequency
"""

import os
import sys
import requests
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict, Counter
from datetime import datetime
from dotenv import load_dotenv
import json
import google.generativeai as genai

# Load environment variables
load_dotenv()

POLYGONSCAN_API_KEY = os.getenv("POLY_SCAN_API")
if not POLYGONSCAN_API_KEY:
    print("❌ POLY_SCAN_API not found in .env file")
    sys.exit(1)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY not found in .env file")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# Load Polymarket contract addresses to filter out
POLYMARKET_CONTRACTS = set()
poly_contracts_str = os.getenv("POLY_CONTRACT_ADDRESSES", "")
if poly_contracts_str:
    POLYMARKET_CONTRACTS.update(addr.strip().lower() for addr in poly_contracts_str.split(",") if addr.strip())

ctf_exchange = os.getenv("POLYMARKET_CTF_EXCHANGE_CONTRACT_ADDRESS", "")
if ctf_exchange:
    POLYMARKET_CONTRACTS.add(ctf_exchange.lower())

neg_risk_exchange = os.getenv("POLYMARKET_NEG_RISK_CTF_EXCHANGE_CONTRACT_ADDRESS", "")
if neg_risk_exchange:
    POLYMARKET_CONTRACTS.add(neg_risk_exchange.lower())

# Load common addresses to exclude from wallet analysis
ADDRESSES_TO_EXCLUDE = set()
exclude_str = os.getenv("ADDRESSES_TO_EXCLUDE_FROM_WALLET", "")
if exclude_str:
    ADDRESSES_TO_EXCLUDE.update(addr.strip().lower() for addr in exclude_str.split(",") if addr.strip())

print(f"📋 Loaded {len(POLYMARKET_CONTRACTS)} Polymarket contract addresses to filter out")
for addr in POLYMARKET_CONTRACTS:
    print(f"   - {addr}")

if ADDRESSES_TO_EXCLUDE:
    print(f"\n📋 Loaded {len(ADDRESSES_TO_EXCLUDE)} common addresses to exclude from wallet candidates")
    for addr in ADDRESSES_TO_EXCLUDE:
        print(f"   - {addr}")

# Polygon network constants
POLYGON_CHAIN_ID = "137"
# Use Etherscan V2 API with chainid parameter for Polygon
POLYGONSCAN_API_BASE = "https://api.etherscan.io/v2/api"

# USDC contract addresses on Polygon
USDC_POLYGON_OLD = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC (bridged)
USDC_POLYGON_NEW = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # USDC.e (native)


class WalletAnalyzer:
    def __init__(self, proxy_wallet: str):
        self.proxy_wallet = proxy_wallet.lower()
        self.transfers = []
        self.filtered_transfers = []
        self.model = genai.GenerativeModel("gemini-2.0-flash-exp")
        self.contract_cache = {}  # Cache contract checks

    def fetch_token_transfers(self, contract_address: str, token_name: str) -> List[Dict]:
        """Fetch ERC-20 token transfers for a wallet."""
        print(f"\n📥 Fetching {token_name} transfers for {self.proxy_wallet}...")

        params = {
            "chainid": POLYGON_CHAIN_ID,
            "module": "account",
            "action": "tokentx",
            "contractaddress": contract_address,
            "address": self.proxy_wallet,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 10000,  # Max results per page
            "sort": "asc",
            "apikey": POLYGONSCAN_API_KEY
        }

        try:
            response = requests.get(POLYGONSCAN_API_BASE, params=params)
            response.raise_for_status()
            data = response.json()

            if data["status"] == "1" and data["result"]:
                transfers = data["result"]
                print(f"  ✓ Found {len(transfers)} {token_name} transfers")
                return transfers
            elif data["status"] == "0":
                if "No transactions found" in data.get("message", ""):
                    print(f"  ℹ️  No {token_name} transfers found")
                    return []
                else:
                    print(f"  ⚠️  API Error: {data.get('message', 'Unknown error')}")
                    print(f"  Debug - Full response: {data}")
                    return []
            else:
                print(f"  ⚠️  Unexpected response status: {data.get('status')}")
                print(f"  Debug - Full response: {data}")
                return []

        except Exception as e:
            print(f"  ❌ Error fetching transfers: {e}")
            return []

    def fetch_all_usdc_transfers(self) -> List[Dict]:
        """Fetch all USDC transfers (both old and new USDC)."""
        all_transfers = []

        # Fetch old USDC (bridged)
        old_transfers = self.fetch_token_transfers(USDC_POLYGON_OLD, "USDC (bridged)")
        all_transfers.extend(old_transfers)

        # Small delay to avoid rate limiting
        time.sleep(0.5)

        # Fetch new USDC (native)
        new_transfers = self.fetch_token_transfers(USDC_POLYGON_NEW, "USDC.e (native)")
        all_transfers.extend(new_transfers)

        # Sort by timestamp
        all_transfers.sort(key=lambda x: int(x["timeStamp"]))

        self.transfers = all_transfers
        print(f"\n✓ Total USDC transfers: {len(all_transfers)}")
        return all_transfers

    def is_contract(self, address: str) -> bool:
        """Check if an address is a smart contract using eth_getCode."""
        address = address.lower()

        # Check cache first
        if address in self.contract_cache:
            return self.contract_cache[address]

        try:
            params = {
                "chainid": POLYGON_CHAIN_ID,
                "module": "proxy",
                "action": "eth_getCode",
                "address": address,
                "tag": "latest",
                "apikey": POLYGONSCAN_API_KEY
            }

            response = requests.get(POLYGONSCAN_API_BASE, params=params)
            response.raise_for_status()
            data = response.json()

            # If result is "0x", it's an EOA (regular wallet), otherwise it's a contract
            is_contract = data.get("result", "0x") != "0x"
            self.contract_cache[address] = is_contract

            time.sleep(0.2)  # Rate limiting
            return is_contract

        except Exception as e:
            print(f"  ⚠️  Error checking if {address} is contract: {e}")
            return False  # Assume wallet if check fails

    def get_contract_info(self, address: str) -> Optional[Dict]:
        """Get contract information including name."""
        address = address.lower()

        try:
            params = {
                "chainid": POLYGON_CHAIN_ID,
                "module": "contract",
                "action": "getsourcecode",
                "address": address,
                "apikey": POLYGONSCAN_API_KEY
            }

            response = requests.get(POLYGONSCAN_API_BASE, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "1" and data.get("result"):
                result = data["result"][0]
                return {
                    "contract_name": result.get("ContractName", "Unknown"),
                    "is_verified": result.get("ContractName", "") != "",
                    "proxy": result.get("Proxy", "0") == "1",
                    "implementation": result.get("Implementation", "")
                }

            time.sleep(0.2)  # Rate limiting
            return None

        except Exception as e:
            print(f"  ⚠️  Error getting contract info for {address}: {e}")
            return None

    def filter_polymarket_transactions(self) -> List[Dict]:
        """Filter out transactions involving Polymarket contract addresses."""
        print("\n" + "="*80)
        print("FILTERING POLYMARKET CONTRACT TRANSACTIONS")
        print("="*80)

        filtered = []
        polymarket_tx_count = 0

        for tx in self.transfers:
            from_addr = tx["from"].lower()
            to_addr = tx["to"].lower()

            # Skip if either from or to is a Polymarket contract
            if from_addr in POLYMARKET_CONTRACTS or to_addr in POLYMARKET_CONTRACTS:
                polymarket_tx_count += 1
                continue

            filtered.append(tx)

        self.filtered_transfers = filtered
        print(f"\n📊 Filtering Results:")
        print(f"  • Total transfers: {len(self.transfers)}")
        print(f"  • Polymarket contract transfers (filtered out): {polymarket_tx_count}")
        print(f"  • Non-Polymarket transfers (for analysis): {len(filtered)}")
        print(f"  • Reduction: {polymarket_tx_count / len(self.transfers) * 100:.1f}% filtered")

        return filtered

    def analyze_transfers(self) -> Dict:
        """Analyze transfers to identify main wallet candidates."""
        if not self.filtered_transfers:
            print("❌ No filtered transfers to analyze")
            return {}

        print("\n" + "="*80)
        print("ANALYZING TRANSFER PATTERNS (Non-Polymarket Only)")
        print("="*80)

        incoming = []  # Transfers TO proxy wallet
        outgoing = []  # Transfers FROM proxy wallet

        for tx in self.filtered_transfers:
            if tx["to"].lower() == self.proxy_wallet:
                incoming.append(tx)
            elif tx["from"].lower() == self.proxy_wallet:
                outgoing.append(tx)

        print(f"\n📊 Transfer Overview:")
        print(f"  • Incoming: {len(incoming)} transfers")
        print(f"  • Outgoing: {len(outgoing)} transfers")

        # Analyze incoming transfers (funding sources)
        incoming_wallets = Counter()
        incoming_volume = defaultdict(float)
        incoming_first = {}
        incoming_last = {}

        for tx in incoming:
            sender = tx["from"].lower()
            value = float(tx["value"]) / (10 ** int(tx["tokenDecimal"]))
            timestamp = int(tx["timeStamp"])

            incoming_wallets[sender] += 1
            incoming_volume[sender] += value

            if sender not in incoming_first:
                incoming_first[sender] = timestamp
            incoming_last[sender] = timestamp

        # Analyze outgoing transfers (withdrawal destinations)
        outgoing_wallets = Counter()
        outgoing_volume = defaultdict(float)
        outgoing_first = {}
        outgoing_last = {}

        for tx in outgoing:
            recipient = tx["to"].lower()
            value = float(tx["value"]) / (10 ** int(tx["tokenDecimal"]))
            timestamp = int(tx["timeStamp"])

            outgoing_wallets[recipient] += 1
            outgoing_volume[recipient] += value

            if recipient not in outgoing_first:
                outgoing_first[recipient] = timestamp
            outgoing_last[recipient] = timestamp

        # Find main wallet candidates
        candidates = {}

        # Score incoming wallets (funding sources)
        print("\n" + "="*80)
        print("TOP FUNDING SOURCES (Incoming USDC)")
        print("="*80)
        print(f"\n{'Rank':<6} {'Address':<44} {'Transfers':<12} {'Total Volume':<20} {'Score'}")
        print("-" * 100)

        for i, (wallet, count) in enumerate(incoming_wallets.most_common(10), 1):
            # Skip excluded addresses
            if wallet in ADDRESSES_TO_EXCLUDE:
                continue

            volume = incoming_volume[wallet]
            avg_transfer = volume / count

            # Calculate score based on:
            # - Number of transfers (frequency)
            # - Total volume
            # - Whether it's the first funder
            # - Regular activity pattern
            score = 0
            score += count * 10  # Frequency score
            score += min(volume / 1000, 100)  # Volume score (capped at 100)

            # Bonus for being the first funder
            if incoming_first[wallet] == min(incoming_first.values()):
                score += 50
                first_funder = True
            else:
                first_funder = False

            # Bonus for recent activity
            days_active = (incoming_last[wallet] - incoming_first[wallet]) / 86400
            if days_active > 30:
                score += 20

            candidates[wallet] = {
                'type': 'funding_source',
                'transfers_in': count,
                'transfers_out': 0,
                'volume_in': volume,
                'volume_out': 0,
                'score': score,
                'first_seen': incoming_first[wallet],
                'last_seen': incoming_last[wallet],
                'first_funder': first_funder,
                'avg_transfer': avg_transfer
            }

            marker = "🥇" if first_funder else "  "
            print(f"{marker} {i:<4} {wallet:<44} {count:<12} ${volume:>18,.2f} {score:>8.1f}")

        # Score outgoing wallets (withdrawal destinations)
        print("\n" + "="*80)
        print("TOP WITHDRAWAL DESTINATIONS (Outgoing USDC)")
        print("="*80)
        print(f"\n{'Rank':<6} {'Address':<44} {'Transfers':<12} {'Total Volume':<20} {'Score'}")
        print("-" * 100)

        for i, (wallet, count) in enumerate(outgoing_wallets.most_common(10), 1):
            # Skip excluded addresses
            if wallet in ADDRESSES_TO_EXCLUDE:
                continue

            volume = outgoing_volume[wallet]
            avg_transfer = volume / count

            score = 0
            score += count * 10
            score += min(volume / 1000, 100)

            days_active = (outgoing_last[wallet] - outgoing_first[wallet]) / 86400
            if days_active > 30:
                score += 20

            if wallet in candidates:
                # This wallet both sends and receives - very likely main wallet!
                candidates[wallet]['transfers_out'] = count
                candidates[wallet]['volume_out'] = volume
                candidates[wallet]['score'] += score + 100  # Big bonus for bidirectional flow
                candidates[wallet]['type'] = 'bidirectional'
            else:
                candidates[wallet] = {
                    'type': 'withdrawal_destination',
                    'transfers_in': 0,
                    'transfers_out': count,
                    'volume_in': 0,
                    'volume_out': volume,
                    'score': score,
                    'first_seen': outgoing_first[wallet],
                    'last_seen': outgoing_last[wallet],
                    'first_funder': False,
                    'avg_transfer': avg_transfer
                }

            print(f"   {i:<4} {wallet:<44} {count:<12} ${volume:>18,.2f} {score:>8.1f}")

        return candidates

    def filter_contract_candidates(self, candidates: Dict) -> Dict:
        """Filter out smart contract addresses from candidates, keeping only wallets."""
        print("\n" + "="*80)
        print("FILTERING OUT PROTOCOL/CONTRACT ADDRESSES")
        print("="*80)
        print("\n🔍 Checking each candidate to see if it's a contract...")

        filtered_candidates = {}
        contracts_found = []

        for wallet, info in candidates.items():
            print(f"\n  Checking {wallet}...")

            # Check if it's a contract
            if self.is_contract(wallet):
                # Get contract details
                contract_info = self.get_contract_info(wallet)

                if contract_info and contract_info["is_verified"]:
                    contract_name = contract_info["contract_name"]
                    print(f"    ❌ EXCLUDED: Contract - {contract_name}")
                    contracts_found.append((wallet, contract_name))
                else:
                    print(f"    ❌ EXCLUDED: Unverified contract")
                    contracts_found.append((wallet, "Unverified Contract"))
            else:
                print(f"    ✅ WALLET: Keeping as candidate")
                filtered_candidates[wallet] = info

        print("\n" + "="*80)
        print(f"📊 Contract Filtering Results:")
        print(f"  • Original candidates: {len(candidates)}")
        print(f"  • Contracts excluded: {len(contracts_found)}")
        print(f"  • Wallets remaining: {len(filtered_candidates)}")

        if contracts_found:
            print(f"\n  Excluded Contracts:")
            for addr, name in contracts_found:
                print(f"    - {addr[:10]}...{addr[-8:]}: {name}")

        print("="*80)

        return filtered_candidates

    def analyze_with_gemini(self, candidates: Dict) -> Dict[str, str]:
        """Use Gemini to analyze wallet patterns and provide insights."""
        if not candidates:
            return {}

        print("\n" + "="*80)
        print("AI ANALYSIS WITH GEMINI")
        print("="*80)
        print("\n🤖 Analyzing wallet patterns with Gemini AI...")

        # Prepare summary data for Gemini
        top_candidates = sorted(
            candidates.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )[:5]

        prompt = f"""Analyze these USDC wallet transaction patterns to identify the main wallet connected to this Polymarket proxy wallet.

PROXY WALLET: {self.proxy_wallet}

CONTEXT:
- All Polymarket contract transactions have been FILTERED OUT
- Only wallet-to-wallet USDC transfers remain
- We're looking for the main funding/withdrawal wallet

TOP 5 WALLET CANDIDATES:

"""

        for i, (wallet, info) in enumerate(top_candidates, 1):
            first_date = datetime.fromtimestamp(info['first_seen']).strftime('%Y-%m-%d')
            last_date = datetime.fromtimestamp(info['last_seen']).strftime('%Y-%m-%d')

            prompt += f"""
{i}. {wallet}
   Type: {info['type'].replace('_', ' ').title()}
   Transfers IN: {info['transfers_in']} (${info['volume_in']:,.2f})
   Transfers OUT: {info['transfers_out']} (${info['volume_out']:,.2f})
   Score: {info['score']:.1f}
   First seen: {first_date}
   Last seen: {last_date}
   First funder: {info['first_funder']}
"""

        prompt += """

TASK:
1. Analyze the transaction patterns above
2. Identify which wallet is most likely the MAIN WALLET
3. If ALL candidates appear to be from centralized exchanges (CEX), bridges, or protocols (not personal wallets), you should indicate "Not Available"
4. Explain the key indicators that support your conclusion
5. Provide a confidence level (High/Medium/Low/Not Available)

Please provide your analysis in the following format:

**Main Wallet:** [wallet address OR "Not Available"]

**Confidence:** [High/Medium/Low/Not Available]

**Reason (if Not Available):** [e.g., "All candidates are from centralized exchanges" OR "All candidates are bridge contracts" OR "All candidates are DeFi protocols"]

**Key Indicators:**
- [Indicator 1]
- [Indicator 2]
- [Indicator 3]

**Analysis:**
[2-3 sentences explaining your reasoning]

IMPORTANT: If you determine the main wallet is "Not Available", make sure to provide a clear reason why (CEX deposits, bridge addresses, protocol contracts, etc.)
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=800,
                )
            )

            analysis = response.text.strip()
            print("\n" + "="*80)
            print(analysis)
            print("="*80)

            return {"analysis": analysis}

        except Exception as e:
            print(f"\n⚠️  Gemini analysis failed: {e}")
            return {}

    def identify_main_wallet(self, candidates: Dict) -> Optional[Tuple[str, Dict]]:
        """Identify the most likely main wallet."""
        if not candidates:
            return None

        print("\n" + "="*80)
        print("MAIN WALLET CANDIDATES (Ranked by Score)")
        print("="*80)

        # Sort by score
        sorted_candidates = sorted(
            candidates.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )

        print(f"\n{'Rank':<6} {'Address':<44} {'Type':<20} {'Score':<10}")
        print("-" * 90)

        for i, (wallet, info) in enumerate(sorted_candidates[:5], 1):
            type_display = info['type'].replace('_', ' ').title()

            marker = "👑" if i == 1 else f"  "
            print(f"{marker} {i:<4} {wallet:<44} {type_display:<20} {info['score']:>8.1f}")

        print("\n" + "="*80)
        print("MAIN WALLET IDENTIFIED")
        print("="*80)

        main_wallet, main_info = sorted_candidates[0]

        print(f"\n🎯 Most Likely Main Wallet: {main_wallet}")
        print(f"\n   Type: {main_info['type'].replace('_', ' ').title()}")
        print(f"   Confidence Score: {main_info['score']:.1f}")
        print(f"   Incoming Transfers: {main_info['transfers_in']}")
        print(f"   Outgoing Transfers: {main_info['transfers_out']}")
        print(f"   Total Volume In: ${main_info['volume_in']:,.2f}")
        print(f"   Total Volume Out: ${main_info['volume_out']:,.2f}")

        first_date = datetime.fromtimestamp(main_info['first_seen']).strftime('%Y-%m-%d %H:%M:%S')
        last_date = datetime.fromtimestamp(main_info['last_seen']).strftime('%Y-%m-%d %H:%M:%S')
        print(f"   First Activity: {first_date}")
        print(f"   Last Activity: {last_date}")

        if main_info['first_funder']:
            print(f"   ✓ This wallet was the FIRST to fund the proxy")

        return main_wallet, main_info

    def save_analysis(self, main_wallet: str, candidates: Dict, gemini_analysis: Dict, output_dir: Path):
        """Save analysis results to JSON."""
        output_dir.mkdir(exist_ok=True)

        result = {
            'proxy_wallet': self.proxy_wallet,
            'main_wallet': main_wallet,
            'analysis_timestamp': datetime.now().isoformat(),
            'total_transfers': len(self.transfers),
            'filtered_transfers': len(self.filtered_transfers),
            'polymarket_transfers_filtered': len(self.transfers) - len(self.filtered_transfers),
            'gemini_analysis': gemini_analysis.get('analysis', 'N/A'),
            'candidates': {
                wallet: {
                    **info,
                    'first_seen': datetime.fromtimestamp(info['first_seen']).isoformat(),
                    'last_seen': datetime.fromtimestamp(info['last_seen']).isoformat()
                }
                for wallet, info in candidates.items()
            }
        }

        output_file = output_dir / f"{self.proxy_wallet}_main_wallet.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        print(f"\n💾 Analysis saved to: {output_file}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Find the main wallet connected to a Polymarket proxy wallet"
    )
    parser.add_argument(
        "proxy_wallet",
        type=str,
        help="Proxy wallet address to analyze"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./processed/wallet_analysis",
        help="Output directory for analysis results"
    )

    args = parser.parse_args()

    print("="*80)
    print("POLYMARKET PROXY WALLET ANALYZER")
    print("="*80)
    print(f"\nProxy Wallet: {args.proxy_wallet}")
    print(f"Network: Polygon (Chain ID: {POLYGON_CHAIN_ID})")
    print("="*80)

    # Create analyzer
    analyzer = WalletAnalyzer(args.proxy_wallet)

    # Fetch all USDC transfers
    transfers = analyzer.fetch_all_usdc_transfers()

    if not transfers:
        print("\n❌ No USDC transfers found. This wallet may not be active or may not use USDC.")
        return

    # Filter out Polymarket contract transactions
    filtered_transfers = analyzer.filter_polymarket_transactions()

    if not filtered_transfers:
        print("\n❌ No non-Polymarket transfers found. This wallet only interacts with Polymarket contracts.")
        return

    # Analyze filtered transfers
    candidates = analyzer.analyze_transfers()

    if not candidates:
        print("\n❌ Could not identify any wallet candidates.")
        return

    # Filter out protocol contracts (Uniswap, etc.)
    wallet_candidates = analyzer.filter_contract_candidates(candidates)

    if not wallet_candidates:
        print("\n❌ All candidates are smart contracts. No wallet addresses found.")
        print("    This might indicate the proxy wallet only interacts with DeFi protocols.")
        return

    # Get Gemini AI analysis
    gemini_analysis = analyzer.analyze_with_gemini(wallet_candidates)

    # Identify main wallet
    result = analyzer.identify_main_wallet(wallet_candidates)

    if result:
        main_wallet, main_info = result

        # Save analysis
        output_dir = Path(args.output_dir)
        analyzer.save_analysis(main_wallet, wallet_candidates, gemini_analysis, output_dir)

        print("\n" + "="*80)
        print("✅ ANALYSIS COMPLETE")
        print("="*80)
        print(f"\nMain Wallet: {main_wallet}")
        print(f"Proxy Wallet: {args.proxy_wallet}")
        print("\nQuick Links:")
        print(f"  • Main Wallet on Polygonscan: https://polygonscan.com/address/{main_wallet}")
        print(f"  • Proxy Wallet on Polygonscan: https://polygonscan.com/address/{args.proxy_wallet}")
        print(f"  • Main Wallet on Arkham: https://intel.arkm.com/explorer/address/{main_wallet}")
        print(f"  • Proxy Wallet on Arkham: https://intel.arkm.com/explorer/address/{args.proxy_wallet}")
        print("="*80 + "\n")


if __name__ == "__main__":
    main()

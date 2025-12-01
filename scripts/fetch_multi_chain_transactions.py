#!/usr/bin/env python3
"""
Fetch all transactions from a wallet across multiple L1/L2 chains
and identify protocol usage.

Supports:
- Ethereum (1)
- Polygon (137)
- Arbitrum (42161)
- Optimism (10)
- Base (8453)
- BNB Chain (56)
"""

import os
import sys
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict, Counter
from datetime import datetime
from dotenv import load_dotenv
import json
import polars as pl

# Load environment variables
load_dotenv()

ETHERSCAN_API_KEY = os.getenv("POLY_SCAN_API")  # Works for all chains via V2
if not ETHERSCAN_API_KEY:
    print("❌ POLY_SCAN_API not found in .env file")
    sys.exit(1)

# Supported chains
CHAINS = {
    "1": {"name": "Ethereum", "explorer": "https://etherscan.io"},
    "137": {"name": "Polygon", "explorer": "https://polygonscan.com"},
    "42161": {"name": "Arbitrum", "explorer": "https://arbiscan.io"},
    "10": {"name": "Optimism", "explorer": "https://optimistic.etherscan.io"},
    "8453": {"name": "Base", "explorer": "https://basescan.org"},
    "56": {"name": "BNB Chain", "explorer": "https://bscscan.com"},
}

ETHERSCAN_API_BASE = "https://api.etherscan.io/v2/api"


class MultiChainAnalyzer:
    def __init__(self, wallet_address: str, cache_file: str = "processed/contract_cache.json"):
        self.wallet = wallet_address.lower()
        self.all_transactions = []
        self.chain_data = {}
        self.contract_cache = {}
        self.protocol_cache = {}
        self.cache_file = Path(cache_file)
        self.cache_modified = False

        # Load existing cache
        self._load_cache()

    def _load_cache(self):
        """Load contract info cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    self.protocol_cache = cache_data
                    print(f"\n📦 Loaded {len(self.protocol_cache)} cached contract entries from {self.cache_file}")
            except Exception as e:
                print(f"\n⚠️  Failed to load cache: {e}")
                self.protocol_cache = {}
        else:
            print(f"\n📦 No existing cache found. Will create new cache at {self.cache_file}")
            self.protocol_cache = {}

    def _save_cache(self):
        """Save contract info cache to disk."""
        if not self.cache_modified:
            return

        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.protocol_cache, f, indent=2)
            print(f"\n💾 Saved {len(self.protocol_cache)} contract entries to cache")
        except Exception as e:
            print(f"\n⚠️  Failed to save cache: {e}")

    def fetch_normal_transactions(self, chain_id: str, start_block: int = 0) -> List[Dict]:
        """Fetch normal (ETH/native) transactions for a wallet on a specific chain."""
        chain_name = CHAINS[chain_id]["name"]
        print(f"\n📥 Fetching normal transactions on {chain_name}...")

        params = {
            "chainid": chain_id,
            "module": "account",
            "action": "txlist",
            "address": self.wallet,
            "startblock": start_block,
            "endblock": 99999999,
            "page": 1,
            "offset": 10000,  # Max per page
            "sort": "asc",
            "apikey": ETHERSCAN_API_KEY
        }

        try:
            response = requests.get(ETHERSCAN_API_BASE, params=params)
            response.raise_for_status()
            data = response.json()

            if data["status"] == "1" and data["result"]:
                txs = data["result"]
                print(f"  ✓ Found {len(txs)} normal transactions")
                return txs
            else:
                print(f"  ℹ️  No normal transactions found")
                return []

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return []

    def fetch_internal_transactions(self, chain_id: str) -> List[Dict]:
        """Fetch internal transactions for a wallet on a specific chain."""
        chain_name = CHAINS[chain_id]["name"]
        print(f"\n📥 Fetching internal transactions on {chain_name}...")

        params = {
            "chainid": chain_id,
            "module": "account",
            "action": "txlistinternal",
            "address": self.wallet,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 10000,
            "sort": "asc",
            "apikey": ETHERSCAN_API_KEY
        }

        try:
            response = requests.get(ETHERSCAN_API_BASE, params=params)
            response.raise_for_status()
            data = response.json()

            if data["status"] == "1" and data["result"]:
                txs = data["result"]
                print(f"  ✓ Found {len(txs)} internal transactions")
                return txs
            else:
                print(f"  ℹ️  No internal transactions found")
                return []

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return []

    def fetch_erc20_transactions(self, chain_id: str) -> List[Dict]:
        """Fetch ERC-20 token transactions for a wallet on a specific chain."""
        chain_name = CHAINS[chain_id]["name"]
        print(f"\n📥 Fetching ERC-20 transactions on {chain_name}...")

        params = {
            "chainid": chain_id,
            "module": "account",
            "action": "tokentx",
            "address": self.wallet,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 10000,
            "sort": "asc",
            "apikey": ETHERSCAN_API_KEY
        }

        try:
            response = requests.get(ETHERSCAN_API_BASE, params=params)
            response.raise_for_status()
            data = response.json()

            if data["status"] == "1" and data["result"]:
                txs = data["result"]
                print(f"  ✓ Found {len(txs)} ERC-20 transactions")
                return txs
            else:
                print(f"  ℹ️  No ERC-20 transactions found")
                return []

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return []

    def get_contract_info(self, address: str, chain_id: str) -> Optional[Dict]:
        """Get contract information including name."""
        cache_key = f"{chain_id}:{address.lower()}"

        if cache_key in self.protocol_cache:
            return self.protocol_cache[cache_key]

        try:
            params = {
                "chainid": chain_id,
                "module": "contract",
                "action": "getsourcecode",
                "address": address,
                "apikey": ETHERSCAN_API_KEY
            }

            response = requests.get(ETHERSCAN_API_BASE, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "1" and data.get("result"):
                result = data["result"][0]
                contract_info = {
                    "contract_name": result.get("ContractName", "Unknown"),
                    "is_verified": result.get("ContractName", "") != "",
                }

                self.protocol_cache[cache_key] = contract_info
                self.cache_modified = True  # Mark cache as modified
                time.sleep(0.2)  # Rate limiting
                return contract_info

            time.sleep(0.2)
            return None

        except Exception as e:
            print(f"  ⚠️  Error getting contract info: {e}")
            return None

    def collect_unique_addresses(self) -> Dict[str, set]:
        """Collect all unique contract addresses from all transactions."""
        print("\n" + "="*80)
        print("COLLECTING UNIQUE CONTRACT ADDRESSES")
        print("="*80)

        addresses_by_chain = defaultdict(set)

        for chain_id, chain_data in self.chain_data.items():
            # From normal transactions
            for tx in chain_data["normal_txs"]:
                to_addr = tx.get("to", "").lower()
                if to_addr and to_addr != self.wallet:
                    addresses_by_chain[chain_id].add(to_addr)

            # From internal transactions
            for tx in chain_data["internal_txs"]:
                to_addr = tx.get("to", "").lower()
                from_addr = tx.get("from", "").lower()
                if to_addr and to_addr != self.wallet:
                    addresses_by_chain[chain_id].add(to_addr)
                if from_addr and from_addr != self.wallet:
                    addresses_by_chain[chain_id].add(from_addr)

            # From ERC-20 transactions
            for tx in chain_data["erc20_txs"]:
                contract_addr = tx.get("contractAddress", "").lower()
                if contract_addr:
                    addresses_by_chain[chain_id].add(contract_addr)

        total_addresses = sum(len(addrs) for addrs in addresses_by_chain.values())
        print(f"\n📊 Unique addresses found:")
        for chain_id, addrs in addresses_by_chain.items():
            chain_name = CHAINS[chain_id]["name"]
            print(f"  • {chain_name}: {len(addrs)} unique addresses")
        print(f"  • Total: {total_addresses} unique addresses")

        return addresses_by_chain

    def batch_fetch_contract_info(self, addresses_by_chain: Dict[str, set]):
        """Batch fetch contract info for addresses not in cache."""
        print("\n" + "="*80)
        print("BATCH FETCHING CONTRACT INFORMATION")
        print("="*80)

        total_to_fetch = 0
        total_cached = 0

        for chain_id, addresses in addresses_by_chain.items():
            chain_name = CHAINS[chain_id]["name"]

            # Check which addresses need fetching
            to_fetch = []
            for addr in addresses:
                cache_key = f"{chain_id}:{addr}"
                if cache_key not in self.protocol_cache:
                    to_fetch.append(addr)
                else:
                    total_cached += 1

            if to_fetch:
                print(f"\n🔍 {chain_name}: Fetching {len(to_fetch)} new contracts (✓ {len(addresses) - len(to_fetch)} cached)")

                for i, addr in enumerate(to_fetch, 1):
                    if i % 10 == 0:
                        print(f"  Progress: {i}/{len(to_fetch)} contracts fetched...")

                    self.get_contract_info(addr, chain_id)
                    total_to_fetch += 1
            else:
                print(f"\n✓ {chain_name}: All {len(addresses)} contracts already cached")

        print(f"\n📊 Batch fetch summary:")
        print(f"  • Cached hits: {total_cached}")
        print(f"  • New fetches: {total_to_fetch}")
        print(f"  • API calls saved: {total_cached}")

        if total_to_fetch > 0:
            print(f"  • Cache hit rate: {total_cached / (total_cached + total_to_fetch) * 100:.1f}%")

    def fetch_all_chain_data(self, chain_ids: List[str] = None):
        """Fetch all transaction data across specified chains."""
        if chain_ids is None:
            chain_ids = list(CHAINS.keys())

        print("\n" + "="*80)
        print("FETCHING MULTI-CHAIN TRANSACTION DATA")
        print("="*80)
        print(f"\nWallet: {self.wallet}")
        print(f"Chains: {len(chain_ids)}")
        print("="*80)

        for chain_id in chain_ids:
            chain_name = CHAINS[chain_id]["name"]
            print(f"\n{'='*80}")
            print(f"CHAIN: {chain_name} (ID: {chain_id})")
            print(f"{'='*80}")

            chain_txs = {
                "chain_id": chain_id,
                "chain_name": chain_name,
                "normal_txs": [],
                "internal_txs": [],
                "erc20_txs": []
            }

            # Fetch normal transactions
            chain_txs["normal_txs"] = self.fetch_normal_transactions(chain_id)
            time.sleep(0.3)  # Rate limiting

            # Fetch internal transactions
            chain_txs["internal_txs"] = self.fetch_internal_transactions(chain_id)
            time.sleep(0.3)

            # Fetch ERC-20 transactions
            chain_txs["erc20_txs"] = self.fetch_erc20_transactions(chain_id)
            time.sleep(0.3)

            total_txs = (
                len(chain_txs["normal_txs"]) +
                len(chain_txs["internal_txs"]) +
                len(chain_txs["erc20_txs"])
            )

            print(f"\n📊 {chain_name} Summary:")
            print(f"  • Normal transactions: {len(chain_txs['normal_txs'])}")
            print(f"  • Internal transactions: {len(chain_txs['internal_txs'])}")
            print(f"  • ERC-20 transactions: {len(chain_txs['erc20_txs'])}")
            print(f"  • Total: {total_txs}")

            self.chain_data[chain_id] = chain_txs

    def categorize_protocol(self, contract_name: str) -> str:
        """Categorize protocol based on contract name patterns."""
        name_lower = contract_name.lower()

        # DeFi Protocol patterns - DEXs
        if "uniswap" in name_lower or "swap" in name_lower and "uni" in name_lower:
            return "🔄 DEX: Uniswap"
        elif "nonfungiblepositionmanager" in name_lower or "swaprouter" in name_lower:
            # Uniswap V3 specific contracts
            return "🔄 DEX: Uniswap V3"
        elif "sushiswap" in name_lower or "sushi" in name_lower:
            return "🔄 DEX: SushiSwap"
        elif "curve" in name_lower:
            return "🔄 DEX: Curve"
        elif "balancer" in name_lower:
            return "🔄 DEX: Balancer"
        elif "1inch" in name_lower or "oneinch" in name_lower or "aggregationrouterv" in name_lower:
            return "🔄 DEX: 1inch"
        elif "pancake" in name_lower:
            return "🔄 DEX: PancakeSwap"
        elif "quickswap" in name_lower or name_lower == "quick" or "quickperiphery" in name_lower:
            return "🔄 DEX: QuickSwap"
        elif "odos" in name_lower or "odosrouter" in name_lower:
            return "🔄 DEX: Odos"
        elif "paraswap" in name_lower:
            return "🔄 DEX: ParaSwap"
        elif "0x" in name_lower and "exchange" in name_lower:
            return "🔄 DEX: 0x Protocol"

        # Lending protocols
        elif "aave" in name_lower or "pool" in name_lower and "aave" in contract_name:
            return "💰 Lending: Aave"
        elif "compound" in name_lower or "comptroller" in name_lower or "ctoken" in name_lower:
            return "💰 Lending: Compound"
        elif "maker" in name_lower or "dai" in name_lower and "vault" in name_lower:
            return "💰 Lending: MakerDAO"
        elif "morpho" in name_lower:
            return "💰 Lending: Morpho"
        elif "radiant" in name_lower:
            return "💰 Lending: Radiant"

        # Bridges
        elif "bridge" in name_lower or "portal" in name_lower:
            if "polygon" in name_lower:
                return "🌉 Bridge: Polygon"
            elif "arbitrum" in name_lower:
                return "🌉 Bridge: Arbitrum"
            elif "optimism" in name_lower:
                return "🌉 Bridge: Optimism"
            elif "stargate" in name_lower:
                return "🌉 Bridge: Stargate"
            elif "hop" in name_lower:
                return "🌉 Bridge: Hop Protocol"
            else:
                return f"🌉 Bridge: {contract_name}"
        elif "cctp" in name_lower or "messagetransmitter" in name_lower or "tokenmessenger" in name_lower:
            return "🌉 Bridge: Circle CCTP"
        elif "across" in name_lower and "bridge" in name_lower:
            return "🌉 Bridge: Across"

        # Polymarket
        elif "polymarket" in name_lower or "conditional" in name_lower:
            return "🎲 Prediction: Polymarket"

        # NFT Marketplaces
        elif "opensea" in name_lower or "seaport" in name_lower:
            return "🖼️ NFT: OpenSea"
        elif "blur" in name_lower:
            return "🖼️ NFT: Blur"
        elif "rarible" in name_lower:
            return "🖼️ NFT: Rarible"

        # Liquid Staking
        elif "lido" in name_lower or "steth" in name_lower:
            return "🔒 Staking: Lido"
        elif "rocketpool" in name_lower or "reth" in name_lower:
            return "🔒 Staking: Rocket Pool"

        # Wallets
        elif "gnosis" in name_lower or "safe" in name_lower:
            return "👛 Wallet: Gnosis Safe"
        elif "multisig" in name_lower:
            return "👛 Wallet: MultiSig"

        # Token contracts (catch-all for proxies and token contracts)
        elif "proxy" in name_lower or "token" in name_lower or "erc20" in name_lower:
            return f"💎 Token: {contract_name}"

        # Unknown/Other
        else:
            return f"❓ Other: {contract_name}"

    def analyze_protocol_usage(self):
        """Analyze which protocols the wallet interacts with (uses cached contract data)."""
        print("\n" + "="*80)
        print("ANALYZING PROTOCOL USAGE")
        print("="*80)

        protocol_interactions = defaultdict(lambda: {
            "chains": set(),
            "tx_count": 0,
            "first_seen": None,
            "last_seen": None,
            "contract_addresses": set()
        })

        for chain_id, chain_data in self.chain_data.items():
            chain_name = chain_data["chain_name"]
            print(f"\n🔍 Analyzing {chain_name}... (using cached contract data)")

            # Analyze normal transactions (these are the most important - direct protocol interactions)
            for tx in chain_data["normal_txs"]:
                to_addr = tx.get("to", "").lower()

                if to_addr and to_addr != self.wallet:
                    # Get contract info from cache (should already be there from batch fetch)
                    cache_key = f"{chain_id}:{to_addr}"
                    contract_info = self.protocol_cache.get(cache_key)

                    if contract_info and contract_info["is_verified"]:
                        raw_contract_name = contract_info["contract_name"]
                        protocol_name = self.categorize_protocol(raw_contract_name)
                        timestamp = int(tx.get("timeStamp", 0))

                        protocol_interactions[protocol_name]["chains"].add(chain_name)
                        protocol_interactions[protocol_name]["tx_count"] += 1
                        protocol_interactions[protocol_name]["contract_addresses"].add(to_addr)

                        if protocol_interactions[protocol_name]["first_seen"] is None:
                            protocol_interactions[protocol_name]["first_seen"] = timestamp
                        else:
                            protocol_interactions[protocol_name]["first_seen"] = min(
                                protocol_interactions[protocol_name]["first_seen"],
                                timestamp
                            )

                        if protocol_interactions[protocol_name]["last_seen"] is None:
                            protocol_interactions[protocol_name]["last_seen"] = timestamp
                        else:
                            protocol_interactions[protocol_name]["last_seen"] = max(
                                protocol_interactions[protocol_name]["last_seen"],
                                timestamp
                            )

        # Clean up contract_addresses for serialization
        for protocol in protocol_interactions.values():
            protocol["contract_addresses"] = list(protocol["contract_addresses"])

        return protocol_interactions

    def generate_report(self, protocol_interactions: Dict, output_dir: Path):
        """Generate comprehensive report."""
        print("\n" + "="*80)
        print("PROTOCOL USAGE REPORT")
        print("="*80)

        # Convert to list and sort by transaction count
        protocols = []
        for protocol, data in protocol_interactions.items():
            first_date = datetime.fromtimestamp(data["first_seen"]).isoformat() if data["first_seen"] else None
            last_date = datetime.fromtimestamp(data["last_seen"]).isoformat() if data["last_seen"] else None

            protocols.append({
                "protocol": protocol,
                "chains": ", ".join(sorted(data["chains"])),  # Convert list to string for CSV
                "chain_count": len(data["chains"]),
                "tx_count": data["tx_count"],
                "first_seen": first_date,
                "last_seen": last_date
            })

        protocols.sort(key=lambda x: x["tx_count"], reverse=True)

        # Print top protocols
        print(f"\n📊 Top 20 Protocols by Transaction Count:")
        print(f"\n{'Rank':<6} {'Protocol':<40} {'Chains':<20} {'Transactions'}")
        print("-" * 90)

        for i, p in enumerate(protocols[:20], 1):
            chains_str = p["chains"]
            if len(chains_str) > 20:
                chains_str = chains_str[:17] + "..."
            print(f"{i:<6} {p['protocol'][:40]:<40} {chains_str:<20} {p['tx_count']}")

        # Save to CSV using polars
        output_dir.mkdir(parents=True, exist_ok=True)

        df = pl.DataFrame(protocols)
        csv_path = output_dir / f"{self.wallet}_protocol_usage.csv"
        df.write_csv(csv_path)
        print(f"\n💾 Protocol usage saved to: {csv_path}")

        # Save chain summary
        chain_summary = []
        for chain_id, chain_data in self.chain_data.items():
            total_txs = (
                len(chain_data["normal_txs"]) +
                len(chain_data["internal_txs"]) +
                len(chain_data["erc20_txs"])
            )
            chain_summary.append({
                "chain_id": chain_id,
                "chain_name": chain_data["chain_name"],
                "normal_txs": len(chain_data["normal_txs"]),
                "internal_txs": len(chain_data["internal_txs"]),
                "erc20_txs": len(chain_data["erc20_txs"]),
                "total_txs": total_txs
            })

        chain_df = pl.DataFrame(chain_summary)
        chain_csv_path = output_dir / f"{self.wallet}_chain_summary.csv"
        chain_df.write_csv(chain_csv_path)
        print(f"💾 Chain summary saved to: {chain_csv_path}")

        # Save protocol usage as JSON
        protocol_json_path = output_dir / f"{self.wallet}_protocol_usage.json"
        with open(protocol_json_path, 'w') as f:
            json.dump(protocols, f, indent=2)
        print(f"💾 Protocol usage JSON saved to: {protocol_json_path}")

        # Save raw transaction data
        print("\n💾 Saving raw transaction data...")
        json_path = output_dir / f"{self.wallet}_raw_transactions.json"
        with open(json_path, 'w') as f:
            json.dump(self.chain_data, f, indent=2)
        print(f"💾 Raw data saved to: {json_path}")

        return protocols


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch multi-chain transactions and analyze protocol usage"
    )
    parser.add_argument(
        "wallet",
        type=str,
        help="Wallet address to analyze"
    )
    parser.add_argument(
        "--chains",
        type=str,
        nargs="+",
        choices=list(CHAINS.keys()),
        default=None,
        help="Chain IDs to fetch (default: all supported chains)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./processed/multi_chain_analysis",
        help="Output directory for results"
    )

    args = parser.parse_args()

    print("="*80)
    print("MULTI-CHAIN WALLET ANALYZER")
    print("="*80)
    print(f"\nWallet: {args.wallet}")

    if args.chains:
        chain_names = [CHAINS[c]["name"] for c in args.chains]
        print(f"Chains: {', '.join(chain_names)}")
    else:
        print(f"Chains: All supported ({len(CHAINS)} chains)")

    print("="*80)

    # Create analyzer
    analyzer = MultiChainAnalyzer(args.wallet)

    # Fetch all data
    analyzer.fetch_all_chain_data(args.chains)

    # Collect unique addresses
    addresses_by_chain = analyzer.collect_unique_addresses()

    # Batch fetch contract info (uses cache, only fetches what's needed)
    analyzer.batch_fetch_contract_info(addresses_by_chain)

    # Save cache
    analyzer._save_cache()

    # Analyze protocols
    protocol_interactions = analyzer.analyze_protocol_usage()

    if not protocol_interactions:
        print("\n❌ No protocol interactions found across any chain.")
        return

    # Generate report
    output_dir = Path(args.output_dir)
    protocols = analyzer.generate_report(protocol_interactions, output_dir)

    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE")
    print("="*80)
    print(f"\nWallet: {args.wallet}")
    print(f"Total Protocols: {len(protocols)}")
    print(f"Total Chains with Activity: {len([c for c in analyzer.chain_data.values() if len(c['normal_txs']) + len(c['internal_txs']) + len(c['erc20_txs']) > 0])}")
    print(f"\nOutput Directory: {output_dir.absolute()}")
    print(f"Contract Cache: {analyzer.cache_file.absolute()}")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()

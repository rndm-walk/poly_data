#!/usr/bin/env python3
"""
Analyze transactions from top parlay users to identify what protocols they're using
beyond Polymarket, using Gemini API for protocol identification.
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any
from dotenv import load_dotenv
import google.generativeai as genai

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Load wallet mappings from single source of truth
from wallet_mappings import WALLET_MAPPINGS

# Load environment variables
load_dotenv()

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")

genai.configure(api_key=GEMINI_API_KEY)

# Known Polymarket contracts to filter out
POLYMARKET_CONTRACTS = {
    "polymarket", "ctf exchange", "conditional tokens",
    "neg risk ctf exchange", "neg risk adapter"
}


class ProtocolAnalyzer:
    def __init__(self, data_dir: Path, model_name: str = "gemini-3-pro-preview"):
        self.data_dir = data_dir
        self.model = genai.GenerativeModel(model_name)
        self.wallet_data = {}
        self.protocol_cache = {}  # Cache for contract -> protocol mappings

    def load_wallet_transactions(self, wallet_address: str) -> List[Dict[str, Any]]:
        """Load transactions for a given wallet address."""
        wallet_file = self.data_dir / f"{wallet_address}.json"

        if not wallet_file.exists():
            print(f"⚠️  No data file found for {wallet_address}")
            return []

        with open(wallet_file, 'r') as f:
            transactions = json.load(f)

        print(f"✓ Loaded {len(transactions):,} transactions for {wallet_address}")
        return transactions

    def extract_contract_interactions(self, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract unique contract addresses and their interaction patterns (both outgoing and incoming)."""
        contracts = defaultdict(lambda: {
            "count": 0,
            "chains": set(),
            "token_transfers": [],
            "contract_names": set(),
            "entity_names": set(),
            "tags": set(),
            "total_usd": 0,
            "sample_txs": [],
            "direction": set()  # Track if outgoing, incoming, or both
        })

        for tx in transactions:
            # Check OUTGOING transactions (wallet sending TO a contract/entity)
            to_addr = tx.get("toAddress", {})
            to_contract = to_addr.get("address")
            to_is_contract = tx.get("toIsContract", False)
            to_has_entity = to_addr.get("arkhamEntity") or to_addr.get("predictedEntity")

            # Check INCOMING transactions (wallet receiving FROM a contract/entity)
            from_addr = tx.get("fromAddress", {})
            from_contract = from_addr.get("address")
            from_is_contract = tx.get("fromIsContract", False)
            from_has_entity = from_addr.get("arkhamEntity") or from_addr.get("predictedEntity")

            # Process OUTGOING interactions
            if to_contract and (to_is_contract or to_has_entity):
                contract_data = contracts[to_contract.lower()]
                contract_data["count"] += 1
                contract_data["chains"].add(tx.get("chain", "unknown"))
                contract_data["direction"].add("outgoing")

                # Extract entity/protocol names
                if to_addr.get("arkhamEntity"):
                    contract_data["entity_names"].add(to_addr["arkhamEntity"].get("name", ""))

                if to_addr.get("predictedEntity"):
                    contract_data["entity_names"].add(to_addr["predictedEntity"].get("name", ""))
                    tags = to_addr.get("predictedEntity", {}).get("populatedTags", [])
                    for tag in tags:
                        contract_data["tags"].add(tag.get("label", ""))

                # Track token transfers
                if tx.get("tokenSymbol"):
                    contract_data["token_transfers"].append({
                        "symbol": tx.get("tokenSymbol"),
                        "value": tx.get("unitValue", 0),
                        "usd": tx.get("historicalUSD", 0)
                    })
                    contract_data["total_usd"] += tx.get("historicalUSD", 0)

                # Keep sample transactions
                if len(contract_data["sample_txs"]) < 3:
                    contract_data["sample_txs"].append({
                        "hash": tx.get("transactionHash"),
                        "timestamp": tx.get("blockTimestamp"),
                        "token": tx.get("tokenSymbol"),
                        "value_usd": tx.get("historicalUSD", 0),
                        "direction": "outgoing"
                    })

            # Process INCOMING interactions
            if from_contract and (from_is_contract or from_has_entity):
                contract_data = contracts[from_contract.lower()]
                contract_data["count"] += 1
                contract_data["chains"].add(tx.get("chain", "unknown"))
                contract_data["direction"].add("incoming")

                # Extract entity/protocol names
                if from_addr.get("arkhamEntity"):
                    contract_data["entity_names"].add(from_addr["arkhamEntity"].get("name", ""))

                if from_addr.get("predictedEntity"):
                    contract_data["entity_names"].add(from_addr["predictedEntity"].get("name", ""))
                    tags = from_addr.get("predictedEntity", {}).get("populatedTags", [])
                    for tag in tags:
                        contract_data["tags"].add(tag.get("label", ""))

                # Track token transfers
                if tx.get("tokenSymbol"):
                    contract_data["token_transfers"].append({
                        "symbol": tx.get("tokenSymbol"),
                        "value": tx.get("unitValue", 0),
                        "usd": tx.get("historicalUSD", 0)
                    })
                    contract_data["total_usd"] += tx.get("historicalUSD", 0)

                # Keep sample transactions
                if len(contract_data["sample_txs"]) < 3:
                    contract_data["sample_txs"].append({
                        "hash": tx.get("transactionHash"),
                        "timestamp": tx.get("blockTimestamp"),
                        "token": tx.get("tokenSymbol"),
                        "value_usd": tx.get("historicalUSD", 0),
                        "direction": "incoming"
                    })

        # Convert sets to lists for JSON serialization
        for addr, data in contracts.items():
            data["chains"] = list(data["chains"])
            data["entity_names"] = list(data["entity_names"])
            data["tags"] = list(data["tags"])
            data["direction"] = list(data["direction"])
            # Also ensure sample_txs is a list
            data["sample_txs"] = list(data["sample_txs"]) if isinstance(data["sample_txs"], set) else data["sample_txs"]

        return dict(contracts)

    def is_polymarket_related(self, contract_data: Dict[str, Any]) -> bool:
        """Check if a contract is related to Polymarket."""
        all_text = " ".join(
            contract_data.get("entity_names", []) +
            contract_data.get("tags", [])
        ).lower()

        return any(pm in all_text for pm in POLYMARKET_CONTRACTS)

    def analyze_contracts_with_gemini(self, contracts: Dict[str, Dict[str, Any]], batch_size: int = 100, full_data: bool = False) -> Dict[str, str]:
        """Use Gemini to identify protocols from contract interactions."""
        # Filter out Polymarket contracts
        non_pm_contracts = {
            addr: data for addr, data in contracts.items()
            if not self.is_polymarket_related(data)
        }

        if not non_pm_contracts:
            return {}

        print(f"\n🤖 Analyzing {len(non_pm_contracts)} non-Polymarket contracts with Gemini...")

        protocol_results = {}
        contract_list = list(non_pm_contracts.items())

        # Process in batches to avoid token limits
        for i in range(0, len(contract_list), batch_size):
            batch = contract_list[i:i+batch_size]

            # Prepare contract data for Gemini
            if full_data:
                # Send complete raw JSON data
                # Deep copy and ensure all sets are converted to lists
                contract_data_json = {}
                for addr, data in batch:
                    # Create a JSON-serializable copy
                    data_copy = {}
                    for key, value in data.items():
                        if isinstance(value, set):
                            data_copy[key] = list(value)
                        elif isinstance(value, list):
                            # Ensure nested sets in lists are also converted
                            data_copy[key] = value
                        else:
                            data_copy[key] = value
                    contract_data_json[addr] = data_copy
                contracts_json_str = json.dumps(contract_data_json, indent=2)
            else:
                # Compact summary (original)
                contract_summaries = []
                for addr, data in batch:
                    summary = f"""
Contract: {addr}
Chains: {', '.join(data['chains'])}
Interactions: {data['count']} times
Total USD: ${data['total_usd']:,.2f}
Entity Names: {', '.join(data['entity_names']) if data['entity_names'] else 'Unknown'}
Tags: {', '.join(data['tags'][:5]) if data['tags'] else 'None'}
"""
                    contract_summaries.append(summary)

            if full_data:
                prompt = f"""You are a blockchain protocol expert. Analyze the complete contract interaction data below and identify what DeFi protocols, dApps, or services they represent.

The data includes:
- Contract addresses
- Entity names and tags from Arkham Intelligence
- All transaction details (direction, chains, tokens, USD values, timestamps)
- Token transfers

For each contract address (the keys in the JSON), provide:
1. The protocol/service name (e.g., "Uniswap", "Aave", "Coinbase", "Kraken")
2. A brief category (e.g., "DEX", "Lending", "Bridge", "NFT", "Gaming", "CEX")

Use all available information including entity_names, tags, token types, and transaction patterns to make accurate identifications.

Contract Data (JSON):
{contracts_json_str}

Format your response as JSON with contract addresses as keys:
{{
  "0xabc...": {{"protocol": "Protocol Name", "category": "Category"}},
  ...
}}

If you cannot identify a contract, use "Unknown" for both fields.
"""
            else:
                prompt = f"""You are a blockchain protocol expert. Analyze these contract interactions and identify what DeFi protocols, dApps, or services they represent.

For each contract, provide:
1. The protocol/service name (e.g., "Uniswap", "Aave", "Bridge Protocol")
2. A brief category (e.g., "DEX", "Lending", "Bridge", "NFT", "Gaming")

Contracts to analyze:
{chr(10).join(contract_summaries)}

Format your response as JSON with contract addresses as keys:
{{
  "0xabc...": {{"protocol": "Protocol Name", "category": "Category"}},
  ...
}}

If you cannot identify a contract, use "Unknown" for both fields.
"""

            try:
                response = self.model.generate_content(prompt)

                # Parse JSON response
                if not response or not response.text:
                    raise ValueError("Empty response from Gemini")

                response_text = response.text.strip()

                # Remove markdown code blocks if present
                if response_text.startswith("```"):
                    # Split by ``` and get the content between first and second ```
                    parts = response_text.split("```")
                    if len(parts) >= 3:
                        response_text = parts[1]
                    elif len(parts) >= 2:
                        response_text = parts[1]
                    # Remove 'json' prefix if present
                    if response_text.startswith("json"):
                        response_text = response_text[4:].strip()

                response_text = response_text.strip()

                if not response_text:
                    raise ValueError("Response text is empty after cleaning")

                # Try to parse JSON
                try:
                    batch_results = json.loads(response_text)
                except json.JSONDecodeError as je:
                    # Print first 500 chars of response for debugging
                    print(f"  ⚠️  JSON parse error. Response preview: {response_text[:500]}")
                    raise je

                protocol_results.update(batch_results)

                print(f"  ✓ Processed batch {i//batch_size + 1}/{(len(contract_list)-1)//batch_size + 1}")

            except Exception as e:
                print(f"  ⚠️  Error processing batch {i//batch_size + 1}: {str(e)[:200]}")
                # Add as unknown if parsing fails
                for addr, _ in batch:
                    protocol_results[addr] = {"protocol": "Unknown", "category": "Unknown"}

        return protocol_results

    def analyze_wallet(self, proxy_wallet: str, main_wallet: str = None, full_data: bool = False) -> Dict[str, Any]:
        """Analyze a single wallet's protocol usage."""
        wallet_to_analyze = main_wallet if main_wallet else proxy_wallet

        print(f"\n{'='*80}")
        print(f"Analyzing: {proxy_wallet}")
        if main_wallet:
            print(f"Main wallet: {main_wallet}")
        print(f"{'='*80}")

        transactions = self.load_wallet_transactions(wallet_to_analyze)

        if not transactions:
            return {"error": "No transactions found"}

        # Extract contract interactions
        contracts = self.extract_contract_interactions(transactions)
        print(f"✓ Found {len(contracts)} unique contract interactions")

        # Analyze with Gemini
        protocol_analysis = self.analyze_contracts_with_gemini(contracts, full_data=full_data)

        # Combine results
        results = {
            "proxy_wallet": proxy_wallet,
            "main_wallet": main_wallet,
            "volume": WALLET_MAPPINGS.get(proxy_wallet.lower(), {}).get("volume", 0),
            "total_transactions": len(transactions),
            "total_contracts": len(contracts),
            "protocols": [],
            "raw_contracts": contracts,  # Store raw contract data for detailed reports
            "protocol_analysis": protocol_analysis  # Store protocol mapping
        }

        # Aggregate by protocol
        protocol_summary = defaultdict(lambda: {
            "category": "",
            "contracts": [],
            "interactions": 0,
            "total_usd": 0,
            "chains": set(),
            "sample_txs": []
        })

        for addr, protocol_info in protocol_analysis.items():
            protocol_name = protocol_info.get("protocol", "Unknown")
            category = protocol_info.get("category", "Unknown")
            contract_data = contracts.get(addr, {})

            protocol_summary[protocol_name]["category"] = category
            protocol_summary[protocol_name]["contracts"].append({
                "address": addr,
                "interactions": contract_data.get("count", 0),
                "total_usd": contract_data.get("total_usd", 0),
                "chains": contract_data.get("chains", []),
                "entity_names": contract_data.get("entity_names", []),
                "sample_txs": contract_data.get("sample_txs", [])
            })
            protocol_summary[protocol_name]["interactions"] += contract_data.get("count", 0)
            protocol_summary[protocol_name]["total_usd"] += contract_data.get("total_usd", 0)
            protocol_summary[protocol_name]["chains"].update(contract_data.get("chains", []))

            # Collect sample transactions
            for tx in contract_data.get("sample_txs", [])[:3]:
                if len(protocol_summary[protocol_name]["sample_txs"]) < 5:
                    protocol_summary[protocol_name]["sample_txs"].append(tx)

        # Sort by interactions
        sorted_protocols = sorted(
            protocol_summary.items(),
            key=lambda x: x[1]["interactions"],
            reverse=True
        )

        for protocol, data in sorted_protocols:
            results["protocols"].append({
                "protocol": protocol,
                "category": data["category"],
                "interactions": data["interactions"],
                "total_usd": data["total_usd"],
                "num_contracts": len(data["contracts"]),
                "chains": list(data["chains"]),
                "contracts": data["contracts"],
                "sample_txs": data["sample_txs"]
            })

        return results

    def analyze_all_wallets(self, full_data: bool = False) -> List[Dict[str, Any]]:
        """Analyze all mapped wallets."""
        all_results = []

        for proxy_wallet, info in WALLET_MAPPINGS.items():
            main_wallet = info.get("main_wallet")

            # Skip CEX wallets (no transaction data)
            if "source" in info and "CEX" in info["source"]:
                print(f"\n⏭️  Skipping {proxy_wallet} (CEX deposit)")
                continue

            result = self.analyze_wallet(proxy_wallet, main_wallet, full_data=full_data)
            all_results.append(result)

        return all_results

    def generate_markdown_report(self, result: Dict[str, Any], output_file: Path):
        """Generate a detailed markdown report for a single wallet."""
        if "error" in result:
            return

        wallet = result.get("main_wallet") or result.get("proxy_wallet")
        proxy = result.get("proxy_wallet")
        volume = result.get("volume", 0)
        total_txs = result.get("total_transactions", 0)
        total_contracts = result.get("total_contracts", 0)
        protocols = result.get("protocols", [])

        md_lines = []

        # Header
        md_lines.append(f"# Protocol Analysis: {wallet}")
        md_lines.append("")
        md_lines.append("**Parlay User Protocol Usage Report**")
        md_lines.append("")

        # Overview
        md_lines.append("## 📊 Overview")
        md_lines.append("")
        md_lines.append(f"- **Main Wallet:** `{wallet}`")
        if proxy and proxy != wallet:
            md_lines.append(f"- **Proxy Wallet:** `{proxy}`")
        md_lines.append(f"- **Parlay Trading Volume:** ${volume:,.2f}")
        md_lines.append(f"- **Total Transactions Analyzed:** {total_txs:,}")
        md_lines.append(f"- **Unique Contracts Interacted:** {total_contracts:,}")
        md_lines.append(f"- **Protocols Identified:** {len(protocols)}")
        md_lines.append("")

        # Summary table
        md_lines.append("## 📈 Protocol Summary")
        md_lines.append("")
        md_lines.append("| Rank | Protocol | Category | Interactions | Total USD | Contracts | Chains |")
        md_lines.append("|------|----------|----------|--------------|-----------|-----------|--------|")

        for i, protocol in enumerate(protocols, 1):
            chains_str = ", ".join(protocol.get("chains", []))
            md_lines.append(
                f"| {i} | **{protocol['protocol']}** | {protocol['category']} | "
                f"{protocol['interactions']:,} | ${protocol['total_usd']:,.2f} | "
                f"{protocol['num_contracts']} | {chains_str} |"
            )

        md_lines.append("")

        # Category breakdown
        md_lines.append("## 🏷️ Protocol Categories")
        md_lines.append("")

        category_stats = defaultdict(lambda: {"count": 0, "interactions": 0, "usd": 0})
        for protocol in protocols:
            cat = protocol["category"]
            category_stats[cat]["count"] += 1
            category_stats[cat]["interactions"] += protocol["interactions"]
            category_stats[cat]["usd"] += protocol["total_usd"]

        sorted_categories = sorted(
            category_stats.items(),
            key=lambda x: x[1]["interactions"],
            reverse=True
        )

        md_lines.append("| Category | Protocols | Interactions | Total USD |")
        md_lines.append("|----------|-----------|--------------|-----------|")
        for cat, stats in sorted_categories:
            md_lines.append(
                f"| {cat} | {stats['count']} | {stats['interactions']:,} | "
                f"${stats['usd']:,.2f} |"
            )

        md_lines.append("")

        # Detailed protocol breakdown
        md_lines.append("## 🔍 Detailed Protocol Analysis")
        md_lines.append("")

        for i, protocol in enumerate(protocols, 1):
            md_lines.append(f"### {i}. {protocol['protocol']}")
            md_lines.append("")
            md_lines.append(f"**Category:** {protocol['category']}")
            md_lines.append("")
            md_lines.append(f"**Statistics:**")
            md_lines.append(f"- Total Interactions: {protocol['interactions']:,}")
            md_lines.append(f"- Total USD Volume: ${protocol['total_usd']:,.2f}")
            md_lines.append(f"- Unique Contracts: {protocol['num_contracts']}")
            md_lines.append(f"- Chains: {', '.join(protocol.get('chains', ['Unknown']))}")
            md_lines.append("")

            # Contract details
            md_lines.append("**Contracts Used:**")
            md_lines.append("")
            md_lines.append("| Contract Address | Interactions | USD Volume | Chains |")
            md_lines.append("|-----------------|--------------|------------|--------|")

            for contract in protocol.get("contracts", [])[:10]:  # Limit to top 10 contracts
                addr = contract.get("address", "Unknown")
                interactions = contract.get("interactions", 0)
                usd = contract.get("total_usd", 0)
                chains = ", ".join(contract.get("chains", []))

                md_lines.append(
                    f"| `{addr}` | {interactions:,} | ${usd:,.2f} | {chains} |"
                )

            md_lines.append("")

            # Sample transactions
            sample_txs = protocol.get("sample_txs", [])
            if sample_txs:
                md_lines.append("**Sample Transactions:**")
                md_lines.append("")

                for tx in sample_txs[:5]:
                    tx_hash = tx.get("hash", "Unknown")
                    timestamp = tx.get("timestamp", "Unknown")
                    token = tx.get("token", "N/A")
                    value_usd = tx.get("value_usd", 0)

                    md_lines.append(f"- **TX:** `{tx_hash}`")
                    md_lines.append(f"  - Time: {timestamp}")
                    md_lines.append(f"  - Token: {token}")
                    md_lines.append(f"  - Value: ${value_usd:,.2f}")
                    md_lines.append("")

            md_lines.append("---")
            md_lines.append("")

        # Footer
        md_lines.append("## 📝 Notes")
        md_lines.append("")
        md_lines.append("- This report excludes Polymarket-related contracts")
        md_lines.append("- Protocol identification powered by Gemini AI")
        md_lines.append("- USD values are historical at time of transaction")
        md_lines.append(f"- Report generated: {Path.cwd()}")
        md_lines.append("")

        # Write to file
        with open(output_file, 'w') as f:
            f.write("\n".join(md_lines))

        print(f"✅ Markdown report saved to: {output_file}")

    def generate_report(self, results: List[Dict[str, Any]], output_file: Path):
        """Generate a comprehensive report."""
        # Save detailed JSON
        json_output = output_file.parent / f"{output_file.stem}_detailed.json"
        with open(json_output, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n{'='*80}")
        print("PROTOCOL USAGE SUMMARY - TOP PARLAY USERS")
        print(f"{'='*80}\n")

        report_lines = []

        # Overall protocol frequency
        all_protocols = defaultdict(lambda: {
            "users": 0,
            "total_interactions": 0,
            "total_usd": 0,
            "categories": set()
        })

        for wallet_result in results:
            if "error" in wallet_result:
                continue

            for protocol_info in wallet_result.get("protocols", []):
                protocol = protocol_info["protocol"]
                all_protocols[protocol]["users"] += 1
                all_protocols[protocol]["total_interactions"] += protocol_info["interactions"]
                all_protocols[protocol]["total_usd"] += protocol_info["total_usd"]
                all_protocols[protocol]["categories"].add(protocol_info["category"])

        # Top protocols across all users
        report_lines.append("## TOP PROTOCOLS ACROSS ALL USERS\n")
        sorted_overall = sorted(
            all_protocols.items(),
            key=lambda x: x[1]["users"],
            reverse=True
        )

        for protocol, data in sorted_overall[:15]:
            categories = ", ".join(data["categories"])
            report_lines.append(
                f"{protocol:30} | Users: {data['users']:2} | "
                f"Interactions: {data['total_interactions']:6,} | "
                f"USD: ${data['total_usd']:12,.0f} | {categories}"
            )

        report_lines.append("\n" + "="*80 + "\n")

        # Per-user breakdown
        report_lines.append("## PER-USER PROTOCOL USAGE\n")

        for wallet_result in results:
            if "error" in wallet_result:
                continue

            proxy = wallet_result["proxy_wallet"]
            volume = wallet_result["volume"]

            report_lines.append(f"\n{proxy} (Parlay Volume: ${volume:,.2f})")
            report_lines.append("-" * 80)

            for i, protocol_info in enumerate(wallet_result.get("protocols", [])[:10], 1):
                report_lines.append(
                    f"  {i:2}. {protocol_info['protocol']:25} | "
                    f"{protocol_info['category']:15} | "
                    f"Interactions: {protocol_info['interactions']:5,} | "
                    f"USD: ${protocol_info['total_usd']:10,.0f}"
                )

        # Write report
        report_text = "\n".join(report_lines)
        with open(output_file, 'w') as f:
            f.write(report_text)

        print(report_text)
        print(f"\n{'='*80}")
        print(f"✅ Reports saved:")
        print(f"   - Summary: {output_file}")
        print(f"   - Detailed: {json_output}")
        print(f"{'='*80}\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze protocol usage for parlay user wallets")
    parser.add_argument(
        "--wallet",
        type=str,
        help="Analyze a specific wallet address (main wallet, not proxy)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Analyze all wallets"
    )
    parser.add_argument(
        "--missing",
        action="store_true",
        help="Analyze only wallets with data files but no .protocols.md file"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-3-pro-preview",
        choices=["gemini-3-pro-preview", "gemini-2.5-flash", "gemini-2.0-flash-exp", "gemini-2.5-pro"],
        help="Gemini model to use for analysis (default: gemini-3-pro-preview)"
    )
    parser.add_argument(
        "--full-data",
        action="store_true",
        help="Send detailed transaction data to Gemini for richer analysis (uses more tokens/cost)"
    )

    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"
    output_dir = project_root / "processed" / "protocol_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Markdown reports go in data folder
    md_output_dir = data_dir

    analyzer = ProtocolAnalyzer(data_dir, model_name=args.model)

    # Print which model we're using
    print(f"🤖 Using Gemini model: {args.model}")
    if args.full_data:
        print(f"⚠️  Full data mode enabled - will use more tokens/cost")
    print()

    if args.wallet:
        # Analyze single wallet
        wallet = args.wallet

        # Find the proxy wallet for this main wallet
        proxy_wallet = None
        for proxy, info in WALLET_MAPPINGS.items():
            if info.get("main_wallet", "").lower() == wallet.lower():
                proxy_wallet = proxy
                break

        if not proxy_wallet:
            print(f"⚠️  Wallet {wallet} not found in mappings. Using it as-is.")
            proxy_wallet = wallet

        result = analyzer.analyze_wallet(proxy_wallet, wallet if wallet != proxy_wallet else None, full_data=args.full_data)

        # Save JSON result (exclude raw data to avoid serialization issues)
        json_result = {k: v for k, v in result.items() if k not in ["raw_contracts", "protocol_analysis"]}
        json_file = output_dir / f"{wallet}_protocol_analysis.json"
        with open(json_file, 'w') as f:
            json.dump(json_result, f, indent=2)

        # Generate markdown report (save in data folder)
        md_file = md_output_dir / f"{wallet}.protocols.md"
        analyzer.generate_markdown_report(result, md_file)

        # Print summary
        print(f"\n{'='*80}")
        print(f"ANALYSIS COMPLETE: {wallet}")
        print(f"{'='*80}\n")
        print(f"Proxy wallet: {result.get('proxy_wallet', 'N/A')}")
        print(f"Parlay volume: ${result.get('volume', 0):,.2f}")
        print(f"Total transactions: {result.get('total_transactions', 0):,}")
        print(f"Unique contracts: {result.get('total_contracts', 0):,}")
        print(f"\nTop 10 protocols:")
        for i, protocol in enumerate(result.get('protocols', [])[:10], 1):
            print(f"  {i:2}. {protocol['protocol']:30} | {protocol['category']:15} | "
                  f"Interactions: {protocol['interactions']:5,} | USD: ${protocol['total_usd']:10,.0f}")

        print(f"\n✅ Reports saved:")
        print(f"   - JSON: {json_file}")
        print(f"   - Markdown: {md_file}\n")

    elif args.all:
        # Analyze all wallets
        results = analyzer.analyze_all_wallets(full_data=args.full_data)

        # Save individual results with both JSON and markdown
        for result in results:
            if "error" in result:
                continue
            main_wallet = result.get("main_wallet") or result.get("proxy_wallet")

            # Save JSON (exclude raw data)
            json_result = {k: v for k, v in result.items() if k not in ["raw_contracts", "protocol_analysis"]}
            json_file = output_dir / f"{main_wallet}_protocol_analysis.json"
            with open(json_file, 'w') as f:
                json.dump(json_result, f, indent=2)

            # Generate markdown report (save in data folder)
            md_file = md_output_dir / f"{main_wallet}.protocols.md"
            analyzer.generate_markdown_report(result, md_file)

        # Generate comprehensive report
        summary_file = output_dir.parent / "parlay_user_protocol_analysis.txt"
        analyzer.generate_report(results, summary_file)

    elif args.missing:
        # Find all .json files in data directory that don't have .protocols.md files
        print("Scanning for wallets with data but no protocol analysis...\n", flush=True)

        print(f"Looking in directory: {data_dir}", flush=True)
        json_files = list(data_dir.glob("*.json"))
        print(f"Found {len(json_files)} .json files", flush=True)
        wallets_to_process = []

        for json_file in json_files:
            wallet_address = json_file.stem  # filename without extension
            md_file = data_dir / f"{wallet_address}.protocols.md"

            # Check if .protocols.md file exists
            if not md_file.exists():
                wallets_to_process.append(wallet_address)

        if not wallets_to_process:
            print("✅ All wallets with data files have been analyzed!")
            print(f"   Found {len(json_files)} .json files, all have corresponding .protocols.md files\n")
            return

        print(f"📊 Found {len(wallets_to_process)} wallet(s) to analyze (out of {len(json_files)} total)")
        print("-" * 80)
        for i, wallet in enumerate(wallets_to_process, 1):
            print(f"  {i}. {wallet}")
        print("-" * 80 + "\n")

        # Process each wallet
        results = []
        for i, wallet_address in enumerate(wallets_to_process, 1):
            print(f"\n[{i}/{len(wallets_to_process)}] Processing {wallet_address}...")

            # Find proxy wallet for this main wallet
            proxy_wallet = None
            for proxy, info in WALLET_MAPPINGS.items():
                if info.get("main_wallet", "").lower() == wallet_address.lower():
                    proxy_wallet = proxy
                    break

            if not proxy_wallet:
                # Use wallet address as both proxy and main
                proxy_wallet = wallet_address

            result = analyzer.analyze_wallet(
                proxy_wallet,
                wallet_address if wallet_address != proxy_wallet else None,
                full_data=args.full_data
            )

            if "error" not in result:
                # Save JSON result
                json_result = {k: v for k, v in result.items() if k not in ["raw_contracts", "protocol_analysis"]}
                json_file = output_dir / f"{wallet_address}_protocol_analysis.json"
                with open(json_file, 'w') as f:
                    json.dump(json_result, f, indent=2)

                # Generate markdown report
                md_file = data_dir / f"{wallet_address}.protocols.md"
                analyzer.generate_markdown_report(result, md_file)

                results.append(result)

        print(f"\n{'='*80}")
        print(f"✅ Successfully analyzed {len(results)} wallet(s)")
        print(f"{'='*80}\n")

        # Show summary
        for result in results:
            wallet = result.get("main_wallet") or result.get("proxy_wallet")
            num_protocols = len(result.get("protocols", []))
            print(f"  • {wallet}: {num_protocols} protocols identified")

    else:
        # List available wallets
        print("Available wallets to analyze:\n")
        print(f"{'Proxy Wallet':45} | {'Main Wallet':45} | {'Volume':15}")
        print("-" * 110)

        for proxy, info in WALLET_MAPPINGS.items():
            main_wallet = info.get("main_wallet", info.get("source", "N/A"))
            volume = info.get("volume", 0)

            # Check if we have data
            has_data = ""
            if main_wallet not in ["N/A"] and not main_wallet.startswith("CEX"):
                data_file = data_dir / f"{main_wallet}.json"
                has_data = "✓" if data_file.exists() else "✗"

            print(f"{has_data:2} {proxy:43} | {main_wallet:43} | ${volume:12,.2f}")

        print("\n" + "="*110)
        print("Usage:")
        print("  Analyze single wallet:  python analyze_parlay_user_protocols.py --wallet 0xADDRESS")
        print("  Analyze all wallets:    python analyze_parlay_user_protocols.py --all")
        print("  Analyze missing only:   python analyze_parlay_user_protocols.py --missing")
        print("\nModel Selection:")
        print("  --model gemini-3-pro-preview     (default, best quality)")
        print("  --model gemini-2.5-flash         (faster, cheaper)")
        print("  --model gemini-2.0-flash-exp     (experimental)")
        print("  --model gemini-2.5-pro           (balanced)")
        print("\nData Mode:")
        print("  --full-data                      Send detailed transaction data (more tokens/cost)")
        print("="*110 + "\n")


if __name__ == "__main__":
    main()

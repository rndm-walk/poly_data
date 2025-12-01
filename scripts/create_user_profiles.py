#!/usr/bin/env python3
"""
Create comprehensive user profiles combining:
1. Parlay market trading behavior (analyzed by Gemini)
2. Protocol usage across DeFi ecosystem
3. Trading statistics and patterns

Generates detailed markdown reports for each top parlay user.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict
import polars as pl
from dotenv import load_dotenv
import google.generativeai as genai

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Load wallet mappings from single source of truth
from wallet_mappings import WALLET_MAPPINGS

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY not found in .env file")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)


class UserProfiler:
    def __init__(self, project_root: Path, model_name: str = "gemini-3-pro-preview"):
        self.project_root = project_root
        self.model = genai.GenerativeModel(model_name)
        self.data_dir = project_root / "data"
        self.processed_dir = project_root / "processed"

        # Load all necessary data
        self._load_data()

    def _load_data(self):
        """Load all necessary data files."""
        print("Loading data files...")

        # Load parlay trades
        parlay_trades_path = self.processed_dir / "parlay_trades.csv"
        if parlay_trades_path.exists():
            self.parlay_trades = pl.read_csv(parlay_trades_path)
            print(f"  ✓ Loaded {len(self.parlay_trades):,} parlay trades")
        else:
            print(f"  ⚠️  Parlay trades not found at {parlay_trades_path}")
            self.parlay_trades = None

        # Load user market breakdown
        user_market_path = self.processed_dir / "top_20_user_market_breakdown.csv"
        if user_market_path.exists():
            self.user_markets = pl.read_csv(user_market_path)
            print(f"  ✓ Loaded user market breakdown")
        else:
            print(f"  ⚠️  User market breakdown not found")
            self.user_markets = None

        # Load user statistics
        user_stats_path = self.processed_dir / "top_20_user_statistics.csv"
        if user_stats_path.exists():
            self.user_stats = pl.read_csv(user_stats_path)
            print(f"  ✓ Loaded user statistics")
        else:
            print(f"  ⚠️  User statistics not found")
            self.user_stats = None

        # Load parlay markets metadata
        parlay_markets_path = self.processed_dir / "parlay_markets_manual.csv"
        if parlay_markets_path.exists():
            self.parlay_markets = pl.read_csv(parlay_markets_path, schema_overrides={'token1': pl.Utf8, 'token2': pl.Utf8})
            print(f"  ✓ Loaded {len(self.parlay_markets):,} parlay markets")
        else:
            print(f"  ⚠️  Parlay markets not found")
            self.parlay_markets = None

    def _load_protocol_analysis(self, proxy_wallet: str) -> Optional[Dict[str, Any]]:
        """Load protocol analysis for a wallet (maps proxy to main wallet)."""
        # Check if this is a proxy wallet and map to main wallet
        wallet_info = WALLET_MAPPINGS.get(proxy_wallet.lower())

        if wallet_info and "main_wallet" in wallet_info:
            main_wallet = wallet_info["main_wallet"]
            json_path = self.processed_dir / "protocol_analysis" / f"{main_wallet}_protocol_analysis.json"

            # Case-insensitive file lookup if exact match doesn't exist
            if not json_path.exists():
                import glob
                pattern = str(json_path).lower()
                for file in glob.glob(str(self.processed_dir / "protocol_analysis" / "*_protocol_analysis.json")):
                    if file.lower() == pattern:
                        json_path = Path(file)
                        break
        else:
            # Try as-is (might be a main wallet directly or CEX user)
            json_path = self.processed_dir / "protocol_analysis" / f"{proxy_wallet}_protocol_analysis.json"

        if json_path.exists():
            with open(json_path, 'r') as f:
                return json.load(f)
        return None

    def _get_user_trades(self, user_address: str) -> pl.DataFrame:
        """Get all parlay trades for a specific user."""
        if self.parlay_trades is None:
            return pl.DataFrame()

        user_trades = self.parlay_trades.filter(
            (pl.col("maker") == user_address) | (pl.col("taker") == user_address)
        )
        return user_trades

    def _analyze_trading_with_gemini(self, user_address: str, trades_data: Dict[str, Any]) -> str:
        """Use Gemini to analyze trading patterns and provide insights."""

        prompt = f"""Analyze this Polymarket parlay trader's behavior and provide insights.

USER DATA:
- Total Parlay Volume: ${trades_data['total_volume']:,.2f}
- Number of Trades: {trades_data['num_trades']:,}
- Unique Markets: {trades_data['unique_markets']}
- Average Trade Size: ${trades_data['avg_trade_size']:,.2f}
- Max Trade Size: ${trades_data['max_trade_size']:,.2f}

TOP MARKETS BY VOLUME:
{self._format_markets_for_gemini(trades_data['top_markets'])}

TRADING PATTERNS:
- Total days active: {trades_data.get('days_active', 'N/A')}
- Maker trades: {trades_data.get('maker_trades', 0):,} ({trades_data.get('maker_pct', 0):.1f}%)
- Taker trades: {trades_data.get('taker_trades', 0):,} ({trades_data.get('taker_pct', 0):.1f}%)

Please provide:
1. **Trading Profile** (2-3 sentences): Describe this trader's overall strategy and behavior
2. **Market Preferences** (2-3 sentences): What types of markets do they prefer and why?
3. **Risk Assessment** (2-3 sentences): Based on trade sizes and diversification, assess their risk profile
4. **Key Insights** (3-4 bullet points): Notable patterns or behaviors

Keep it concise and insightful. Focus on actionable observations.
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=1000,
                )
            )
            return response.text.strip()
        except Exception as e:
            print(f"  ⚠️  Gemini analysis failed: {e}")
            return "Analysis unavailable due to API error."

    def _format_markets_for_gemini(self, markets: List[Dict]) -> str:
        """Format market data for Gemini prompt."""
        lines = []
        for i, market in enumerate(markets[:10], 1):
            lines.append(
                f"{i}. {market['question'][:80]} - "
                f"{market['num_trades']} trades, ${market['volume']:,.0f}"
            )
        return "\n".join(lines)

    def _prepare_trading_data(self, user_address: str) -> Dict[str, Any]:
        """Prepare comprehensive trading data for a user."""
        # Get user stats
        if self.user_stats is not None:
            user_stat = self.user_stats.filter(pl.col("user") == user_address)
            if len(user_stat) == 0:
                return None

            stats = user_stat.row(0, named=True)
        else:
            return None

        # Get user markets
        if self.user_markets is not None:
            user_mkts = (
                self.user_markets
                .filter(pl.col("user") == user_address)
                .sort("market_volume", descending=True)
            )

            top_markets = []
            for row in user_mkts.iter_rows(named=True):
                top_markets.append({
                    'market_id': row['market_id'],
                    'question': row['question'],
                    'num_trades': row['num_trades'],
                    'volume': row['market_volume']
                })
        else:
            top_markets = []

        # Get detailed trades
        trades = self._get_user_trades(user_address)

        # Calculate additional metrics
        maker_trades = len(trades.filter(pl.col("maker") == user_address)) if len(trades) > 0 else 0
        taker_trades = len(trades.filter(pl.col("taker") == user_address)) if len(trades) > 0 else 0
        total_trades = maker_trades + taker_trades

        # Parse timestamps to get days active
        days_active = "N/A"
        if len(trades) > 0:
            try:
                timestamps = trades.select(pl.col("timestamp")).to_series()
                # Convert to datetime and count unique dates
                dates = pl.Series([str(ts)[:10] for ts in timestamps])
                days_active = dates.n_unique()
            except:
                days_active = "N/A"

        return {
            'total_volume': stats['total_volume'],
            'num_trades': stats['num_trades'],
            'unique_markets': stats['unique_markets'],
            'avg_trade_size': stats['avg_trade_size'],
            'max_trade_size': stats['max_trade_size'],
            'top_markets': top_markets,
            'maker_trades': maker_trades,
            'taker_trades': taker_trades,
            'maker_pct': (maker_trades / total_trades * 100) if total_trades > 0 else 0,
            'taker_pct': (taker_trades / total_trades * 100) if total_trades > 0 else 0,
            'days_active': days_active,
        }

    def generate_user_profile(self, user_address: str, output_path: Path):
        """Generate comprehensive user profile report."""
        print(f"\n{'='*80}")
        print(f"Generating profile for: {user_address}")
        print(f"{'='*80}")

        # Prepare trading data
        print("  📊 Preparing trading data...")
        trading_data = self._prepare_trading_data(user_address)

        if trading_data is None:
            print(f"  ❌ No trading data found for {user_address}")
            return False

        # Get Gemini analysis of trading behavior
        print("  🤖 Analyzing trading patterns with Gemini...")
        trading_analysis = self._analyze_trading_with_gemini(user_address, trading_data)

        # Load protocol analysis
        print("  📦 Loading protocol analysis...")
        protocol_data = self._load_protocol_analysis(user_address)

        # Generate markdown report
        print("  📝 Generating markdown report...")
        self._write_profile_markdown(
            user_address,
            trading_data,
            trading_analysis,
            protocol_data,
            output_path
        )

        print(f"  ✅ Profile saved to: {output_path}")
        return True

    def _load_protocol_markdown(self, proxy_wallet: str) -> Optional[str]:
        """Load the full .protocols.md file content if it exists."""
        # Check if this is a proxy wallet and map to main wallet
        wallet_info = WALLET_MAPPINGS.get(proxy_wallet.lower())

        if wallet_info and "main_wallet" in wallet_info:
            main_wallet = wallet_info["main_wallet"]
            # Case-insensitive file lookup
            # Try exact match first
            md_path = self.data_dir / f"{main_wallet}.protocols.md"
            if not md_path.exists():
                # Try finding file with case-insensitive match
                import glob
                pattern = str(self.data_dir / f"{main_wallet}.protocols.md").lower()
                for file in glob.glob(str(self.data_dir / "*.protocols.md")):
                    if file.lower() == pattern:
                        md_path = Path(file)
                        break
        else:
            # Try as-is
            md_path = self.data_dir / f"{proxy_wallet}.protocols.md"

        if md_path.exists():
            with open(md_path, 'r') as f:
                return f.read()
        return None

    def _write_profile_markdown(
        self,
        user_address: str,
        trading_data: Dict[str, Any],
        trading_analysis: str,
        protocol_data: Optional[Dict[str, Any]],
        output_path: Path
    ):
        """Write comprehensive markdown profile."""
        md = []

        # Header
        md.append(f"# Parlay User Profile: {user_address}")
        md.append("")
        md.append("**Comprehensive Analysis of Trading Behavior & DeFi Activity**")
        md.append("")
        md.append("---")
        md.append("")

        # Executive Summary
        md.append("## 📊 Executive Summary")
        md.append("")
        md.append(f"- **Wallet Address:** `{user_address}`")
        md.append(f"- **Total Parlay Volume:** ${trading_data['total_volume']:,.2f}")
        md.append(f"- **Parlay Trades:** {trading_data['num_trades']:,} trades across {trading_data['unique_markets']} markets")
        md.append(f"- **Average Trade Size:** ${trading_data['avg_trade_size']:,.2f}")

        if protocol_data:
            md.append(f"- **DeFi Protocols Used:** {len(protocol_data.get('protocols', []))} protocols")
            md.append(f"- **Blockchain Transactions:** {protocol_data.get('total_transactions', 0):,} total transactions")

        md.append("")
        md.append("---")
        md.append("")

        # Links Section
        md.append("## 🔗 Quick Links")
        md.append("")
        md.append(f"- **Polymarket Analytics:** [View Trader Profile](https://polymarketanalytics.com/traders/{user_address})")
        md.append(f"- **Arkham Intelligence (Polymarket Wallet):** [View on Arkham](https://intel.arkm.com/explorer/address/{user_address})")

        # Add main wallet link if this is a proxy wallet
        wallet_info = WALLET_MAPPINGS.get(user_address.lower())
        if wallet_info and "main_wallet" in wallet_info:
            main_wallet = wallet_info["main_wallet"]
            md.append(f"- **Arkham Intelligence (Main Wallet):** [View on Arkham](https://intel.arkm.com/explorer/address/{main_wallet})")

        md.append("")
        md.append("---")
        md.append("")

        # Polymarket Trading Analysis (Gemini-powered)
        md.append("## 🎯 Polymarket Trading Analysis")
        md.append("")
        md.append("*AI-powered analysis of trading patterns and behavior*")
        md.append("")
        md.append(trading_analysis)
        md.append("")
        md.append("---")
        md.append("")

        # Trading Statistics
        md.append("## 📈 Trading Statistics")
        md.append("")
        md.append("### Overview")
        md.append("")
        md.append(f"- **Total Volume:** ${trading_data['total_volume']:,.2f}")
        md.append(f"- **Total Trades:** {trading_data['num_trades']:,}")
        md.append(f"- **Unique Markets:** {trading_data['unique_markets']}")
        md.append(f"- **Average Trade Size:** ${trading_data['avg_trade_size']:,.2f}")
        md.append(f"- **Maximum Trade Size:** ${trading_data['max_trade_size']:,.2f}")
        md.append(f"- **Days Active:** {trading_data.get('days_active', 'N/A')}")
        md.append("")

        md.append("### Trading Role Distribution")
        md.append("")
        md.append(f"- **Maker (Limit Orders):** {trading_data['maker_trades']:,} trades ({trading_data['maker_pct']:.1f}%)")
        md.append(f"- **Taker (Market Orders):** {trading_data['taker_trades']:,} trades ({trading_data['taker_pct']:.1f}%)")
        md.append("")

        # Top Markets
        md.append("### Top Markets by Volume")
        md.append("")
        md.append("| Rank | Market | Trades | Volume |")
        md.append("|------|--------|--------|--------|")

        for i, market in enumerate(trading_data['top_markets'][:15], 1):
            question = market['question'][:60] + "..." if len(market['question']) > 60 else market['question']
            md.append(
                f"| {i} | {question} | {market['num_trades']:,} | ${market['volume']:,.2f} |"
            )

        md.append("")
        md.append("---")
        md.append("")

        # Load and include full .protocols.md content if available
        protocol_md_content = self._load_protocol_markdown(user_address)

        if protocol_md_content:
            # Add a separator and then include the full protocol analysis
            md.append("---")
            md.append("")
            md.append("# DeFi Protocol Analysis")
            md.append("")
            md.append("*The following section contains detailed analysis of non-Polymarket blockchain activity*")
            md.append("")
            md.append("---")
            md.append("")

            # Skip the first few lines of the protocol markdown (header and title)
            # to avoid duplication since we already have our own header
            lines = protocol_md_content.split('\n')

            # Find where the actual content starts (after the initial header)
            start_index = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('##') and 'Overview' in line:
                    start_index = i
                    break

            # Include everything from the Overview section onwards
            md.append('\n'.join(lines[start_index:]))
            md.append("")
        else:
            md.append("## 🌐 DeFi Protocol Usage")
            md.append("")
            md.append("*No non-Polymarket protocol activity found or user is a pure Polymarket trader.*")
            md.append("")
            md.append("---")
            md.append("")

        # User Segmentation
        md.append("## 🏷️ User Segmentation")
        md.append("")

        # Determine user segments
        segments = []

        # Volume-based
        if trading_data['total_volume'] > 200000:
            segments.append("🐋 **Whale Trader** - High volume participant")
        elif trading_data['total_volume'] > 100000:
            segments.append("🦈 **Power Trader** - Significant volume")
        elif trading_data['total_volume'] > 50000:
            segments.append("🐬 **Active Trader** - Regular participant")

        # Strategy-based
        if trading_data['maker_pct'] > 70:
            segments.append("📊 **Liquidity Provider** - Primarily uses limit orders")
        elif trading_data['taker_pct'] > 70:
            segments.append("⚡ **Market Taker** - Primarily uses market orders")
        else:
            segments.append("⚖️ **Balanced Trader** - Mix of limit and market orders")

        # Diversification-based
        if trading_data['unique_markets'] > 20:
            segments.append("🎲 **Diversified** - Trades across many markets")
        elif trading_data['unique_markets'] == 1:
            segments.append("🎯 **Specialist** - Focused on single market")
        else:
            segments.append("🎪 **Focused** - Concentrated on few markets")

        # DeFi activity
        if protocol_data and len(protocol_data.get('protocols', [])) > 50:
            segments.append("🌐 **DeFi Power User** - Extensive protocol usage")
        elif protocol_data and len(protocol_data.get('protocols', [])) > 10:
            segments.append("🔗 **DeFi Active** - Regular DeFi participant")
        elif protocol_data and len(protocol_data.get('protocols', [])) > 0:
            segments.append("🔗 **DeFi Casual** - Some DeFi activity")
        else:
            segments.append("🎲 **Polymarket Native** - Exclusively Polymarket")

        for segment in segments:
            md.append(f"- {segment}")

        md.append("")
        md.append("---")
        md.append("")

        # Footer
        md.append("---")
        md.append("")
        md.append("## 📝 Report Metadata")
        md.append("")
        md.append(f"- **Report Generated:** {Path.cwd()}")
        md.append(f"- **Parlay Trading Analysis:** AI-powered by Gemini")
        md.append(f"- **Protocol Analysis:** Blockchain transaction history via Arkham")
        md.append("")

        # Write to file
        with open(output_path, 'w') as f:
            f.write("\n".join(md))


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate comprehensive user profiles for parlay traders"
    )
    parser.add_argument(
        "--wallet",
        type=str,
        help="Generate profile for specific wallet address"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate profiles for all top 20 users"
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of top users to process (default: 20)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-3-pro-preview",
        choices=["gemini-3-pro-preview", "gemini-2.5-flash", "gemini-2.0-flash-exp", "gemini-2.5-pro"],
        help="Gemini model to use for analysis (default: gemini-3-pro-preview)"
    )

    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    output_dir = project_root / "data" / "user_profiles"
    output_dir.mkdir(exist_ok=True)

    profiler = UserProfiler(project_root, model_name=args.model)

    if args.wallet:
        # Single wallet
        output_file = output_dir / f"{args.wallet}.profile.md"
        profiler.generate_user_profile(args.wallet, output_file)

    elif args.all:
        # Process top N users
        if profiler.user_stats is None:
            print("❌ User statistics not available. Run find_parlay_users.ipynb first.")
            return

        top_users = (
            profiler.user_stats
            .sort("total_volume", descending=True)
            .head(args.top_n)
        )

        # Filter to only include users in wallet mappings with main wallets
        users_to_process = []
        skipped_not_mapped = []
        skipped_no_main_wallet = []

        for row in top_users.iter_rows(named=True):
            user_address = row['user']
            if user_address.lower() not in WALLET_MAPPINGS:
                skipped_not_mapped.append(user_address)
            elif 'main_wallet' not in WALLET_MAPPINGS[user_address.lower()]:
                # Skip CEX/Bridge sources - they don't have main wallets
                skipped_no_main_wallet.append(user_address)
            else:
                users_to_process.append(row)

        print(f"\n{'='*80}")
        print(f"Generating profiles for top {args.top_n} parlay users")
        print(f"{'='*80}\n")

        if skipped_not_mapped:
            print(f"⚠️  Skipping {len(skipped_not_mapped)} wallets not in mappings (Polymarket contracts):")
            for addr in skipped_not_mapped:
                print(f"   - {addr}")
            print()

        if skipped_no_main_wallet:
            print(f"⚠️  Skipping {len(skipped_no_main_wallet)} CEX/Bridge wallets (no main wallet):")
            for addr in skipped_no_main_wallet:
                info = WALLET_MAPPINGS.get(addr.lower(), {})
                source = info.get('source', 'Unknown')
                print(f"   - {addr} ({source})")
            print()

        print(f"Processing {len(users_to_process)} wallets with main wallet mappings...\n")

        success_count = 0
        for i, row in enumerate(users_to_process, 1):
            user_address = row['user']

            # Check if already exists
            output_file = output_dir / f"{user_address}.profile.md"
            if output_file.exists():
                print(f"\n[{i}/{len(users_to_process)}] ✓ Skipping {user_address} (already exists)")
                success_count += 1
                continue

            print(f"\n[{i}/{len(users_to_process)}] Processing {user_address}")

            if profiler.generate_user_profile(user_address, output_file):
                success_count += 1

            # Small delay to avoid rate limiting
            if i < len(users_to_process):
                import time
                time.sleep(1)

        print(f"\n{'='*80}")
        print(f"✅ Generated {success_count}/{len(users_to_process)} user profiles (from wallets in mappings)")
        print(f"{'='*80}")
        print(f"\nProfiles saved to: {output_dir}/")
        print(f"\nTo view a profile:")
        print(f"  cat {output_dir}/<WALLET_ADDRESS>.profile.md")
        print(f"\n{'='*80}\n")

    else:
        # Show available users
        if profiler.user_stats is None:
            print("❌ User statistics not available. Run find_parlay_users.ipynb first.")
            return

        print("\n" + "="*80)
        print("Top Parlay Users")
        print("="*80 + "\n")

        top_users = profiler.user_stats.sort("total_volume", descending=True).head(20)

        print(f"{'Rank':<6} {'Address':<44} {'Volume':<20} {'Trades':<10}")
        print("-" * 80)

        for i, row in enumerate(top_users.iter_rows(named=True), 1):
            profile_exists = (output_dir / f"{row['user']}.profile.md").exists()
            status = "✓" if profile_exists else " "
            print(
                f"{status} {i:<4} {row['user']:<44} "
                f"${row['total_volume']:>18,.2f} {row['num_trades']:>9,}"
            )

        print("\n" + "="*80)
        print("Usage:")
        print("  Single user:  python create_user_profiles.py --wallet 0xADDRESS")
        print("  All top 20:   python create_user_profiles.py --all")
        print("  Top N users:  python create_user_profiles.py --all --top-n 10")
        print("="*80 + "\n")


if __name__ == "__main__":
    main()

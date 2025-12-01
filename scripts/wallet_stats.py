#!/usr/bin/env python3
"""
Display statistics and insights about wallet mappings.

Shows:
- Total wallets
- Wallets with main wallet addresses
- Wallets from CEX/bridges
- Wallets needing transaction fetch
- Uncertain mappings
"""

from wallet_mappings import WALLET_MAPPINGS

def analyze_mappings():
    """Analyze and display wallet mapping statistics."""

    total = len(WALLET_MAPPINGS)
    with_main_wallet = sum(1 for info in WALLET_MAPPINGS.values() if "main_wallet" in info)
    with_source = sum(1 for info in WALLET_MAPPINGS.values() if "source" in info)
    uncertain = sum(1 for info in WALLET_MAPPINGS.values() if info.get("uncertain"))
    needs_fetch = sum(1 for info in WALLET_MAPPINGS.values() if info.get("needs_fetch"))

    # Calculate volume stats
    total_volume = sum(info["volume"] for info in WALLET_MAPPINGS.values())
    avg_volume = total_volume / total if total > 0 else 0

    print("="*80)
    print("WALLET MAPPING STATISTICS")
    print("="*80)
    print(f"\n📊 Overview:")
    print(f"  • Total wallets: {total:,}")
    print(f"  • Total volume: ${total_volume:,.2f}")
    print(f"  • Average volume per wallet: ${avg_volume:,.2f}")

    print(f"\n🔗 Wallet Relationships:")
    print(f"  • With main wallet: {with_main_wallet:,} ({with_main_wallet/total*100:.1f}%)")
    print(f"  • From CEX/Bridge: {with_source:,} ({with_source/total*100:.1f}%)")
    print(f"  • No mapping yet: {total - with_main_wallet - with_source:,}")

    print(f"\n⚠️  Data Quality:")
    print(f"  • Uncertain mappings: {uncertain:,} ({uncertain/total*100:.1f}%)")
    print(f"  • Needs transaction fetch: {needs_fetch:,} ({needs_fetch/total*100:.1f}%)")

    # Show top wallets needing fetch
    print(f"\n📋 Top 10 High-Volume Wallets Needing Transaction Fetch:")
    print("-"*80)

    need_fetch_wallets = [
        (addr, info) for addr, info in WALLET_MAPPINGS.items()
        if info.get("needs_fetch")
    ]
    need_fetch_wallets.sort(key=lambda x: x[1]["volume"], reverse=True)

    for i, (addr, info) in enumerate(need_fetch_wallets[:10], 1):
        volume = info["volume"]
        main = info.get("main_wallet", "N/A")
        unc = " ⚠️ uncertain" if info.get("uncertain") else ""
        print(f"{i:2}. {addr}")
        print(f"    Volume: ${volume:>15,.2f} | Main: {main}{unc}")

    # Show CEX/Bridge sources
    print(f"\n🏦 Funding Sources (CEX/Bridge):")
    print("-"*80)

    sources = {}
    for info in WALLET_MAPPINGS.values():
        if "source" in info:
            source = info["source"]
            if source not in sources:
                sources[source] = {"count": 0, "volume": 0}
            sources[source]["count"] += 1
            sources[source]["volume"] += info["volume"]

    sources_sorted = sorted(sources.items(), key=lambda x: x[1]["volume"], reverse=True)

    for source, stats in sources_sorted[:10]:
        print(f"  • {source:30s} - {stats['count']:4,} wallets (${stats['volume']:>15,.2f})")

    print("="*80 + "\n")


if __name__ == "__main__":
    analyze_mappings()

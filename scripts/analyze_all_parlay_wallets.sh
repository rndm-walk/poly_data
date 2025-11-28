#!/bin/bash

# Analyze all parlay user wallets one by one
# This script processes each wallet individually with Gemini API

WALLETS=(
    "0xc3060219B14df14dc7f139066adF64638057B51f"
    "0x1881ad6e231a14a8be0f9ae6f9efd8f3cfb09919"
    "0x9483Ca5C6A3BaD47D0AB9bC64bd379dEbD76B0Af"
    "0x0C369571604d68B45d78943f51811938dd4EDD2E"
    "0x710BE84efbd0dfD4B1a67B9525A778ae5C420ff8"
    "0xE4e26c843F5bC1C5FC610F8BD4830C677298b1f4"
    "0xF6aE6dF55d8108B2f22A13e14CFbdCdf62630439"
)

echo "========================================"
echo "Analyzing ${#WALLETS[@]} parlay user wallets"
echo "========================================"

for wallet in "${WALLETS[@]}"; do
    echo ""
    echo "Processing: $wallet"
    echo "----------------------------------------"

    # Check if already analyzed (check markdown file in data folder)
    md_file="data/${wallet}.protocols.md"
    if [ -f "$md_file" ]; then
        echo "✓ Already analyzed. Skipping..."
        continue
    fi

    # Analyze wallet
    python scripts/analyze_parlay_user_protocols.py --wallet "$wallet"

    # Check if successful
    if [ $? -eq 0 ]; then
        echo "✓ Success"
    else
        echo "✗ Failed"
    fi

    # Add a small delay to avoid rate limiting
    echo "Waiting 2 seconds..."
    sleep 2
done

echo ""
echo "========================================"
echo "Analysis complete!"
echo "========================================"
echo ""
echo "Markdown reports saved in: data/"
echo "JSON reports saved in: processed/protocol_analysis/"
echo ""
ls -lh data/*.protocols.md 2>/dev/null

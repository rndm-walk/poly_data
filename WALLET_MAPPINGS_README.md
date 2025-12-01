# Wallet Mappings - Single Source of Truth

## Overview

The [parlay_user_volume_notes.csv](processed/parlay_user_volume_notes.csv) file serves as the single source of truth for all proxy-to-main wallet mappings in this project.

All scripts now use the centralized [wallet_mappings.py](scripts/wallet_mappings.py) module to load and access this data, ensuring consistency across the codebase.

## CSV Format

The CSV uses the following notation in the `total_usd` column:

| Notation | Meaning | Example |
|----------|---------|---------|
| `(0xADDRESS)` | Confirmed main wallet | `173704.76752(0x9483Ca5C6A3BaD47D0AB9bC64bd379dEbD76B0Af)` |
| `(0xADDRESS?)` | Uncertain main wallet | `(0x3f77a673a29e8cea345f0ed1f4f40a914156fc32?)` |
| `(0xADDRESS)(need)` | Needs transaction fetch | `(0xc3060219B14df14dc7f139066adF64638057B51f)(need)` |
| `(0xADDRESS?)(need)` | Uncertain + needs fetch | `(0x3f77...fc32?)(need)` |
| `(CEX, ...)` | Funded from CEX | `(CEX, Binance)` |
| `(Bridge, ...)` | Funded from bridge | `(Bridge, Relay)` |

## Usage

### Loading All Mappings

```python
from wallet_mappings import WALLET_MAPPINGS

# Access mapping
proxy_address = "0xf419573877439e31131f83aba0be82e697179728"
mapping = WALLET_MAPPINGS.get(proxy_address)

# Example output:
# {
#   "volume": 246703.58982,
#   "source": "Bridge, Relay",
#   "needs_fetch": False
# }
```

### Helper Functions

```python
from wallet_mappings import (
    get_main_wallet,
    get_funding_source,
    needs_transaction_fetch,
    is_uncertain
)

# Get main wallet address
main_wallet = get_main_wallet("0x662ce90c51d613a2975a536272e477ab7c38bfe7")
# Returns: "0xc3060219b14df14dc7f139066adf64638057b51f"

# Get funding source
source = get_funding_source("0xf419573877439e31131f83aba0be82e697179728")
# Returns: "Bridge, Relay"

# Check if needs transaction fetch
needs_fetch = needs_transaction_fetch("0x662ce90c51d613a2975a536272e477ab7c38bfe7")
# Returns: True

# Check if uncertain
uncertain = is_uncertain("0xfcf2378f20cf408d077c21e731272f21cccea469")
# Returns: True
```

## Statistics

Run the stats script to see current mapping coverage:

```bash
python scripts/wallet_stats.py
```

Example output:
```
📊 Overview:
  • Total wallets: 11,016
  • Total volume: $8,684,252.09

🔗 Wallet Relationships:
  • With main wallet: 11 (0.1%)
  • From CEX/Bridge: 5 (0.0%)
  • Needs transaction fetch: 6 (0.1%)
```

## Scripts Using This Module

1. **[create_user_profiles.py](scripts/create_user_profiles.py)** - Generates comprehensive user profiles
2. **[analyze_parlay_user_protocols.py](scripts/analyze_parlay_user_protocols.py)** - Analyzes protocol usage

## Metadata Fields

Each wallet entry can contain:

| Field | Type | Description |
|-------|------|-------------|
| `volume` | float | Total USD trading volume |
| `main_wallet` | str | Main wallet address (if known) |
| `source` | str | Funding source (CEX/Bridge name) |
| `uncertain` | bool | Whether main wallet is uncertain (marked with `?`) |
| `needs_fetch` | bool | Whether transactions need to be fetched |

## Benefits

✅ **Single Source of Truth** - No duplicate hardcoded mappings
✅ **Easy Updates** - Edit CSV file, all scripts automatically use new data
✅ **11,016 Wallets** - Comprehensive coverage
✅ **Rich Metadata** - Uncertainty flags, fetch requirements, sources
✅ **Type Safety** - Helper functions for common queries

## Adding New Mappings

Edit [parlay_user_volume_notes.csv](processed/parlay_user_volume_notes.csv):

```csv
address,total_usd
0xNEWADDRESS,12345.67(0xMAINWALLET)
0xANOTHER,54321.00(CEX, Coinbase)
0xUNCERTAIN,9999.99(0xMAYBE?)(need)
```

The module will automatically reload on next import.

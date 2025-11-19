# Polymarket Data (Cloud-Optimized Fork)

> **⚡ Modified Version**: This is a forked and modified version of the original Polymarket data pipeline, optimized for **RAM-deficient devices** using **Supabase Storage** for cloud-hosted data. You can now analyze 10M+ trades on a lightweight laptop without running the full data pipeline locally!

## 🆕 What's Different in This Fork?

### **Original Version** (Resource-Intensive)
- ❌ Requires running `update_all.py` to download 50+ GB of data
- ❌ Full Goldsky/processing pipeline on every device

### **This Version** (Cloud-Optimized)
- ✅ **Download pre-processed data from Supabase** (~380 MB)
- ✅ **Works on 4GB RAM laptops** - perfect for Jupyter notebooks
- ✅ **Instant setup** - no data pipeline required on client
- ✅ **Daily updates** - server uploads fresh data to Supabase automatically
- ✅ **Public access** - anyone can download the latest data

---

## 🚀 Quick Start (New Users)

### **Option 1: Download from Supabase (Recommended - 5 minutes)**

Perfect for data analysis on lightweight devices:

```bash
# 1. Clone the repo
git clone <this-repo>
cd polymarket

# 2. Install minimal dependencies (no Supabase SDK needed!)
pip install -r requirements.txt

# 3. Download latest data from public storage (379 MB, no auth required)
python scripts/download_data.py

# 4. Start analyzing!
jupyter notebook notebooks/
```

**Dependencies**: Only `polars`, `pandas`, `matplotlib`, `jupyter`, `requests`, and `tqdm` - no Supabase SDK or credentials needed!

**That's it!** You now have the latest 10M trades ready for analysis.

### **Option 2: Run Full Pipeline (Advanced - For Server)**

Only needed if you want to run the data collection server:

**First-time users**: Download the [latest data snapshot](https://polydata-archive.s3.us-east-1.amazonaws.com/archive.tar.xz) and extract it in the main repository directory before your first run. This will save you over 2 days of initial data collection time.

## 📊 Data Architecture

### **Cloud-First Approach**

```
┌─────────────────────────────────────┐
│   DATA SERVER (Runs Daily)          │
│  • Fetches markets from Polymarket  │
│  • Scrapes Goldsky for trades       │
│  • Processes 194M+ trades           │
│  • Uploads to Supabase Storage      │
└─────────────────────────────────────┘
              ↓ Upload (379 MB)
┌─────────────────────────────────────┐
│       SUPABASE STORAGE              │
│  • markets.csv (70 MB)              │
│  • latest_10M_trades.parquet (309M) │
│  • metadata.json (timestamps)       │
│  📍 PUBLIC ACCESS - No auth needed  │
└─────────────────────────────────────┘
              ↓ Download
┌─────────────────────────────────────┐
│   YOUR LAPTOP (Analysis)            │
│  • Download latest data (5 min)     │
│  • Run Jupyter notebooks            │
│  • Analyze 10M trades               │
│  • 4GB RAM sufficient!              │
└─────────────────────────────────────┘
```

### **What You Get**

When you run `download_data.py`, you download:

- **markets.csv** (70 MB) - 170K+ market metadata
- **latest_10000000_trades.parquet** (309 MB) - Latest 10M trades (~7 days)
- **metadata.json** - Update timestamps and data ranges

**No need to**:
- ❌ Download 50 GB of raw data
- ❌ Run `update_all.py` locally
- ❌ Process millions of trades
- ❌ Wait hours for data pipeline

## Overview (Original Pipeline)

This pipeline performs three main operations (runs on server only):

1. **Market Data Collection** - Fetches all Polymarket markets with metadata
2. **Order Event Scraping** - Collects order-filled events from Goldsky subgraph
3. **Trade Processing** - Transforms raw order events into structured trade data

## Installation

This project uses [UV](https://docs.astral.sh/uv/) for fast, reliable package management.

### Install UV

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

### Install Dependencies

```bash
# Install all dependencies
uv sync

# Install with development dependencies (Jupyter, etc.)
uv sync --extra dev
```

## Quick Start

```bash
# Run with UV (recommended)
uv run python update_all.py

# Or activate the virtual environment first
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
python update_all.py
```

This will sequentially run all three pipeline stages:
- Update markets from Polymarket API
- Update order-filled events from Goldsky
- Process new orders into trades

## Project Structure

```
poly_data/
├── update_all.py              # Main orchestrator script
├── update_utils/              # Data collection modules
│   ├── update_markets.py      # Fetch markets from Polymarket API
│   ├── update_goldsky.py      # Scrape order events from Goldsky
│   └── process_live.py        # Process orders into trades
├── poly_utils/                # Utility functions
│   └── utils.py               # Market loading and missing token handling
├── markets.csv                # Main markets dataset
├── missing_markets.csv        # Markets discovered from trades (auto-generated)
├── goldsky/                   # Order-filled events (auto-generated)
│   └── orderFilled.csv
└── processed/                 # Processed trade data (auto-generated)
    └── trades.csv
```

## Data Files

### markets.csv
Market metadata including:
- Market question, outcomes, and tokens
- Creation/close times and slugs
- Trading volume and condition IDs
- Negative risk indicators

**Fields**: `createdAt`, `id`, `question`, `answer1`, `answer2`, `neg_risk`, `market_slug`, `token1`, `token2`, `condition_id`, `volume`, `ticker`, `closedTime`

### goldsky/orderFilled.csv
Raw order-filled events with:
- Maker/taker addresses and asset IDs
- Fill amounts and transaction hashes
- Unix timestamps

**Fields**: `timestamp`, `maker`, `makerAssetId`, `makerAmountFilled`, `taker`, `takerAssetId`, `takerAmountFilled`, `transactionHash`

### processed/trades.csv
Structured trade data including:
- Market ID mapping and trade direction
- Price, USD amount, and token amount
- Maker/taker roles and transaction details

**Fields**: `timestamp`, `market_id`, `maker`, `taker`, `nonusdc_side`, `maker_direction`, `taker_direction`, `price`, `usd_amount`, `token_amount`, `transactionHash`

## Pipeline Stages

### 1. Update Markets (`update_markets.py`)

Fetches all markets from Polymarket API in chronological order.

**Features**:
- Automatic resume from last offset (idempotent)
- Rate limiting and error handling
- Batch fetching (500 markets per request)

**Usage**:
```bash
uv run python -c "from update_utils.update_markets import update_markets; update_markets()"
```

### 2. Update Goldsky (`update_goldsky.py`)

Scrapes order-filled events from Goldsky subgraph API.

**Features**:
- Resumes from last timestamp automatically
- Handles GraphQL queries with pagination
- Deduplicates events

**Usage**:
```bash
uv run python -c "from update_utils.update_goldsky import update_goldsky; update_goldsky()"
```

### 3. Process Live Trades (`process_live.py`)

Processes raw order events into structured trades.

**Features**:
- Maps asset IDs to markets using token lookup
- Calculates prices and trade directions
- Identifies BUY/SELL sides
- Handles missing markets by discovering them from trades
- Incremental processing from last checkpoint

**Usage**:
```bash
uv run python -c "from update_utils.process_live import process_live; process_live()"
```

**Processing Logic**:
- Identifies non-USDC asset in each trade
- Maps to market and outcome token (token1/token2)
- Determines maker/taker directions (BUY/SELL)
- Calculates price as USDC amount per outcome token
- Converts amounts from raw units (divides by 10^6)

---

## ☁️ Supabase Storage (Server Setup)

### **For Server Administrators**

If you're running the data collection server and want to upload to Supabase:

1. **Install Server Dependencies**
   ```bash
   # Install server-side dependencies (includes Supabase SDK)
   pip install -r requirements-server.txt
   ```

2. **Create Supabase Account** (Free tier works!)
   - Go to [supabase.com](https://supabase.com)
   - Create a new project
   - Create a public storage bucket named `polymarket-data`

3. **Set Up Credentials**
   ```bash
   # Copy example env file
   cp .env.example .env

   # Edit with your Supabase credentials
   nano .env
   ```

   Add your credentials:
   ```
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_KEY=your-service-role-key
   ```

4. **Upload Data Daily**
   ```bash
   # Run full pipeline
   python update_all.py

   # Upload to Supabase
   python scripts/upload_to_supabase.py
   ```

5. **Automate with Cron** (Optional)
   ```bash
   # Add to crontab (runs daily at 2 AM)
   0 2 * * * cd /path/to/polymarket && python update_all.py && python scripts/upload_to_supabase.py
   ```

📖 **Full documentation**: See [SUPABASE_SETUP.md](SUPABASE_SETUP.md) for detailed setup instructions.

### **Public Access URLs**

Data is publicly accessible (no authentication required):

```
https://hgzttvjqhfepdnngsrhs.supabase.co/storage/v1/object/public/polymarket-data/markets.csv
https://hgzttvjqhfepdnngsrhs.supabase.co/storage/v1/object/public/polymarket-data/latest_10000000_trades.parquet
https://hgzttvjqhfepdnngsrhs.supabase.co/storage/v1/object/public/polymarket-data/metadata.json
```

---

## Dependencies

Dependencies are managed via `pyproject.toml` and installed automatically with `uv sync`.

**Key Libraries**:
- `polars` - Fast DataFrame operations
- `pandas` - Data manipulation
- `gql` - GraphQL client for Goldsky
- `requests` - HTTP requests to Polymarket API
- `flatten-json` - JSON flattening for nested responses

**Development Dependencies** (optional, installed with `--extra dev`):
- `jupyter` - Interactive notebooks
- `notebook` - Jupyter notebook interface
- `ipykernel` - Python kernel for Jupyter

## Features

### Resumable Operations
All stages automatically resume from where they left off:
- **Markets**: Counts existing CSV rows to set offset
- **Goldsky**: Reads last timestamp from orderFilled.csv
- **Processing**: Finds last processed transaction hash

### Error Handling
- Automatic retries on network failures
- Rate limit detection and backoff
- Server error (500) handling
- Graceful fallbacks for missing data

### Missing Market Discovery
The processing stage automatically discovers markets that weren't in the initial markets.csv (e.g., markets created after last update) and fetches them via the Polymarket API, saving to `missing_markets.csv`.

## Data Schema Details

### Trade Direction Logic
- **Taker Direction**: BUY if paying USDC, SELL if receiving USDC
- **Maker Direction**: Opposite of taker direction
- **Price**: Always expressed as USDC per outcome token

### Asset Mapping
- `makerAssetId`/`takerAssetId` of "0" represents USDC
- Non-zero IDs are outcome token IDs (token1/token2 from markets)
- Each trade involves USDC and one outcome token

## Notes

- All amounts are normalized to standard decimal format (divided by 10^6)
- Timestamps are converted from Unix epoch to datetime
- Platform wallets (`0xc5d563a36ae78145c45a50134d48a1215220f80a`, `0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e`) are tracked in `poly_utils/utils.py`
- Negative risk markets are flagged in the market data

## Troubleshooting

**Issue**: Markets not found during processing
**Solution**: Run `update_markets()` first, or let `process_live()` auto-discover them

**Issue**: Duplicate trades
**Solution**: Deduplication is automatic - re-run processing from scratch if needed

**Issue**: Rate limiting
**Solution**: The pipeline handles this automatically with exponential backoff

## 📊 Data Analysis

### Loading Data (After Downloading from Supabase)

```python
import polars as pl
import pandas as pd
from poly_utils import get_markets, PLATFORM_WALLETS

# Load markets (all 170K+)
markets_df = get_markets()

# Load trades (latest 10M from Supabase - FAST!)
trades_df = pl.read_parquet("processed/latest_10000000_trades.parquet")

# Already has proper datetime type - no conversion needed!
print(f"Loaded {len(trades_df):,} trades")
print(f"Date range: {trades_df['timestamp'].min()} to {trades_df['timestamp'].max()}")
```

### Available Notebooks

After downloading data, explore these Jupyter notebooks in `notebooks/`:

- **polymarket_analytics.ipynb** - 20+ analytical functions (top traders, markets, PnL)
- **top_traders_market_analysis.ipynb** - Top 1000 traders with visualizations
- **single_trader_analysis.ipynb** - Deep dive on individual traders with 15+ charts

```bash
# Start Jupyter
jupyter notebook notebooks/
```

### Filtering Trades by User

**Important**: When filtering for a specific user's trades, filter by the `maker` column. Even though it appears you're only getting trades where the user is the maker, this is how Polymarket generates events at the contract level. The `maker` column shows trades from that user's perspective including price.

```python
USERS = {
    'domah': '0x9d84ce0306f8551e02efef1680475fc0f1dc1344',
    '50pence': '0x3cf3e8d5427aed066a7a5926980600f6c3cf87b3',
    'fhantom': '0x6356fb47642a028bc09df92023c35a21a0b41885',
    'car': '0x7c3db723f1d4d8cb9c550095203b686cb11e5c6b',
    'theo4': '0x56687bf447db6ffa42ffe2204a05edaa20f55839'
}

# Get all trades for a specific user
trader_df = trades_df.filter(pl.col("maker") == USERS['domah'])
print(f"Found {len(trader_df):,} trades for domah")
```

## License

Go wild with it

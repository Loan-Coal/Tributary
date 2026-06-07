# Data Sources — Lenovo Group Consolidated Balance Sheet

## Overview
This directory contains consolidated balance sheet data for **Lenovo Group Limited**, fetched from three international stock exchange listings. All three CSV files represent the **same company and the same consolidated statement** — they differ only in the exchange listing from which the data is sourced.

## Data Files

### 1. Hong Kong Listing
- **File**: `lenovo_consolidated_hong_kong_0992HK.csv`
- **Ticker**: `0992.HK`
- **Exchange**: Hong Kong Stock Exchange (HKEX)
- **Status**: Primary listing
- **Currency**: USD (consolidated reporting)
- **Description**: Lenovo's primary global listing, where the company reports consolidated financials for international investors.

### 2. United States Listing
- **File**: `lenovo_consolidated_united_states_LNVGY.csv`
- **Ticker**: `LNVGY`
- **Exchange**: OTC Markets (over-the-counter)
- **Status**: American Depositary Receipt (ADR)
- **Currency**: USD (consolidated reporting)
- **Description**: US-tradable ADR representing Lenovo shares. Investors in the US access the same consolidated statement via this vehicle.

### 3. German Listing
- **File**: `lenovo_consolidated_germany_LHL_F.csv`
- **Ticker**: `LHL.F`
- **Exchange**: Frankfurt Stock Exchange
- **Status**: Secondary listing
- **Currency**: USD (consolidated reporting)
- **Description**: German/European trading venue for Lenovo shares, also reporting identical consolidated figures.

## Key Points

### Why Three Files?
Multinational corporations file **one consolidated financial statement** in a single reporting currency (Lenovo uses USD). Multiple exchange listings for the same company pull the identical statement — the listing location does not change the underlying financial data, only where investors can trade the shares.

### Why Not China?
Lenovo has **no mainland Chinese listing**. The company's planned Shanghai STAR Market CDR (China Depositary Receipt) was withdrawn in 2021. Therefore, there is no Chinese-filed statement to include.

### Data Structure
Each CSV contains:
- **Rows**: Balance sheet line items (Assets, Liabilities, Equity, etc.)
- **Columns**: Fiscal year-ends (dates or converted to string format for stable parsing)
- **Values**: Financial figures in USD

Row labels are sanitized (special characters removed) for database compatibility.

### Data Source
- **Tool**: `yfinance` Python library
- **Fetch Method**: Historical balance sheet snapshots for all available fiscal years
- **Refresh**: Run `python3 data/raw/get_data.py` to fetch the latest data

## Usage

### Running the Data Fetch Script
```bash
cd /Users/rishabh/Desktop/Hackathon/Tributary
python3 data/raw/get_data.py
```

This will:
1. Query yfinance for each ticker
2. Retrieve the full historical balance sheet
3. Sanitize and export to CSV
4. Display status for each download

### Expected Output Files
All three CSVs will be created/updated in this directory (`data/raw/`). They contain identical consolidated statement data for Lenovo Group across multiple fiscal years.

## Notes
- **All three files are identical**: Same company, same currency (USD), same consolidated statement
- **Multi-jurisdiction**: Demonstrates how the same multinational's consolidated financials can be accessed through different market listings
- **Data Availability**: Subject to yfinance's data coverage and exchange rate policies; some exchanges may be rate-limited on repeated requests
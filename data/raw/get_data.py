from pathlib import Path

import yfinance as yf

# All source data lives alongside this script in data/raw/, regardless of the
# working directory the script is launched from.
RAW_DIR = Path(__file__).resolve().parent

# The SAME company (Lenovo Group Limited) as it is listed/traded across countries.
# A multinational files ONE consolidated balance sheet; querying different exchange
# listings returns identical figures in the group's reporting currency (USD). The
# listing only changes where the shares trade, not the underlying statement.
#
# China is intentionally absent: Lenovo has no mainland listing (its planned Shanghai
# STAR Market CDR was withdrawn in 2021), so there is no real Chinese-filed statement.
target_nodes = {
    "hong_kong": {
        "ticker": "0992.HK",   # primary listing, Hong Kong Stock Exchange
        "output_file": "lenovo_consolidated_hong_kong_0992HK.csv",
    },
    "united_states": {
        "ticker": "LNVGY",     # US ADR (OTC)
        "output_file": "lenovo_consolidated_united_states_LNVGY.csv",
    },
    "germany": {
        "ticker": "LHL.F",     # Frankfurt listing
        "output_file": "lenovo_consolidated_germany_LHL_F.csv",
    },
}

REPORTING_CURRENCY = "USD"  # Lenovo Group reports consolidated financials in USD.

print("[+] Pulling Lenovo Group consolidated balance sheet per country listing...\n")

for node_name, node in target_nodes.items():
    ticker = node["ticker"]
    try:
        company = yf.Ticker(ticker)

        # Full historical balance sheet (all fiscal years yfinance serves).
        bs_history = company.balance_sheet

        if bs_history.empty:
            print(f"[-] Warning: No data accessible for node: {ticker} ({node_name}) "
                  f"- exchange may be rate-limited; retry.")
            continue

        # Clean column dates and row labels for stable database parsing.
        bs_history.columns = bs_history.columns.astype(str)
        bs_history.index = bs_history.index.str.replace(r"[^a-zA-Z0-9 ]", "", regex=True)

        output_path = RAW_DIR / node["output_file"]
        bs_history.to_csv(output_path)

        years = list(bs_history.columns)
        print(f"[✓] {node_name}: {company.info.get('longName', ticker)} ({ticker}) "
              f"-> {output_path} (Currency: {REPORTING_CURRENCY}, years: {years})")

    except Exception as error:
        print(f"[X] Execution error on ticker {ticker}: {str(error)}")

print(f"\n[i] Note: all three files report the SAME consolidated statement in {REPORTING_CURRENCY}.")
print("\n[+] Download sequence completed.")

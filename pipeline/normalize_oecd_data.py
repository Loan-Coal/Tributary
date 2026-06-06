"""
Normalize OECD tax revenue data into transaction records for Neo4j ingestion.
Reads from: data/raw/transactions_raw.csv
Writes to: data/processed/transactions_normalized.csv
"""

import csv
import pandas as pd
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def normalize_oecd_to_transactions(input_path: Path, output_path: Path):
    """
    Transform OECD tax revenue data into standardized transaction format.
    """
    
    # Read the raw OECD data
    df = pd.read_csv(input_path)
    
    print(f"Loaded {len(df)} records from {input_path}")
    print(f"Columns: {df.columns.tolist()}")
    
    # Map OECD data to transaction format
    transactions = []
    
    for idx, row in df.iterrows():
        try:
            # Extract relevant fields
            ref_area = row.get('REF_AREA', '').strip()
            revenue_code = row.get('REVENUE_CODE', '').strip()
            amount = row.get('OBS_VALUE', 0)
            currency = row.get('UNIT_MEASURE', 'HKD').strip()
            time_period = row.get('TIME_PERIOD', '2014')
            measure_desc = row.get('Measure', '').strip()
            
            # Skip invalid records
            if pd.isna(amount) or amount == 0 or amount == '':
                continue
            
            # Create transaction record
            transaction = {
                'id': f"tx_oecd_{ref_area}_{revenue_code}_{time_period}_{idx}",
                'account_id': f"acc_{ref_area.lower()}_{revenue_code}",
                'counterparty_id': f"gov_{ref_area.lower()}",
                'date': f"{time_period}-01-01",  # Assume Jan 1st for annual data
                'amount': float(amount),
                'currency': currency,
                'flow_direction': 'inbound',  # Tax revenue is inbound
                'description': f"Tax revenue: {measure_desc}",
                'gl_code': revenue_code,
                'data_source': 'OECD_CTP',
                'record_type': 'tax_revenue'
            }
            
            transactions.append(transaction)
            
        except Exception as e:
            print(f"Warning: Skipped row {idx}: {str(e)}")
            continue
    
    print(f"\nTransformed {len(transactions)} valid records")
    
    # Write to normalized CSV
    if transactions:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', newline='') as f:
            fieldnames = [
                'id', 'account_id', 'counterparty_id', 'date', 
                'amount', 'currency', 'flow_direction', 'description', 
                'gl_code', 'data_source', 'record_type'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(transactions)
        
        print(f"✅ Normalized data written to: {output_path}")
        print(f"\nSample records:")
        with open(output_path) as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i < 3:
                    print(row)
                else:
                    break
    else:
        print("❌ No valid records to write")


if __name__ == "__main__":
    raw_path = Path("data/raw/transactions_raw.csv")
    output_path = Path("data/processed/transactions_normalized.csv")
    
    if not raw_path.exists():
        print(f"❌ Raw data not found at {raw_path}")
    else:
        normalize_oecd_to_transactions(raw_path, output_path)

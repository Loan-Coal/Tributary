import json
from pathlib import Path
from tributary.rules.db import query_rules

def main():
    db = Path('examples/rules.db')
    results = query_rules(db, query='service', jurisdictions=['HK'], limit=10)
    print('Found', len(results), 'HK rules matching "service"')
    # Normalize DB results to the RuleSummary shape expected by the runner
    normalized = []
    for r in results:
        normalized.append({
            'id': r.get('rule_id'),
            'summary': r.get('summary') or r.get('full_text', ''),
            'as_of_date': r.get('as_of_date'),
            'source_citation': r.get('source_citation'),
        })

    out = {
        'transaction_id': 'txn-1000',
        'transaction_context': {
            'transaction_text': 'Provision of software development services to an overseas related party.',
            'related_party': True,
            'service_type': 'Software development',
            'contract_reference': 'PO-2026-042',
            'candidate_jurisdictions': ['HK']
        },
        'rule_summaries': normalized
    }
    with open('examples/input_with_hk_rules.json','w',encoding='utf-8') as fh:
        json.dump(out, fh, indent=2)
    print('Wrote examples/input_with_hk_rules.json')

if __name__ == '__main__':
    main()

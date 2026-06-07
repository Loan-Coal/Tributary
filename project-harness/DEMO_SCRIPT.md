# Tributary — Demo Script
## Meridian Group: Cross-Border Tax Copilot

**Audience:** Hackathon judges, tax professionals, investors.
**Time:** 5–7 minutes for live demo + Q&A.
**Goal:** Show an end-to-end run producing 4 fully cited filing briefs and a cross-border conflict report for a realistic multinational group.

---

## Setup (before the room fills)

```bash
# 1. Start Neo4j (takes ~10 seconds)
docker-compose up -d

# 2. Seed the graph with the Meridian Group golden scenario
make ingest

# 3. (One-time, if AI narratives not cached) Generate AI prose
#    Requires your configured LLM backend (TRIBUTARY_LLM in .env — ollama, qwen, or claude).
make snapshot-ai
```

**On Windows (PowerShell), run `snapshot-ai` manually:**
```powershell
$env:TRIBUTARY_AI_ENABLED = "1"
python -m tributary.engine.cli snapshot_ai
```

Verify graph is seeded: open Neo4j Browser at http://localhost:7474
Login: neo4j / (password from .env → NEO4J_PASSWORD)
Run: `MATCH (e:Entity) RETURN e` — you should see 4 entity nodes.

---

## Demo run

```bash
make demo
```

**On Windows (PowerShell):**
```powershell
$env:TRIBUTARY_AI_ENABLED = "1"
$env:TRIBUTARY_AI_CACHE_ONLY = "1"
python -m tributary.engine.cli demo
```

**What happens (narrate aloud):**

1. The engine ingests all 11 transactions from the Meridian Group.
2. For each of 4 entities, the deterministic engine applies the relevant rule packs
   (HK, DE, FR, US) — no AI computes figures.
3. 4 filing briefs are written to `output/` in Markdown.
4. 1 cross-border conflict report is written to `output/conflict_report.md`.

---

## Show the outputs

```bash
# List all generated files
ls output/

# View a brief
cat output/MERID-HK_brief.md
cat output/MERID-DE_brief.md
cat output/MERID-US_brief.md

# View the conflict report
cat output/conflict_report.md
```

**On Windows (PowerShell) — use `-Encoding UTF8` to render special characters correctly:**
```powershell
Get-ChildItem output/
Get-Content output/MERID-HK_brief.md -Encoding UTF8
Get-Content output/MERID-DE_brief.md -Encoding UTF8
Get-Content output/MERID-US_brief.md -Encoding UTF8
Get-Content output/conflict_report.md -Encoding UTF8
```

**Key numbers to call out:**

| Entity | Jurisdiction | CIT (HKD) | Key point |
|--------|-------------|-----------|-----------|
| MERID-HK | Hong Kong | HKD 445,500 | Territorial source — royalties + mgmt fees only |
| MERID-DE | Germany | HKD 47,673 | Loss carryforward applied; PE Triangle planted |
| MERID-FR | France | HKD 1,030,938 | WHT on royalty paid to DE; VAT filing obligation |
| MERID-US | United States | HKD 816,900 | 21% federal CIT; 30% WHT on upstream dividend |

**The conflict to highlight:**
> "The PE Triangle — MERID-DE sends staff to France for 185 days. Both Germany (residence)
> and France (PE jurisdiction) claim taxing rights on the same income. The engine detects
> this automatically, applies the exemption method under the DE-FR treaty (Article 23),
> and flags residual double-tax = 0. Without the treaty, the same income would be taxed
> twice."

---

## Show the graph in Neo4j Browser

Navigate to http://localhost:7474

**Ownership graph:**
```cypher
MATCH (parent:Entity)-[r:OWNS]->(child:Entity)
RETURN parent, r, child
```
Shows: MERID-HK → MERID-DE → MERID-FR and MERID-HK → MERID-US

**Transaction flows:**
```cypher
MATCH (t:Transaction)
RETURN t.transaction_id, t.activity_type, t.amount_hkd, t.source_entity_id, t.counterparty_entity_id
ORDER BY t.transaction_id
```

**Presence records (PE trigger):**
```cypher
MATCH (p:PresenceRecord)
RETURN p.entity_id, p.host_jurisdiction, p.total_days_present
```
Shows 185 days in France → over the 183-day PE threshold.

---

## Key talking points

### "The AI never computes figures."
All tax amounts, rates, and thresholds come from rule packs (versioned JSON, hand-authored
from statute). The AI layer classifies flow nature (royalty vs. dividend vs. service fee)
and writes the prose narrative. Every number traces back to a rule citation with a
`source_citation` field pointing to the authoritative statute (e.g. `KStG §23`, `IRC §11`).

### "Every output is cited."
Every brief section shows which rule produced the figure, its as-of date, and the public
statutory source. A tax professional reviewing the brief can verify every number.

### "The conflict is deterministic."
The PE Triangle conflict is detected by pure Python logic comparing day counts from
presence records against PE thresholds from the DE and FR rule packs. No AI is involved
in conflict detection — it's structurally impossible to hallucinate a conflict.

### "Adding a new country is one JSON file."
The engine is country-agnostic. Adding Singapore or UK means authoring a new rule pack
JSON file — zero engine code change (per architecture decision DEC-006). The golden
scenario supports this: MERID-US was added with `data/rules/us.json` and no engine edits.

---

## Anticipated Q&A

**Q: How accurate are the tax figures?**
A: The engine computes correctly against the demo rule packs. The packs use real statutory
rates (HK 16.5%, DE 15.825%, FR 25%, US 21%) from publicly available statutes, with
as-of dates. For production, these would be replaced with a licensed data feed (e.g. IBFD)
behind the same JSON interface. The output is a *brief for professional review*, not
a filed return — the disclaimer is explicit in every output.

**Q: What if a rule changes?**
A: Update the JSON rule pack. The as-of-date field on every rule ensures historical runs
are reproducible. The engine immediately picks up new rates — no code change.

**Q: Does the AI hallucinate tax law?**
A: No. The AI never sees raw tax codes. It receives structured summaries of the rule pack
rules as context, classifies the nature of cash flows, and writes prose. Rates, thresholds,
and deadlines are engine-filled before the AI touches the output — the AI can't alter them.

**Q: What about GILTI and FDII for the US entity?**
A: Both are flagged `needs_review=True` in the US brief, with a clear note that GILTI
inclusion calculations and FDII deductions require professional assessment. The engine
never produces an incorrect number on these — it surfaces the gap for the reviewer.

**Q: Can this file a return?**
A: Not yet — that's post-hackathon scope (E1 in the expansion roadmap). The current output
is a cited brief that a tax professional uses as a structured work product, saving hours
of manual computation. The statutory form filling layer would read the brief fields.

**Q: How long does a run take?**
A: The deterministic engine runs in milliseconds. The AI narrative layer (when live) adds
~5–10 seconds per entity for prose generation. In demo mode (cached), the entire run
completes in under 2 seconds.

---

## Fallback: if Neo4j is not running

If `docker-compose up -d` fails or Neo4j is unavailable, the demo can still show:

1. The pre-generated output files in `output/` (from the last run)
2. The EXPECTED.md hand-computed figures at `data/golden/EXPECTED.md`
3. The rule pack files at `data/rules/` to show the statutory sources
4. The test suite: `make test` shows 279 tests passing, including golden scenario validation

The system is designed so the engine can be tested without Neo4j using the
`FakeGraphReader` (see `tests/support/fakes.py`).

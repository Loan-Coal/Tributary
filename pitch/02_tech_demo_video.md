# Tech Demo Video Script — 2 minutes

**Jury context:** Operator background, Fintech Association of HK. Lead with what the product does for a user, not how it works internally. Show the web UI. Explain the architecture briefly but anchor everything in the user experience.

**Format:** Web UI → ingest → engine running → conflict alert → brief → rule pack → CTA

---

## [0:00–0:15] Open on the web UI

**Show:** Browser, Tributary web interface. Dashboard or home screen visible.

> "This is Tributary. You log in, you see your entities — in our demo, Meridian Group: a Hong Kong parent, subsidiaries in Germany, France, and the US. The intercompany flows between them are already mapped."

---

## [0:15–0:35] Trigger the analysis

**Show:** Click "Run analysis" or equivalent. Show the engine processing and results appearing.

> "We kick off the multi-jurisdiction analysis. The engine runs every applicable tax rule across all four jurisdictions simultaneously — CIT, withholding tax, VAT, trade tax, cross-border conflicts.
>
> This is what would take a team of advisors weeks to coordinate. It takes Tributary seconds."

---

## [0:35–1:00] The PE Triangle conflict alert

**Show:** Conflict report or alert in the UI. Highlight the PE Triangle finding.

> "Here's the headline finding. MERID-DE — the German entity — had employees delivering services in France for 185 days. That's two days over the 183-day threshold in the DE-FR tax treaty.
>
> France now claims the right to tax 35% of MERID-DE's profits. Germany claims the same profits under worldwide taxation. That's a double-tax conflict — and nobody in the group caught it.
>
> Tributary catches it automatically. It applies the treaty exemption method, shows you the net exposure, and tells you exactly which treaty article resolves it."

---

## [1:00–1:20] Filing brief walkthrough

**Show:** Click into one jurisdiction brief — Germany or France. Scroll through it.

> "Each jurisdiction gets a full filing brief — structured, readable by the advisor who needs to sign off.
>
> Every number traces to a source transaction. Every rule shows the statute it came from and the date it was verified. The AI wrote the narrative you're reading. The engine computed every figure. They can't be confused — that separation is the core of the system."

---

## [1:20–1:40] Show how jurisdiction coverage works

**Show:** Briefly show `data/rules/us.json` or equivalent UI view of the US rule pack. Keep it quick.

> "Adding a jurisdiction is one configuration file. The US pack covers federal corporate tax, outbound withholding, and flags two regime elections — FDII and GILTI — as needing professional input, because those require judgment we don't pretend to replace.
>
> Singapore, UK, any jurisdiction: one file, no engine change. The advisor community can contribute rule packs; the engine stays the same."

---

## [1:40–2:00] Close on the brief / output

**Show:** The full brief or the conflict summary in the UI, clean and readable.

> "This is what lands in the advisor's inbox instead of a blank engagement letter. Findings already structured, sources already cited, conflicts already flagged.
>
> The advisor still reviews. She still signs off. We just make sure she has the right information before she walks into that conversation — not six weeks after."

---

## Preparation checklist before recording

- [ ] Web UI running locally (or deployed)
- [ ] Golden scenario data seeded (`make ingest`)
- [ ] Demo runs cleanly end-to-end in the browser
- [ ] Browser zoom level set for readability on video
- [ ] Have conflict report visible and ready to navigate to
- [ ] Have at least one complete brief visible (DE or FR recommended — shows EU complexity)
- [ ] Mute notifications before recording

# Q&A Preparation — Likely Jury Questions

**Jury context:** Fintech Association of HK board member, has owned companies. Her questions will be operator- and market-focused. She may probe liability, GTM, and HK-specificity. Technical questions will be brief and practical — she wants to know if it actually works and if the business makes sense.

---

## Business & Market Questions (most likely)

---

**Q: "Who's your customer — the company or the tax advisor?"**

> Both, but the entry point is different. We sell to the CFO of a mid-market multinational as a monitoring tool — she gets visibility she didn't have before, without a six-week engagement. We also sell to the tax practice as a workflow accelerator — the brief arrives structured and cited, so the advisor spends time on judgment rather than on building the picture from scratch. The advisor channel is probably faster to close: one firm has dozens of multinational clients, each of whom is a billing unit for us.

---

**Q: "What happens when the engine is wrong? Who carries the liability?"**

> Same person who carries it today — the professional advisor who reviews and signs off. Tributary is a brief-generation and conflict-detection tool, not a tax opinion. Every output is explicitly labelled with the rule's as_of_date and source citation, and any item requiring professional judgment is flagged "needs review" rather than given a hard answer. We're not replacing the advisor's liability; we're giving them better information before they form their view. The brief is the starting point for the engagement, not the end of it.

---

**Q: "Why would a company use this instead of just hiring a Big 4 firm?"**

> They're not mutually exclusive — the advisor still reviews the output. But a Big 4 engagement starts at $50,000 and takes six weeks to produce a picture that Tributary generates in seconds. For a mid-market CFO who doesn't have a dedicated tax team, that's the difference between annual exposure monitoring and a crisis response. We also catch things that fall between advisors — the PE Triangle in our demo is exactly that: the German advisor knows German law, the French advisor knows French law, and nobody is watching the interaction between them. We watch the whole graph.

---

**Q: "The HK market is small. How do you scale?"**

> HK is the beachhead, not the ceiling. Every HK-incorporated holding company has European and US subsidiaries — that's already a multi-jurisdiction problem. Adding a new jurisdiction to Tributary is one JSON configuration file; the engine never changes. We expand on customer demand: the first client asking about Singapore is the signal to write the Singapore rule pack. The rule pack library is the asset that compounds — and it's the same interface that a licensed data provider like IBFD would plug into, so the commercial ceiling is global.

---

**Q: "How does this fit the fintech sector specifically?"**

> Fintech is actually the most acute case. Cross-border payment companies have high transaction volumes, multi-entity structures, and thin margins where an unexpected WHT exposure or PE trigger can materially change the unit economics. Digital asset treasury operations don't have clear jurisdiction guidance yet — exactly the kind of "needs professional review" flag our system surfaces correctly. The Fintech Association's member base is our natural early adopter cohort: sophisticated operators, international by design, and currently underserved by tools built for Fortune 500 budgets.

---

**Q: "What's your pricing?"**

> We haven't fixed final pricing, but the model is SaaS per entity per jurisdiction — so a four-entity multinational covering three jurisdictions would pay four times three times the per-entity rate. We're targeting a price point significantly below the cost of one advisory engagement, so the ROI conversation is easy. Annual subscription, with a premium tier for the conflict detection and alert layer.

---

**Q: "Why you? What's the team's background?"**

> *(Answer based on actual backgrounds. Suggested framing:)*
> "We have the combination that this problem requires: [X] comes from [tax/finance/legal] and validated every statutory rule pack from primary sources — the engine doesn't guess at tax law because a human read the statutes. [Y] architected the system with the discipline that professional tools require: every output cites its source, every number is auditable. Hackathons are about what you build under pressure — we think what we shipped shows how we'd build the real product."

---

**Q: "What's mocked in the demo?"**

> We're fully transparent about this in our HONESTY.md — it's in the repo. The financial data is a golden demo scenario we authored. The AI outputs are pre-cached so the demo runs offline. The tax engine, conflict detection, and brief assembly are real and running live. We think being honest about what's demo-ready and what's production-ready is a feature, not a weakness — a system that knows its own limits is one you can trust.

---

## Technical Questions (less likely, but possible)

---

**Q: "How do you prevent the AI from making up tax rates?"**

> By design — the AI never sees raw financial data and never computes a number. It receives a brief template with all figures already filled in by the deterministic engine, and it only writes the narrative prose around them. Every amount in the output traces to a specific transaction and a specific rule. If the AI were to emit a figure, the architecture would reject it — that separation is enforced at the layer boundary, not by prompting.

---

**Q: "How do you keep the rules current? Tax law changes."**

> Every rule carries an as_of_date and a statutory citation — so the brief transparently shows the reviewer when each rule was last verified. In production, the rule pack interface is the same one a licensed data provider like IBFD or Bloomberg Tax would plug into. The engine never changes; you upgrade the data source. For the demo, we authored the packs from primary statutory sources with that date visible in every output.

---

**Q: "Explain the PE Triangle."**

> In plain terms: our German entity had staff working in France for 185 days. The DE-FR tax treaty says that if you deliver services in the other country for more than 183 days, you've created a taxable presence there — a permanent establishment. France then has the right to tax profits attributed to that presence. Germany also taxes the same entity on worldwide profits. Same money, two tax authorities claiming it. The treaty has a resolution mechanism — the exemption method — but you have to know the conflict exists before you can apply the resolution. That's what Tributary catches.

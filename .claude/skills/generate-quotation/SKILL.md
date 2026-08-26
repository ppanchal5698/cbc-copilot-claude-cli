---
name: generate-quotation
description: >
  Renders the draft quotation - grouped by door with subtotals, a separate
  restroom-accessories block, an FRP block, a TBD freight line, and standard
  commercial terms. Produces projects/{project}/quotation.html from the priced
  line items. Use in Phase 4/6 of a CBC bid, after every line has a cost and a
  margin.
---

# Generate Quotation

## Structure the estimator expects

1. **Header** - Hamilton Parker Company / CBC, quote number, date, 30-day validity
2. **Customer block** - GC name, initiator, project name, location, bid due date
3. **Doors, grouped by door** - one block per opening: frame, door, then each
   hardware item, with a **subtotal per door**
4. **Restroom accessories** - a separate block, never mixed into the door groups
   (partitions, grab bars, mirrors, dispensers, hand dryers)
5. **FRP** - its own block when in scope (panels, trim, adhesive)
6. **Freight** - a `TBD` line, unpriced. Freight is handled when a quote becomes a
   job, not at estimate stage
7. **Grand total**, with sales tax only for Ohio and Kentucky
8. **Commercial terms** - HP PO required, supply-only material, 30-day validity
9. **Footer** - estimator name and contact

## Steps

1. Read `priced/line_items.json` and `priced/margin_applied.json`.
2. Roll up with `mcp__calc-engine__compute_totals`, passing `project_state` so tax
   is applied correctly - **do not total by hand**.
3. Render `templates/quotation.html` with `scripts/render_quote.py`.
4. Write via `mcp__artifact-storage__save_artifact` so the draft is versioned.
5. **Stop.** The quotation is a draft. Do not convert, route, attach or send it.

## Lines that are not fully priced

Never hide them. Render them in place with:

- `PRICE PENDING - MANUAL` for manual cut-off items
- `AWAITING VENDOR QUOTE` for RFQ lines
- `price may be out of date - refresh` for distributor-bought lines

A quote with three visible gaps is useful. A quote with three silently guessed
numbers is dangerous.

## Rules

- @.claude/rules/human-in-the-loop.md
- @.claude/rules/auditability.md

## Reference data

- @.claude/memory/sales_tax_rules.md
- @.claude/memory/process_flow.md - Phase 6

## Script

```bash
python .claude/skills/generate-quotation/scripts/render_quote.py dutch_bros_macarthur_2026
```

## Output

`projects/{project}/quotation.html`. The pipeline then halts with
**"Draft ready for estimator review"**.

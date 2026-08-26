---
name: scan-product-catalog
description: >
  Searches the vendor price-book PDFs (Hager, National Guard, PEMKO/Markar,
  Rockwood, ASI, Bobrick, Bradley, Gamco, World Dryer, NUDO) for a product by
  part number, series or description, and returns list price with page-level
  traceability. Use when a matched item needs a list price before the multiplier
  is applied.
---

# Scan Product Catalog

## Search strategy

Work down this ladder and stop at the first step that answers:

1. **Exact part number** - `mcp__pricebook__lookup_pricing` with `part_number`,
   `vendor` and the multiplier `category`. Returns every candidate price on the
   page with its `source_page`; it deliberately refuses to pick one when the page
   is ambiguous.
2. **Series or keyword** - `mcp__pricebook__search_product` with a `vendor`
   filter. Always pass the vendor; a library-wide search across 26 books is slow
   and noisy.
3. **Multiplier** - `mcp__pricebook__get_multiplier`. Hager prices **by product
   category**, so pass the category (`locks`, `door_controls`, `exit_devices`,
   `architectural_hinges`, `electrified_products`, ...). Other vendors carry a
   single tier.
4. **Give up cleanly.** No hit means MANUAL, not "close enough".

## Applying the multiplier

```
cost = list_price x multiplier
```

Hager example, verified end to end: a 3500-series storeroom lock lists **256.31**;
the locks tier is **0.290** (50/42% discount); cost is **74.33**. At the commodity
margin that is a **101.82** sale each.

**Adders are never included** in a price-book lookup. Electrification, NRP hinges
and premium finishes are added deliberately from
`reference-library/adders/manual_adders.json`.

## Vendors with no usable price book

- **Allegion** - not bought direct. Banner Solutions or SecLock, manual entry.
- **Zero, Alarm Lock, Cal-Royal, Dorma** - outside the Phase-1 top-10.
- **Bobrick and Gamco** - priced from HP program NET sheets (2017), not list x
  multiplier. The sheets are old; verify before quoting.
- **Scranton** - access lost. Out of scope entirely.

## Rules

- @.claude/rules/auditability.md
- @.claude/rules/file-safety.md - `pricebooks/` is read-only during a run

## Reference data

- @.claude/memory/vendor_tiers.md
- @.claude/memory/cost_sourcing_rules.md

## Script

```bash
python .claude/skills/scan-product-catalog/scripts/search_pricebook.py --list
```

```bash
python .claude/skills/scan-product-catalog/scripts/search_pricebook.py hager 3510 --category locks
```

## Output

Every result carries `source_file`, `source_page`, `effective_date`, the
`multiplier_tier` used and its `multiplier_effective_date` - the full provenance
chain NFR-3 requires.

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

The catalog tools tell you **which page to open**. They do not return prices,
and nothing stored knows one - the price is on the sheet, and you read it there.
That is deliberate: pre-extracting every row is what produced an index where 37.8%
of the part codes carried no letter and effective dates were recorded as parts.

1. **Learn the book** - `mcp__catalog__get_catalog_overview` when the vendor is
   unfamiliar. A few hundred tokens on how that publisher organises things, and it
   saves opening the wrong pages.
2. **Find the page** - `mcp__catalog__find_pages` with the part number, series or
   description, and a `vendor` filter. Always pass the vendor; a library-wide
   search is noisier. Each hit carries a two-line description, the part families
   on the page, whether it carries prices, and why it matched.
3. **Read the page** - `mcp__pdf-tools__extract_tables` on the `pdf_page` from the
   hit. This is where the price comes from. If the page does not hold the part,
   try the next hit rather than settling for the nearest row on the wrong page.
4. **Multiplier** - `mcp__catalog__get_multiplier`. Hager prices **by product
   category**, so pass the category (`locks`, `door_controls`, `exit_devices`,
   `architectural_hinges`, `electrified_products`, ...). Other vendors carry a
   single tier.
5. **Give up cleanly.** No page, or a page that turns out not to hold the part,
   means MANUAL - not "close enough".

**Cite the `locator` exactly as given.** It carries both the PDF page and the
number printed on the page, and they differ on 775 of the 1,216 indexed pages
because section numbering restarts. An estimator sent to "page 23" of a 744-page
book cannot find the line without both.

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

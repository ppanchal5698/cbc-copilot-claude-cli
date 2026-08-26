# Price Books

26 vendor files across 10 vendors, copied from `final_pricebooks/`. Machine-readable
inventory: `index.json` (vendor, file, effective date, kind, divisions).

**These files are READ-ONLY during a pipeline run.** The `pre_delete_guard.py` hook
blocks any `rm` that touches this directory, and `.claude/rules/file-safety.md`
forbids writes. Updating a price book is a deliberate, human-initiated act.

## Inventory

| Vendor | File | Effective | Kind |
|---|---|---|---|
| Hager | `hager_price_book_18.pdf` | 2026-02-02 | price book (744 pages) |
| Hager | `hager_multipliers.pdf` | 2026-03-02 | multiplier sheet (acct HGR 17907) |
| ASI | `asi_price_list.pdf` | 2026-01-12 | price book (.375) |
| National Guard | `national_guard_price_list.pdf` | 2026-06-08 | price book (.45) |
| National Guard | `national_guard_threshold_catalog.pdf` | - | catalog |
| PEMKO / Markar | `pemko_markar_price_book_2026.pdf` | 2026-01-01 | price book |
| PEMKO | `pemko_buying_program.pdf` | 2020-01-01 | multiplier sheet (acct 4244636) |
| Rockwood | `rockwood_architectural_price_book.pdf` | 2025-03-03 | price book |
| Rockwood | `rockwood_architectural_price_book_alt.pdf` | - | price book |
| Rockwood | `rockwood_accessories_price_book.pdf` | - | price book (.55) |
| Rockwood | `rockwood_lites_louvers_price_book.pdf` | 2023-02-27 | price book |
| Rockwood | `rockwood_glass_solutions_price_book.pdf` | 2022-07-29 | price book |
| Bradley | `bradley_price_book_2026.pdf` | 2026-01-01 | price book (WAD .53) |
| Bobrick | `bobrick_price_list.pdf` | 2020-01-01 | price book |
| Bobrick | `bobrick_hp_program_net.xlsx` | 2017-01-01 | NET program sheet |
| Bobrick | `bobrick_multiplier.docx` | - | multiplier memo |
| Bobrick | `bobrick_cross_reference.xlsx` | - | crosswalk |
| Gamco | `gamco_price_list.pdf` / `.xlsx` | 2020-01-01 | price book |
| Gamco | `gamco_hp_program_net.xlsx` | 2017-01-01 | NET program sheet |
| Gamco | `gamco_crossover.xls` | - | crosswalk |
| World Dryer | `world_dryer_l3_pricing.xlsx` | 2022-09-01 | price book (L3 .339) |
| World Dryer | `world_dryer_l3_memo.pdf` | 2022-09-12 | pricing memo |
| NUDO | `nudo_frp_pricing.pdf` | 2026-05-11 | price book (Midwest-East Coast FRP) |
| NUDO | `nudo_vinyl_moldings_pricing.pdf` | 2026-05-11 | price book |
| NUDO | `nudo_price_increase_memo.msg` | - | memo |

## Vendors with no price book here

- **Allegion** (Von Duprin, LCN, Schlage, Ives) - not bought direct. Purchased
  through Banner Solutions or SecLock, so every Allegion line is manual price entry.
- **Zero, Alarm Lock, Cal-Royal, Dorma** - outside the Phase-1 top-10.
- **Scranton** - access lost, out of scope entirely.

## Freshness

Only PDFs are text-indexed by the `pricebook` MCP server. The `.xlsx`, `.xls`,
`.docx` and `.msg` files are inventoried for reference and human lookup.

```bash
bash scripts/refresh_pricebooks.sh
```

At the time of writing, **11 of 26 files are past 180 days** and **7 carry no
effective date**. That is reported on every pre-flight rather than suppressed.

**NFR-10 (data stewardship) is OPEN** - no owner and no refresh cadence have been
assigned. Until they are, staleness is visible but not prevented. See
`.claude/rules/data-stewardship.md`.

## Pointing elsewhere

Set `PRICEBOOK_DIR` to use a different directory - a network share, for instance -
without duplicating ~56 MB of PDFs.

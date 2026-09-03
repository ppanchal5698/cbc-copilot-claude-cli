# CBC Data Dependencies (Estimator Session v1.3)

Items the pipeline **cannot invent**. When missing, agents flag `PENDING` or
`MANUAL` and stop — matching how an estimator would pause and call purchasing.

| ID | Deliverable | Blocks | Owner | Pipeline interim behavior |
|---|---|---|---|---|
| NR-6 | Authoritative top-10 stock lists per product type | FR-4, NR-13 cut-off | CBC Estimating | Draft `hager_top10_stock.json`; `is_stock_item` uses draft |
| Open Item 5 | FRP conversion constants (panel, waste, trim, adhesive) | FR-12 | Estimating | Geometry in `frp_takeoff.json`; qty `null`, `PENDING_CONSTANTS` |
| NR-7/8 | Hager adder values + lite-kit table logic | NR-1, NR-4 | CBC / Estimating | Six list adders on file; lite grid extracted; NR-8 logic partial |
| NR-10 | P21 read-only + part-number matching | FR-6 Path 1 | IT / Dash | Structured MANUAL when disconnected |
| Open Item 9 | Fire-rating rules (where, price-sensitive categories) | FR-2 pricing | Sr. Estimator | Extract + high-severity flag; no hard-stop |
| FR-11 | Prior completed quotes for templated mode | Phase 1 reuse | CBC Estimating | Empty `reference-library/prior_quotes/` → one-off |
| FR-14 / Item 11 | Alternates/addenda reconciliation policy | Phase 4b | Estimating Lead | Distinct line groups + version diff; explicit PENDING banner |
| NR-9 | Special-customer margin values (e.g. Wendy's) | FR-5 | CBC | Structure in settings; values owed |
| NR-11 | HP-Fabrication "peelle" door terminology | Scope | CBC | Term unconfirmed in agents |
| NFR-10 / Item 15 | Data stewardship owner + refresh cadence | Staleness prevention | Purchasing | Staleness report only; no auto-block |

**Ingestion:** When CBC supplies prior quotes, place under
`reference-library/prior_quotes/` and re-run templated intake so
`reuse-prior-quote` can rank candidates.

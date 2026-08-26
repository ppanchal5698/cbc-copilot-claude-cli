# Requirements Matrix

Source: `docs/CBC_Req_Validation_v1_3.xlsx`. About 50 of 54 rows carry a
confirmation from the 14 Jul 2026 estimator session with Kevin, Rick and Shanna.

**Status key:** Accurate = confirmed · Pending = still needs an answer ·
Deferred = out of scope for this phase.

## Functional requirements

| Ref | Requirement | Status | Where it lives |
|---|---|---|---|
| FR-1 | Accept a bid-set PDF (and email/RFP text) as the trigger for a new estimate | Accurate | `intake-coordinator` |
| FR-2 | Extract door/opening schedule - number, size, handing, finish, **fire rating**, HW-set callouts, alternate designation | Accurate | `takeoff-engineer`, `extract-door-schedule` |
| FR-3 | Maintain a central structured reference library, independent of any job file | Accurate | `reference-library/` |
| FR-4 | Match each opening to the closest library entry - rating, handing, finish - and propose lines | Accurate | `product-matcher`, `match-hardware-sets` |
| FR-5 | Apply the product-type margin framework as an editable default per line | Accurate | `apply-margin`, `calc-engine` |
| FR-6 | Source cost from P21 last-PO, or list x multiplier, or a vendor RFQ - honouring freshness and recording the source | Accurate | `pricing-engineer`, `price-line-item` |
| FR-7 | Generate a draft quote grouped by door with subtotals, a separate accessories block, and a freight line | Accurate | `quote-builder`, `templates/quotation.html` |
| FR-8 | Assign a confidence score per match; flag low confidence, missing ratings, unparsed content | Accurate | `quality-reviewer` |
| FR-9 | Provide a review/edit interface - accept, edit, delete, add - before approval | Accurate | `templates/review_summary.html` |
| FR-10 | Export the approved quote to PDF with standard commercial terms | Accurate | `delivery-agent` |
| FR-11 | Reuse the closest prior quote (brand / architect / GC) as a starting draft | Accurate | `reuse-prior-quote` |
| FR-12 | Assist the FRP take-off - perimeter and corners to quantities | Accurate | `frp-specialist` (**constants pending**) |
| FR-13 | Capture estimator corrections as structured feedback | Accurate (future-leaning) | `review/estimator_notes.md` |
| FR-14 | Version an estimate - base bid plus alternates, absorb addenda | **Pending** | blocked on Matrix 4.1 |
| FR-15 | Flag any line below the product-type margin floor | **Deferred** | flag implemented, routing deferred |
| FR-16 | Support the vendor-RFQ loop - mark awaiting, capture the price, slot it in | Accurate | `price-line-item` Path 3 |

## Non-functional requirements and guardrails

| Ref | Guardrail | Status | Enforcement | Owner |
|---|---|---|---|---|
| NFR-1 | **Human-in-the-loop** - nothing is sent without estimator approval | Accurate | `pre_send_quote.py` hook (exit 2), deny list, `delivery-agent` halt | Estimating |
| NFR-2 | **Accuracy / trust** - confidence visible, never silently guess | Accurate | `accuracy-trust` rule, confidence on every match, review flags | Estimating |
| NFR-3 | **Auditability** - every line traces to a source page and a price-sheet version | Accurate | `source_page` on all extraction, cost provenance on all pricing, `audit_trail.jsonl` | Estimating + IT |
| NFR-4 | **Data security** - drawings and pricing stay in an approved environment | **Pending** | owner not confirmed | IT (TBC) |
| NFR-5 | **Integration** - P21 read-only, no write-back | Accurate | `p21-connector` exposes no write tools; asserted at import | IT + Dash |
| NFR-6 | **Performance** - a 10-40 opening bid produces a reviewable draft in minutes | Aligned | headless pipeline; no formal target set | Estimating + Dash |
| NFR-7 | **Usability** - review interface usable by senior and junior estimators | Accurate | `review_summary.html` | Estimating |
| NFR-8 | **Margin governance** - floor per product type, below-band flagged | **Deferred** | `validate_margin` flags; no routing | future |
| NFR-9 | **Approval authority and QA** - who may approve, thresholds | **Deferred** | - | future |
| NFR-10 | **Data stewardship** - named owner and refresh cadence per pricing source | **OPEN** | `refresh_pricebooks.sh` reports staleness as interim mitigation | Purchasing + Estimating |
| NFR-11 | **Adoption and change management** | Accurate | both estimating modes supported | Estimating Lead + Dash |

## Business rules confirmed

| Ref | Rule |
|---|---|
| 2.1 | In scope: metal and wood doors, HM frames (welded and knock-down), HP-Fabrication doors, door hardware, Division 10 specialties, FRP wall panels |
| 2.3 | Out of scope: ceiling tile and grid, tile, brick, masonry, aluminum/glass storefront, coiling/overhead/oversized doors, engineered wood, metal siding, JL Industries. Plus **Scranton** (access lost) and **American Dryer** (not used) |
| 2.4 | Supply-only material. Sales tax for **Ohio (~8%)** and **Kentucky (6.5%)** only; other 48 states and Canada none |
| 3.0 | Two modes: templated (Shanna) and one-off (Kevin; exceptions McDonald's, Cava). Rick uses his own Excel |
| 5.0 | Only Quantity, Our Cost and Margin are manual. **Unit weight removed** |
| 6.1 | Margin bands: commodity 27%, restroom partitions 35%, specialty 40%, custom-built 25%; accessories derive to **56%**. Overridable by sourcing |
| 6.2 | Cost = P21 **last-PO** price, never the supplier-list/cost fields. Freshness: <6mo fresh, 6-8mo+ unreliable, 3-4yr discard |
| 6.3 | Cost = list x customer multiplier. Hager prices **by category**. MAP is not cost. **Adders are not in the price book** |
| 6.4 | Direct equals: propose the closest of the top 2-3 brands **with a note**; the GC approves |
| 6.5 | Record the sourcing rationale - direct vs distributor - on every line |
| 6.6 | Vendor RFQ for custom sizes, unusual preps, options not sold in years |
| 7.0 | Five standard frame throats: 5-5/8, 5-3/4, 5-7/8, 7-3/4, 8-1/4, plus CUSTOM (~10 max). Adjustable frames exist |
| 7.1 | 4-digit door notation: `3070` = 3'-0" x 7'-0"; `3670` = 3'-6" x 7'-0" |
| 7.2 | No single standard HW list. Build around top-10 stock per product type plus a custom/other tab |
| 7.4 | Handing appears per opening in the schedule |
| 7.5 | Dual finish nomenclature: US26D = 626, **US19 and 26D are different satins**, 619 = US15 |
| 7.7 | Architects specify by part number and series; reconcile to CBC stock |

## Still open - do not invent answers to these

| # | Item | Impact |
|---|---|---|
| 9 | **Fire rating** - where it lives in bid sets, which categories price on it, whether a missing rating hard-stops | `fire_rating_rules.md` marked PENDING; missing ratings flagged at severity high |
| 11 | **Alternates and addenda** - how alternates are quoted, how addenda are reconciled | FR-14 pending; base and alternates kept as distinct groups |
| 15 | **Data stewardship** - owner and refresh cadence per pricing sheet | NFR-10 OPEN; staleness reported, not prevented |
| 5 | **FRP conversion constants** - panel size, waste %, trim stick, adhesive coverage | Partial; geometry captured, quantities null |
| 16 | **Baseline and target metrics** | Not captured |

## New requirements from the 14 Jul session

| Ref | Item | State |
|---|---|---|
| NR-1 | Light-kit (lites/louvers) pricing calculator | Not built - data on file (NGP, PEMKO/Markar, Rockwood books indexed) |
| NR-2 | Manual price entry for distributor lines with a "refresh" prompt | **Built** - `p21-connector` and `price-line-item` |
| NR-3 | Dual finish-nomenclature interpreter | **Built** - `finish_crosswalk.json` |
| NR-4 | Manual adders not in the base price book | **Built** - `manual_adders.json`, with real Hager list adders |
| NR-5 | "Create new bid request" for phone-in bids | **Built** - `intake-coordinator` |
| NR-6 | Top-10 stock list per product type | **CBC owes this.** Draft harvested from the price book, marked PENDING |
| NR-7 | Hager adder values | Partial - six list adders extracted from Price Book #18 p.297 |
| NR-8 | Light-kit table logic | CBC owes this |
| NR-9 | Special-customer margins (e.g. Wendy's) | CBC owes the values; structure in place |
| NR-10 | P21 integration feasibility and part-number matching strategy | Dash/IT investigating; connector returns "manual entry required" |
| NR-11 | Exact term for HP-Fabrication "peelle" doors | CBC to confirm |
| NR-12 | Hager live-data / API feed instead of the static PDF | Dash to investigate |
| NR-13 | **Automate stock, hard MANUAL cut-off beyond it** | **Built** - `manual_cutoff.md` and enforced across the agents |

# Margin Bands

| Band | Key | Margin | Divisor | Sale $ EA from cost 100.00 |
|---|---|---|---|---|
| Commodity | commodity | 27% | 0.73 | 136.99 |
| Restroom partitions | restroom_partitions | 35% | 0.65 | 153.85 |
| Specialty | specialty | 40% | 0.60 | 166.67 |
| Custom-built (outside fabricator) | custom_built | 25% | 0.75 | 133.33 |
| Restroom accessories | accessories | 56% | 0.44 | 227.27 |

Source: Requirements Matrix 6.1, confirmed in the 14 Jul estimator session.
Machine-readable: reference-library/margins/margin_framework.json

## Accessories: 56%, not 35%

The original documentation recorded restroom accessories at 35%. The estimator
session corrected this: the data derives to about **56%**. Use 56%.

## Overridable, by design

Margin is an editable default. It is overridden on essentially every quote based
on sourcing:

- **Wendys** - special margin when the product is bought via Banner Solutions or
  SecLock at a higher cost. Exact value PENDING from CBC (NR-9).
- **Distributor buys** generally - higher cost in, lower margin out.
- **Lead time** and genuinely custom first builds - hand-entered margin.

Record the reason every time. An unexplained below-band margin is what the flag
exists to catch.

## Worked example, end to end

Hager 3500-series storeroom lock:

| Step | Value | Source |
|---|---|---|
| List price | 256.31 | Price Book #18, page 297 |
| Multiplier (locks tier) | 0.290 | Hager discount sheet, effective 2026-03-02 |
| Cost | 74.33 | list x multiplier |
| Band | commodity, 27% | margin_framework.json |
| Sale $ EA | 101.82 | cost / 0.73 |
| Qty 3, Ext | 305.46 | sale_ea x qty |

## Governance

Below-band lines are FLAGGED, never blocked. Approval routing is deferred
(NFR-8 / Matrix 6.7) - there is no margin deviation today and estimators hold to
the standard bands. Revisit when the estimating team grows.

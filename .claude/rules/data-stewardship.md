# Data Stewardship (NFR-10) — **STATUS: OPEN**

Each pricing source needs a **named owner and a refresh cadence** so automated quotes never
run on stale data. **Neither has been assigned yet** (Open Item 15) — this rule records the
gap rather than papering over it.

## Sources that need an owner and a cadence
| Source | Path | Owner | Cadence |
|---|---|---|---|
| Reference library | reference-library/ | **UNASSIGNED** | **UNDEFINED** |
| Vendor multiplier sheets | pricebooks/ | **UNASSIGNED** | **UNDEFINED** |
| Margin sheet | reference-library/margins/ | **UNASSIGNED** | **UNDEFINED** |
| Top-10 stock list | reference-library/hardware_sets/ | **UNASSIGNED** (CBC to provide, NR-6) | **UNDEFINED** |

## Interim mitigation
- Every price-book file carries its **effective date** in pricebooks/index.json and that date
  is echoed onto every priced line (see the auditability rule).
- scripts/refresh_pricebooks.sh reports the age of each price book and warns past **180 days**.
- Manually entered prices always show the **"price may be out of date — refresh"** prompt (NR-2).
- The P21 freshness rule (6-8 months unreliable, 3-4 years discard) applies independently.

## Risk if left open
Stale price sheets drive wrong quotes — silently, and at scale.

## Owner
CBC Purchasing and Estimating. **Still to be named.**

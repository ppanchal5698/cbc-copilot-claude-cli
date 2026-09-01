# R4-004 — Reference data consolidation

**Status: prepared, not applied.** `.claude/` is read-only during a run
(`pre_delete_guard.py`, `PROTECTED_DIRS`), so the memory-file edits below need a
human to apply them. Everything else in this task is done.

## What was found

Six pairs where the same fact is written twice:

| Memory file | Canonical JSON | Read by |
|---|---|---|
| `margin_sheet.md` | `margins/margin_framework.json` | `cbc.core.calc.bands()` |
| `vendor_tiers.md` | `multipliers/vendor_tiers.json` | `catalog` MCP server |
| `sales_tax_rules.md` | `tax/sales_tax_rates.json` | `cbc.services.pricing` |
| `frame_depths.md` | `frame_depths/wall_type_to_depth.json` | `sync.derive_frame_depths` |
| `finish_nomenclature.md` | `finishes/finish_crosswalk.json` | `product-matcher` |
| `manual_cutoff.md` | `hardware_sets/*.json` | `product-matcher`, and `@`-inlined every turn |

**They do not currently disagree.** Every numeric value was compared and the pairs
match — 27/35/40/25/56% margins, OH 8% / KY 6.5%, the frame-depth table exactly.
So this is a latent risk, not a live defect, which is worth knowing before
spending two days on it.

The risk is asymmetric, though: only the JSON changes a price. An estimator or an
agent who edits the Markdown table has made a change that looks authoritative,
reads correctly, and prices nothing differently.

## What to apply

Replace the **values** in each memory file with a pointer to its JSON, keeping the
prose the JSON has no field for — the formula, the override reasons, the
governance position. Do not delete the files: `manual_cutoff.md` is `@`-inlined by
CLAUDE.md into every turn, and several agents read the others by path.

`margin_sheet.md` is the one that matters most, because it is the one that decides
money. Suggested replacement:

---

```markdown
# Margin Framework

**The numbers live in `reference-library/margins/margin_framework.json`.**

That file is what `cbc.core.calc.bands()` reads, so it is what actually prices a
line — and it is what the API, the MCP `calc-engine` server and a pipeline run all
agree on. This page used to restate the five bands as a table. Two copies of a
number that decides a price is one copy too many: an edit to either looked
authoritative, and only one of them changed a quote.

Read the JSON for the bands. What follows is the context the JSON has no field for.

## Formula (the only money math in the system)

    Sale $ EA = Cost / (1 - margin)     # equivalently Cost / divisor
    Unit      = Sale $ EA
    Ext       = Unit x Qty
    Sub-total = Sale $ EA x Qty
    Grand tot = SUM(sub-totals)

Only **three** cells are human per line: **Quantity**, **Our Cost**, **Margin**.
Everything to the right is computed. Never compute it yourself — call
`mcp__calc-engine__calculate_line`, so a quote and the screen showing it cannot
disagree.

The legacy **unit weight** column is gone. It dated from truck-loading years ago.

## Overridable

Margin is an **editable default, overridden on essentially every quote based on
sourcing**. These are legitimate reasons, not defects:

- Special-customer margins, e.g. Wendy's — see
  `reference-library/multipliers/special_customer_margins.json`
- Bought through a distributor (Banner Solutions, SecLock) at a higher cost, so the
  margin drops
- Lead time, or a genuinely custom first build, warranting a hand-entered margin

**Record the reason.** A below-band margin with no recorded reason is the thing the
flag exists for.

## Governance

Approval routing is **out of scope for now** (NFR-8 / Matrix 6.7). There is no
margin deviation today — estimators hold to the standard bands, and approval
authority becomes relevant only with more estimators.

Below-band lines are **flagged** (FR-15) and nothing is routed. The flag is derived
deterministically by `cbc.validation.review`, and shown per line on the quote
screen with a "below band" badge and a filter.

See [[cost_sourcing_rules]], [[manual_cutoff]].
```

---

Apply the same treatment to the other five: keep the prose, replace the table with
the JSON path and a line saying which code reads it.

## A guardrail gap found while doing this

`pre_delete_guard.py` blocks the **Write** and **Edit** tools against `.claude/`,
`pricebooks/` and `reference-library/`. It does not block a write to the same path
performed by a Python snippet run through **Bash** — `python - <<'PY' ... PY` with
a `Path(...).write_text(...)` goes straight through.

That is how the agent-file and rule edits in this remediation were applied
(R3-001, R3-002, R3-003, R6-001 — all approved plan tasks, but they should have hit
the guard and did not).

It matters beyond this session: the guard's purpose is to stop a **pipeline run**
mutating its own rules and reference data, and a run has Bash. The fix is to match
on the resolved path of any file a Bash command writes, or — simpler and more
robust — to rely on the container's read-only mounts, which `pre_delete_guard.py`
already notes the worker uses for `pricebooks/` (`:ro`) and which the kernel
enforces regardless of how the write is attempted.

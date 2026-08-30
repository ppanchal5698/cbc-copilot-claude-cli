# Development Description

## The problem

CBC - Construction Building Components, the national-accounts division of The
Hamilton Parker Company - quotes commercial building components to GCs and
national restaurant and retail chains. Three estimators do it by hand.

A bid arrives by email. Someone reads the specs and drawings, takes off every
opening, looks each item up in P21 or on a vendor multiplier sheet, types cost
into a password-protected Excel workbook, applies a margin band, exports a PDF and
emails it back to whoever asked.

Reading the specs and drawings is the single largest time cost in every bid.
Estimating knowledge sits with three people. Both facts are the reason for this
system.

## What was built

A Claude Code CLI application that runs the same Phase 0-6 workflow autonomously
and stops at a reviewable draft.

| Layer | Count | What |
|---|---|---|
| Agents | 9 | One per process phase |
| Skills | 9 | Reusable task workflows plus scripts |
| Rules | 8 | Auto-loaded constraints |
| Hooks | 5 | Executable guardrails |
| Memory | 13 | Business rules and reference data |
| MCP servers | 5 | PDF, pricebook, calc, storage, P21 |
| Workflows | 9 | Headless orchestration |
| Reference JSON | 10 | Margins, multipliers, finishes, frame depths, adders, stock lists |
| Price books | 26 | Real vendor files across 10 vendors |
| Tests | 6 | 48 pytest checks plus 23 guardrail checks |

## Build order

1. Scaffold
2. `CLAUDE.md` and the 13 memory files - business rules first, because everything
   else references them
3. 8 rules
4. 5 hooks, then `settings.json` - guardrails before anything can run
5. 5 MCP servers
6. 9 skills
7. 9 agents
8. Reference library
9. Templates, scripts, workflows
10. Docs and tests

Rules and memory precede agents so the agents' `@` imports resolve. Guardrails
precede the pipeline so nothing can run unguarded.

## Decisions worth knowing about

**Word-position clustering instead of table detection.** Architectural bid sets
are CAD exports. Sheet A2.2 of the test fixture carries 13,397 vector line
segments; `pdfplumber.find_tables()` returns 35 candidates, roughly one of which
is the door schedule. Clustering positioned words by y-coordinate recovers the
schedule and the hardware groups cleanly. This was verified against the real
fixture before the rest of the pipeline was written.

**Python hooks, not bash.** `jq` is not installed on the target machine. A
jq-based hook exits 127 when jq is missing, which is not 2, which means the tool
call proceeds. A guardrail that silently stops guarding is worse than none.

**stdlib `difflib` instead of rapidfuzz.** Part-number matching is
containment-first. The dependency did not earn its place.

**One arithmetic implementation.** Every margin, subtotal and tax figure comes from
`calc-engine`. Nothing else computes money.

**Gaps stay visible.** Fire-rating rules and FRP conversion constants are genuinely
unanswered by CBC. They are modelled as `PENDING`, and the code refuses to
substitute a default. A missing rating is flagged at severity high; FRP quantities
come back `null` with `blocked_on` attached.

## Stakeholders

| Person | Role | What the system had to accommodate |
|---|---|---|
| **Kevin** | Estimator - one-off mode | Builds from scratch; prices manually from vendor sheets and calls vendors. Exceptions McDonald's and Cava, worked templated |
| **Rick** | Estimator - own Excel | Works outside both shared workbooks; occasionally includes freight for customers who want an all-inclusive number |
| **Shanna** | Estimator - templated mode | Starts from a previous job's workbook and trims down; owns the FRP take-off in Vu360 |
| Kellan, Matt, Rebecca, Tina | Sales queue initiators | Quotes route back to the specific person who asked, never a group email |
| CBC Purchasing | Vendor tiers and multipliers | Supplies the sheets; NFR-10 owner still unnamed |
| CBC IT | P21 access | Read-only; integration feasibility still open |

The system supports **both** estimating modes. Neither was forced on the other -
"it only helps" was the adoption test.

## What CBC still owes

| Item | Blocks |
|---|---|
| Fire-rating rules (Matrix 7.3 / Open Item 9) | Where the rating lives, which categories price on it, whether a missing rating hard-stops |
| FRP conversion constants (Open Item 5) | Panel size, waste %, trim stick length, adhesive coverage |
| Alternates and addenda handling (Matrix 4.1 / Open Item 11) | FR-14 versioning |
| Top-10 stock list per product type (NR-6) | The item picker; a draft is harvested from the price book meanwhile |
| Special-customer margin values (NR-9) | Wendy's and any others |
| Data stewardship owner and cadence (NFR-10 / Open Item 15) | Stale price sheets stay visible but unprevented |
| Light-kit table logic (NR-8) | The lites/louvers calculator (NR-1) |
| P21 integration feasibility (NR-10) | Cost path 1 |

None of these block the design. Each firms up a specific rule or data source.

## Engagement model

Long-term, with ongoing maintenance - not one-and-done. Phase 1 covers the top-10
vendors and the stock list, which the estimators estimated could speed 80-90% of
quotes. The long tail stays manual by design (NR-13), and the reference library
grows as estimator corrections come back as structured feedback (FR-13).

The guiding principle, from the requirements workbook and unchanged throughout:

> The estimator stays in control of every quote. The copilot drafts, sources and
> calculates - it does not send. Its job is to remove manual re-keying and lookup,
> not to replace estimating judgment.

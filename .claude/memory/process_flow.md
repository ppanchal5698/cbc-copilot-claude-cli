# CBC Process Flow — Phase 0 to 6 (the canonical workflow)

Reading the specs and drawings up front is **the single largest time cost in every bid**.

| Phase | Activity | System / tool | Output | Agent |
|---|---|---|---|---|
| **0 — Intake** | Receive bid request | Outlook (mostly email; sometimes phone) | Bid set PDFs, alternates + due date noted | intake-coordinator |
| **1 — File setup** | Create job workbook | Excel (pw estimator) | New job workbook | intake-coordinator |
| **2 — Spec scoping** | Identify Div 08 + Div 10 scope from specs | PDF specs | Confirmed scope + rating/HW notes | spec-scope-analyst |
| **3 — Drawing take-offs** | Counts, door sizes, handing, rating | Edge viewer / Vu360 | Quantities + opening attributes | takeoff-engineer |
| **3b — FRP take-off** | Perimeter LF, inside/outside corners | Vu360 + calculator | FRP material quantities | frp-specialist |
| **4 — Pricing and build** | Populate and price every line | Excel + P21 + vendor sheets / RFQ | Priced draft quote | product-matcher, pricing-engineer, quote-builder |
| **4b — Alternates and addenda** | Base bid + alternates; reconcile addenda | Excel / Outlook | Base + alternates | *(PENDING — see below)* |
| **5 — Judgment, reuse and RFIs** | Reuse closest prior job; direct-equal subs; RFIs | Excel / email | Resolved quote + RFIs | quality-reviewer |
| **6 — Deliver** | Export PDF proposal, route to sales initiator | Excel to PDF / Outlook | Customer-facing PDF | delivery-agent |

## Phase-by-phase detail

**Phase 0 — Intake.** Bid arrives mostly by email with the job workbook plus plans/RFP
attached; sometimes by phone, hence the "create new bid request" option (NR-5). The request
comes from the internal initiator in the queue (Kellan / Matt / Rebecca / Tina), **not** the
architect. Note bid alternates and the **bid-due date** at intake. A bid set may be **one
combined PDF or several separate PDFs** — handle both.

**Phase 1 — File setup.** Templated mode copies an existing workbook and modifies it per the
RFP (Shanna); one-off mode builds from scratch (Kevin; exceptions McDonald's, Cava).
Clearing the previous job residual rows is the first task in templated mode.

**Phase 2 — Spec scoping.** Scope identified manually from the spec/RFP PDFs: Division 08
doors/frames/hardware plus Division 10 specialties plus FRP. Read fire ratings and the
hardware-set (HW) schedule. Architects specify hardware **by part number / series**;
reconcile to the CBC stock list, and push everything beyond it to the custom/other tab.

**Phase 3 — Drawing take-offs.** Drawings reviewed and taken off manually. Extract door
number, size, handing, finish, fire rating, hardware-set callout, frame type, and wall type.

**Phase 3b — FRP.** Set drawing scale in Vu360, capture perimeter (LF) and inside/outside
corners. Vu360 gives **geometry only**; the estimator converts to material quantities by hand.
**The conversion constants are still pending from CBC.**

**Phase 4 — Pricing.** Only Qty / Cost / Margin are manual; everything else computes.
Three cost paths — see [[cost_sourcing_rules]]. Margin per [[margin_sheet]].
Freight usually carried TBD.

**Phase 4b — Alternates and addenda. PENDING.** Formal handling was **not covered** in the
14 Jul session (Matrix 4.1 / FR-14 / Open Item 11). Until answered: keep base bid and each
alternate as **distinct, comparable line groups**, and never overwrite prior work when an
addendum lands.

**Phase 5 — Judgment.** Reuse the closest prior quote for a repeat brand/architect/GC
(FR-11). Value-engineering: when a specified line is not available, propose the closest of
the top 2-3 brands **with a note**. Raise RFIs for unclear or missing info before finalizing.

**Phase 6 — Deliver.** Export a PDF proposal — doors/frames/hardware **grouped by door with
subtotals**, a **separate restroom-accessories block**, a freight line (often TBD), and
standard commercial terms (HP PO required, 30-day validity). Send back to **whoever initiated
the request in the queue**, not a group email; they deal with the customer.

**The copilot stops here.** It produces the draft and reports
"Draft ready for estimator review". A human sends it (NFR-1).

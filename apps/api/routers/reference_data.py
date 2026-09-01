"""Editable reference data (pricing configuration).

The reference-library JSON files are the source of truth the pricing pass reads.
Editing them here is the deliberate, human-initiated act the file-safety rule
allows - the same pattern price-book category multipliers already use. Margin
bands feed cbc_core.calc.bands(), which re-reads the file whenever its mtime
moves, so an edit takes effect on the next line priced without a restart.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from apps.api.deps import Actor, AdminActor
from cbc.schemas import (
    FinishesUpdate,
    FrameDepthsUpdate,
    FrpConstantsUpdate,
    HagerAddersUpdate,
    MarginFrameworkUpdate,
    SpecialMarginsUpdate,
    TaxRatesUpdate,
)
from cbc.services import audit
from cbc.services import reference_library as reflib
from cbc.core import calc

router = APIRouter(prefix="/api/reference", tags=["reference"])


def _framework() -> dict[str, Any]:
    payload = reflib.load_margins()
    return {
        "bands": payload.get("bands", []),
        "accessoriesDerived": payload.get("accessories_derived"),
        "formula": payload.get("formula"),
        "overridable": payload.get("overridable"),
        "governance": payload.get("governance"),
        "source": payload.get("source"),
        # What the pricing engine will actually apply, read straight back through
        # calc so the screen cannot drift from the numbers a quote uses.
        "effective": calc.bands(),
    }


def _tax() -> dict[str, Any]:
    payload = reflib.load_tax_rates()
    return {
        # Read back through calc so the screen shows what pricing actually applies.
        "rates": calc.tax_rates(),
        "description": payload.get("description"),
        "source": payload.get("source"),
        "note": payload.get("note"),
    }


@router.get("/margins")
async def get_margins(actor: Actor) -> dict[str, Any]:
    try:
        return _framework()
    except FileNotFoundError as exc:
        raise HTTPException(404, "margin framework file is missing") from exc


@router.patch("/margins")
async def update_margins(body: MarginFrameworkUpdate, actor: AdminActor) -> dict[str, Any]:
    if not body.bands and body.accessories is None:
        return _framework()

    before = reflib.load_margins()
    before_bands = {b.get("key"): b.get("margin") for b in before.get("bands", [])}
    before_bands["accessories"] = before.get("accessories_derived")

    try:
        reflib.update_margins(bands=body.bands, accessories=body.accessories)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    after = reflib.load_margins()
    after_bands = {b.get("key"): b.get("margin") for b in after.get("bands", [])}
    after_bands["accessories"] = after.get("accessories_derived")

    changed = {
        key: value for key, value in after_bands.items() if before_bands.get(key) != value
    }
    await audit.record(
        "reference.margins.update",
        actor,
        {"file": "reference-library/margins/margin_framework.json"},
        before={key: before_bands.get(key) for key in changed},
        after=changed,
    )
    return _framework()


@router.get("/tax")
async def get_tax(actor: Actor) -> dict[str, Any]:
    try:
        return _tax()
    except FileNotFoundError as exc:
        raise HTTPException(404, "sales tax file is missing") from exc


@router.patch("/tax")
async def update_tax(body: TaxRatesUpdate, actor: AdminActor) -> dict[str, Any]:
    if not body.rates and not body.remove:
        return _tax()

    before = reflib.load_tax_rates().get("rates", {})
    try:
        reflib.update_tax_rates(rates=body.rates, remove=body.remove)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    after = reflib.load_tax_rates().get("rates", {})
    touched = set(before) | set(after)
    changed = {
        code: after.get(code) for code in touched if before.get(code) != after.get(code)
    }
    await audit.record(
        "reference.tax.update",
        actor,
        {"file": "reference-library/tax/sales_tax_rates.json"},
        before={code: before.get(code) for code in changed},
        after=changed,
    )
    return _tax()


def _adder_items(payload: dict[str, Any]) -> dict[str, Any]:
    return {r.get("name"): r.get("list_adder") for r in payload.get("hager_list_adders", {}).get("items", [])}


def _adders() -> dict[str, Any]:
    payload = reflib.load_adders()
    block = payload.get("hager_list_adders", {})
    return {
        "adderTypes": payload.get("adder_types", []),
        "hagerListAdders": {
            "source": block.get("source"),
            "status": block.get("status"),
            "application": block.get("application"),
            "items": block.get("items", []),
        },
        "pending": payload.get("pending", []),
        "rule": payload.get("rule"),
    }


@router.get("/adders")
async def get_adders(actor: Actor) -> dict[str, Any]:
    try:
        return _adders()
    except FileNotFoundError as exc:
        raise HTTPException(404, "manual adders file is missing") from exc


@router.patch("/adders")
async def update_adders(body: HagerAddersUpdate, actor: AdminActor) -> dict[str, Any]:
    if not body.items and not body.remove:
        return _adders()

    before = _adder_items(reflib.load_adders())
    try:
        reflib.update_hager_adders(items=body.items, remove=body.remove)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    after = _adder_items(reflib.load_adders())
    touched = set(before) | set(after)
    changed = {name: after.get(name) for name in touched if before.get(name) != after.get(name)}
    await audit.record(
        "reference.adders.update",
        actor,
        {"file": "reference-library/adders/manual_adders.json"},
        before={name: before.get(name) for name in changed},
        after=changed,
    )
    return _adders()


def _special_margins(payload: dict[str, Any]) -> dict[str, Any]:
    return {c.get("name"): c.get("margin") for c in payload.get("customers", [])}


def _special() -> dict[str, Any]:
    payload = reflib.load_special_margins()
    return {
        "customers": payload.get("customers", []),
        "rule": payload.get("rule"),
        "status": payload.get("status"),
        "description": payload.get("description"),
    }


@router.get("/special-margins")
async def get_special_margins(actor: Actor) -> dict[str, Any]:
    try:
        return _special()
    except FileNotFoundError as exc:
        raise HTTPException(404, "special customer margins file is missing") from exc


@router.patch("/special-margins")
async def update_special_margins(body: SpecialMarginsUpdate, actor: AdminActor) -> dict[str, Any]:
    if not body.customers and not body.remove:
        return _special()

    before = _special_margins(reflib.load_special_margins())
    try:
        reflib.update_special_margins(
            customers=[c.model_dump(exclude_unset=True) for c in (body.customers or [])],
            remove=body.remove,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    after = _special_margins(reflib.load_special_margins())
    touched = set(before) | set(after)
    changed = {name: after.get(name) for name in touched if before.get(name) != after.get(name)}
    await audit.record(
        "reference.special_margins.update",
        actor,
        {"file": "reference-library/multipliers/special_customer_margins.json"},
        before={name: before.get(name) for name in changed},
        after=changed,
    )
    return _special()


@router.get("/finishes")
async def get_finishes(actor: Actor) -> dict[str, Any]:
    try:
        return reflib.load_finishes()
    except FileNotFoundError as exc:
        raise HTTPException(404, "finish crosswalk file is missing") from exc


@router.patch("/finishes")
async def update_finishes(body: FinishesUpdate, actor: AdminActor) -> dict[str, Any]:
    if not body.finishes and not body.remove:
        return reflib.load_finishes()

    before = {f.get("us_code") for f in reflib.load_finishes().get("finishes", [])}
    try:
        reflib.update_finishes(
            finishes=[f.model_dump(exclude_unset=True) for f in (body.finishes or [])],
            remove=body.remove,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    after = {f.get("us_code") for f in reflib.load_finishes().get("finishes", [])}
    await audit.record(
        "reference.finishes.update",
        actor,
        {"file": "reference-library/finishes/finish_crosswalk.json"},
        before=sorted(before),
        after=sorted(after),
    )
    return reflib.load_finishes()


@router.get("/frame-depths")
async def get_frame_depths(actor: Actor) -> dict[str, Any]:
    try:
        return reflib.load_frame_depths()
    except FileNotFoundError as exc:
        raise HTTPException(404, "frame depths file is missing") from exc


@router.patch("/frame-depths")
async def update_frame_depths(body: FrameDepthsUpdate, actor: AdminActor) -> dict[str, Any]:
    if not body.wall_types and not body.remove:
        return reflib.load_frame_depths()

    before = {w.get("type") for w in reflib.load_frame_depths().get("wall_types", [])}
    try:
        reflib.update_frame_depths(
            wall_types=[w.model_dump(exclude_unset=True) for w in (body.wall_types or [])],
            remove=body.remove,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    after = {w.get("type") for w in reflib.load_frame_depths().get("wall_types", [])}
    await audit.record(
        "reference.frame_depths.update",
        actor,
        {"file": "reference-library/frame_depths/wall_type_to_depth.json"},
        before=sorted(before),
        after=sorted(after),
    )
    return reflib.load_frame_depths()


@router.get("/frp-constants")
async def get_frp_constants(actor: Actor) -> dict[str, Any]:
    try:
        return reflib.load_frp_constants()
    except FileNotFoundError as exc:
        raise HTTPException(404, "FRP constants file is missing") from exc


@router.patch("/frp-constants")
async def update_frp_constants(body: FrpConstantsUpdate, actor: AdminActor) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=True)
    if not values:
        return reflib.load_frp_constants()

    before = reflib.load_frp_constants()
    try:
        after = reflib.update_frp_constants(values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    await audit.record(
        "reference.frp_constants.update",
        actor,
        {"file": "reference-library/frp_constants/conversion_constants.json"},
        before={field: before.get(field) for field in values} | {"status": before.get("status")},
        after={field: after.get(field) for field in values} | {"status": after.get("status")},
    )
    return after

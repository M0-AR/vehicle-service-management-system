"""NHTSA vPIC VIN decoding (free, keyless, no registration).

Doc: https://vpic.nhtsa.dot.gov/api/ — DecodeVinValues returns a flat record
for a 17-character VIN. Network failures raise httpx.HTTPError; the router
translates them into a 502 so callers get a clear upstream error.
"""

from __future__ import annotations

import re

import httpx

VPIC_URL = (
    "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
)
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def normalize_vin(vin: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", vin or "").upper()


def is_valid_vin(vin: str) -> bool:
    """17 chars, no I/O/Q (NHTSA standard)."""
    return bool(VIN_RE.match(vin))


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value or value.lower() in ("not applicable", "null"):
        return None
    return value


def _map_fuel(value: str) -> str | None:
    v = (value or "").lower()
    if not v:
        return None
    if "hybrid" in v:
        return "hybrid"
    if "electric" in v:
        return "electric"
    if "diesel" in v:
        return "diesel"
    if "gasoline" in v or "petrol" in v:
        return "petrol"
    if "lpg" in v or "propane" in v:
        return "lpg"
    return None


def _engine_label(results: dict) -> str | None:
    parts: list[str] = []
    displacement = _clean(results.get("DisplacementL"))
    if displacement:
        parts.append(f"{displacement}L")
    cylinders = _clean(results.get("EngineCylinders"))
    if cylinders:
        config = _clean(results.get("EngineConfiguration")) or ""
        parts.append(f"{config}{cylinders}".strip() or f"{cylinders} cyl")
    if not parts:
        return None
    return " ".join(parts)


async def decode_vin(vin: str) -> dict:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(VPIC_URL.format(vin=vin))
        response.raise_for_status()
        data = response.json()

    results = (data.get("Results") or [{}])[0]
    model_year = _clean(results.get("ModelYear"))
    error_code = _clean(results.get("ErrorCode"))
    decoded = bool(_clean(results.get("Make")) and model_year)

    return {
        "vin": vin,
        "decoded": decoded,
        "make": _clean(results.get("Make")),
        "model": _clean(results.get("Model")),
        "year": int(model_year) if model_year and model_year.isdigit() else None,
        "trim": _clean(results.get("Trim")),
        "body_class": _clean(results.get("BodyClass")),
        "fuel_type": _map_fuel(results.get("FuelTypePrimary", "")),
        "engine": _engine_label(results),
        "vehicle_type": _clean(results.get("VehicleType")),
        "message": _clean(results.get("ErrorText"))
        if error_code not in (None, "0")
        else None,
    }

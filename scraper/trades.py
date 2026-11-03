"""Which trades a building permit is likely to create work for.

The permit report says what is being built, not who needs to be hired, so
these are inferred from permit type, building use, work class and declared
value. They are leads, not facts: each match carries a short reason so a
reader can judge it. Rules are deliberately plain so they can be edited
without touching code elsewhere.
"""

NEW_BUILD_TYPES = {
    "Single/Semi-Detached Dwelling 1-2 units",
    "Multi-Unit Dwelling 3+ Units",
    "New Commercial",
    "Backyard/Laneway Suite",
}
RESIDENTIAL_FIT_OUT = {"Secondary Suite", "Basement Development"}
COMMERCIAL_USES = {"Commercial", "Institutional", "Industrial"}


def _cost(p: dict) -> float:
    return p.get("Estimated Cost of Construction") or 0


def _new_build(p: dict) -> bool:
    return p["Permit Application Type"] in NEW_BUILD_TYPES


def _commercial(p: dict) -> bool:
    return p.get("Building Use") in COMMERCIAL_USES


def _is_fit_out(p: dict) -> bool:
    return p["Permit Application Type"] in ("Renovation/Alteration", "Addition") and _commercial(p)


def electrical(p):
    if _new_build(p):
        return "New building: full electrical service and wiring"
    if p["Permit Application Type"] in RESIDENTIAL_FIT_OUT:
        return "Suite or basement build-out: new circuits and panel work"
    if _is_fit_out(p) and _cost(p) >= 50_000:
        return "Commercial renovation: lighting, power and panel work likely"
    if p["Permit Application Type"] == "Addition" and _cost(p) >= 50_000:
        return "Addition: new wiring"
    return None


def commercial_cleaning(p):
    if not _commercial(p):
        return None
    t = p["Permit Application Type"]
    if (t == "New Commercial" or p.get("Work Class") in ("Superstructure or part of new building", "Foundation (new)")) and _cost(p) >= 100_000:
        return "New commercial building: post-construction clean and then a janitorial contract"
    if t == "Multi-Unit Dwelling 3+ Units":
        return "New multi-unit building: final clean and common-area contract"
    if _is_fit_out(p) and _cost(p) >= 100_000:
        return "Non-residential renovation or addition: post-construction clean, and a possible new occupant to service"
    return None


def hvac(p):
    if _new_build(p):
        return "New building: heating, cooling and ventilation"
    if p["Permit Application Type"] in RESIDENTIAL_FIT_OUT:
        return "Suite or basement build-out: heating and ventilation"
    if _is_fit_out(p) and _cost(p) >= 100_000:
        return "Commercial renovation: mechanical changes likely"
    if p.get("Work Class") == "Mechanical":
        return "Mechanical permit"
    return None


def roofing(p):
    if _new_build(p):
        return "New building: roof system"
    if p["Permit Application Type"] == "Addition" and _cost(p) >= 100_000:
        return "Addition: roof tie-in"
    return None


def concrete(p):
    if _new_build(p) or p.get("Work Class") == "Foundation (new)":
        return "New building: footings, foundation and slab"
    if p["Permit Application Type"] == "Garage/Carport" and _cost(p) >= 20_000:
        return "Garage: slab and footings"
    if p["Permit Application Type"] in ("Addition", "Pool") and _cost(p) >= 50_000:
        return "Concrete for new foundation or pool shell"
    return None


def signage(p):
    if p["Permit Application Type"] == "New Commercial":
        return "New commercial building: tenant and building signs"
    if _is_fit_out(p) and p.get("Building Use") == "Commercial" and _cost(p) >= 50_000:
        return "Commercial renovation: likely new or rebranded tenant"
    return None


def security(p):
    if p["Permit Application Type"] == "New Commercial":
        return "New commercial building: alarm, access control, cameras"
    if p["Permit Application Type"] == "Multi-Unit Dwelling 3+ Units" and _cost(p) >= 1_000_000:
        return "New multi-unit building: access control and cameras"
    if _is_fit_out(p) and _commercial(p) and _cost(p) >= 150_000:
        return "Commercial renovation: system upgrade likely"
    return None


def insurance(p):
    if _new_build(p) and _cost(p) >= 1_000_000:
        return "Large new build: builders' risk, then commercial property cover"
    if _commercial(p) and _cost(p) >= 500_000:
        return "Large commercial project: coverage review for owner and tenants"
    return None


TRADES = {
    "electrical": {"label": "Electrical", "rule": electrical},
    "commercial-cleaning": {"label": "Commercial cleaning", "rule": commercial_cleaning},
    "hvac": {"label": "HVAC", "rule": hvac},
    "roofing": {"label": "Roofing", "rule": roofing},
    "concrete": {"label": "Concrete", "rule": concrete},
    "signage": {"label": "Signage", "rule": signage},
    "security": {"label": "Security systems", "rule": security},
    "insurance": {"label": "Insurance brokers", "rule": insurance},
}


def trades_for(permit: dict) -> dict[str, str]:
    """{trade_key: reason} for every trade the permit is a lead for."""
    out = {}
    for key, spec in TRADES.items():
        reason = spec["rule"](permit)
        if reason:
            out[key] = reason
    return out

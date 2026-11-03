"""Keep businesses, drop individuals.

The Building Permit Report's `Name` column mixes contractors, corporate
owners and private individuals (the City redacts some owner names but not
all). This project sells intelligence about properties and businesses, not
people, so a name is only kept when it reads as a business. Everything else
becomes null; the rule errs toward dropping.

Names can hold several parts ("COLBY KIRKPATRICK - PACESETTER HOMES",
"GRAHAM CONSTRUCTION - TYSON SNIDER | GRAHAM DESIGN BUILDERS LP"). Each part
is judged separately and only business parts are kept.
"""
import re

BUSINESS_WORDS = [
    "LTD", "LIMITED", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "COMPANIES",
    "LP", "LLP", "ULC", "GP", "REIT", "HOMES", "HOME", "CONSTRUCTION", "CONSTRUCTIONS", "CONTRACTING",
    "CONTRACTORS", "CONTRACTOR", "BUILDERS", "BUILDER", "BUILDING", "DEVELOPMENT", "DEVELOPMENTS",
    "DEVELOPERS", "ELECTRIC", "ELECTRICAL", "PLUMBING", "HEATING", "COOLING", "MECHANICAL",
    "ROOFING", "RENOVATIONS", "RENOVATION", "RENOS", "ENTERPRISES", "ENTERPRISE", "SERVICES",
    "SERVICE", "GROUP", "HOLDINGS", "PROPERTIES", "PROPERTY", "ASSOCIATION", "SOCIETY", "CHURCH",
    "SCHOOL", "DIVISION", "CITY OF", "PROVINCE", "GOVERNMENT", "CROWN", "UNIVERSITY", "REALTY",
    "INVESTMENTS", "MANAGEMENT", "INDUSTRIES", "SYSTEMS", "SOLUTIONS", "DESIGN", "DESIGNS",
    "CONCRETE", "FOUNDATION", "FOUNDATIONS", "EXCAVATING", "EXCAVATION", "DEMOLITION", "TRENCHING",
    "LANDSCAPING", "SIGNS", "SIGN", "SECURITY", "CLEANING", "RESTORATION", "RESTORATIONS",
    "SASKATCHEWAN", "REGINA", "SASK", "CREDIT UNION", "BANK", "HOTEL", "CENTRE", "CENTER", "CLUB",
    "TRUST", "STORAGE", "SUPPLY", "SUPPLIES", "WINDOWS", "FLOORING", "PAINTING", "DRYWALL",
    "INSULATION", "STEEL", "ENGINEERING", "ARCHITECTS", "ARCHITECTURE", "PARTNERSHIP",
    "COOPERATIVE", "CO-OP", "SHOP", "CARPENTRY", "INTERIORS", "ENCLOSURES", "SUNROOMS", "RENTALS",
    "COMMUNITIES", "VENTURES", "IMPROVEMENTS", "FINISHING", "LEISURESCAPES", "CABINETS", "ALLIANCE",
    "ARMY", "COUNCIL", "CONDOMINIUM", "SPRAY FOAM", "PAVING", "FENCING", "DECKS", "DECK", "GLASS",
    "HANDYMAN", "REMODELING", "LEVELING", "BRACING", "STUCCO", "TILE", "MASONRY", "WELDING",
]
_WORD_RE = re.compile(
    r"(?<![A-Z0-9])(" + "|".join(re.escape(w) for w in sorted(BUSINESS_WORDS, key=len, reverse=True)) + r")(?![A-Z0-9])"
)
_KEEP_UPPER = {"LP", "LLP", "ULC", "GP", "REIT", "PCL", "HVAC", "RSR", "BMO", "DKM", "HRC", "JS", "BTA",
               "KBF", "SWC", "AFE", "SDM", "II", "III", "IV", "NW", "SW", "NE", "SE", "SK", "SGI"}


def _smart_title(text: str) -> str:
    out = []
    for token in text.split(" "):
        core = token.strip(".,")
        if core in {"LTD", "INC", "CORP", "CO"}:
            out.append(token.capitalize())
        elif core in _KEEP_UPPER or (len(core) <= 3 and core.isalpha() and not re.search("[AEIOUY]", core)):
            out.append(token)
        elif re.match(r"^\d", token):
            out.append(token)
        else:
            out.append(token.capitalize() if token.isupper() else token)
    return " ".join(out)


# Professional corporations (vets, doctors, realtors, lawyers...) are named after
# the individual, so they are treated as individuals and dropped.
_PROFESSIONAL_RE = re.compile(r"(?<![A-Z0-9])(P\.?\s?C\.?|PROFESSIONAL|DVM|D\.V\.M\.?|DR\.?|MD|M\.D\.|BARRISTER|CPA|C\.P\.A\.)(?=[\s,.]|$)")


def business_name(raw: str | None) -> str | None:
    if not raw:
        return None
    name = re.sub(r"\s+", " ", str(raw)).strip().upper()
    if not name or name == "REDACTED":
        return None

    kept: list[str] = []
    for segment in re.split(r"\s*\|\s*", name):
        for part in re.split(r"\s+-\s+|\s+/\s+", segment):
            part = part.strip()
            if not part or part in {"CONTRACTOR", "OWNER", "AGENT"}:
                continue
            if _PROFESSIONAL_RE.search(part):
                continue
            if _WORD_RE.search(part.replace(".", "")) or re.match(r"^\d{5,}", part):
                if part not in kept:
                    kept.append(part)
    if not kept:
        return None
    return " | ".join(_smart_title(p) for p in kept)

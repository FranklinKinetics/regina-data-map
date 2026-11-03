"""Hard verifier checks. Each raises VerificationError on failure.

A run's new data is only committed as the latest snapshot if every check
here passes — "did it run" is not enough, these confirm the data is sound.
"""

MIN_ROW_COUNT_RATIO = 0.5  # new pull must be at least half of the previous pull's size
MIN_GEOCODE_SUCCESS_RATE = 0.95


class VerificationError(Exception):
    pass


def check_no_duplicate_keys(keys: list, label: str) -> None:
    seen = set()
    dupes = set()
    for k in keys:
        if k in seen:
            dupes.add(k)
        seen.add(k)
    if dupes:
        raise VerificationError(f"{label}: duplicate keys found: {sorted(dupes)[:10]}")


def check_not_suspicious_drop(new_count: int, previous_count: int | None, label: str) -> None:
    if previous_count is None or previous_count == 0:
        return
    if new_count < previous_count * MIN_ROW_COUNT_RATIO:
        raise VerificationError(
            f"{label}: new count ({new_count}) is less than "
            f"{MIN_ROW_COUNT_RATIO:.0%} of previous count ({previous_count}) "
            "— looks like a truncated or partial fetch"
        )


def check_proposed_development_entries(entries: list[dict]) -> None:
    """Structural check for the hand-authored Proposed Development page.

    This source has no stable row count to compare against (the list is
    small and applications age off as they're resolved, so a ratio-based
    drop check would false-positive constantly) -- the real failure mode
    here is the city restructuring the page and the parser silently
    getting nothing, or getting rows with missing required fields.
    """
    if not entries:
        raise VerificationError(
            "Proposed Development: parsed zero entries. Either the list is "
            "genuinely empty or the city changed the page structure -- check "
            "the parser against the live page before trusting this."
        )
    for e in entries:
        missing = [
            f for f in ("File Number", "Address", "Application Type") if not e.get(f)
        ]
        if missing:
            raise VerificationError(
                f"Proposed Development: entry missing required field(s) {missing}: {e}"
            )


MAX_YEAR_OVER_YEAR_CHANGE = 0.3  # generous -- real rent/population growth here hit ~9%/11%


def check_time_series_entries(entries: list[dict], required_fields: list[str], label: str) -> None:
    """Structural check for an annual time-series source (population,
    rental market): every entry must have its key metric(s) present -- a
    None here means the source's page/table structure changed and the
    parser silently missed a column, not that the value is genuinely absent.
    """
    if not entries:
        raise VerificationError(f"{label}: parsed zero entries.")
    for e in entries:
        missing = [f for f in required_fields if e.get(f) is None]
        if missing:
            raise VerificationError(f"{label}: entry missing required field(s) {missing}: {e}")


def check_no_wild_swing(entries: list[dict], field: str, label: str) -> None:
    """Flag an implausible year-over-year jump/drop in an annual metric --
    catches a parsing bug (e.g. misaligned columns) producing a nonsense
    value, not real-world volatility (checked against real data first: nothing
    here moves anywhere near this threshold in a genuine year)."""
    by_year = sorted((e["Year"], e[field]) for e in entries if e.get(field) is not None)
    for (year_a, value_a), (year_b, value_b) in zip(by_year, by_year[1:]):
        if value_a == 0:
            continue
        change = abs(value_b - value_a) / abs(value_a)
        if change > MAX_YEAR_OVER_YEAR_CHANGE:
            raise VerificationError(
                f"{label}: {field} moved {change:.0%} between {year_a} ({value_a}) and "
                f"{year_b} ({value_b}) -- beyond the {MAX_YEAR_OVER_YEAR_CHANGE:.0%} "
                "sanity threshold, looks like a parsing error rather than real change"
            )


def check_reconciles_to_source(row_count: int, cost_total: float, source_meta: dict, label: str) -> None:
    """After geocoding/joining/privacy filtering, the permit count and total
    declared construction value must still equal what the source files
    contained for the same window -- i.e. the pipeline neither dropped nor
    invented permits, and no join multiplied rows."""
    if row_count != source_meta["rows_in_window"]:
        raise VerificationError(
            f"{label}: output has {row_count} permits but the source window had "
            f"{source_meta['rows_in_window']}"
        )
    if abs(cost_total - source_meta["cost_total_in_window"]) > 1:
        raise VerificationError(
            f"{label}: output cost total {cost_total:,.0f} differs from source "
            f"{source_meta['cost_total_in_window']:,.0f}"
        )


def check_geocode_success_rate(addresses: list[str], geocoded: dict) -> None:
    if not addresses:
        return
    success = sum(1 for a in addresses if geocoded.get(a) is not None)
    rate = success / len(addresses)
    if rate < MIN_GEOCODE_SUCCESS_RATE:
        raise VerificationError(
            f"Geocode success rate {rate:.1%} is below the "
            f"{MIN_GEOCODE_SUCCESS_RATE:.0%} threshold "
            f"({success}/{len(addresses)} addresses resolved)"
        )

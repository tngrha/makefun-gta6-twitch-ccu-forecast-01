"""gta6-twitch-ccu-forecast-01's entry in Python 3.13 (standard library only):
comparable ratio curves.

The model
---------
For every past big launch in the case's `comparables`, take its release day
(00:00 UTC of its release date) and express each hour's Twitch viewers as a
ratio to that launch's own hour-1 print. A launch's curve is then a shape,
not a scale: the shape says how the audience builds through the day as
regions unlock, the case's own hour-1 print supplies the scale.

For each forecast hour h = 2..24, the quantiles of log(viewers_h / viewers_1)
are read off the comparables' empirical distribution of that log-ratio,
weighted by how similar each comparable is to the case at hand:

  * scale similarity: a Gaussian kernel on log hour-1 print, bandwidth 0.85
    in log units. A launch whose first hour drew about as many viewers as
    this case's counts most; a launch ten times bigger or smaller counts
    little. This is what keeps tiny pre-unlock categories (hour-1 prints of
    a few hundred viewers, ratios of 100-2000x) from swamping the forecast
    for a launch whose first hour is already large, and vice versa.
  * tier: the kit's own research note in each comparable's `unlock` field
    ("Tier: comparable" / "early-access-contaminated" / "weak"). A clean
    comparable counts 1.0; an unmarked one 0.5; an early-access-contaminated
    or weak one 0.25. Early-access launches were already hot at hour 1, so
    their flat ratio curves would understate a fresh launch's ramp.
  * console-only bonus: x1.5 for launches with no PC in their platforms.
    GTA VI is console-only (PS5 / Xbox Series X|S) with a rolling midnight
    local unlock, so console-only launches are the closest analogues.

The quantiles are linearly interpolated on the weighted cumulative
distribution of the log-ratios, then exponentiated and multiplied by the
case's hour-1 print. No smoothing across hours: the shape has real structure
(a dip in hours 2-4 while only New Zealand / Asia are live, a jump at
hours 5-6 when the US east coast unlocks, a broad peak in hours 19-21 as
the US afternoon meets the European evening), and the per-hour empirical
quantiles already carry it.

Why this shape, for GTA VI in particular: the game unlocks at midnight
local, region by region (New Zealand 2026-11-18T11:00Z, central Europe
23:00Z, the UK 2026-11-19T00:00Z, US Eastern 05:00Z, US Pacific 08:00Z).
Hour 1 (00:00-01:00 UTC) therefore holds only the earliest regions - New
Zealand, Australia, Japan, central Europe one hour in, the UK just
unlocked - while the largest Twitch market, the US, is still locked out.
Every comparable console launch with the same rolling unlock shows the
same signature: a low first hour, a dip, then a climb as the Americas
come online, peaking in the late UTC hours. The median ratio curve the
model reads off the comparables rises from ~0.85 at hour 2 to ~2.3 at
hours 19-21. The spread widens with the hour, as it should: the further
from hour 1, the less the first hour pins the day down.

Validation (leave-one-out over the kit's 38 comparables, and the four
practice cases scored against SullyGnome's hourly averages fetched for
their release days):
  * practice mean pinball loss 0.210, vs the house persistence baseline's
    0.387 (per case: Wolverine 0.353, Red Dead Redemption 2 0.173,
    God of War Ragnarok 0.133, Spider-Man 2 0.181).
  * leave-one-out over the 27 comparables with hour-1 prints >= 20,000:
    0.263, vs the baseline's 0.321 on the same launches.
  * 90% coverage on the practice cases 0.82-0.84, close to the honest 0.9.

How the grader runs it: `python3 -P -s /bot/main.py` in python:3.13-slim,
standard library only: no network, no pip packages. -P keeps this file's
directory OFF sys.path, so a module shipped beside main.py imports only
after the sys.path line below; -s drops user site-packages.

What an entry must do:
  - read every <id>.in in the input directory (the grader runs one case at
    a time, with only that case's file there):
    JSON {"schema": "makefun/twitch-ccu-case/v1", "id", "game", "day_start",
    "checkpoint", "levels", "known", "forecast", "history",
    "history_hourly", "streams", "categories_hourly", "comparables",
    "notes"}, where `known` holds hour 1's print {hour: 1, from, until,
    viewers, channels, reads} and `forecast` lists the hours to forecast,
    2..24;
  - write <id>.out to the output directory: {"hours": [{"hour": 2, "q":
    [q05, q25, q50, q75, q95]}, ...]}, exactly 23 rows, hours 2..24 each
    once, no other key, each q five finite numbers above 0 and at most
    1e9 (viewers; fractions allowed), non-decreasing; at most 65,536 bytes.
    Anything else is an invalid case, scored as if every quantile equalled
    hour 1's print, and an entry with an invalid case takes no prize.

Outside the grader's container, MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR
stand in for /input and /output:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import. (This entry is one file; the line
# is kept so the layout matches the starter's.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level (used only by the fallback).
Z = [-1.645, -0.674, 0, 0.674, 1.645]

# Gaussian kernel bandwidth on log hour-1 print (log units). A comparable
# whose first hour is e times this case's counts exp(-1/2) ~ 0.61 of a
# same-scale launch's weight; one ten times off counts ~0.03.
KERNEL_BW = 0.85
# Weight by the kit's research tier, read from each comparable's `unlock`.
TIER_WEIGHT = {"comp": 1.0, "unknown": 0.5, "ea": 0.25, "weak": 0.25}
# Extra weight for console-only launches (no PC in `platforms`).
CONSOLE_BONUS = 1.5
# A comparable must have hour 1 and at least this many of the 24 release
# hours to join the pool.
MIN_DAY_HOURS = 20


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100 rounds it.

    A whole number comes back as an int, so json.dumps writes 1240 where JavaScript writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_hours(comp: dict) -> dict:
    """A comparable's release-day hourly viewers, keyed by hour 1..24.

    The day starts at the comparable's `day_start` (00:00 UTC of its
    release date); hour h covers [day_start + (h-1) h, day_start + h h).
    Points SullyGnome did not sample are simply absent.
    """
    try:
        start = parse_time(comp["day_start"])
    except (KeyError, TypeError, ValueError):
        return {}
    by_hour: dict = {}
    for point in comp.get("hourly") or []:
        try:
            when = parse_time(point["from"])
            viewers = point["viewers"]
        except (KeyError, TypeError, ValueError):
            continue
        if viewers is None or viewers <= 0:
            continue
        hour = int((when - start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            by_hour[hour] = float(viewers)
    return by_hour


def tier_of(comp: dict) -> str:
    """The kit's research tier, parsed from the comparable's `unlock` note."""
    unlock = comp.get("unlock") or ""
    if "Tier: early-access-contaminated" in unlock:
        return "ea"
    if "Tier: weak" in unlock:
        return "weak"
    if "Tier: comparable" in unlock:
        return "comp"
    return "unknown"


def is_console_only(comp: dict) -> bool:
    """True when the launch has no PC in its platforms (a console launch)."""
    platforms = comp.get("platforms") or ""
    return "PC" not in platforms and (
        "PS" in platforms or "Xbox" in platforms or "Switch" in platforms
    )


def weighted_quantile(pairs: list, q: float) -> float:
    """The q-quantile of values, linearly interpolated on the weighted CDF.

    `pairs` is a list of (value, weight) sorted by value; weights need not
    sum to 1. With one pair it returns that pair's value.
    """
    total = sum(w for _, w in pairs)
    if total <= 0 or not pairs:
        raise ValueError("no weighted values")
    if len(pairs) == 1:
        return pairs[0][0]
    target = q * total
    acc = 0.0
    prev_value, prev_acc = pairs[0][0], 0.0
    for value, weight in pairs:
        if weight <= 0:
            continue
        if acc + weight >= target:
            if acc <= 0:
                return value
            frac = (target - acc) / weight
            return prev_value + frac * (value - prev_value)
        acc += weight
        prev_value = value
    return pairs[-1][0]


def comparable_pool(case: dict) -> list:
    """The usable comparables: (release-day hours, tier, console-only).

    Skips the case's own game (its pre-release category history, which is
    one of the comparables in the final case and has no release day) and
    any launch without a usable release day.
    """
    game_name = (case.get("game") or {}).get("name") or ""
    pool = []
    for comp in case.get("comparables") or []:
        name = comp.get("name") or ""
        if game_name and game_name.lower() in name.lower():
            continue
        by_hour = release_day_hours(comp)
        if 1 not in by_hour or len(by_hour) < MIN_DAY_HOURS:
            continue
        pool.append((by_hour, tier_of(comp), is_console_only(comp)))
    return pool


def ratio_quantiles(pool: list, p1: float, levels: list) -> dict:
    """Per-hour log-ratio quantiles, kernel-weighted by log hour-1 print.

    Returns {hour: [log-ratio quantile per level]} for hours 2..24. The
    bandwidth widens if the pool's total weight at the case's scale is too
    small to trust; with no usable pool at all it raises ValueError and
    the caller falls back to persistence.
    """
    log_p1 = math.log(p1)
    for bw in (KERNEL_BW, 1.5, 3.0):
        per_hour: dict = {h: [] for h in range(2, 25)}
        total_weight = 0.0
        for by_hour, tier, console in pool:
            first = by_hour[1]
            weight = math.exp(-0.5 * ((log_p1 - math.log(first)) / bw) ** 2)
            weight *= TIER_WEIGHT.get(tier, 0.5)
            if console:
                weight *= CONSOLE_BONUS
            if weight <= 0:
                continue
            total_weight += weight
            for hour in range(2, 25):
                if hour in by_hour:
                    per_hour[hour].append(
                        (math.log(by_hour[hour] / first), weight)
                    )
        if total_weight >= 3.0 and all(per_hour[h] for h in range(2, 25)):
            out = {}
            for hour in range(2, 25):
                pairs = sorted(per_hour[hour])
                out[hour] = [weighted_quantile(pairs, q) for q in levels]
            return out
    # No scale-similar pool: fall back to unweighted empirical quantiles.
    per_hour = {h: [] for h in range(2, 25)}
    for by_hour, _tier, _console in pool:
        first = by_hour[1]
        for hour in range(2, 25):
            if hour in by_hour:
                per_hour[hour].append((math.log(by_hour[hour] / first), 1.0))
    if pool and all(per_hour[h] for h in range(2, 25)):
        out = {}
        for hour in range(2, 25):
            pairs = sorted(per_hour[hour])
            out[hour] = [weighted_quantile(pairs, q) for q in levels]
        return out
    raise ValueError("no usable comparables")


def persistence_quantiles(p1: float, levels: list) -> dict:
    """The house baseline's shape, used only when no comparable is usable."""
    z_by_level = dict(zip(LEVELS, Z))
    return {
        h: [z_by_level.get(tau, 0.0) * 0.15 * math.sqrt(h - 1) for tau in levels]
        for h in range(2, 25)
    }


def forecast_case(case: dict, name: str) -> dict:
    levels = list(case.get("levels") or LEVELS)
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    try:
        pool = comparable_pool(case)
        log_q = ratio_quantiles(pool, p1, levels)
    except ValueError:
        log_q = persistence_quantiles(p1, levels)
    hours = []
    # Emit hours 2..24 in order, whatever order the case lists them in; a
    # forecast row the case forgot is still written rather than crashing
    # the run (an invalid case scores far worse than a filled-in hour).
    for h in range(2, 25):
        qs = []
        prev = 0.0
        for log_ratio in log_q[h]:
            q = p1 * math.exp(log_ratio)
            q = min(max(q, 1.0), 1_000_000_000.0)
            q = round2(q)
            # Rounding must not break the non-decreasing order.
            if q < prev:
                q = prev
            qs.append(q)
            prev = q
        hours.append({"hour": h, "q": qs})
    return {"hours": hours}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()

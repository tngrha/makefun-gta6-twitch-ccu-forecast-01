# Comparable Ratio Curves — GTA VI launch-day Twitch viewers, hour by hour

Forecasts how many people watch Grand Theft Auto VI live on Twitch in each
hour of its release day (2026-11-19 UTC), as five quantiles per hour, from
everything recorded up to the end of hour 1. One file, `main.py`, Python 3.13
standard library only, no network, deterministic.

## The model

For every past big launch in the case's `comparables`, take its release day
(00:00 UTC of its release date) and express each hour's Twitch viewers as a
ratio to that launch's own hour-1 print. A launch's curve becomes a *shape*,
not a scale: the shape says how the audience builds through the day as
regions unlock; the case's own hour-1 print supplies the scale.

For each forecast hour h = 2..24, the quantiles of log(viewers_h / viewers_1)
are read off the comparables' empirical distribution of that log-ratio,
weighted by how similar each comparable is to the case at hand:

- **Scale similarity** — a Gaussian kernel on log hour-1 print, bandwidth
  0.85 in log units. A launch whose first hour drew about as many viewers as
  this case's counts most; one ten times bigger or smaller counts little.
  This is what keeps tiny pre-unlock categories (hour-1 prints of a few
  hundred viewers, ratios of 100–2000×) from swamping the forecast for a
  launch whose first hour is already large, and vice versa.
- **Tier** — the kit's own research note in each comparable's `unlock`
  field (`Tier: comparable` / `early-access-contaminated` / `weak`). A clean
  comparable counts 1.0, an unmarked one 0.5, an early-access-contaminated
  or weak one 0.25. Early-access launches were already hot at hour 1, so
  their flat ratio curves would understate a fresh launch's ramp.
- **Console-only bonus** — ×1.5 for launches with no PC in their
  platforms. GTA VI is console-only (PS5 / Xbox Series X|S) with a rolling
  midnight-local unlock, so console-only launches are the closest analogues.

The quantiles are linearly interpolated on the weighted cumulative
distribution of the log-ratios, then exponentiated and multiplied by the
case's hour-1 print. No smoothing across hours: the shape has real structure
and the per-hour empirical quantiles already carry it. If no comparable is
usable at the case's scale, the bandwidth widens, then the model falls back
to unweighted empirical quantiles, then to the house persistence baseline.

## Why the curve ramps: the unlock

GTA VI unlocks at midnight local, region by region — New Zealand
2026-11-18T11:00Z, central Europe 23:00Z, the UK 2026-11-19T00:00Z, US
Eastern 05:00Z, US Pacific 08:00Z. Hour 1 (00:00–01:00 UTC) therefore holds
only the earliest regions — New Zealand, Australia, Japan, central Europe
one hour in, the UK just unlocked — while the largest Twitch market, the US,
is still locked out. Every comparable console launch with the same rolling
unlock shows the same signature: a low first hour, a dip in hours 2–4,
a jump at hours 5–6 when the US east coast unlocks, then a climb to a broad
peak in hours 19–21 as the US afternoon meets the European evening. The
median ratio curve the model reads off the comparables rises from ~0.85 at
hour 2 to ~2.3 at hours 19–21. The spread widens with the hour, as it
should: the further from hour 1, the less the first hour pins the day down.

## Validation

Measured two ways, both against the same pinball loss on the log scale the
contest scores:

- **Practice cases, scored against the real answers.** The four practice
  launches' release-day hourly averages were fetched from SullyGnome (the
  kit's own source; the hour-1 prints match the case files exactly) and the
  entry was run on the kit's practice inputs. Mean pinball loss **0.210**,
  vs the house persistence baseline's **0.387** on the same cases.
  Per case: Marvel's Wolverine 0.353, Red Dead Redemption 2 0.173,
  God of War Ragnarök 0.133, Marvel's Spider-Man 2 0.181. Typical miss
  19–28% on three of the four (84% on Wolverine, the smallest launch);
  90% coverage 0.78–1.00.
- **Leave-one-out over the comparables.** Hold one launch out, build the
  ratio curves from the rest, forecast its release day from its hour-1
  print, score against its actual hours 2–24. Over the 27 comparables with
  hour-1 prints ≥ 20,000 (the scale GTA VI will be at): mean loss **0.263**,
  vs the baseline's **0.321** on the same launches.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

All four practice cases produce valid `.out` files in ~0.2 s total, and two
runs are byte-identical.

## Files

- `main.py` — the whole entry (stdlib only)
- `LICENSE` — MIT (the kit starter's licence)
- `.makefun/owner.json` — the wallet that owns this entry

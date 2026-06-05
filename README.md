# Compute Spot Index

Compute Spot Index is a small public data page that tracks graphics processor rental prices and translates them into rough AI data center economics.

The core question is simple: if public spot markets price scarce AI compute at several dollars per graphics processor-hour, what does that imply about the value of dedicated data center capacity?

Live page: https://chiragmirani.github.io/compute-spot-index/

## What The Page Shows

- Median rental price per graphics processor-hour
- Annual rental revenue for a 100,000-processor site
- Annual surplus after scaled total annualized data center costs
- Estimated present value of 10-year surplus using a 10%-15% discount rate
- A cost analogy using Epoch AI's one-gigawatt AI data center cost estimate

The valuation hook uses B300 prices when available, and otherwise falls back to B200.

## Data Sources

- Vast.ai Search Offers API for public rental-market prices
- Epoch AI, 'Frontier Data Centers'. Published online at epoch.ai. Retrieved from 'https://epoch.ai/data/data-centers' [online resource].
- Amelia Michael and Ben Cottier (2026), "Servers account for 60% of the total cost of ownership of a one-gigawatt AI data center". Published online at epoch.ai. Retrieved from 'https://epoch.ai/data-insights/ai-datacenter-cost-breakdown' [online resource]. Accessed 20 May 2026.

## Methodology

The public page uses the latest saved snapshot in `data/latest-public.json`.

For each graphics processor type:

```text
annual surplus after total annualized costs =
median hourly rental price * 100,000 processors * 8,760 hours * 65% utilization
- scaled total annualized data center costs
```

Scaled total annualized costs use Epoch AI's one-gigawatt annual cost model. The model includes annualized capital costs for servers, facility, network infrastructure, utility works, and land, plus operating costs for energy, taxes, maintenance, labor, and water. The one-gigawatt total is about $8.5 billion per year; scaled to a 120-megawatt proxy site, this is about $1.0 billion per year.

Present value is calculated on annual surplus after total annualized costs over 10 years using discount rates from 10% to 15%.

## Caveats

These are public spot-market prices, not hyperscaler procurement costs or net margins. The calculation uses a stylized annualized cost stack rather than site-specific electricity, maintenance, staffing, tax, construction, networking, and procurement contracts. It still excludes downtime, hardware replacement timing beyond Epoch's stylized lifespans, and the risk that rental prices fall as graphics processor supply expands.

## Local Live Refresh

The public GitHub Pages version is static. To refresh the Vast.ai data locally:

```powershell
cd C:\Users\chira\Desktop\sports\datascience\vast-gpu-price-tracker
$env:VAST_API_KEY="your-key-here"
C:\Users\chira\anaconda3\python.exe server.py
```

Then open:

```text
http://127.0.0.1:8788
```

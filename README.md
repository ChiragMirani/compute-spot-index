# Compute Spot Index

Compute Spot Index is a small public data page that tracks graphics processor rental prices and translates them into rough AI data center economics.

The core question is simple: if public spot markets price scarce AI compute at several dollars per graphics processor-hour, what does that imply about the value of dedicated data center capacity?

Live page: https://chiragmirani.github.io/compute-spot-index/

## What The Page Shows

- Median rental price per graphics processor-hour
- Annual gross rental-market value for a 100,000-processor site
- Estimated present value over 10 years using a 10%-15% discount rate
- A cost analogy using Epoch AI's one-gigawatt AI data center cost estimate

## Data Sources

- Vast.ai Search Offers API for public rental-market prices
- Epoch AI, 'Frontier Data Centers'. Published online at epoch.ai. Retrieved from 'https://epoch.ai/data/data-centers' [online resource].
- Epoch AI data insight: "We estimate the cost breakdown for 60% of the total cost of ownership of a one-gigawatt AI data center"

## Methodology

The public page uses the latest saved snapshot in `data/latest-public.json`.

For each graphics processor type:

```text
annual gross value =
median hourly rental price * 100,000 processors * 8,760 hours * 65% utilization
```

Present value is calculated over 10 years using discount rates from 10% to 15%.

## Caveats

These are public spot-market prices, not hyperscaler procurement costs or net margins. The calculation excludes electricity, maintenance, financing, networking, downtime, taxes, hardware replacement, and the risk that rental prices fall as graphics processor supply expands.

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

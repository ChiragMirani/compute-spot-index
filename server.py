from __future__ import annotations

import json
import os
import statistics
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "snapshots.jsonl"
LATEST_PATH = DATA_DIR / "latest.json"
VAST_BUNDLES_URL = "https://console.vast.ai/api/v0/bundles/"
RUNTIME_API_KEY = ""

GPU_QUERIES = [
    {"label": "B300", "queries": ["B300", "GB300"]},
    {"label": "B200", "queries": ["B200"]},
    {"label": "H100 SXM", "queries": ["H100 SXM", "H100 SXM5"]},
    {"label": "H100 NVL", "queries": ["H100 NVL"]},
    {"label": "A100 80GB", "queries": ["A100 SXM4", "A100 PCIE"], "min_vram_gb": 75},
    {"label": "A100 40GB", "queries": ["A100 SXM4", "A100 PCIE"], "max_vram_gb": 60},
    {"label": "RTX 5090", "queries": ["RTX 5090"]},
]


def get_api_key() -> str:
    key = (RUNTIME_API_KEY or os.environ.get("VAST_API_KEY", "")).strip()
    if key:
        return key
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('VAST_API_KEY','User')"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def vast_request(body: dict, api_key: str) -> dict:
    raw = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        VAST_BUNDLES_URL,
        data=raw,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_offers_for_gpu(gpu: dict, api_key: str) -> list[dict]:
    normalized = []
    seen_ids = set()
    for query in gpu["queries"]:
        body = {
            "rentable": {"eq": True},
            "gpu_name": {"eq": query},
            "type": "ondemand",
            "order": [["dph_total", "asc"]],
            "limit": 200,
        }
        response = vast_request(body, api_key)
        offers = response.get("offers") or response.get("results") or []
        for offer in offers:
            offer_id = offer.get("id") or offer.get("ask_contract_id") or offer.get("bundle_id")
            if offer_id in seen_ids or not keep_offer(offer, gpu):
                continue
            seen_ids.add(offer_id)
            normalized.append(normalize_offer(offer))
    return sorted(normalized, key=lambda offer: offer.get("price_per_hour") or 1e9)


def keep_offer(offer: dict, gpu: dict) -> bool:
    vram = first_number(offer, ["gpu_ram", "gpu_total_ram", "gpu_vram", "gpu_mem"], divisor=1024)
    reliability = first_number(offer, ["reliability2", "reliability", "host_reliability"])
    gpu_fraction = first_number(offer, ["gpu_frac"], divisor=1)
    if reliability is not None and reliability <= 1:
        reliability *= 100
    if reliability is not None and reliability < 90:
        return False
    if gpu_fraction is not None and gpu_fraction < 0.99:
        return False
    if gpu.get("min_vram_gb") is not None and vram is not None and vram < gpu["min_vram_gb"]:
        return False
    if gpu.get("max_vram_gb") is not None and vram is not None and vram > gpu["max_vram_gb"]:
        return False
    return True


def normalize_offer(offer: dict) -> dict:
    total_price = first_number(offer, ["dph_total", "dph_base", "price_gpu", "min_bid"])
    gpu_count = first_number(offer, ["num_gpus"], divisor=1) or 1
    price = total_price / gpu_count if total_price is not None else None
    reliability = first_number(offer, ["reliability2", "reliability", "host_reliability"])
    if reliability is not None and reliability <= 1:
        reliability *= 100
    return {
        "id": offer.get("id") or offer.get("ask_contract_id") or offer.get("bundle_id"),
        "gpu_name": offer.get("gpu_name") or offer.get("gpu_display_name"),
        "price_per_hour": price,
        "gpu_count": gpu_count,
        "total_price_per_hour": total_price,
        "reliability": reliability,
        "dlperf": first_number(offer, ["dlperf", "dlperf_per_dphtotal"]),
        "vram_gb": first_number(offer, ["gpu_ram", "gpu_total_ram", "gpu_vram", "gpu_mem"], divisor=1024),
        "region": offer.get("geolocation") or offer.get("country") or offer.get("location"),
        "machine_id": offer.get("machine_id"),
    }


def first_number(offer: dict, keys: list[str], divisor: float = 1.0) -> float | None:
    for key in keys:
        value = offer.get(key)
        if value is None:
            continue
        try:
            return float(value) / divisor
        except (TypeError, ValueError):
            continue
    return None


def summarize_offers(label: str, offers: list[dict]) -> dict:
    prices = sorted(offer["price_per_hour"] for offer in offers if offer.get("price_per_hour") is not None)
    reliabilities = sorted(offer["reliability"] for offer in offers if offer.get("reliability") is not None)
    return {
        "gpu": label,
        "offers": len(offers),
        "min_price": prices[0] if prices else None,
        "median_price": statistics.median(prices) if prices else None,
        "p25_price": percentile(prices, 0.25),
        "p75_price": percentile(prices, 0.75),
        "median_reliability": statistics.median(reliabilities) if reliabilities else None,
        "sample_offers": offers[:8],
    }


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    idx = round((len(values) - 1) * pct)
    return values[idx]


def collect_snapshot() -> dict:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("Set VAST_API_KEY in PowerShell before refreshing Vast.ai prices.")

    rows = []
    errors = []
    for gpu in GPU_QUERIES:
        try:
            offers = fetch_offers_for_gpu(gpu, api_key)
            rows.append(summarize_offers(gpu["label"], offers))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as exc:
            rows.append(summarize_offers(gpu["label"], []))
            errors.append({"gpu": gpu["label"], "error": str(exc)})

    snapshot = {
        "timestamp": now_iso(),
        "source": "Vast.ai Search Offers API",
        "assumptions": {
            "rentable": True,
            "price_basis": "per full graphics processor-hour",
            "minimum_host_reliability": "90%",
            "rental_type": "ondemand",
        },
        "rows": rows,
        "errors": errors,
    }
    DATA_DIR.mkdir(exist_ok=True)
    LATEST_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    with SNAPSHOT_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(snapshot) + "\n")
    return snapshot


def load_history() -> dict:
    if not SNAPSHOT_PATH.exists():
        return {"snapshots": []}
    snapshots = []
    for line in SNAPSHOT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        snapshots.append(
            {
                "timestamp": item.get("timestamp"),
                "rows": [
                    {
                        "gpu": row.get("gpu"),
                        "min_price": row.get("min_price"),
                        "median_price": row.get("median_price"),
                        "offers": row.get("offers"),
                    }
                    for row in item.get("rows", [])
                ],
            }
        )
    return {"snapshots": snapshots[-90:]}


def latest_or_refresh() -> dict:
    latest = read_json(LATEST_PATH, {})
    if not get_api_key():
        if latest:
            latest["refresh_error"] = "VAST_API_KEY is not set for this server process."
            return latest
        sample = sample_payload()
        sample["refresh_error"] = "VAST_API_KEY is not set for this server process."
        return sample
    timestamp = latest.get("timestamp")
    if timestamp:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)
            if age < timedelta(hours=20):
                return latest
        except ValueError:
            pass
    try:
        return collect_snapshot()
    except Exception as exc:  # noqa: BLE001 - keep the public page useful offline
        if latest:
            latest["refresh_error"] = str(exc)
            return latest
        sample = sample_payload()
        sample["refresh_error"] = str(exc)
        return sample


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.serve_file(ROOT / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/api/latest":
            params = parse_qs(parsed.query)
            try:
                if params.get("refresh", ["0"])[0] == "1":
                    payload = collect_snapshot()
                elif params.get("auto", ["0"])[0] == "1":
                    payload = latest_or_refresh()
                else:
                    payload = read_json(LATEST_PATH, sample_payload())
                self.write_json(payload)
            except Exception as exc:  # noqa: BLE001 - return readable local API errors
                self.write_json({"error": str(exc), "sample": sample_payload()}, status=400)
            return
        if parsed.path == "/api/history":
            self.write_json(load_history())
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/key":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            api_key = str(payload.get("apiKey", "")).strip()
            if len(api_key) < 20:
                self.write_json({"error": "API key looks too short."}, status=400)
                return
            global RUNTIME_API_KEY
            RUNTIME_API_KEY = api_key
            self.write_json({"ok": True, "message": "Key stored in memory for this local server session."})
        except Exception as exc:  # noqa: BLE001
            self.write_json({"error": str(exc)}, status=400)

    def serve_file(self, path: Path, content_type: str) -> None:
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def write_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def sample_payload() -> dict:
    return {
        "timestamp": "2026-06-05T16:36:10+00:00",
        "source": "Saved Vast.ai Search Offers API snapshot",
        "assumptions": {
            "rentable": True,
            "price_basis": "per full graphics processor-hour",
            "minimum_host_reliability": "90%",
            "rental_type": "ondemand",
            "site_size": "100,000 graphics processors",
            "utilization": "65%",
            "discount_rate": "10%-15%",
            "horizon": "10 years",
        },
        "rows": [
            {"gpu": "B300", "offers": 7, "median_price": 6.000185185185186},
            {"gpu": "B200", "offers": 11, "median_price": 6.238390313390314},
            {"gpu": "H100 SXM", "offers": 4, "median_price": 2.0005555555555556},
            {"gpu": "H100 NVL", "offers": 3, "median_price": 2.575555555555555},
            {"gpu": "A100 80GB", "offers": 16, "median_price": 1.0674074074074074},
            {"gpu": "A100 40GB", "offers": 12, "median_price": 1.0685185185185184},
            {"gpu": "RTX 5090", "offers": 72, "median_price": 0.9608796296296298},
        ],
        "errors": [],
    }


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8788), Handler)
    print("Vast GPU Price Tracker: http://127.0.0.1:8788")
    server.serve_forever()

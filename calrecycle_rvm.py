import requests, csv, json, sys, time
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

SESSION_URL  = "https://www2.calrecycle.ca.gov/BevContainer/RecyclingCenters"
GRID_URL     = "https://www2.calrecycle.ca.gov/BevContainer/RecyclingCenters/_RCLocatorGridData"
DETAIL_URL   = "https://www2.calrecycle.ca.gov/BevContainer/RecyclingCenters/Details"
OUTPUT_CSV   = "calrecycle_rvm.csv"
OUTPUT_JSON  = "calrecycle_rvm.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": SESSION_URL,
}

# ── Step 1: Get all AccountLocationIDs from grid ─────────────────────────────
print("Step 1: Seeding session...")
session = requests.Session()
session.headers.update({"User-Agent": HEADERS["User-Agent"]})
seed = session.get(SESSION_URL, timeout=30)
print(f"  Seed: {seed.status_code}  cookies={list(session.cookies.keys())}")

print("Step 1b: Fetching grid data (all centers)...")
grid_headers = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}
payload = {
    "sort": "RecyclingLocationName-asc",
    "page": "1", "pageSize": "5000",
    "group": "", "filter": "",
    "hasMap": "false", "searchString": "",
}
r = session.post(GRID_URL, data=payload, headers=grid_headers, timeout=60)
print(f"  Grid response: {r.status_code}  length={len(r.text)}  CT={r.headers.get('Content-Type')}")

if not r.text.strip():
    print("  Grid returned empty — trying hasMap=true...")
    payload["hasMap"] = "true"
    r = session.post(GRID_URL, data=payload, headers=grid_headers, timeout=60)
    print(f"  Retry: {r.status_code}  length={len(r.text)}")

if not r.text.strip():
    print("ERROR: Grid still empty. Cannot continue.")
    sys.exit(1)

data = r.json()
centers = data.get("Data") or data.get("data") or (data if isinstance(data, list) else [])
print(f"  Total centers: {len(centers)}")
if not centers:
    print("  No centers found. Raw:", r.text[:300])
    sys.exit(1)

# Extract IDs — try common field names
sample = centers[0]
print(f"  Fields: {list(sample.keys())}")
id_field = None
for f in ["AccountLocationID", "accountLocationID", "LocationId", "Id", "ID"]:
    if f in sample:
        id_field = f
        break
if not id_field:
    print(f"  Can't find ID field. Sample: {json.dumps(sample, indent=2)[:500]}")
    sys.exit(1)
print(f"  Using ID field: {id_field}")

ids = [c[id_field] for c in centers if c.get(id_field)]
print(f"  Got {len(ids)} IDs to scrape")

# ── Step 2: Scrape detail pages ───────────────────────────────────────────────
print(f"\nStep 2: Scraping {len(ids)} detail pages (threaded, 10 workers)...")

def scrape_detail(loc_id):
    try:
        url = f"{DETAIL_URL}?AccountLocationID={loc_id}"
        r = session.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Find "Reverse Vending Machines:" label and get the next text
        rvm = None
        for b in soup.find_all("b"):
            if "Reverse Vending" in b.text:
                # Value is the next sibling text
                sibling = b.next_sibling
                if sibling:
                    rvm = sibling.strip()
                break
        
        # Also grab name, address, city, zip, phone while we're here
        name = soup.find("h1")
        name = name.text.replace("Recycling Center Details for", "").strip() if name else ""
        
        return {
            "AccountLocationID": loc_id,
            "Name": name,
            "HasRVM": rvm,
            "URL": url,
        }
    except Exception as e:
        return {"AccountLocationID": loc_id, "HasRVM": None, "Error": str(e)}

results = []
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(scrape_detail, lid): lid for lid in ids}
    for i, future in enumerate(as_completed(futures)):
        results.append(future.result())
        if (i+1) % 50 == 0:
            print(f"  Scraped {i+1}/{len(ids)}...")

print(f"  Done scraping. Total results: {len(results)}")

# Filter RVM=Yes
rvm_centers = [r for r in results if (r.get("HasRVM") or "").strip().lower() == "yes"]
print(f"  Centers with RVM=Yes: {len(rvm_centers)}")

# Sample of what we got
print(f"  Sample result: {results[0] if results else 'none'}")
print(f"  RVM values seen: {set(r.get('HasRVM') for r in results[:20])}")

if not rvm_centers:
    print("  No RVM centers found. Check HasRVM values above.")
    # Save all results anyway for debugging
    with open("calrecycle_all.json", "w") as f:
        json.dump(results[:50], f, indent=2)
    sys.exit(1)

# ── Step 3: Save outputs ──────────────────────────────────────────────────────
fields = list(rvm_centers[0].keys())
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rvm_centers)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rvm_centers, f, indent=2)

print(f"\n✅ Done! Saved {len(rvm_centers)} RVM centers → {OUTPUT_CSV}")

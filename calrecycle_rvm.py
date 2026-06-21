import requests, csv, json, sys
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://www2.calrecycle.ca.gov"
SESSION_URL = f"{BASE}/BevContainer/RecyclingCenters"
GRID_URL    = f"{BASE}/BevContainer/RecyclingCenters/_RCLocatorGridData"
DETAIL_URL  = f"{BASE}/BevContainer/RecyclingCenters/Details"
OUTPUT_CSV  = "calrecycle_rvm.csv"
OUTPUT_JSON = "calrecycle_rvm.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": SESSION_URL,
}

session = requests.Session()
session.headers.update({"User-Agent": HEADERS["User-Agent"]})

print("Seeding session...")
seed = session.get(SESSION_URL, timeout=30)
print(f"  Seed: {seed.status_code}  cookies={list(session.cookies.keys())}")

# Use GET with RCLocatorGrid- prefixed params
print("Fetching grid data via GET...")
params = {
    "RCLocatorGrid-sort": "RecyclingLocationName-asc",
    "RCLocatorGrid-page": "1",
    "RCLocatorGrid-pageSize": "5000",
    "RCLocatorGrid-group": "",
    "RCLocatorGrid-filter": "",
}
r = session.get(GRID_URL, params=params, headers=HEADERS, timeout=60)
print(f"  Response: {r.status_code}  length={len(r.text)}  CT={r.headers.get('Content-Type')}")
print(f"  Raw (first 300): {r.text[:300]}")

if not r.text.strip() or "json" not in r.headers.get("Content-Type", ""):
    print("Still empty — trying without prefix...")
    params2 = {
        "sort": "RecyclingLocationName-asc",
        "page": "1",
        "pageSize": "5000",
        "group": "",
        "filter": "",
    }
    r = session.get(GRID_URL, params=params2, headers=HEADERS, timeout=60)
    print(f"  Retry: {r.status_code}  length={len(r.text)}")
    print(f"  Raw (first 300): {r.text[:300]}")

if not r.text.strip():
    print("ERROR: Grid still empty.")
    sys.exit(1)

data = r.json()
centers = data.get("Data") or data.get("data") or (data if isinstance(data, list) else [])
print(f"Total centers: {len(centers)}")
if centers:
    print(f"Fields: {list(centers[0].keys())}")

if not centers:
    sys.exit(1)

# Find ID field
id_field = next((f for f in ["AccountLocationID","LocationId","Id","ID"] if f in centers[0]), None)
print(f"ID field: {id_field}")
ids = [c[id_field] for c in centers if c.get(id_field)]
print(f"Got {len(ids)} IDs. Sample: {ids[:5]}")

# Scrape detail pages
print(f"\nScraping {len(ids)} detail pages...")

def scrape(loc_id):
    try:
        r = session.get(f"{DETAIL_URL}?AccountLocationID={loc_id}", timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        h1 = soup.find("h1")
        if not h1 or "Details for" not in h1.text:
            return None
        name = h1.text.replace("Recycling Center Details for", "").strip()
        rvm = None
        for b in soup.find_all("b"):
            if "Reverse Vending" in b.text:
                sib = b.next_sibling
                if sib:
                    rvm = sib.strip()
                break
        return {"AccountLocationID": loc_id, "Name": name, "HasRVM": rvm}
    except:
        return None

results = []
with ThreadPoolExecutor(max_workers=15) as ex:
    futures = {ex.submit(scrape, i): i for i in ids}
    for n, f in enumerate(as_completed(futures)):
        r = f.result()
        if r:
            results.append(r)
        if (n+1) % 100 == 0:
            print(f"  {n+1}/{len(ids)} checked, {len(results)} valid so far...")

rvm_centers = [r for r in results if (r.get("HasRVM") or "").strip().lower() == "yes"]
print(f"\nTotal valid centers: {len(results)}  RVM=Yes: {len(rvm_centers)}")
print(f"RVM values seen: {set(r.get('HasRVM') for r in results[:30])}")

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["AccountLocationID","Name","HasRVM"])
    w.writeheader()
    w.writerows(rvm_centers)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rvm_centers, f, indent=2)

print(f"✅ Saved {len(rvm_centers)} RVM centers.")

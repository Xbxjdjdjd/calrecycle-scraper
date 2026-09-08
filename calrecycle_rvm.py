import requests, csv, json, sys
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE        = "https://www2.calrecycle.ca.gov"
SESSION_URL = f"{BASE}/BevContainer/RecyclingCenters"
GRID_URL    = f"{BASE}/BevContainer/RecyclingCenters/_RCLocatorGridData"
DETAIL_URL  = f"{BASE}/BevContainer/RecyclingCenters/Details"
OUTPUT_CSV  = "calrecycle_rvm.csv"
OUTPUT_JSON = "calrecycle_rvm.json"

# All 58 California counties (IDs from the page source dropdown)
COUNTY_IDS = list(range(1, 59))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": SESSION_URL,
    "Origin": BASE,
}

session = requests.Session()
session.headers.update({"User-Agent": HEADERS["User-Agent"]})

print("Seeding session...")
seed = session.get(SESSION_URL, timeout=30)
print(f"  Seed: {seed.status_code}  cookies={list(session.cookies.keys())}")

# Test with county 1 (Alameda) first
print("\nTesting with CountyID=1 (Alameda)...")
test_payload = {
    "sort": "RecyclingLocationName-asc",
    "page": "1", "pageSize": "500",
    "group": "", "filter": "",
    "CountyID": "1",
    "searchString": "",
}
r = session.post(GRID_URL, data=test_payload, headers=HEADERS, timeout=30)
print(f"  Status: {r.status_code}  length={len(r.text)}  CT={r.headers.get('Content-Type')}")
print(f"  Raw (first 200): {r.text[:200]}")

if not r.text.strip():
    # Try with hasMap and CountyID
    print("  Empty — trying with hasMap=false and CountyID...")
    test_payload["hasMap"] = "false"
    r = session.post(GRID_URL, data=test_payload, headers=HEADERS, timeout=30)
    print(f"  Status: {r.status_code}  length={len(r.text)}")
    print(f"  Raw: {r.text[:200]}")

if not r.text.strip():
    # Try GET with CountyID
    print("  Still empty — trying GET with CountyID...")
    r = session.get(GRID_URL, params=test_payload, headers=HEADERS, timeout=30)
    print(f"  GET Status: {r.status_code}  length={len(r.text)}")
    print(f"  Raw: {r.text[:200]}")

if not r.text.strip():
    print("ERROR: Still empty. Printing all cookies and headers for debugging:")
    print(f"  Cookies: {dict(session.cookies)}")
    sys.exit(1)

# If we got data, parse it
data = r.json()
centers = data.get("Data") or data.get("data") or (data if isinstance(data, list) else [])
print(f"\n✅ Got {len(centers)} centers for Alameda county!")
if centers:
    print(f"Fields: {list(centers[0].keys())}")
    print(f"Sample: {json.dumps(centers[0], indent=2)[:400]}")

# Now fetch all counties
print(f"\nFetching all 58 counties...")
all_centers = []
working_payload = {k: v for k, v in test_payload.items()}

for county_id in COUNTY_IDS:
    working_payload["CountyID"] = str(county_id)
    working_payload["page"] = "1"
    working_payload["pageSize"] = "1000"
    try:
        if r.request.method == "GET":
            resp = session.get(GRID_URL, params=working_payload, headers=HEADERS, timeout=30)
        else:
            resp = session.post(GRID_URL, data=working_payload, headers=HEADERS, timeout=30)
        if resp.text.strip():
            d = resp.json()
            c = d.get("Data") or d.get("data") or (d if isinstance(d, list) else [])
            all_centers.extend(c)
            print(f"  County {county_id}: {len(c)} centers")
        else:
            print(f"  County {county_id}: empty")
    except Exception as e:
        print(f"  County {county_id}: error {e}")

print(f"\nTotal centers across all counties: {len(all_centers)}")
id_field = next((f for f in ["AccountLocationID","LocationId","Id","ID"] if f in (all_centers[0] if all_centers else {})), None)
print(f"ID field: {id_field}")

if not id_field or not all_centers:
    sys.exit(1)

# Deduplicate
seen = set()
unique_centers = []
for c in all_centers:
    cid = c.get(id_field)
    if cid not in seen:
        seen.add(cid)
        unique_centers.append(c)
print(f"Unique centers: {len(unique_centers)}")
ids = [c[id_field] for c in unique_centers]
print(f"Sample IDs: {ids[:10]}")

# Scrape detail pages for RVM status
print(f"\nScraping {len(ids)} detail pages for RVM status...")

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
        r2 = f.result()
        if r2:
            results.append(r2)
        if (n+1) % 100 == 0:
            print(f"  {n+1}/{len(ids)} done, {len(results)} valid...")

rvm_centers = [r for r in results if (r.get("HasRVM") or "").strip().lower() == "yes"]
print(f"\nTotal valid: {len(results)}  RVM=Yes: {len(rvm_centers)}")

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["AccountLocationID","Name","HasRVM"])
    w.writeheader()
    w.writerows(rvm_centers)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rvm_centers, f, indent=2)

print(f"✅ Saved {len(rvm_centers)} RVM centers.")

# VERSION: COOKIE-HARVEST-V1
import requests, csv, json, sys
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE       = "https://www2.calrecycle.ca.gov"
DETAIL_URL = f"{BASE}/BevContainer/RecyclingCenters/Details"
OUTPUT_CSV  = "calrecycle_rvm.csv"
OUTPUT_JSON = "calrecycle_rvm.json"

ID_START = 1
ID_END   = 60000

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})

def scrape(loc_id):
    try:
        r = session.get(f"{DETAIL_URL}?AccountLocationID={loc_id}", timeout=15)
        if r.status_code != 200 or "Details for" not in r.text:
            return None
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
        # Grab address and phone too while we're here
        text = soup.get_text(" ", strip=True)
        return {"AccountLocationID": loc_id, "Name": name, "HasRVM": rvm}
    except:
        return None

print(f"Scanning IDs {ID_START}-{ID_END} with 25 workers...")
all_centers = []
rvm_centers = []
checked = 0

with ThreadPoolExecutor(max_workers=25) as ex:
    futures = {ex.submit(scrape, i): i for i in range(ID_START, ID_END + 1)}
    for future in as_completed(futures):
        result = future.result()
        checked += 1
        if result:
            all_centers.append(result)
            if (result.get("HasRVM") or "").strip().lower() == "yes":
                rvm_centers.append(result)
        if checked % 1000 == 0:
            print(f"  {checked}/{ID_END - ID_START} checked | {len(all_centers)} centers found | {len(rvm_centers)} RVM=Yes")

print(f"\nDone! {len(all_centers)} valid centers, {len(rvm_centers)} with RVM=Yes")

if not rvm_centers:
    print("No RVM centers found. Sample of what we got:")
    print(json.dumps(all_centers[:5], indent=2))
    with open("calrecycle_all_sample.json", "w") as f:
        json.dump(all_centers[:50], f, indent=2)
    sys.exit(1)

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["AccountLocationID", "Name", "HasRVM"])
    w.writeheader()
    w.writerows(rvm_centers)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rvm_centers, f, indent=2)

print(f"✅ Saved {len(rvm_centers)} RVM centers → {OUTPUT_CSV}")

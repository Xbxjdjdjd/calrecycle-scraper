import requests, csv, json, sys
from bs4 import BeautifulSoup

SESSION_URL = "https://www2.calrecycle.ca.gov/BevContainer/RecyclingCenters"
DATA_URL    = "https://www2.calrecycle.ca.gov/BevContainer/RecyclingCenters/_RCLocatorGridData"

PAYLOAD = {
    "sort": "RecyclingLocationName-asc",
    "page": "1", "pageSize": "5000",
    "group": "", "filter": "",
    "hasMap": "true", "searchString": "",
}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"})

print("Seeding session...")
seed = session.get(SESSION_URL, timeout=30)
print(f"Seed: {seed.status_code}  cookies={list(session.cookies.keys())}")

# Try to find CSRF token
token = None
soup = BeautifulSoup(seed.text, "html.parser")
tag = soup.find("input", {"name": "__RequestVerificationToken"})
if tag:
    token = tag["value"]
    print(f"Got CSRF token: {token[:20]}...")
else:
    print("No CSRF token found in page HTML")

# Try WITHOUT token first — server returned 200 but empty body last time,
# meaning the request got through but something in the payload was wrong
headers = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": SESSION_URL,
    "Origin": "https://www2.calrecycle.ca.gov",
}

print("\n--- Attempt 1: No token, pageSize=100 (small test) ---")
test_payload = {**PAYLOAD, "pageSize": "100"}
r = session.post(DATA_URL, data=test_payload, headers=headers, timeout=60)
print(f"Status: {r.status_code}  Content-Type: {r.headers.get('Content-Type')}")
print(f"Body length: {len(r.text)} chars")
print(f"Raw response (first 500 chars):\n{r.text[:500]}")

if r.text.strip() and "json" in r.headers.get("Content-Type", ""):
    print("\n✅ Got JSON! Parsing...")
    data = r.json()
    records = data.get("Data") or data.get("data") or (data if isinstance(data, list) else [])
    print(f"Records: {len(records)}")
    if records:
        print(f"Fields: {list(records[0].keys())}")
        rvm = [x for x in records if x.get("HasReverseVendingMachine") is True]
        print(f"RVM centers in sample: {len(rvm)}")

        # Now do full pull
        print("\n--- Full pull: pageSize=5000 ---")
        full_payload = {**PAYLOAD, "pageSize": "5000"}
        r2 = session.post(DATA_URL, data=full_payload, headers=headers, timeout=60)
        data2 = r2.json()
        all_records = data2.get("Data") or data2.get("data") or []
        rvm_all = [x for x in all_records if x.get("HasReverseVendingMachine") is True]
        print(f"Total records: {len(all_records)}  RVM centers: {len(rvm_all)}")

        fields = list(rvm_all[0].keys()) if rvm_all else list(all_records[0].keys())
        with open("calrecycle_rvm.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rvm_all)
        with open("calrecycle_rvm.json", "w", encoding="utf-8") as f:
            json.dump(rvm_all, f, indent=2)
        print(f"✅ Saved {len(rvm_all)} RVM centers.")
else:
    print("\n❌ Still empty or non-JSON. Server may require different parameters.")
    print("Trying with hasMap=false...")
    r3 = session.post(DATA_URL, data={**test_payload, "hasMap": "false"}, headers=headers, timeout=60)
    print(f"Status: {r3.status_code}  Body length: {len(r3.text)}")
    print(f"Raw: {r3.text[:500]}")


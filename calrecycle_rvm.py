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

token = None
soup = BeautifulSoup(seed.text, "html.parser")
tag = soup.find("input", {"name": "__RequestVerificationToken"})
if tag:
    token = tag["value"]
    print(f"Got CSRF token: {token[:20]}...")
    PAYLOAD["__RequestVerificationToken"] = token

headers = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": SESSION_URL,
    "Origin": "https://www2.calrecycle.ca.gov",
}
if token:
    headers["RequestVerificationToken"] = token

print("POSTing to grid endpoint...")
r = session.post(DATA_URL, data=PAYLOAD, headers=headers, timeout=60)
print(f"Response: {r.status_code}  Content-Type: {r.headers.get('Content-Type')}")

if "json" not in r.headers.get("Content-Type", ""):
    print("ERROR: Got non-JSON response:")
    print(r.text[:1000])
    sys.exit(1)

data = r.json()
records = data.get("Data") or data.get("data") or (data if isinstance(data, list) else [])
print(f"Total records: {len(records)}")

if records:
    print(f"Fields: {list(records[0].keys())}")

rvm = [x for x in records if x.get("HasReverseVendingMachine") is True]
print(f"RVM centers: {len(rvm)}")

if not rvm:
    print("No RVM=true records found. Dumping sample:")
    print(json.dumps(records[:2], indent=2))
    sys.exit(1)

fields = list(rvm[0].keys())
with open("calrecycle_rvm.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rvm)

with open("calrecycle_rvm.json", "w", encoding="utf-8") as f:
    json.dump(rvm, f, indent=2)

print(f"Done! Saved {len(rvm)} RVM centers.")

import requests, csv, json, sys
from bs4 import BeautifulSoup

SESSION_URL = "https://www2.calrecycle.ca.gov/BevContainer/RecyclingCenters"
DATA_URL    = "https://www2.calrecycle.ca.gov/BevContainer/RecyclingCenters/_RCLocatorGridData"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"})

print("Seeding session...")
seed = session.get(SESSION_URL, timeout=30)
print(f"Seed: {seed.status_code}  cookies={list(session.cookies.keys())}")

# Print page HTML snippet to find any hidden form fields
soup = BeautifulSoup(seed.text, "html.parser")
print("\n--- All hidden inputs on seed page ---")
for inp in soup.find_all("input", {"type": "hidden"}):
    print(f"  name={inp.get('name')}  value={str(inp.get('value',''))[:40]}")

print("\n--- All forms on seed page ---")
for form in soup.find_all("form"):
    print(f"  action={form.get('action')}  method={form.get('method')}")

base_headers = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": SESSION_URL,
    "Origin": "https://www2.calrecycle.ca.gov",
}

# Try multiple payload variations
payloads = [
    ("Kendo default (original)", {
        "sort": "RecyclingLocationName-asc",
        "page": "1", "pageSize": "25",
        "group": "", "filter": "",
        "hasMap": "true", "searchString": "",
    }),
    ("No hasMap param", {
        "sort": "RecyclingLocationName-asc",
        "page": "1", "pageSize": "25",
        "group": "", "filter": "",
        "searchString": "",
    }),
    ("Completely empty payload", {}),
    ("Just page and pageSize", {
        "page": "1", "pageSize": "25",
    }),
    ("camelCase variants", {
        "Sort": "RecyclingLocationName-asc",
        "Page": "1", "PageSize": "25",
        "Group": "", "Filter": "",
    }),
]

working_payload = None
for label, payload in payloads:
    print(f"\n--- Trying: {label} ---")
    r = session.post(DATA_URL, data=payload, headers=base_headers, timeout=30)
    print(f"  Status: {r.status_code}  Body length: {len(r.text)}  CT: {r.headers.get('Content-Type','?')}")
    if r.text.strip():
        print(f"  Response: {r.text[:300]}")
        working_payload = (label, payload, r)
        break

if not working_payload:
    print("\n❌ All payload variations returned empty. Printing seed page HTML for inspection:")
    print(seed.text[:3000])
    sys.exit(1)

label, payload, r = working_payload
print(f"\n✅ Working payload: {label}")
data = r.json()
records = data.get("Data") or data.get("data") or (data if isinstance(data, list) else [])
print(f"Records: {len(records)}")
if records:
    print(f"Fields: {list(records[0].keys())}")
    rvm = [x for x in records if x.get("HasReverseVendingMachine") is True]
    print(f"RVM in sample: {len(rvm)}")

    # Full pull
    payload["pageSize"] = "5000"
    r2 = session.post(DATA_URL, data=payload, headers=base_headers, timeout=60)
    data2 = r2.json()
    all_records = data2.get("Data") or data2.get("data") or []
    rvm_all = [x for x in all_records if x.get("HasReverseVendingMachine") is True]
    print(f"\nFull pull: {len(all_records)} total, {len(rvm_all)} RVM centers")

    fields = list(rvm_all[0].keys()) if rvm_all else list(all_records[0].keys())
    with open("calrecycle_rvm.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rvm_all)
    with open("calrecycle_rvm.json", "w", encoding="utf-8") as f:
        json.dump(rvm_all, f, indent=2)
    print(f"✅ Saved {len(rvm_all)} RVM centers to CSV and JSON.")

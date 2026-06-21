from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import json, csv, time

URL = "https://www2.calrecycle.ca.gov/BevContainer/RecyclingCenters"

print("Starting headless Chrome...")
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

driver = webdriver.Chrome(options=options)

print(f"Loading {URL}...")
driver.get(URL)
time.sleep(5)

# Get cookies from the seeded session to use in our fetch call
cookies = driver.get_cookies()
cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
print(f"Session cookies: {[c['name'] for c in cookies]}")

# Use the page's own jQuery/fetch to make the POST from within the page context
# This way it inherits all session state, headers, tokens automatically
print("Triggering _RCLocatorGridData via in-page fetch...")
result = driver.execute_script("""
    return new Promise((resolve) => {
        $.ajax({
            url: '/BevContainer/RecyclingCenters/_RCLocatorGridData',
            method: 'POST',
            data: {
                sort: 'RecyclingLocationName-asc',
                page: 1,
                pageSize: 5000,
                group: '',
                filter: '',
                hasMap: 'true',
                searchString: ''
            },
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            success: function(data) { resolve({ok: true, data: data}); },
            error: function(xhr, status, err) {
                resolve({ok: false, status: xhr.status, text: xhr.responseText.substring(0, 500), err: err});
            }
        });
    });
""")

print(f"Ajax result ok={result.get('ok')}")

if not result.get('ok'):
    print(f"Ajax failed: status={result.get('status')} err={result.get('err')}")
    print(f"Response text: {result.get('text')}")
    driver.quit()
    exit(1)

data = result.get('data')
if isinstance(data, str):
    data = json.loads(data)

records = data.get("Data") or data.get("data") or (data if isinstance(data, list) else [])
print(f"Total records: {len(records)}")
if records:
    print(f"Fields: {list(records[0].keys())}")

rvm = [r for r in records if r.get("HasReverseVendingMachine") is True]
print(f"RVM centers: {len(rvm)}")

if not rvm:
    print("No RVM=true. Sample:", json.dumps(records[0], indent=2)[:500] if records else "empty")
    driver.quit()
    exit(1)

fields = list(rvm[0].keys())
with open("calrecycle_rvm.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rvm)

with open("calrecycle_rvm.json", "w", encoding="utf-8") as f:
    json.dump(rvm, f, indent=2)

print(f"\n✅ Done! Saved {len(rvm)} RVM centers.")
driver.quit()

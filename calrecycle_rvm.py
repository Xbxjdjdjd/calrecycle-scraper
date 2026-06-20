from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json, csv, time

URL = "https://www2.calrecycle.ca.gov/BevContainer/RecyclingCenters"

print("Starting headless Chrome...")
options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
driver = webdriver.Chrome(options=options)

# Intercept all XHR/fetch responses via Chrome DevTools Protocol
driver.execute_cdp_cmd("Network.enable", {})

captured = []

def response_received(response):
    url = response.get("response", {}).get("url", "")
    if "_RCLocatorGridData" in url:
        request_id = response["requestId"]
        captured.append(request_id)

driver.add_listener("Network.responseReceived", response_received)

print(f"Loading {URL}...")
driver.get(URL)

# Wait for the Kendo grid to load (it fires the POST automatically on page load)
print("Waiting for grid to populate...")
try:
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".k-grid-content tr"))
    )
    print("Grid rows appeared!")
except:
    print("Timed out waiting for grid rows — trying to proceed anyway")

time.sleep(3)  # Extra buffer for XHR to complete

# Extract data via JavaScript execution — read directly from the Kendo grid datasource
print("Extracting data from Kendo grid datasource...")
records = driver.execute_script("""
    try {
        var grid = $(".k-grid").data("kendoGrid");
        if (!grid) return {error: "No Kendo grid found"};
        var ds = grid.dataSource;
        if (!ds) return {error: "No dataSource"};
        var data = ds.data();
        if (!data || data.length === 0) return {error: "DataSource empty", total: ds.total()};
        return data.toJSON ? data.toJSON() : JSON.parse(JSON.stringify(data));
    } catch(e) {
        return {error: e.toString()};
    }
""")

print(f"Raw result type: {type(records)}")

if isinstance(records, dict) and "error" in records:
    print(f"Grid extract error: {records}")
    # Fallback: scrape visible rows from the DOM
    print("Falling back to DOM scrape...")
    rows = driver.execute_script("""
        var rows = [];
        document.querySelectorAll('.k-grid-content tr[role=row]').forEach(function(tr) {
            var cells = tr.querySelectorAll('td');
            rows.push(Array.from(cells).map(function(td){ return td.innerText.trim(); }));
        });
        return rows;
    """)
    print(f"DOM rows found: {len(rows)}")
    print("First 3 rows:", rows[:3])
    driver.quit()
    exit(1)

print(f"Total records from grid: {len(records)}")
if records:
    print(f"Fields: {list(records[0].keys())}")

rvm = [r for r in records if r.get("HasReverseVendingMachine") is True]
print(f"RVM centers: {len(rvm)}")

if not rvm:
    print("No RVM=true found. Checking field names...")
    sample = records[0] if records else {}
    rvm_keys = [k for k in sample if "vend" in k.lower() or "rvm" in k.lower() or "machine" in k.lower()]
    print(f"RVM-related fields: {rvm_keys}")
    print("Sample record:", json.dumps(sample, indent=2)[:500])
    driver.quit()
    exit(1)

fields = list(rvm[0].keys())
with open("calrecycle_rvm.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rvm)

with open("calrecycle_rvm.json", "w", encoding="utf-8") as f:
    json.dump(rvm, f, indent=2)

print(f"\n✅ Saved {len(rvm)} RVM centers to calrecycle_rvm.csv and calrecycle_rvm.json")
driver.quit()

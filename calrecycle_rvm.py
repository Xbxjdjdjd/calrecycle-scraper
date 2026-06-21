from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

# Type a broad search and click the map search button (id=mapSearch)
print("Filling in location and clicking map search...")
try:
    location_input = driver.find_element(By.ID, "Location")
    location_input.clear()
    location_input.send_keys("CA")
    print("Typed 'CA' into location field")
except Exception as e:
    print(f"Couldn't fill location: {e}")

try:
    search_btn = driver.find_element(By.ID, "mapSearch")
    driver.execute_script("arguments[0].click();", search_btn)
    print("Clicked mapSearch button")
except Exception as e:
    print(f"Couldn't click mapSearch: {e}")

print("Waiting 15s for grid XHR to fire...")
time.sleep(15)

# Scan performance logs for the grid call
print("Scanning network logs for _RCLocatorGridData...")
logs = driver.get_log("performance")
grid_request_id = None
for entry in logs:
    msg = json.loads(entry["message"])["message"]
    if msg.get("method") == "Network.responseReceived":
        url = msg["params"]["response"]["url"]
        if "_RCLocatorGridData" in url:
            grid_request_id = msg["params"]["requestId"]
            print(f"Found it! request_id={grid_request_id}")

if not grid_request_id:
    print("Still no grid XHR. All CalRecycle URLs seen after click:")
    for entry in logs:
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") == "Network.responseReceived":
            url = msg["params"]["response"]["url"]
            if "calrecycle" in url.lower():
                print(f"  {url}")
    driver.quit()
    exit(1)

body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": grid_request_id})
grid_response = json.loads(body["body"])
records = grid_response.get("Data") or grid_response.get("data") or (grid_response if isinstance(grid_response, list) else [])
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

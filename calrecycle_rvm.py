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
# Spoof a real browser to avoid bot detection
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

driver = webdriver.Chrome(options=options)

print(f"Loading {URL}...")
driver.get(URL)

# Give the page plenty of time to load and fire XHRs
print("Waiting 15s for page JS to run...")
time.sleep(15)

# Print page title and any console errors
print(f"Page title: {driver.title}")

# Check what's actually on the page
html_snippet = driver.execute_script("return document.body.innerHTML.substring(0, 2000)")
print(f"Body snippet:\n{html_snippet}")

# Scan performance logs for the grid data XHR
print("\nScanning network logs for _RCLocatorGridData response...")
logs = driver.get_log("performance")
grid_response = None
for entry in logs:
    msg = json.loads(entry["message"])["message"]
    if msg.get("method") == "Network.responseReceived":
        url = msg["params"]["response"]["url"]
        if "_RCLocatorGridData" in url:
            request_id = msg["params"]["requestId"]
            print(f"Found grid request! ID={request_id} URL={url}")
            # Get the response body
            try:
                body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                grid_response = json.loads(body["body"])
                print(f"Got response body! Keys: {list(grid_response.keys()) if isinstance(grid_response, dict) else 'list'}")
            except Exception as e:
                print(f"Error getting body: {e}")

if not grid_response:
    print("Grid XHR not found in logs. All XHR URLs seen:")
    for entry in logs:
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") == "Network.responseReceived":
            url = msg["params"]["response"]["url"]
            if "calrecycle" in url.lower() or "bevcon" in url.lower():
                print(f"  {url}")
    driver.quit()
    exit(1)

records = grid_response.get("Data") or grid_response.get("data") or (grid_response if isinstance(grid_response, list) else [])
print(f"\nTotal records: {len(records)}")
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

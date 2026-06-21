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

# Print all buttons and links to find the search trigger
print("Buttons on page:")
buttons = driver.find_elements(By.TAG_NAME, "button")
for b in buttons:
    print(f"  button: id={b.get_attribute('id')} class={b.get_attribute('class')} text={b.text[:50]}")

print("Input elements:")
inputs = driver.find_elements(By.TAG_NAME, "input")
for i in inputs:
    print(f"  input: id={i.get_attribute('id')} type={i.get_attribute('type')} value={i.get_attribute('value')} placeholder={i.get_attribute('placeholder')}")

print("Trying to trigger grid by clicking search/locate button...")
triggered = False
for b in buttons:
    bid = (b.get_attribute('id') or '').lower()
    btext = (b.text or '').lower()
    bclass = (b.get_attribute('class') or '').lower()
    if any(x in bid+btext+bclass for x in ['search', 'locat', 'find', 'submit', 'go', 'show']):
        print(f"  Clicking: {b.get_attribute('id')} / {b.text}")
        try:
            driver.execute_script("arguments[0].click();", b)
            triggered = True
            time.sleep(10)
            break
        except Exception as e:
            print(f"  Click failed: {e}")

if not triggered:
    print("No obvious button found — trying to trigger grid via JS directly...")
    driver.execute_script("""
        var grid = $(".k-grid").data("kendoGrid");
        if (grid) { grid.dataSource.read(); }
    """)
    time.sleep(10)

# Check network logs for the grid call
print("Scanning network logs...")
logs = driver.get_log("performance")
grid_request_id = None
for entry in logs:
    msg = json.loads(entry["message"])["message"]
    if msg.get("method") == "Network.responseReceived":
        url = msg["params"]["response"]["url"]
        if "_RCLocatorGridData" in url:
            grid_request_id = msg["params"]["requestId"]
            print(f"Found _RCLocatorGridData! request_id={grid_request_id}")

if not grid_request_id:
    print("Still no grid XHR. All CalRecycle URLs now seen:")
    for entry in logs:
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") == "Network.responseReceived":
            url = msg["params"]["response"]["url"]
            if "calrecycle" in url.lower():
                print(f"  {url}")
    # Last resort: dump page source to see what's actually there
    print("\nPage source snippet (3000 chars):")
    print(driver.page_source[:3000])
    driver.quit()
    exit(1)

body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": grid_request_id})
grid_response = json.loads(body["body"])
records = grid_response.get("Data") or grid_response.get("data") or (grid_response if isinstance(grid_response, list) else [])
print(f"Total records: {len(records)}")

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

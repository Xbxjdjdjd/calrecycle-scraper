# VERSION: COOKIE-HARVEST-V1
import requests, csv, json, sys
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

BASE       = "https://www2.calrecycle.ca.gov"
DETAIL_URL = f"{BASE}/BevContainer/RecyclingCenters/Details"
OUTPUT_CSV  = "calrecycle_rvm.csv"
OUTPUT_JSON = "calrecycle_rvm.json"

ID_START = 1
ID_END   = 60000

# Step 1: Use Selenium to load a real page and harvest cookies
print("Step 1: Launching browser to get valid session cookies...")
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
driver = webdriver.Chrome(options=options)

# Load a known-good detail page to get a fully initialized session
print(f"  Loading known detail page ID=361...")
driver.get(f"{DETAIL_URL}?AccountLocationID=361")
time.sleep(5)

print(f"  Page title: {driver.title}")
print(f"  Page contains 'Details for': {'Details for' in driver.page_source}")

# Harvest all cookies
cookies = driver.get_cookies()
print(f"  Cookies: {[c['name'] for c in cookies]}")
driver.quit()

# Step 2: Transfer cookies into requests session
print("\nStep 2: Transferring cookies to requests session...")
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/BevContainer/RecyclingCenters",
})
for cookie in cookies:
    session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.calrecycle.ca.gov'))

# Verify it works on known ID
print("  Verifying session works on ID=361...")
test = session.get(f"{DETAIL_URL}?AccountLocationID=361", timeout=15)
print(f"  Status: {test.status_code}  Contains 'Details for': {'Details for' in test.text}")
print(f"  First 200 chars: {test.text[:200]}")

if "Details for" not in test.text:
    print("ERROR: Session cookies not working. Aborting.")
    sys.exit(1)

# Step 3: Brute force scan
print(f"\nStep 3: Scanning IDs {ID_START}-{ID_END} with 20 workers...")

def scrape(loc_id):
    try:
        r = session.get(f"{DETAIL_URL}?AccountLocationID={loc_id}", timeout=15)
        if "Details for" not in r.text:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        h1 = soup.find("h1")
        if not h1:
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

all_centers = []
rvm_centers = []
checked = 0

with ThreadPoolExecutor(max_workers=20) as ex:
    futures = {ex.submit(scrape, i): i for i in range(ID_START, ID_END + 1)}
    for future in as_completed(futures):
        result = future.result()
        checked += 1
        if result:
            all_centers.append(result)
            if (result.get("HasRVM") or "").strip().lower() == "yes":
                rvm_centers.append(result)
        if checked % 1000 == 0:
            print(f"  {checked}/{ID_END} checked | {len(all_centers)} centers | {len(rvm_centers)} RVM=Yes")

print(f"\nDone! {len(all_centers)} valid centers, {len(rvm_centers)} with RVM=Yes")

if not rvm_centers:
    print("Sample centers found:", json.dumps(all_centers[:3], indent=2))
    sys.exit(1)

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["AccountLocationID", "Name", "HasRVM"])
    w.writeheader()
    w.writerows(rvm_centers)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rvm_centers, f, indent=2)

print(f"✅ Saved {len(rvm_centers)} RVM centers → {OUTPUT_CSV}")

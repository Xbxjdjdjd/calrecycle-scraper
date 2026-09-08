# VERSION: FINAL-V1
import requests, csv, json, sys, re
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

print("=== VERSION: FINAL-V1 ===")

BASE        = "https://www2.calrecycle.ca.gov"
DETAIL_URL  = f"{BASE}/BevContainer/RecyclingCenters/Details"
OUTPUT_CSV  = "calrecycle_rvm.csv"
OUTPUT_JSON = "calrecycle_rvm.json"
ID_START    = 1
ID_END      = 60000

# Step 1: Harvest cookies via Selenium
print("Step 1: Launching browser to harvest cookies...")
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
driver = webdriver.Chrome(options=options)
driver.get(f"{DETAIL_URL}?AccountLocationID=361")
time.sleep(5)
cookies = driver.get_cookies()
print(f"  Cookies: {[c['name'] for c in cookies]}")
driver.quit()

# Step 2: Transfer cookies to requests session
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})
for cookie in cookies:
    session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.calrecycle.ca.gov'))
print("  Session ready.")

# Step 3: Scrape function
def scrape(loc_id):
    try:
        r = session.get(f"{DETAIL_URL}?AccountLocationID={loc_id}", timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # Name: second h1 contains "Recycling Center Details for X"
        h1s = soup.find_all("h1")
        name = ""
        for h in h1s:
            t = h.text.strip()
            if "Details for" in t:
                name = t.replace("Recycling Center Details for", "").strip()
                break
        if not name:
            return None

        # RVM: find "Reverse Vending Machines:" in full text
        full_text = soup.get_text(" ", strip=True)
        match = re.search(r"Reverse Vending Machines:\s*(\w+)", full_text)
        rvm = match.group(1) if match else None

        return {"AccountLocationID": loc_id, "Name": name, "HasRVM": rvm}
    except:
        return None

# Step 4: Scan all IDs
print(f"\nStep 3: Scanning IDs {ID_START}-{ID_END} with 20 workers...")
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
if all_centers:
    print(f"Sample: {all_centers[:3]}")
if not rvm_centers:
    print("No RVM=Yes centers found in this range.")
    sys.exit(1)

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["AccountLocationID", "Name", "HasRVM"])
    w.writeheader()
    w.writerows(rvm_centers)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rvm_centers, f, indent=2)

print(f"✅ Saved {len(rvm_centers)} RVM centers.")

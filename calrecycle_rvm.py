# VERSION: AUTODISCOVER-V1
import requests, csv, json, sys, re, base64
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

print("=== VERSION: AUTODISCOVER-V1 ===")

BASE        = "https://www2.calrecycle.ca.gov"
SEARCH_URL  = f"{BASE}/BevContainer/RecyclingCenters"
DETAIL_URL  = f"{BASE}/BevContainer/RecyclingCenters/Details"
OUTPUT_CSV  = "calrecycle_rvm.csv"
OUTPUT_JSON = "calrecycle_rvm.json"

# ============================================================
# STEP 1: Use the browser to search several major cities and
# harvest real AccountLocationIDs from the map's info windows
# ============================================================
print("--- STEP 1: Discovering real IDs via map search ---")
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1280,900")
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
driver = webdriver.Chrome(options=options)

cities = ["Los Angeles", "San Francisco", "San Diego", "Sacramento", "Fresno", "Oakland", "Long Beach", "Bakersfield"]
discovered_ids = set()

for city in cities:
    print(f"  Searching '{city}'...")
    driver.get(SEARCH_URL)
    time.sleep(3)
    try:
        loc_input = driver.find_element(By.ID, "Location")
        loc_input.clear()
        loc_input.send_keys(city)
        search_btn = driver.find_element(By.ID, "mapSearch")
        driver.execute_script("arguments[0].click();", search_btn)
        time.sleep(6)

        # Look for links to Details pages that Mapbox popups create
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='AccountLocationID']")
        for l in links:
            href = l.get_attribute("href")
            m = re.search(r"AccountLocationID=(\d+)", href)
            if m:
                discovered_ids.add(int(m.group(1)))

        # Also check page source directly for any embedded IDs
        matches = re.findall(r"AccountLocationID['\"]?\s*[:=]\s*['\"]?(\d+)", driver.page_source)
        for m in matches:
            discovered_ids.add(int(m))

        print(f"    Total unique IDs so far: {len(discovered_ids)}")
    except Exception as e:
        print(f"    Error searching {city}: {e}")

print(f"\n  Discovered {len(discovered_ids)} unique IDs from map searches")
if discovered_ids:
    sorted_ids = sorted(discovered_ids)
    print(f"  Min ID: {sorted_ids[0]}  Max ID: {sorted_ids[-1]}")
    print(f"  Sample IDs: {sorted_ids[:20]}")

cookies = driver.get_cookies()
driver.quit()

# ============================================================
# STEP 2: Build session
# ============================================================
print("\n--- STEP 2: Session setup ---")
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})
for c in cookies:
    session.cookies.set(c['name'], c['value'], domain=c.get('domain', '.calrecycle.ca.gov'))

def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    name = ""
    for h in soup.find_all("h1"):
        if "Details for" in h.text:
            name = h.text.replace("Recycling Center Details for", "").strip()
            break
    if not name:
        return None
    full_text = soup.get_text(" ", strip=True)
    match = re.search(r"Reverse Vending Machines:\s*(\w+)", full_text)
    rvm = match.group(1) if match else None
    return name, rvm

# Determine scan range based on discovered IDs
if discovered_ids:
    id_min = max(1, min(discovered_ids) - 5000)
    id_max = max(discovered_ids) + 5000
else:
    print("  No IDs discovered — falling back to 1-100000")
    id_min, id_max = 1, 100000

print(f"  Scan range determined: {id_min} to {id_max} ({id_max - id_min} IDs)")

def scrape(loc_id):
    try:
        r = session.get(f"{DETAIL_URL}?AccountLocationID={loc_id}", timeout=15)
        if "Details for" not in r.text:
            return None
        result = parse_page(r.text)
        if not result:
            return None
        name, rvm = result
        return {"AccountLocationID": loc_id, "Name": name, "HasRVM": rvm}
    except:
        return None

# Verify discovered IDs work
if discovered_ids:
    print("\n  Verifying a few discovered IDs...")
    for test_id in list(discovered_ids)[:5]:
        r = session.get(f"{DETAIL_URL}?AccountLocationID={test_id}", timeout=15)
        result = parse_page(r.text)
        print(f"    ID {test_id}: {result}")

# ============================================================
# STEP 3: Full scan over determined range
# ============================================================
print(f"\n--- STEP 3: Scanning {id_min}-{id_max} with 30 workers ---")
all_centers = []
rvm_centers = []
checked = 0

with ThreadPoolExecutor(max_workers=30) as ex:
    futures = {ex.submit(scrape, i): i for i in range(id_min, id_max + 1)}
    for future in as_completed(futures):
        result = future.result()
        checked += 1
        if result:
            all_centers.append(result)
            if (result.get("HasRVM") or "").strip().lower() == "yes":
                rvm_centers.append(result)
                print(f"  *** RVM=YES: {result} ***")
        if checked % 5000 == 0:
            print(f"  {checked}/{id_max - id_min} | {len(all_centers)} centers | {len(rvm_centers)} RVM=Yes")

print(f"\n--- FINAL RESULTS ---")
print(f"  Total centers: {len(all_centers)}")
print(f"  RVM=Yes: {len(rvm_centers)}")

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["AccountLocationID", "Name", "HasRVM"])
    w.writeheader()
    w.writerows(rvm_centers)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rvm_centers, f, indent=2)

with open("calrecycle_all_centers.json", "w", encoding="utf-8") as f:
    json.dump(all_centers, f, indent=2)

with open("discovered_ids.json", "w", encoding="utf-8") as f:
    json.dump(sorted(discovered_ids), f, indent=2)

print(f"✅ Saved {len(rvm_centers)} RVM centers.")

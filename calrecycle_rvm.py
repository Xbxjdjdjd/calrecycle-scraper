# VERSION: FINAL-SAFE-V1
import requests, csv, json, sys, re, base64
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

print("=== VERSION: FINAL-SAFE-V1 ===")
print("This script will: (1) verify session in <1 min, (2) pilot scan 5000 IDs in ~2 min,")
print("(3) only if both pass, run the full 100k scan. Bails immediately on any failure.\n")

BASE        = "https://www2.calrecycle.ca.gov"
DETAIL_URL  = f"{BASE}/BevContainer/RecyclingCenters/Details"
OUTPUT_CSV  = "calrecycle_rvm.csv"
OUTPUT_JSON = "calrecycle_rvm.json"
KNOWN_IDS   = {361: "Drive In Recycling", 79492: None, 80925: None}

# ============================================================
# STEP 1: Harvest cookies + take screenshot + dump raw HTML
# ============================================================
print("--- STEP 1: Browser setup & diagnostics ---")
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1280,900")
options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36")
driver = webdriver.Chrome(options=options)
driver.get(f"{DETAIL_URL}?AccountLocationID=361")
time.sleep(5)

print(f"  Title: {driver.title} | URL: {driver.current_url}")
print(f"  Has 'Details for': {'Details for' in driver.page_source} | Has 'Reverse Vending': {'Reverse Vending' in driver.page_source}")

try:
    screenshot = driver.get_screenshot_as_base64()
    with open("screenshot_browser.png", "wb") as f:
        f.write(base64.b64decode(screenshot))
    print("  Screenshot saved.")
except Exception as e:
    print(f"  Screenshot failed: {e}")

with open("debug_html_id361.html", "w", encoding="utf-8") as f:
    f.write(driver.page_source)
print("  Full HTML saved to debug_html_id361.html")

cookies = driver.get_cookies()
print(f"  Cookies: {[c['name'] for c in cookies]}")
driver.quit()

# ============================================================
# STEP 2: Build session, verify known IDs
# ============================================================
print("\n--- STEP 2: Session verification ---")
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

verification_failed = False
for test_id, expected_name in KNOWN_IDS.items():
    r = session.get(f"{DETAIL_URL}?AccountLocationID={test_id}", timeout=15)
    result = parse_page(r.text)
    if result:
        name, rvm = result
        print(f"  ID {test_id}: name='{name}' rvm={rvm} -- OK")
    else:
        print(f"  ID {test_id}: FAILED TO PARSE -- status={r.status_code} len={len(r.text)}")
        verification_failed = True

if verification_failed:
    print("\n❌ SESSION VERIFICATION FAILED. Aborting to save time/usage.")
    print("   Check screenshot_browser.png and debug_html_id361.html artifacts for details.")
    sys.exit(1)

print("  ✅ All known IDs verified successfully!")

# ============================================================
# STEP 3: Pilot scan (small range) to confirm scraping works at scale
# ============================================================
print("\n--- STEP 3: Pilot scan (IDs 1-5000) ---")

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

pilot_centers = []
with ThreadPoolExecutor(max_workers=30) as ex:
    futures = {ex.submit(scrape, i): i for i in range(1, 5001)}
    for future in as_completed(futures):
        result = future.result()
        if result:
            pilot_centers.append(result)

print(f"  Pilot found {len(pilot_centers)} centers in IDs 1-5000")
if len(pilot_centers) < 3:
    print("❌ PILOT SCAN FOUND TOO FEW CENTERS. Something is wrong. Aborting full scan.")
    print(f"   Pilot results: {pilot_centers}")
    sys.exit(1)

print(f"  ✅ Pilot passed! Sample: {pilot_centers[:3]}")

# ============================================================
# STEP 4: Full scan
# ============================================================
print(f"\n--- STEP 4: Full scan (IDs 5001-100000) ---")
all_centers = list(pilot_centers)  # include pilot results
rvm_centers = [c for c in all_centers if (c.get("HasRVM") or "").strip().lower() == "yes"]
checked = 5000

with ThreadPoolExecutor(max_workers=30) as ex:
    futures = {ex.submit(scrape, i): i for i in range(5001, 100001)}
    for future in as_completed(futures):
        result = future.result()
        checked += 1
        if result:
            all_centers.append(result)
            if (result.get("HasRVM") or "").strip().lower() == "yes":
                rvm_centers.append(result)
                print(f"  *** RVM=YES: {result} ***")
        if checked % 5000 == 0:
            print(f"  {checked}/100000 | {len(all_centers)} centers | {len(rvm_centers)} RVM=Yes")

print(f"\n--- FINAL RESULTS ---")
print(f"  Total centers: {len(all_centers)}")
print(f"  RVM=Yes: {len(rvm_centers)}")

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["AccountLocationID", "Name", "HasRVM"])
    w.writeheader()
    w.writerows(rvm_centers)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rvm_centers, f, indent=2)

# Also save ALL centers (not just RVM=Yes) for debugging
with open("calrecycle_all_centers.json", "w", encoding="utf-8") as f:
    json.dump(all_centers, f, indent=2)

print(f"✅ Saved {len(rvm_centers)} RVM centers to {OUTPUT_CSV}")

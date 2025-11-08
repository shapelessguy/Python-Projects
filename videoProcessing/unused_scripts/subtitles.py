import requests
import os
import json


from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
import time


# options = Options()
# options.add_experimental_option("prefs", {
#     "download.default_directory": r"C:\Users\shape\Downloads\subtitles",  # change path
#     "download.prompt_for_download": False,
#     "download.directory_upgrade": True,
#     "safebrowsing.enabled": True,
#     "safebrowsing.disable_download_protection": True  # allow unverified downloads
# })

# service = Service(r"C:\Users\shape\Documents\ChromeTools\chromedriver-win64\chromedriver.exe")
# driver = webdriver.Chrome(service=service, options=options)

# subtitle_id = "1234567"
# page_url = f"https://www.opensubtitles.org/en/subtitles/5588201"
# driver.get(page_url)

# wait = WebDriverWait(driver, 10)
# download_button = wait.until(
#     EC.element_to_be_clickable((By.ID, "bt-dwl-bt"))
# )
# download_button.click()

# time.sleep(3000)
# driver.quit()
# raise




login_url = "https://api.opensubtitles.com/api/v1/login"
secrets_path = os.path.join(os.path.dirname(__file__), ".api.json")
init_keys = {'api_token': None, 'username': None, 'password': None, 'bearer': None}
APP_NAME = "autoSub"


with open(secrets_path, "r") as f:
    keys = {**init_keys, **json.loads(f.read())}
    API_KEY = keys['api_token']
    USERNAME = keys['username']
    PASSWORD = keys['password']
    BEARER = keys['bearer']


def login():
    headers = {
        "Content-Type": "application/json",
        "Api-Key": API_KEY,
        "User-Agent": APP_NAME
    }
    payload = {
        "username": USERNAME,
        "password": PASSWORD
    }

    response = requests.post(login_url, headers=headers, json=payload)

    if response.ok:
        data = response.json()
        BEARER = data.get("token")
        keys['bearer'] = BEARER
        with open(secrets_path, "w") as f:
            json.dump(keys, f, indent=4)
        print("✅ Login successful!")
    else:
        print("❌ Login failed:", response.status_code, response.text)


login()

def search_movie(title, year=None, language="en"):
    url = f"https://api.opensubtitles.com/api/v1/subtitles"
    headers = {
        "Content-Type": "application/json",
        "Api-Key": API_KEY,
        "Authorization": f"Bearer {BEARER}",
        "User-Agent": APP_NAME
    }

    params = {
        "query": title,
        "languages": language
    }
    if year:
        params["year"] = year

    response = requests.get(url, headers=headers, params=params)

    if response.ok:
        results = response.json()
        for i, item in enumerate(results.get("data", [])[:5], start=1):
            print(f"{i}. {item['attributes']['release']} - {item['attributes']['files']}")
            subtitle_id = item['id']
            page_url = f"https://www.opensubtitles.org/en/subtitles/{subtitle_id}"
            print(f"{i} - {page_url}")
        return results
    else:
        print("❌ Search failed:", response.status_code, response.text)
        return None

search_movie("Inception", 2010, "en")
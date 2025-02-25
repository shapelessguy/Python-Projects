from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time


chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
driver = webdriver.Chrome(options=chrome_options)
stock_url = "https://www.boerse-frankfurt.de/aktie/nvidia-corp"
driver.get(stock_url)


try:
    while True:
        time.sleep(0.1)
        stock_price = driver.find_element(By.CSS_SELECTOR, '.widget-table-cell.askBidLimit').text
        stock_brief_price = driver.find_element(By.CSS_SELECTOR, '.widget-table-cell.askBidLimit.text-right').text
        print(f"Current stock price: {stock_price}")
except Exception as e:
    print(f"Error extracting stock price: {e}")

driver.quit()
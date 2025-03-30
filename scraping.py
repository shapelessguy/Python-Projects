from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import threading
from playsound import playsound


chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
driver = webdriver.Chrome(options=chrome_options)
stock_url = "https://www.boerse-frankfurt.de/aktie/nvidia-corp"
driver.get(stock_url)
signal = {'kill': False, 'alarm_flag': False}


def playAlarm(signal):
    while True:
        time.sleep(1)
        if signal['alarm_flag']:
            for _ in range(1):
                if signal["kill"]:
                    return
                playsound('C:/Users/shape/Documents/WorkC#Space/CyanSystemManager/Sounds/Allarme.wav')
                time.sleep(1)
            signal['alarm_flag'] = False

threading.Thread(target=playAlarm, args=(signal,), daemon=True).start()

try:
    while not signal['kill']:
        time.sleep(0.1)
        price_str = driver.find_element(By.CSS_SELECTOR, '.widget-table-cell.askBidLimit').text.replace(",", ".")
        stock_price = float(price_str)
        stock_brief_price = driver.find_element(By.CSS_SELECTOR, '.widget-table-cell.askBidLimit.text-right').text
        if len(str(stock_price).split('.')[1]) == 1:
            price_str = str(stock_price) + "0"
        print(f"Current stock price: {price_str}")
        if stock_price > 1 and (stock_price > 100 or stock_price < 99):
            signal['alarm_flag'] = True
except Exception as e:
    print(f"Error extracting stock price: {e}")

driver.quit()
signal['kill'] = True

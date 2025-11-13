from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import threading
from tick_manager import initialize_windows

from fastapi import FastAPI
import uvicorn
import traceback
from fastapi.middleware.cors import CORSMiddleware


POLLING_TIME = 2
RELOAD_TIMEOUT = 0 # 60 * 3


class Controller:
    kill = False
    reload = False
    stocks = []
    ready = False

    def __init__(self, stocks):
        self.stocks = stocks


class URL:
    deutscheboerse = {
        "check": EC.presence_of_element_located((By.XPATH, "//*[contains(@class, 'askBidLimit')]")),
        "get_value": lambda d: float(d.find_element(By.XPATH, "//*[contains(@class, 'askBidLimit')]").text.replace(",", "."))
    }
    yahoo = {
        "check": EC.presence_of_element_located((By.CSS_SELECTOR, 'span[data-testid="qsp-price"]')),
        "get_value": lambda d: float(d.find_element(By.CSS_SELECTOR, 'span[data-testid="qsp-price"]').text.replace(",", ".")),
    }


class Stock:
    def __init__(self, title, url, url_type, symbol):
        self.title = title
        self.url = url
        self.url_type = url_type
        self.symbol = symbol
        self.driver = None
        self.tab = None
        self.cur_value = 0
        self.cur_type = ""
        self.windows = initialize_windows(symbol)
    
    def refresh_tab(self):
        self.driver.switch_to.window(self.tab)
        WebDriverWait(self.driver, 10).until(lambda d: d.current_url == self.url)
        while True:
            try:
                self.driver.refresh()
                WebDriverWait(self.driver, 10).until(self.url_type["check"])
                break
            except Exception:
                time.sleep(0.1)
    
    def insert_value(self, value):
        if value != 0:
            self.cur_value = value
            self.cur_type = ""
    
    def push_values(self):
        self.windows.insert(self.cur_value)
    
    def get_price(self):
        self.driver.switch_to.window(self.tab)
        WebDriverWait(self.driver, 10).until(lambda d: d.current_url == self.url)
        try:
            self.insert_value(self.url_type["get_value"](self.driver))
        except Exception as e:
            print(f"{self.title} error: {e}")


def cruise(controller):
    time_init = time.time()
    while not controller.kill and not controller.reload:
        time_start = time.time()
        for stock in controller.stocks:
            stock.get_price()
        time_end = time.time() - time_start
        if time_end < POLLING_TIME:
            time.sleep(POLLING_TIME - time_end)
        else:
            print(f"POLLING TIME: {POLLING_TIME} is unrealistic with a real delay of {time_end}")
        controller.ready = True
        if (time.time() - time_init) > RELOAD_TIMEOUT and RELOAD_TIMEOUT > 0:
            controller.reload = True
            time_init = time.time()


def monitor(controller):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=chrome_options)
    tab_map = {}
    for stock in controller.stocks:
        if stock.url not in tab_map:
            driver.execute_script(f"window.open('{stock.url}');")
            tab = driver.window_handles[-1]
            tab_map[stock.url] = tab
        else:
            tab = tab_map[stock.url]
        
        driver.switch_to.window(tab)
        WebDriverWait(driver, 10).until(lambda d: d.current_url == stock.url)
        stock.driver = driver
        stock.tab = tab

    while not controller.kill:
        controller.reload = False
        for stock in controller.stocks:
            stock.refresh_tab()
        cruise(controller)

    driver.quit()
    controller.kill = True

def push_values(controller):
    while not controller.kill and not controller.reload:
        time.sleep(1)
        for stock in controller.stocks:
            stock.push_values()


controller = Controller([
    # Stock("NVIDIA", "https://live.deutsche-boerse.com/aktie/nvidia-corp?mic=XFRA", URL.deutscheboerse, "NVD.DE"),
    Stock("NVIDIA (us)", "https://finance.yahoo.com/quote/NVDA/", URL.yahoo, "NVDA"),
    # Stock("Leonardo", "https://live.deutsche-boerse.com/equity/leonardo-s-p-a?mic=XFRA", URL.deutscheboerse, "FMNB.DE"),
    # Stock("Berkshire", "https://live.deutsche-boerse.com/equity/berkshire-hathaway-b?mic=XFRA", URL.deutscheboerse, "BRYN.F"),
    # Stock("Nasdaq", "https://live.deutsche-boerse.com/en/etf/ishares-nasdaq-100-ucits-etf-de?currency=EUR", URL.deutscheboerse, "EEXXT.DE"),
    # Stock("SP500", "https://live.deutsche-boerse.com/en/etf/ishares-core-s-p-500-ucits-etf-usd-acc?currency=EUR", URL.deutscheboerse, "CSSPXM.XD"),
    # Stock("AMD", "https://live.deutsche-boerse.com/equity/advanced-micro-devices-inc?mic=XFRA", URL.deutscheboerse, "AMD.DE"),
    # Stock("Nuclear", "https://live.deutsche-boerse.com/en/etf/vaneck-uranium-and-nuclear-technologies-ucits-etf?currency=EUR", URL.deutscheboerse, "NUKL.DE"),
])

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/status")
def status_check():
    return {"status": "ok", "ready": controller.ready}

@app.get("/get_all")
def get_all():
    try:
        output = {}
        for s in controller.stocks:
            output[s.title] = s.windows.get_formatted()
    except:
        return {"status": "error", "msg": traceback.format_exc()}
    return {"status": "ok", "data": output}

@app.get("/get_stock")
def get_stock(stock: str, freq: str):
    try:
        s = next((s for s in controller.stocks if s.title == stock), None)
        if not s:
            return {"status": "error", "msg": f"Stock '{stock}' not found"}
        data = s.windows.get_formatted(freq)
    except Exception:
        return {"status": "error", "msg": traceback.format_exc()}
    return {"status": "ok", "data": data}

@app.get("/get_updates")
def get_updates():
    try:
        output = {}
        for s in controller.stocks:
            output[s.title] = {"value": s.cur_value, "type": s.cur_type}
    except:
        return {"status": "error", "msg": traceback.format_exc()}
    return {"status": "ok", "data": output}

if __name__ == "__main__":
    threading.Thread(target=monitor, args=(controller,)).start()
    while not controller.ready:
        time.sleep(0.1)
    threading.Thread(target=push_values, args=(controller,)).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)


controller.kill = True

import yfinance as yf


stock = yf.Ticker("NVD.DE")


price = stock.history(period="1mo", interval="5m")["Close"]
print(f"NVD.DE stock price: {price}")

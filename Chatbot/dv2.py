text = """
write me a code in python. I want a server http that receives data, process them and that can even send data back

ChatGPT
Sure, here's an example code in Python using the Flask web framework that creates a simple HTTP server which receives data via HTTP POST requests, processes it, and sends back a response:
"""

import numpy as np
import pandas as pd
import time
import requests

url = 'http://129.247.34.81:5000/process_data'
data = {'input_text': text,
        'cuda': 0,
        'do_sample': False,
        'resp_length': 40,
        'top_p': 0.7,
        'top_k': 0,
        'temperature': 1.0
}

response = requests.post(url, json=data).json()
out_text = response["result"] # .replace('\n', '\\n')
print(f'{out_text}')
text = """
write me a code in python. I want a server http that receives data, process them and that can even send data back

ChatGPT
Sure, here's an example code in Python using the Flask web framework that creates a simple HTTP server which receives 
data via HTTP POST requests, processes it, and sends back a response:
"""

text = """
In the article is written: 
"
There are still some further works we could do
based on the previous analysis. First, besides the
baseline prompt and general prompt, there are still
more combinations of different prompt designs and
temperatures that we could test, suggesting that
there might be more explorations when we analyze
GPT-3’s linguistic knowledge. Besides, our study
mainly focuses on the semantic information of linguistic phenomena, which is restricted to a limited
amount of probing tasks to test the model. A more
exhaustive list of probing tasks or a carefully designed benchmark based on the error analysis could
be created to better test the language model’s linguistic knowledge in the future. Moreover, further
human annotations could be applied in identifying
mistake types for each scenario, which provides the
quantitative measurement for each phenomenon
where GPT-3 makes a mistake."

In fewer words its says that:"""

from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import time
import requests

url = 'http://129.247.34.81:5000/process_data'
data = {'input_text': text,
        'cuda': 0,
        'do_sample': True,
        'resp_length': 250,
        'top_p': 0.9,
        'top_k': 0,
        'temperature': 1.0
}

response = requests.post(url, json=data).json()
out_text = response["result"]
print(out_text)

# times = []
# gen_tokens = []
# ns = [1, 2, 3, 6, 15, 30]
# for n in ns:
#         time1 = time.time()
#         data['resp_length'] = 300 // n
#         for _ in range(n):
#                 response = requests.post(url, json=data).json()
#                 out_text = response["result"]
#         time2 = time.time() - time1
#         gen_tokens.append(data['resp_length'])
#         times.append(time2)
# plt.plot(gen_tokens, times, '.')
# plt.title('Network overhead on 300 new tokens')
# plt.xlabel('generated_tokens (adm)')
# plt.ylabel('computation_time (s)')
# plt.show()

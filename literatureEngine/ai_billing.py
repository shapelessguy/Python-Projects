import os
import json
import requests
from utils import get_responses_path, WORKSPACES_PATH
rate = None


def convert_euro(price_dollar):
    global rate
    if rate is None:
        response = requests.get("https://api.frankfurter.app/latest", params={"from": "EUR", "to": "USD"})
        rate = response.json()["rates"]["USD"]
    return price_dollar / rate


model_pricing = {
    "gemini-3-pro-preview": {
        "input": 2.00,
        "output": 9.00
    },
    "gemini-2.5-pro": {
        "input": 1.25,
        "output": 7.50
    },
    "gemini-3-flash-preview": {
        "input": 0.25,
        "output": 1.50
    },
    "gemini-2.5-flash": {
        "input": 0.15,
        "output": 1.25
    },
    "gemini-2.5-flash-lite": {
        "input": 0.05,
        "output": 0.20
    },
    "gemini-2.5-flash-lite-preview-09-2025": {
        "input": 0.05,
        "output": 0.20
    }
}


def get_costs(model, input_tokens, output_tokens, n_requests, total_cost=None, batch=True):
    if not total_cost:
        mult = 2 if not batch else 1
        total_cost = ((model_pricing[model]['input'] * input_tokens +
                       model_pricing[model]['output'] * output_tokens) / 10**6) * mult * n_requests
    cost_per_req = convert_euro(total_cost) / n_requests
    estimated_n_queries = int(10 / cost_per_req)

    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "n_requests": n_requests,
        "price": round(convert_euro(total_cost), 2),
        "estimated_n_queries": estimated_n_queries,
    }


def print_stats(only_workspaces=(), only_names=()):
    tokens_by_model = {k: {} for k in model_pricing}
    all_workspaces = [x for x in os.listdir(WORKSPACES_PATH) if os.path.isdir(os.path.join(WORKSPACES_PATH, x))]
    
    if len(only_workspaces):
        all_workspaces = only_workspaces
    
    num = 0
    for workspace in all_workspaces:
        all_responses = os.listdir(get_responses_path(workspace, False))
        if len(only_names):
            all_responses = [x for x in all_responses if x.split("-")[0] in only_names]

        for fp in [os.path.join(get_responses_path(workspace, False), x) for x in all_responses]:
            with open(fp, "r", encoding='utf8') as file:
                json_ = json.load(file)
                for content in json_["contents"]:
                    num += 1
                    response = content["response"]
                    model = response["model_version"]
                    tokens_by_model[model]["input"] = tokens_by_model[model].get("input", 0)
                    tokens_by_model[model]["output"] = tokens_by_model[model].get("output", 0)
                    tokens_by_model[model]["cost"] = tokens_by_model[model].get("cost", 0)

                    prompt_tokens = response["prompt_tokens"]
                    gen_tokens = response["total_tokens"] - prompt_tokens
                    tokens_by_model[model]["input"] += prompt_tokens
                    tokens_by_model[model]["output"] += gen_tokens
                    mult = 2 if json_["uploadedBatchName"] is None else 1
                    cost = ((model_pricing[model]['input'] * prompt_tokens + model_pricing[model]['output'] * gen_tokens) / 10**6) * mult
                    tokens_by_model[model]["cost"] += cost

    tokens_by_model = {k: v for k, v in tokens_by_model.items() if len(v)}

    resp_text = f" -> {only_names}" if len(only_names) else ""
    all_ = f"" if len(only_names) else " all"
    stats = f"Billing for{all_} responses{resp_text}:\n"
    for model, v in tokens_by_model.items():
        costs = get_costs(model, input_tokens=v['input'], output_tokens=v['output'],
                          n_requests=num, total_cost=v['cost'])
        stats += f"\n\tModel: {costs['model']}\n"
        stats += f"\t  Number of requests: {costs['n_requests']}\n"
        stats += f"\t  Prompt tokens: {costs['input_tokens']}\n"
        stats += f"\t  Generated tokens: {costs['output_tokens']}\n"
        stats += f"\t  Price: {costs['price']}€ (~ {costs['estimated_n_queries']} queries/10€)\n"
    print(stats)


def print_scenario(model, input_tokens, output_tokens, n_requests, batch=True):
    costs = get_costs(model, input_tokens, output_tokens, n_requests, batch=batch)
    stats = f"Billing for scenario:\n"
    stats += f"\n\tModel: {costs['model']}\n"
    stats += f"\t  Number of requests: {costs['n_requests']}\n"
    stats += f"\t  Prompt tokens: {costs['input_tokens']}\n"
    stats += f"\t  Generated tokens: {costs['output_tokens']}\n"
    stats += f"\t  Price: {costs['price']}€ (~ {costs['estimated_n_queries']} queries/10€)\n"
    print(stats)


if __name__ == "__main__":
    # print_scenario(model="gemini-3-flash-preview", input_tokens=10000, output_tokens=3000, n_requests=100)
    print_stats()

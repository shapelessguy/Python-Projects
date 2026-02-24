

class Model:
    def __init__(self, model_name, model_info):
        if model_name not in model_info:
            raise Exception(f"Model {model_name} not recognized")
        self.model_name = model_name
        self.pricing = model_info.get("pricing", {"input": 0.0, "output": 0.0})
    
    def send_request(self, request):
        full_requests = request.get_full_requests()
        print(full_requests)
        pass


class LocalModel(Model):
    model_info = {
        "gemma3": {}
    }

    def __init__(self, model_name):
        super().__init__(model_name, self.model_info)
    
    def send_batch(self, requests, generationConfig, instant=False):
        return


class GeminiModel(Model):
    model_info = {
        "gemini-3-pro-preview": {
            "pricing": {
                "input": 2.00,
                "output": 9.00
            }
        },
        "gemini-2.5-pro": {
            "pricing": {
                "input": 1.25,
                "output": 7.50
            }
        },
        "gemini-3-flash-preview": {
            "pricing": {
                "input": 0.25,
                "output": 1.50
            }
        },
        "gemini-2.5-flash": {
            "pricing": {
                "input": 0.15,
                "output": 1.25
            }
        },
        "gemini-2.5-flash-lite": {
            "pricing": {
                "input": 0.05,
                "output": 0.20
            }
        },
        "gemini-2.5-flash-lite-preview-09-2025": {
            "pricing": {
                "input": 0.05,
                "output": 0.20
            }
        }
    }

    def __init__(self, model_name):
        super().__init__(model_name, self.model_info)
    
    def send_batch(self, requests, generationConfig, instant=False):

        return {"ai": "cla"}


class ModelClass:
    GEMINI = GeminiModel
    LOCAL = LocalModel

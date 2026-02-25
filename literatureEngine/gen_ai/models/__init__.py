import os


for provider in [x.replace(".py", "") for x in os.listdir(os.path.dirname(__file__)) if x.endswith(".py")]:
    mod = __import__(f"gen_ai.models.{provider}", fromlist=['*'])
    globals().update({k: v for k, v in mod.__dict__.items() if not k.startswith('_')})

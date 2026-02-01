import json
import os


def clean():
    for filename in os.listdir("batches/responses"):
        path = os.path.join("batches/responses", filename)
        with open(path, "r", encoding='utf8') as file:
            di = json.load(file)
            for c in di["contents"]:
                for content in c["request"]["contents"]:
                    for part in content["parts"]:
                        text = part["text"]
        with open(path, "w", encoding='utf8') as file:
            json.dump(di, file, indent=2)


if __name__ == "__main__":
    clean()

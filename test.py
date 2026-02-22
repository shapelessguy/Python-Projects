import os
import json
folder = r"C:\ProgramData\Cyan\CyanLauncher"

for f in os.listdir(folder):
    file_path = os.path.join(folder, f, "Info.txt")
    output_path = os.path.join(folder, f, "info.json")
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            text = file.read()
        
        new_content = []
        for line in text.split("\n"):
            if line != "":
                segments = line.split("|^_^|")
                exe, name, icon, as_admin = segments
                new_content.append({
                    "exe_path": exe,
                    "name": name,
                    "icon": icon,
                    "as_admin": as_admin == "true",
                })
        json_ = json.dumps(new_content, indent=2)
        if not os.path.exists(output_path):
            with open(output_path, "w") as file:
                json.dump(new_content, file, indent=2)

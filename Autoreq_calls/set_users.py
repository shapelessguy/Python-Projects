import requests
from requests.auth import HTTPBasicAuth


def create_user(project, data):
    url = f"http://localhost:10001/projects/{project}/user"
    headers = {
        "accept": "*/*",
        "Content-Type": "application/json"
    }
    auth = HTTPBasicAuth('SuperUser', '123')
    response = requests.post(url, headers=headers, auth=auth, json=data)

    print("Status Code:", response.status_code)
    print("Response Body:", response.text)


users = [
    ["claudio", "Claudio", "claudio", "claudio.ciano@dlr.de", "OWNER", ""],
    ["philippFisch", "Philipp Martin Fischer", "philippf", "Philipp.Fischer@dlr.de", "OWNER", ""],
    ["andrea", "Andrea Monti", "andrea", "Andrea.Monti@dlr.de", "OWNER", ""],
    ["moritz", "Moritz Edelhaeuser", "moritz", "Moritz.Edelhaeuser@dlr.de", "OWNER", ""],
    ["philippChrs", "Philipp Chrszon", "philc", "Philipp.Chrszon@dlr.de", "OWNER", ""],
    ["tobias", "Tobias Franz", "tobias", "Tobias.Franz@dlr.de", "OWNER", ""],
    ["lucia", "Lucia Andrea Jara Garcia", "lucia", "Lucia.JaraGarcia@dlr.de", "OWNER", ""],
    ["robert", "Robert Uebelacker", "robert", "Robert.Uebelacker@dlr.de", "OWNER", ""],
    ["julia", "Julia Getselev", "julia", "julia.getselev@dlr.de", "OWNER", ""],
]

user_data = [{k: v for k, v in zip(["id", "name", "password", "email", "permission", "domains"], values)} for values in users]
for ud in user_data:
    create_user("default", ud)
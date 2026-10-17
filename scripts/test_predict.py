import json, sys, urllib.request
import pandas as pd

URL = "http://127.0.0.1:8000"
df = pd.read_csv("data/creditcard.csv")
features = json.load(open("artifacts/metadata.json"))["features"]


def post(row):
    body = json.dumps({"features": {f: float(row[f]) for f in features}}).encode()
    req = urllib.request.Request(URL + "/predict", body, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


fraud = df[df.Class == 1].sample(5, random_state=1)
legit = df[df.Class == 0].sample(5, random_state=1)
for name, rows in (("FRAUD", fraud), ("LEGIT", legit)):
    for _, r in rows.iterrows():
        out = post(r)
        print(f"actual={name:5s} predicted={out['prediction']:5s} prob={out['fraud_probability']:.4f}")
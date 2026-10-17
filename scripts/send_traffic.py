import json, random, urllib.request
import pandas as pd

URL = "http://127.0.0.1:8000"
df = pd.read_csv("data/creditcard.csv")
features = json.load(open("artifacts/metadata.json"))["features"]
v_cols = [c for c in features if c.startswith("V")]


def post(row):
    body = json.dumps({"features": {f: float(row[f]) for f in features}}).encode()
    req = urllib.request.Request(URL + "/predict", body, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


print("Phase 1: normal traffic")
for _, r in df[df.Class == 0].sample(300, random_state=2).iterrows():
    out = post(r)
print("  drift score:", out["drift_score"])

print("Phase 2: shifted traffic (simulated drift)")
for _, r in df[df.Class == 0].sample(300, random_state=3).iterrows():
    r = r.copy()
    for c in v_cols:
        r[c] += random.uniform(1.5, 3.0)       # push every V feature away from normal
    out = post(r)
print("  drift score:", out["drift_score"])
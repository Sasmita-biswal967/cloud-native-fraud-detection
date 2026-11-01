"""Heavy traffic to trigger autoscaling.
Usage: python scripts/hpa_load.py http://<LB-address> [seconds=180] [threads=30]"""
import json, random, sys, threading, time, urllib.request

url = sys.argv[1].rstrip("/")
seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 180
threads = int(sys.argv[3]) if len(sys.argv) > 3 else 30

meta = json.load(open("artifacts/metadata.json"))
stats = meta["reference_stats"]
count = {"ok": 0, "err": 0}
lock = threading.Lock()
stop = time.time() + seconds


def worker():
    while time.time() < stop:
        feats = {f: random.gauss(stats[f]["mean"], stats[f]["std"]) for f in meta["features"]}
        req = urllib.request.Request(url + "/predict", json.dumps({"features": feats}).encode(),
                                     {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10).read()
            key = "ok"
        except Exception:
            key = "err"
        with lock:
            count[key] += 1


for _ in range(threads):
    threading.Thread(target=worker, daemon=True).start()

start = time.time()
while time.time() < stop:
    time.sleep(10)
    print(f"{time.time() - start:5.0f}s  ok={count['ok']}  errors={count['err']}  "
          f"~{count['ok'] / (time.time() - start):.0f} req/s", flush=True)
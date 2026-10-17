import json, os, threading
from collections import deque
from contextlib import asynccontextmanager

import joblib, numpy as np, pandas as pd
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

MODEL_DIR = os.getenv("MODEL_DIR", "artifacts")
MODEL_BUCKET = os.getenv("MODEL_BUCKET")            # set later on AWS: model is pulled from S3
MODEL_VERSION = os.getenv("MODEL_VERSION", "latest")
WINDOW = int(os.getenv("DRIFT_WINDOW", "200"))      # recent requests used for the drift check
DRIFT_THRESHOLD = float(os.getenv("DRIFT_THRESHOLD", "1.0"))

# ---- Prometheus metrics ----
PRED_TOTAL = Counter("predictions_total", "Predictions served", ["label"])
LATENCY = Histogram("prediction_latency_seconds", "Prediction latency")
FRAUD_PROB = Histogram("fraud_probability", "Predicted fraud probability",
                       buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99])
DRIFT = Gauge("data_drift_score", "Average shift of recent inputs from training data (in std devs)")
DRIFT_FLAG = Gauge("data_drift_detected", "1 if drift score is above the threshold")
MODEL_INFO = Gauge("model_info", "Loaded model", ["version", "name"])

state = {"model": None, "meta": None}
recent = deque(maxlen=WINDOW)
lock = threading.Lock()


def load_model():
    if MODEL_BUCKET:
        import boto3
        s3 = boto3.client("s3")
        os.makedirs(MODEL_DIR, exist_ok=True)
        for f in ("model.joblib", "metadata.json"):
            s3.download_file(MODEL_BUCKET, f"models/{MODEL_VERSION}/{f}", f"{MODEL_DIR}/{f}")
    model = joblib.load(f"{MODEL_DIR}/model.joblib")
    with open(f"{MODEL_DIR}/metadata.json") as f:
        meta = json.load(f)
    MODEL_INFO.labels(version=meta["version"], name=meta["model_name"]).set(1)
    return model, meta


@asynccontextmanager
async def lifespan(app):
    try:
        state["model"], state["meta"] = load_model()
    except Exception as e:      # stay alive so /health can report the problem
        print("Model load failed:", e)
    yield


app = FastAPI(title="Fraud Detection API", version="1.0", lifespan=lifespan)


class Transaction(BaseModel):
    features: dict[str, float]


def compute_drift():
    """Average absolute shift of recent feature means from training means, in training std devs."""
    ref = state["meta"]["reference_stats"]
    df = pd.DataFrame(list(recent))
    shifts = [abs(df[c].mean() - ref[c]["mean"]) / (ref[c]["std"] + 1e-9) for c in ref if c in df]
    score = float(np.mean(shifts)) if shifts else 0.0
    DRIFT.set(score)
    DRIFT_FLAG.set(1 if score > DRIFT_THRESHOLD else 0)
    return score


@app.get("/health")
def health():
    if state["model"] is None:
        raise HTTPException(503, "model not loaded")
    m = state["meta"]
    return {"status": "ok", "model": m["model_name"], "version": m["version"]}


@app.post("/predict")
def predict(tx: Transaction):
    if state["model"] is None:
        raise HTTPException(503, "model not loaded")
    meta = state["meta"]
    missing = [f for f in meta["features"] if f not in tx.features]
    if missing:
        raise HTTPException(422, f"missing features: {missing[:5]}")

    row = pd.DataFrame([[tx.features[f] for f in meta["features"]]], columns=meta["features"])
    with LATENCY.time():
        prob = float(state["model"].predict_proba(row)[0, 1])

    label = "fraud" if prob >= meta["threshold"] else "legit"
    PRED_TOTAL.labels(label).inc()
    FRAUD_PROB.observe(prob)

    with lock:
        recent.append(tx.features)
        drift = compute_drift() if len(recent) >= min(50, WINDOW) else None

    return {"fraud_probability": prob, "prediction": label,
            "threshold": meta["threshold"], "model_version": meta["version"],
            "drift_score": drift}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
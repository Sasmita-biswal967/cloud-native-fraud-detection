"""API tests. They build a tiny throw-away model with the same file layout as ml/train.py,
so they need no dataset and no AWS access (works in CI and inside `docker build`)."""
import json
import os

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

FEATURES = ["Time", "Amount"] + [f"V{i}" for i in range(1, 29)]


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("model")
    rng = np.random.RandomState(0)
    X = pd.DataFrame(rng.normal(size=(600, len(FEATURES))), columns=FEATURES)
    y = ((X["V1"] + X["V2"]) > 1.5).astype(int)
    pipe = Pipeline([
        ("prep", ColumnTransformer([("scale", RobustScaler(), ["Time", "Amount"])],
                                   remainder="passthrough")),
        ("clf", LogisticRegression(max_iter=500)),
    ]).fit(X, y)
    joblib.dump(pipe, d / "model.joblib")
    meta = {
        "model_name": "ci-test-model", "version": "ci", "threshold": 0.5, "metrics": {},
        "features": FEATURES,
        "reference_stats": {c: {"mean": float(X[c].mean()), "std": float(X[c].std())} for c in FEATURES},
    }
    (d / "metadata.json").write_text(json.dumps(meta))

    os.environ["MODEL_DIR"] = str(d)      # must be set BEFORE the app is imported
    os.environ.pop("MODEL_BUCKET", None)
    import app.main as main
    with TestClient(main.app) as c:       # runs the startup that loads the model
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["version"] == "ci"


def test_predict_returns_valid_probability(client):
    r = client.post("/predict", json={"features": {f: 0.0 for f in FEATURES}})
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["fraud_probability"] <= 1.0
    assert body["prediction"] in ("fraud", "legit")
    assert body["threshold"] == 0.5


def test_missing_features_rejected(client):
    r = client.post("/predict", json={"features": {"Time": 1.0}})
    assert r.status_code == 422


def test_metrics_endpoint(client):
    text = client.get("/metrics").text
    assert "predictions_total" in text
    assert "prediction_latency_seconds" in text


def test_drift_is_detected_on_shifted_inputs(client):
    shifted = {f: 6.0 for f in FEATURES}          # ~6 std devs away from the training data
    for _ in range(60):
        assert client.post("/predict", json={"features": shifted}).status_code == 200
    assert "data_drift_detected 1.0" in client.get("/metrics").text

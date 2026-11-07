from app.cloudwatch_metrics import Publisher


class FakeClient:
    def __init__(self):
        self.calls = []

    def put_metric_data(self, Namespace, MetricData):
        self.calls.append((Namespace, MetricData))


def names(data):
    return {d["MetricName"] for d in data}


def test_disabled_without_namespace():
    p = Publisher(namespace=None)
    p.record(0.01, 0.1, "legit")
    assert p.build_metric_data() is None


def test_no_traffic_sends_nothing():
    p = Publisher(client=FakeClient(), namespace="Test")
    p.flush()
    assert p.client.calls == []


def test_metrics_are_built_and_sent():
    client = FakeClient()
    p = Publisher(client=client, namespace="Test")
    for i in range(30):
        p.record(0.01 + i * 0.0001, 0.9 if i < 3 else 0.01, "fraud" if i < 3 else "legit", drift=2.5, drift_threshold=1.0)
    p.flush()
    ns, data = client.calls[0]
    assert ns == "Test"
    assert {"PredictionsFraud", "PredictionsLegit", "PredictionLatency", "FraudShare",
            "DriftScore", "DriftDetected", "AvgFraudProbability"} <= names(data)
    by = {d["MetricName"]: d for d in data}
    assert by["PredictionsFraud"]["Value"] == 3 and by["PredictionsLegit"]["Value"] == 27
    assert by["DriftDetected"]["Value"] == 1
    assert abs(by["FraudShare"]["Value"] - 0.1) < 1e-9
    assert len(by["PredictionLatency"]["Values"]) == len(by["PredictionLatency"]["Counts"]) <= 150


def test_fraud_share_skipped_on_tiny_samples_and_state_resets():
    p = Publisher(client=FakeClient(), namespace="Test")
    p.record(0.01, 0.9, "fraud")
    assert "FraudShare" not in names(p.build_metric_data())
    assert p.build_metric_data() is None   # the interval was cleared

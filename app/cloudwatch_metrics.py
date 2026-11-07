"""Publishes model metrics to Amazon CloudWatch as custom metrics.
Disabled unless CLOUDWATCH_NAMESPACE is set, so tests and local runs never call AWS."""
import os
import threading
from collections import Counter

NAMESPACE = os.getenv("CLOUDWATCH_NAMESPACE")
INTERVAL = int(os.getenv("CLOUDWATCH_INTERVAL", "60"))
MIN_FOR_SHARE = int(os.getenv("CLOUDWATCH_MIN_FOR_SHARE", "20"))  # avoid a noisy fraud share on tiny samples
DIMENSIONS = [{"Name": "Service", "Value": "fraud-api"}]


class Publisher:
    def __init__(self, client=None, namespace=None):
        self.namespace = namespace or NAMESPACE
        self.client = client
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._reset()

    @property
    def enabled(self):
        return bool(self.namespace)

    def _reset(self):
        self.latencies = []
        self.fraud = 0
        self.legit = 0
        self.prob_sum = 0.0
        self.drift = None
        self.drift_flag = None

    def record(self, latency, probability, label, drift=None, drift_threshold=None):
        if not self.enabled:
            return
        with self.lock:
            self.latencies.append(latency)
            self.prob_sum += probability
            if label == "fraud":
                self.fraud += 1
            else:
                self.legit += 1
            if drift is not None:
                self.drift = drift
                self.drift_flag = 1 if (drift_threshold is not None and drift > drift_threshold) else 0

    def build_metric_data(self):
        """Turns what was recorded since the last call into CloudWatch metric data (None if nothing happened)."""
        with self.lock:
            lat, fraud, legit = self.latencies, self.fraud, self.legit
            prob_sum, drift, flag = self.prob_sum, self.drift, self.drift_flag
            self._reset()
        total = fraud + legit
        if total == 0:
            return None  # no traffic: send nothing, so alarms fall back to OK instead of staying stale

        def datum(name, value, unit="None"):
            return {"MetricName": name, "Dimensions": DIMENSIONS, "Value": float(value), "Unit": unit}

        data = [datum("PredictionsFraud", fraud, "Count"), datum("PredictionsLegit", legit, "Count"),
                datum("AvgFraudProbability", prob_sum / total)]
        # latency as a distribution, so CloudWatch can compute p50 / p95 itself
        for digits in (3, 2, 1):
            counts = Counter(round(x, digits) for x in lat)
            if len(counts) <= 150:  # CloudWatch accepts at most 150 distinct values per datum
                break
        data.append({"MetricName": "PredictionLatency", "Dimensions": DIMENSIONS, "Unit": "Seconds",
                     "Values": [float(v) for v in counts], "Counts": [float(c) for c in counts.values()]})
        if total >= MIN_FOR_SHARE:
            data.append(datum("FraudShare", fraud / total))
        if drift is not None:
            data.append(datum("DriftScore", drift))
            data.append(datum("DriftDetected", flag))
        return data

    def _client(self):
        if self.client is None:
            import boto3
            self.client = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"))
        return self.client

    def flush(self):
        data = self.build_metric_data()
        if not data:
            return
        try:
            self._client().put_metric_data(Namespace=self.namespace, MetricData=data)
        except Exception as exc:  # monitoring must never break predictions
            print("CloudWatch publish failed:", exc)

    def _loop(self):
        while not self._stop.wait(INTERVAL):
            self.flush()

    def start(self):
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            print(f"CloudWatch publishing to namespace '{self.namespace}' every {INTERVAL}s")

    def stop(self):
        self._stop.set()
        if self.enabled:
            self.flush()


publisher = Publisher()

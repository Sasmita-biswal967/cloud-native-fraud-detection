import argparse, json, os, time
import joblib, numpy as np, pandas as pd
import mlflow
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, f1_score, precision_recall_curve,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler
from xgboost import XGBClassifier


def load_data(path):
    df = pd.read_csv(path)
    df = df.drop_duplicates().reset_index(drop=True)   # drop BEFORE splitting
    X = df.drop(columns=["Class"])
    y = df["Class"]
    return X, y


def build_pipelines(y_train):
    # how many legit transactions per fraud transaction (used by XGBoost)
    spw = (y_train == 0).sum() / (y_train == 1).sum()

    def prep():
        # scale only Time and Amount; V1-V28 are already PCA outputs
        return ColumnTransformer([("scale", RobustScaler(), ["Time", "Amount"])],
                                 remainder="passthrough")

    models = {
        "logistic_regression": LogisticRegression(max_iter=2000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=100, max_depth=12, min_samples_leaf=2,
            class_weight="balanced_subsample", n_jobs=-1, random_state=42),
        "xgboost": XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.1,
            scale_pos_weight=spw, eval_metric="aucpr", n_jobs=-1, random_state=42),
    }
    return {name: Pipeline([("prep", prep()), ("clf", clf)]) for name, clf in models.items()}


def evaluate(model, X, y, threshold=0.5):
    proba = model.predict_proba(X)[:, 1]
    pred = (proba >= threshold).astype(int)
    return {
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred),
        "f1": f1_score(y, pred),
        "roc_auc": roc_auc_score(y, proba),
        "pr_auc": average_precision_score(y, proba),
    }


def pick_threshold(pipe, X_train, y_train, target_recall):
    # predictions from models that did NOT see each row (cross-validation)
    proba = cross_val_predict(
        clone(pipe), X_train, y_train, method="predict_proba",
        cv=StratifiedKFold(3, shuffle=True, random_state=42))[:, 1]
    prec, rec, thr = precision_recall_curve(y_train, proba)
    ok = np.where(rec[:-1] >= target_recall)[0]        # thresholds that reach the recall goal
    if len(ok) == 0:
        return 0.5
    best = ok[np.argmax(prec[:-1][ok])]                # among them, the best precision
    return float(thr[best])


def save_artifacts(pipe, name, threshold, metrics, X_train, out):
    os.makedirs(out, exist_ok=True)
    joblib.dump(pipe, f"{out}/model.joblib")
    meta = {
        "model_name": name,
        "version": time.strftime("%Y%m%d%H%M%S"),
        "threshold": threshold,
        "metrics": {k: float(v) for k, v in metrics.items()},
        "features": list(X_train.columns),     # exact column order the API must use
        "reference_stats": {c: {"mean": float(X_train[c].mean()), "std": float(X_train[c].std())}
                            for c in X_train.columns},   # for drift detection later
    }
    with open(f"{out}/metadata.json", "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def main(args):
    X, y = load_data(args.data)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42)

    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow.set_experiment("fraud-detection")

    results, fitted = {}, {}
    for name, pipe in build_pipelines(y_tr).items():
        print(f"Training {name} ...")
        with mlflow.start_run(run_name=name):
            pipe.fit(X_tr, y_tr)
            results[name] = evaluate(pipe, X_te, y_te)
            fitted[name] = pipe
            mlflow.log_param("model", name)
            mlflow.log_metrics(results[name])
        print("  ", {k: round(v, 4) for k, v in results[name].items()})

    best = max(results, key=lambda k: results[k]["pr_auc"])
    thr = pick_threshold(fitted[best], X_tr, y_tr, args.target_recall)
    final = evaluate(fitted[best], X_te, y_te, threshold=thr)
    meta = save_artifacts(fitted[best], best, thr, final, X_tr, args.out)

    pd.DataFrame(results).T.round(4).to_csv(f"{args.out}/comparison.csv")
    print(f"\nBest model: {best} | threshold: {thr:.4f}")
    print("Final test metrics:", {k: round(v, 4) for k, v in final.items()})
    print(f"Saved to {args.out}/ (version {meta['version']})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/creditcard.csv")
    p.add_argument("--out", default="artifacts")
    p.add_argument("--target-recall", type=float, default=0.85)
    p.add_argument("--tracking-uri", default="sqlite:///mlflow.db")
    main(p.parse_args())
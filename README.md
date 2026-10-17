# Cloud-Native ML Model Deployment & Monitoring (AWS)

Fraud-detection model -> FastAPI -> Docker -> ECR -> EKS, provisioned with Terraform, delivered by Jenkins,
observed with Prometheus + Grafana, secured with IAM/IRSA, RBAC, Trivy, Gitleaks and Checkov.

```
GitHub -> Jenkins (test, scan, build) -> ECR -> EKS (HPA, rolling update, rollback)
                                            ^ model pulled from S3 (versioned)       |
ml/train.py -> MLflow + S3  ........................      Prometheus -> Grafana + alerts (drift, latency)
```

## Prerequisites
AWS account + CLI (`aws configure`), Terraform >= 1.6, Docker, kubectl, Helm, Python 3.11, Git.
Optional: Kaggle "creditcardfraud" CSV saved as `data/creditcard.csv` (otherwise synthetic data is used).

## Phase 1 - Train locally
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python ml/train.py            # compares LogReg / RandomForest / XGBoost, writes artifacts/
mlflow ui                     # optional: view runs at http://127.0.0.1:5000
pytest -q
```
Screenshot the metrics table and MLflow UI for your report.

## Phase 2 - Run locally (API + Prometheus + Grafana)
```
docker compose up --build
python scripts/load_test.py http://localhost:8000 --n 300
python scripts/load_test.py http://localhost:8000 --n 300 --drift   # triggers drift
```
API docs http://localhost:8000/docs | Prometheus :9090 | Grafana :3000 (admin/admin; build panels from
`predictions_total`, `prediction_latency_seconds`, `data_drift_score`).

## Phase 3 - Provision AWS with Terraform
```
cd terraform
terraform init
terraform apply -var alert_email=you@example.com      # ~15 min, creates VPC, EKS, ECR, S3, IAM, SNS
terraform output
```

## Phase 4 - Publish model + image
```
BUCKET=$(terraform output -raw model_bucket); ECR=$(terraform output -raw ecr_repository_url)
cd .. && python ml/train.py --s3-bucket $BUCKET
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin ${ECR%%/*}
docker build -t $ECR:v1 . && docker push $ECR:v1
```

## Phase 5 - Deploy to EKS
```
aws eks update-kubeconfig --name mlops-fraud-eks --region ap-south-1
# edit k8s/*.yaml: REPLACE_WITH_API_ROLE_ARN, REPLACE_ECR_URI:latest -> $ECR:v1, REPLACE_MODEL_BUCKET
kubectl apply -f k8s/
kubectl -n ml-platform get pods,svc,hpa
curl http://<EXTERNAL-IP>/health
```
Install the metrics server (needed by HPA) and monitoring stack:
```
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80
```
Add a ServiceMonitor/pod annotation scrape for `fraud-api` (annotations already in the Deployment) and
import the alert rules from `monitoring/alerts.yml`.

## Phase 6 - Jenkins CI/CD
1. Launch an EC2 (t3.medium, Ubuntu) with an IAM role allowing ECR push + `eks:DescribeCluster`; install Jenkins, Docker, aws-cli, kubectl, trivy, gitleaks, checkov.
2. Add the instance role to the cluster: `aws eks create-access-entry` / `aws-auth` for kubectl access.
3. Add Jenkins secret-text credential `ecr-uri`. Create a Pipeline job from SCM (your GitHub repo) + GitHub webhook.
4. Push a commit -> pipeline: test -> secret/IaC scan -> build -> Trivy -> push -> deploy -> auto-rollback on failure.

## Phase 7 - Demonstrate operations
| Demo | Command |
|---|---|
| Autoscaling | run `load_test.py` against the ELB with high `--n` from several terminals; `kubectl get hpa -w` |
| Drift alert | `load_test.py --drift`; watch `data_drift_detected` in Grafana |
| Rollback | `./scripts/rollback.sh` or `./scripts/rollback.sh <model-version>` |
| Retraining | `./scripts/retrain.sh` (schedule it in Jenkins with cron) |
| Security | Trivy/Gitleaks/Checkov stage output, IRSA role scoped to `s3:GetObject`, K8s RBAC Role |

## Cleanup (IMPORTANT - EKS + NAT cost ~USD 5-6/day)
```
kubectl delete -f k8s/ ; helm uninstall monitoring -n monitoring
cd terraform && terraform destroy -var alert_email=you@example.com
```

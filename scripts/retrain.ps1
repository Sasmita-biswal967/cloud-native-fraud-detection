param(
    [string]$Data = "data/creditcard.csv",
    [double]$TargetRecall = 0.85,
    [string]$Region = "ap-south-1",
    [switch]$SkipTrain,  # reuse the model already in artifacts/ instead of training again
    [switch]$Restart,    # also restart the pods on the cluster so they load the new model
    [switch]$Force       # promote even if the new model scores lower
)
$ErrorActionPreference = "Stop"
function Check($step) { if ($LASTEXITCODE -ne 0) { throw "FAILED at: $step" } }

$BUCKET = terraform -chdir=terraform output -raw model_bucket
Check "read bucket name"
if (-not $BUCKET -or $BUCKET -is [array] -or $BUCKET -match "\s") {
    throw "Bucket name looks wrong: '$BUCKET'. Run: terraform -chdir=terraform output -raw model_bucket"
}
Write-Host "Bucket: $BUCKET"

# ---- 1. train (or reuse) ----
if ($SkipTrain) {
    if (-not (Test-Path artifacts/model.joblib)) { throw "No artifacts/model.joblib - run without -SkipTrain" }
    Write-Host "`n[1/4] Skipping training, using the existing artifacts/" -ForegroundColor Cyan
} else {
    Write-Host "`n[1/4] Training on $Data ..." -ForegroundColor Cyan
    python ml/train.py --data $Data --target-recall $TargetRecall
    Check "training"
}

$meta = Get-Content artifacts/metadata.json | ConvertFrom-Json
$VERSION = $meta.version
$new = $meta.metrics
Write-Host "New model: $($meta.model_name) v$VERSION | precision=$([math]::Round($new.precision,4)) recall=$([math]::Round($new.recall,4)) pr_auc=$([math]::Round($new.pr_auc,4))"

# ---- 2. validation gate: compare with the model currently in production ----
Write-Host "`n[2/4] Comparing with the current model in S3 ..." -ForegroundColor Cyan
$tmp = Join-Path $env:TEMP "current-model-metadata.json"
if (Test-Path $tmp) { Remove-Item $tmp -Force }

$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"    # a failed aws call must not crash the script here
$out = (aws s3 cp "s3://$BUCKET/models/latest/metadata.json" $tmp --region $Region 2>&1 | Out-String)
$code = $LASTEXITCODE
$ErrorActionPreference = $prev

$promote = $true
if ($code -eq 0 -and (Test-Path $tmp)) {
    $old = Get-Content $tmp | ConvertFrom-Json
    Write-Host "Current model: v$($old.version) pr_auc=$([math]::Round($old.metrics.pr_auc,4))"
    if ($new.pr_auc -lt ($old.metrics.pr_auc - 0.005)) { $promote = $false }
} elseif ($out -match "404|does not exist|NoSuchKey|Not Found") {
    Write-Host "No current model in S3 - this will be the first one."
} else {
    throw "Could not read the current model from S3:`n$out"
}
if ($Force) { $promote = $true }

# ---- 3. upload: always keep the versioned copy; move "latest" only if the model passed ----
Write-Host "`n[3/4] Uploading ..." -ForegroundColor Cyan
foreach ($f in "model.joblib", "metadata.json") {
    aws s3 cp "artifacts/$f" "s3://$BUCKET/models/$VERSION/$f" --region $Region
    Check "upload versioned $f"
}
if ($promote) {
    foreach ($f in "model.joblib", "metadata.json") {
        aws s3 cp "artifacts/$f" "s3://$BUCKET/models/latest/$f" --region $Region
        Check "promote $f"
    }
    Write-Host "PROMOTED: v$VERSION is now 'latest'." -ForegroundColor Green
} else {
    Write-Host "NOT PROMOTED: the new model scored lower (pr_auc). 'latest' is unchanged. Use -Force to override." -ForegroundColor Yellow
}

# ---- 4. roll the new model out to the cluster ----
if ($Restart -and $promote) {
    Write-Host "`n[4/4] Rolling restart so pods load the new model ..." -ForegroundColor Cyan
    kubectl -n ml-platform rollout restart deployment/fraud-api
    kubectl -n ml-platform rollout status deployment/fraud-api --timeout=300s
    Check "rollout"
} else {
    Write-Host "`n[4/4] Skipped restart (add -Restart while the cluster is running)."
}
# The API pods (IRSA role from main.tf) may publish custom metrics to ONE CloudWatch namespace, nothing else.
resource "aws_iam_role_policy" "api_cloudwatch" {
  name = "publish-model-metrics"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["cloudwatch:PutMetricData"]
      Resource = "*"
      Condition = {
        StringEquals = { "cloudwatch:namespace" = "FraudModel" }
      }
    }]
  })
}

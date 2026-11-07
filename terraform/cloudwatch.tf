# CloudWatch monitoring for the fraud model: alarms + dashboard.
# The API publishes custom metrics (app/cloudwatch_metrics.py); alerts go to the SNS topic from alerts.tf.
locals {
  cw_namespace = "FraudModel"
}

resource "aws_cloudwatch_metric_alarm" "drift" {
  alarm_name          = "${var.project}-drift-detected"
  alarm_description   = "Input data drift detected - consider retraining"
  namespace           = local.cw_namespace
  metric_name         = "DriftDetected"
  dimensions          = { Service = "fraud-api" }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching" # no traffic -> no data -> the alarm returns to OK
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "latency" {
  alarm_name          = "${var.project}-high-latency-p95"
  alarm_description   = "p95 prediction latency above 500 ms"
  namespace           = local.cw_namespace
  metric_name         = "PredictionLatency"
  dimensions          = { Service = "fraud-api" }
  extended_statistic  = "p95"
  period              = 60
  evaluation_periods  = 3
  threshold           = 0.5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching" # no traffic -> no data -> the alarm returns to OK
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "fraud_share" {
  alarm_name          = "${var.project}-fraud-rate-spike"
  alarm_description   = "More than 10 percent of predictions are fraud"
  namespace           = local.cw_namespace
  metric_name         = "FraudShare"
  dimensions          = { Service = "fraud-api" }
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 2
  threshold           = 0.1
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching" # no traffic -> no data -> the alarm returns to OK
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_dashboard" "fraud" {
  dashboard_name = "${var.project}-fraud-model"
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 6
        height = 4
        properties = {
          title   = "Drift status (1 = drift)"
          view    = "singleValue"
          region  = var.region
          stat    = "Maximum"
          period  = 60
          stacked = false
          metrics = [[local.cw_namespace, "DriftDetected", "Service", "fraud-api"]]
        }
      },
      {
        type   = "metric"
        x      = 6
        y      = 0
        width  = 6
        height = 4
        properties = {
          title   = "Drift score (std devs)"
          view    = "singleValue"
          region  = var.region
          stat    = "Maximum"
          period  = 60
          stacked = false
          metrics = [[local.cw_namespace, "DriftScore", "Service", "fraud-api"]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 6
        height = 4
        properties = {
          title   = "Fraud predictions"
          view    = "singleValue"
          region  = var.region
          stat    = "Sum"
          period  = 60
          stacked = false
          metrics = [[local.cw_namespace, "PredictionsFraud", "Service", "fraud-api"]]
        }
      },
      {
        type   = "metric"
        x      = 18
        y      = 0
        width  = 6
        height = 4
        properties = {
          title   = "Legit predictions"
          view    = "singleValue"
          region  = var.region
          stat    = "Sum"
          period  = 60
          stacked = false
          metrics = [[local.cw_namespace, "PredictionsLegit", "Service", "fraud-api"]]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 4
        width  = 12
        height = 6
        properties = {
          title   = "Predictions per minute"
          view    = "timeSeries"
          region  = var.region
          stat    = "Sum"
          period  = 60
          stacked = false
          metrics = [[local.cw_namespace, "PredictionsLegit", "Service", "fraud-api", { label = "legit" }], [local.cw_namespace, "PredictionsFraud", "Service", "fraud-api", { label = "fraud" }]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 4
        width  = 12
        height = 6
        properties = {
          title   = "Prediction latency (seconds)"
          view    = "timeSeries"
          region  = var.region
          stat    = "Sum"
          period  = 60
          stacked = false
          metrics = [[local.cw_namespace, "PredictionLatency", "Service", "fraud-api", { stat = "p95", label = "p95" }], [local.cw_namespace, "PredictionLatency", "Service", "fraud-api", { stat = "p50", label = "p50" }]]
          annotations = { horizontal = [{ label = "alarm threshold", value = 0.5 }] }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 10
        width  = 12
        height = 6
        properties = {
          title   = "Data drift score"
          view    = "timeSeries"
          region  = var.region
          stat    = "Maximum"
          period  = 60
          stacked = false
          metrics = [[local.cw_namespace, "DriftScore", "Service", "fraud-api"]]
          annotations = { horizontal = [{ label = "alarm threshold", value = 1 }] }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 10
        width  = 12
        height = 6
        properties = {
          title   = "Average fraud probability"
          view    = "timeSeries"
          region  = var.region
          stat    = "Average"
          period  = 60
          stacked = false
          metrics = [[local.cw_namespace, "AvgFraudProbability", "Service", "fraud-api"]]
          yAxis = { left = { min = 0, max = 1 } }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 16
        width  = 12
        height = 6
        properties = {
          title   = "Fraud share of predictions"
          view    = "timeSeries"
          region  = var.region
          stat    = "Average"
          period  = 60
          stacked = false
          metrics = [[local.cw_namespace, "FraudShare", "Service", "fraud-api"]]
          annotations = { horizontal = [{ label = "alarm threshold", value = 0.1 }] }
          yAxis = { left = { min = 0, max = 1 } }
        }
      },
    ]
  })
}

output "dashboard_name" {
  value = aws_cloudwatch_dashboard.fraud.dashboard_name
}

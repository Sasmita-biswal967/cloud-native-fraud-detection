data "aws_iam_user" "ci" {
  user_name = "${var.project}-jenkins-ci" # created in Stage A (terraform/iam-ci.tf)
}

data "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts" # created in Stage A (terraform/alerts.tf)
}

# Maps the CI user to the Kubernetes group "ml-deployers".
# What that group may do is defined by the Role in k8s/rbac.yaml (RBAC).
resource "aws_eks_access_entry" "ci" {
  cluster_name      = module.eks.cluster_name
  principal_arn     = data.aws_iam_user.ci.arn
  kubernetes_groups = ["ml-deployers"]
  type              = "STANDARD"
}

# CloudWatch alarm on the worker nodes' CPU -> notification through SNS
resource "aws_cloudwatch_metric_alarm" "node_cpu_high" {
  alarm_name          = "${local.name}-node-cpu-high"
  alarm_description   = "Average CPU of the EKS worker nodes is above 80%"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    AutoScalingGroupName = module.eks.eks_managed_node_groups["default"].node_group_autoscaling_group_names[0]
  }

  alarm_actions = [data.aws_sns_topic.alerts.arn]
  ok_actions    = [data.aws_sns_topic.alerts.arn]
}

output "cpu_alarm_name" {
  value = aws_cloudwatch_metric_alarm.node_cpu_high.alarm_name
}

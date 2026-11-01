output "cluster_name" {
  value = module.eks.cluster_name
}

output "api_role_arn" {
  value = aws_iam_role.api.arn
}

output "region" {
  value = var.region
}
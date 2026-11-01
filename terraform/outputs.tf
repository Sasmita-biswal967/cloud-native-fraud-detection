output "model_bucket" {
  value = aws_s3_bucket.models.bucket
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}
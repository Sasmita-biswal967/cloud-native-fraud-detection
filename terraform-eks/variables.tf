variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "project" {
  type    = string
  default = "mlops-fraud" # must match Stage A so the S3 bucket name resolves
}
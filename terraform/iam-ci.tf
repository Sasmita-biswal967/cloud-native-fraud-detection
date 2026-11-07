# Dedicated IAM user for Jenkins: can push images to ONE ECR repo and describe ONE cluster. Nothing else.
resource "aws_iam_user" "ci" {
  name = "${var.project}-jenkins-ci"
}

resource "aws_iam_user_policy" "ci" {
  name = "ecr-push-and-eks-describe"
  user = aws_iam_user.ci.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:BatchGetImage",
          "ecr:DescribeImages"
        ]
        Resource = aws_ecr_repository.api.arn
      },
      {
        Effect   = "Allow"
        Action   = ["eks:DescribeCluster"]
        Resource = "arn:aws:eks:${var.region}:${data.aws_caller_identity.me.account_id}:cluster/${var.project}-demo"
      }
    ]
  })
}

output "jenkins_ci_user" {
  value = aws_iam_user.ci.name
}

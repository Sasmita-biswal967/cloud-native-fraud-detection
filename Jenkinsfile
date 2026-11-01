pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    timeout(time: 45, unit: 'MINUTES')
  }

  // Checks GitHub every ~2 minutes. (A webhook would need a public URL for this local Jenkins.)
  triggers { pollSCM('H/2 * * * *') }

  parameters {
    booleanParam(name: 'PUSH_TO_ECR',   defaultValue: false, description: 'Push the image to AWS ECR (needs the aws-creds credential)')
    booleanParam(name: 'DEPLOY_TO_EKS', defaultValue: false, description: 'Deploy to EKS (the cluster must be running - demo day only)')
  }

  environment {
    AWS_REGION     = 'ap-south-1'
    IMAGE          = 'fraud-api'
    ECR_REPO       = 'mlops-fraud-api'
    EKS_CLUSTER    = 'mlops-fraud-demo'
    TRIVY_CACHE_DIR = '/var/jenkins_home/trivy-cache'
  }

  stages {
    stage('Prepare') {
      steps {
        script { env.TAG = sh(returnStdout: true, script: 'git rev-parse --short HEAD').trim() }
        echo "Building image tag: ${env.TAG}"
      }
    }

    stage('Security: secrets + IaC') {
      parallel {
        stage('Gitleaks (secrets)') {
          steps { sh 'gitleaks detect --source . --no-banner --redact --exit-code 1' }
        }
        stage('Checkov (Terraform + K8s)') {
          // soft-fail: findings are reported but do not stop the build
          steps { sh 'checkov -d terraform -d terraform-eks -d k8s --framework terraform kubernetes --compact --quiet --soft-fail' }
        }
      }
    }

    stage('Unit tests (inside Docker)') {
      steps { sh 'docker build --target test -t ${IMAGE}-test:${TAG} .' }
    }

    stage('Build image') {
      steps { sh 'docker build -t ${IMAGE}:${TAG} .' }
    }

    stage('Trivy image scan') {
      steps {
        // report HIGH and CRITICAL, but only CRITICAL issues that have a fix fail the build
        sh 'trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 0 ${IMAGE}:${TAG}'
        sh 'trivy image --severity CRITICAL --ignore-unfixed --exit-code 1 ${IMAGE}:${TAG}'
      }
    }

    stage('Push to ECR') {
      when { expression { params.PUSH_TO_ECR || params.DEPLOY_TO_EKS } }
      steps {
        withCredentials([usernamePassword(credentialsId: 'aws-creds',
                         usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {
          sh '''
            ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
            REGISTRY=$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com
            aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $REGISTRY
            docker tag $IMAGE:$TAG $REGISTRY/$ECR_REPO:$TAG
            docker push $REGISTRY/$ECR_REPO:$TAG
          '''
        }
      }
    }

    stage('Deploy to EKS') {
      when { expression { params.DEPLOY_TO_EKS } }
      steps {
        withCredentials([usernamePassword(credentialsId: 'aws-creds',
                         usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {
          sh '''
            ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
            REGISTRY=$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com
            aws eks update-kubeconfig --name $EKS_CLUSTER --region $AWS_REGION
            kubectl -n ml-platform set image deployment/fraud-api api=$REGISTRY/$ECR_REPO:$TAG
            # roll back automatically if the new version does not become healthy
            if ! kubectl -n ml-platform rollout status deployment/fraud-api --timeout=300s; then
              kubectl -n ml-platform rollout undo deployment/fraud-api
              echo "Deployment failed - rolled back to the previous version"
              exit 1
            fi
          '''
        }
      }
    }
  }

  post {
    always  { sh 'docker image prune -f || true' }
    success { echo "Pipeline finished: image ${env.IMAGE}:${env.TAG}" }
    failure { echo 'Pipeline failed - open the failing stage in the console output.' }
  }
}

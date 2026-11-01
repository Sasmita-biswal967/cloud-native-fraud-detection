FROM jenkins/jenkins:lts-jdk21
USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg git python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI only. The engine is Docker Desktop's, reached through the mounted socket.
RUN install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list \
 && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
 && rm -rf /var/lib/apt/lists/*

# Security scanners
RUN curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
ARG GITLEAKS_VERSION=8.18.4
RUN curl -sSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
    | tar -xz -C /usr/local/bin gitleaks

# Checkov (IaC scanner) and AWS CLI, in their own virtualenv
RUN python3 -m venv /opt/tools && /opt/tools/bin/pip install --no-cache-dir checkov awscli
ENV PATH="/opt/tools/bin:${PATH}"

# kubectl
RUN curl -fsSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
 && chmod +x /usr/local/bin/kubectl

# Runs as root so it can use the Docker socket (acceptable for a local demo; not for production)
USER root

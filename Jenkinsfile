// OAN sandbox CI/CD: sandbox-platform@develop + the latest oan-helm chart on the
// dev k3s VM (release `sandbox`, namespace develop).
//
//   1. Versions  image tag = develop commit; chart = newest oan-helm tag
//                `oan-sandbox-*` (or CHART_REF), else oan-helm main
//   2. Test + build + push the API and web images, only if that commit's images
//                are not in the registry yet
//   3. Deploy    helm upgrade with that chart and those images, only if the
//                release does not already run exactly them (deployment/jenkins/deploy.sh)
//
// The cron trigger re-checks oan-helm, so a new chart release (or a new commit on
// main while there is none) is deployed without a sandbox-platform change.
//
// Jenkins setup: Pipeline from SCM, this repository, branch develop, script path
// Jenkinsfile; an agent labelled `docker` with Docker and git. Credentials:
//   ghcr-creds      username + PAT (write:packages) for ghcr.io; also used by the
//                   cluster to pull (Secret ghcr-pull in the namespace)
//   sandbox-vm-ssh  SSH username + private key for the VM (sandbox-platform-dev.pem)
pipeline {
  agent { label 'docker' }

  options {
    disableConcurrentBuilds()
    timestamps()
    timeout(time: 90, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '30'))
  }

  triggers {
    pollSCM('H/5 * * * *')     // sandbox-platform@develop (or use a GitHub webhook)
    cron('H/15 * * * *')       // new oan-helm chart versions
  }

  parameters {
    string(name: 'CHART_REF', defaultValue: '',
           description: 'oan-helm tag or branch. Empty: latest oan-sandbox-* release tag, else main.')
    booleanParam(name: 'FORCE_BUILD', defaultValue: false, description: 'Rebuild images even if already pushed.')
    booleanParam(name: 'FORCE_DEPLOY', defaultValue: false, description: 'Run helm upgrade even if up to date.')
  }

  environment {
    IMAGE_PREFIX     = 'ghcr.io/centre-for-open-societal-systems/oan-sandbox'
    OAN_HELM_REPO    = 'https://github.com/Centre-for-Open-Societal-Systems/oan-helm.git'
    SANDBOX_HOSTNAME = 'sandbox.development.oanstaging.com'
    SSH_HOST         = 'ec2-13-233-3-96.ap-south-1.compute.amazonaws.com'
    NAMESPACE        = 'develop'
    // Registry login stays in this workspace, not in the agent's ~/.docker.
    DOCKER_CONFIG    = "${WORKSPACE}/.docker"
  }

  stages {
    stage('Versions') {
      steps {
        script {
          env.TAG = sh(returnStdout: true, script: 'git rev-parse --short=12 HEAD').trim()
          env.API_IMAGE = "${env.IMAGE_PREFIX}-api:${env.TAG}"
          env.WEB_IMAGE = "${env.IMAGE_PREFIX}-web:${env.TAG}"

          def ref = params.CHART_REF?.trim()
          if (!ref) {
            ref = sh(returnStdout: true, script: '''
              git ls-remote --tags --refs "$OAN_HELM_REPO" 'refs/tags/oan-sandbox-*' \
                | sed 's#.*refs/tags/##' | sort -V | tail -n 1
            ''').trim() ?: 'main'
          }
          env.CHART_REF_RESOLVED = ref
          sh 'rm -rf oan-helm && git clone -q --depth 1 --branch "$CHART_REF_RESOLVED" "$OAN_HELM_REPO" oan-helm'
          def version = sh(returnStdout: true,
                           script: "sed -n 's/^version: *//p' oan-helm/charts/oan-sandbox/Chart.yaml").trim()
          def sha = sh(returnStdout: true, script: 'git -C oan-helm rev-parse --short=12 HEAD').trim()
          env.CHART_ID = "oan-helm ${ref}@${sha} chart ${version}"
          currentBuild.description = "${env.TAG} / chart ${version} (${ref})"
          echo "Images: ${env.API_IMAGE}, ${env.WEB_IMAGE}\nChart:  ${env.CHART_ID}"
        }
      }
    }

    stage('Registry') {
      steps {
        withCredentials([usernamePassword(credentialsId: 'ghcr-creds',
                                          usernameVariable: 'GHCR_USER', passwordVariable: 'GHCR_TOKEN')]) {
          sh 'printf "%s" "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin'
        }
        script {
          def pushed = sh(returnStatus: true,
                          script: 'docker manifest inspect "$API_IMAGE" >/dev/null && docker manifest inspect "$WEB_IMAGE" >/dev/null') == 0
          env.NEED_BUILD = (params.FORCE_BUILD || !pushed).toString()
          echo(env.NEED_BUILD == 'true' ? 'Images not in the registry: building.' : 'Images already pushed: skipping build.')
        }
      }
    }

    stage('Test') {
      when { environment name: 'NEED_BUILD', value: 'true' }
      parallel {
        stage('Backend') {
          steps {
            // Tests use an in-memory SQLite database (backend/tests/conftest.py).
            sh '''
              docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/backend:/src" -w /src python:3.12-slim sh -ec '
                python -m venv /tmp/venv && . /tmp/venv/bin/activate
                pip install -q -r requirements.txt
                ruff check app tests
                pytest -p no:cacheprovider'
            '''
          }
        }
        stage('UI') {
          steps {
            sh '''
              docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e NEXT_TELEMETRY_DISABLED=1 \
                -v "$PWD/ui:/src" -w /src node:22-alpine sh -ec '
                npm ci --no-audit --no-fund
                npm run typecheck
                npm run lint
                npm run build'
            '''
          }
        }
      }
    }

    stage('Build and push') {
      when { environment name: 'NEED_BUILD', value: 'true' }
      steps {
        sh '''
          docker build -f docker/sandbox-api/Dockerfile -t "$API_IMAGE" -t "$IMAGE_PREFIX-api:develop" .
          # The browser API URL is built into the web image (one image per environment).
          docker build -t "$WEB_IMAGE" -t "$IMAGE_PREFIX-web:develop" \
            --build-arg NEXT_PUBLIC_API_BASE_URL="https://$SANDBOX_HOSTNAME/oan" \
            --build-arg NEXT_PUBLIC_DEFAULT_COUNTRY=ET \
            --build-arg NEXT_PUBLIC_SITE_NAME="Open Agri Net" ui
          for image in "$API_IMAGE" "$IMAGE_PREFIX-api:develop" "$WEB_IMAGE" "$IMAGE_PREFIX-web:develop"; do
            docker push "$image"
          done
        '''
      }
    }

    stage('Deploy') {
      steps {
        withCredentials([
          sshUserPrivateKey(credentialsId: 'sandbox-vm-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
          usernamePassword(credentialsId: 'ghcr-creds', usernameVariable: 'GHCR_USER', passwordVariable: 'GHCR_TOKEN'),
        ]) {
          sh '''
            SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 $SSH_USER@$SSH_HOST"

            # The chart at the resolved oan-helm ref.
            tar -C oan-helm/charts -czf - oan-sandbox \
              | $SSH 'rm -rf ~/oan-deploy && mkdir -p ~/oan-deploy && tar -xzf - -C ~/oan-deploy'

            # Lets the cluster pull the GHCR images (private packages).
            printf '%s' "$GHCR_TOKEN" | $SSH "kubectl -n $NAMESPACE create secret docker-registry ghcr-pull \
              --docker-server=ghcr.io --docker-username='$GHCR_USER' --docker-password=\\"\\$(cat)\\" \
              --dry-run=client -o yaml | kubectl apply -f -"

            $SSH "API_IMAGE='$API_IMAGE' WEB_IMAGE='$WEB_IMAGE' CHART_DIR=\\$HOME/oan-deploy/oan-sandbox \
              CHART_ID='$CHART_ID' HOST='$SANDBOX_HOSTNAME' NAMESPACE='$NAMESPACE' PULL_SECRET=ghcr-pull \
              FORCE='$FORCE_DEPLOY' bash -s" < deployment/jenkins/deploy.sh
          '''
        }
      }
    }
  }

  post {
    always {
      sh 'rm -rf "$DOCKER_CONFIG"'
    }
    success {
      echo "https://${env.SANDBOX_HOSTNAME}  ${env.CHART_ID}  api/web ${env.TAG}"
    }
  }
}

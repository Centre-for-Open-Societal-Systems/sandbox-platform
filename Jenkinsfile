// OAN sandbox CI/CD: sandbox-platform@develop + the latest oan-helm chart on the
// oan-services-dev k3s VM (release oan-sandbox-1-1794475648, namespace sandbox,
// APISIX ingress), images in Amazon ECR.
//
//   1. Versions  chart = newest oan-helm release tag `oan-sandbox-*` (or CHART_REF),
//                else oan-helm main, pulled fresh on every run
//   2. Registry  ECR login; creates the repositories if missing; skips the build
//                when that chart version and that commit are both already in ECR
//                (eoan/sandbox-platform/oan-sandbox-api, eoan/sandbox-platform/oan-sandbox-web)
//   3. Test + build + push the API and web images (only when needed), tagged
//                <chart version>-<build number>  e.g. 1.0.0-dev.19-49  (unique, deployed)
//                <chart version>                 e.g. 1.0.0-dev.19     (latest build of it)
//                <commit>                        e.g. 8d7226c1a2b3
//                develop
//   4. Deploy    helm upgrade with that chart and the <chart version>-<build number>
//                images, unless the release already runs exactly them
//                (deployment/jenkins/deploy.sh). When the build was skipped, the
//                images keep the build-number tag they were pushed with.
//
// Pods pull from ECR without a pull Secret: k3s on the VM runs AWS's
// ecr-credential-provider with the instance role oan-services-dev-ecr-pull (the same
// way a2c and grievance pull). That role needs pull access to eoan/sandbox-platform/*.
//
// Builds start when a PR is merged into develop. The 6-hourly timer re-pulls
// oan-helm, so a new chart release, or a change to
// charts/oan-sandbox on main while there is no release, is deployed without a
// sandbox-platform change. Other charts in oan-helm do not cause a redeploy.
//
// Jenkins setup: the sandbox.platform GitHub Organization Folder (or a Pipeline
// from SCM, branch develop); an agent with Docker and git, labelled `docker`,
// `vpn-agent` or `vpn-agent2`. Only develop pushes images and deploys: other
// branches and PRs run Versions, Registry checks and Test. Credentials:
//   aws-ecr-creds   AWS key for ECR: either kind "AWS Credentials" or
//                   "Username with password" (access key id / secret access key);
//                   permissions in deployment/jenkins/ecr-policy.json
//   oan-services-dev-ssh  SSH username (ubuntu) + private key for the VM
//                   (oan-services-dev.pem)
//   ghcr-creds      only with PUSH_GHCR: username + PAT (write:packages)

// Exposes AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY from the aws-ecr-creds credential,
// whichever kind it is. Failures inside body are rethrown, not retried with the other kind.
def withAws(Closure body) {
  String AWS_CREDENTIALS_ID = 'aws-ecr-creds'
  boolean entered = false
  try {
    withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: AWS_CREDENTIALS_ID,
                      accessKeyVariable: 'AWS_ACCESS_KEY_ID', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) {
      entered = true
      body()
    }
  } catch (err) {
    if (entered) { throw err }
    echo "${AWS_CREDENTIALS_ID} is not an AWS Credentials entry; using it as username/password."
    withCredentials([usernamePassword(credentialsId: AWS_CREDENTIALS_ID,
                                      usernameVariable: 'AWS_ACCESS_KEY_ID', passwordVariable: 'AWS_SECRET_ACCESS_KEY')]) {
      body()
    }
  }
}

pipeline {
  agent { label 'docker || vpn-agent || vpn-agent2' }

  options {
    disableConcurrentBuilds()
    timestamps()
    timeout(time: 90, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '30'))
  }

  // A merged PR (push to develop) starts the build through the GitHub organization
  // folder's webhook; no polling. The timer runs develop every 6 hours only to pick
  // up a new oan-helm chart; it rebuilds or redeploys nothing that is already up to date.
  triggers {
    cron(env.BRANCH_NAME == null || env.BRANCH_NAME == 'develop' ? 'H H/6 * * *' : '')
  }

  parameters {
    string(name: 'CHART_REF', defaultValue: '',
           description: 'oan-helm tag or branch. Empty: latest oan-sandbox-* release tag, else main.')
    booleanParam(name: 'FORCE_BUILD', defaultValue: false, description: 'Rebuild images even if already in ECR.')
    booleanParam(name: 'FORCE_DEPLOY', defaultValue: false, description: 'Run helm upgrade even if up to date.')
    booleanParam(name: 'PUSH_GHCR', defaultValue: false, description: 'Also push new images to ghcr.io.')
  }

  environment {
    AWS_REGION         = 'ap-south-1'
    AWS_DEFAULT_REGION = 'ap-south-1'
    // ECR repositories eoan/sandbox-platform/oan-sandbox-api, eoan/sandbox-platform/oan-sandbox-web
    ECR_REPO_PREFIX    = 'eoan/sandbox-platform/oan-sandbox'
    GHCR_PREFIX        = 'ghcr.io/centre-for-open-societal-systems/oan-sandbox'
    OAN_HELM_REPO      = 'https://github.com/Centre-for-Open-Societal-Systems/oan-helm.git'
    SANDBOX_HOSTNAME   = 'sandbox.development.oanstaging.com'
    SSH_HOST           = 'ec2-13-234-239-132.ap-south-1.compute.amazonaws.com'
    NAMESPACE          = 'sandbox'
    RELEASE            = 'oan-sandbox-1-1794475648'
    // The chart has no Ingress; deploy.sh applies one for this class.
    INGRESS_CLASS      = 'apisix'
    // AWS CLI in a container: nothing to install on the agent.
    AWS = 'docker run --rm -i -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_SESSION_TOKEN -e AWS_REGION -e AWS_DEFAULT_REGION amazon/aws-cli:2.15.0'
    // Registry logins stay in this workspace, not in the agent's ~/.docker.
    DOCKER_CONFIG = "${WORKSPACE}/.docker"
  }

  stages {
    stage('Versions') {
      steps {
        script {
          env.COMMIT_TAG = sh(returnStdout: true, script: 'git rev-parse --short=12 HEAD').trim()

          def ref = params.CHART_REF?.trim()
          if (!ref) {
            // Newest release by version; a pre-release (1.1.0-rc.1) sorts before its release (1.1.0).
            ref = sh(returnStdout: true, script: '''
              git ls-remote --tags --refs "$OAN_HELM_REPO" 'refs/tags/oan-sandbox-*' \
                | sed 's#.*refs/tags/##' \
                | while read -r t; do printf '%s %s\\n' "$(echo "${t#oan-sandbox-}" | sed 's/-/~/')" "$t"; done \
                | sort -V -k1,1 | tail -n 1 | cut -d' ' -f2
            ''').trim() ?: 'main'
          }
          env.CHART_REF_RESOLVED = ref
          sh 'rm -rf oan-helm && git clone -q --depth 1 --branch "$CHART_REF_RESOLVED" "$OAN_HELM_REPO" oan-helm'
          def version = sh(returnStdout: true,
                           script: "sed -n 's/^version: *//p' oan-helm/charts/oan-sandbox/Chart.yaml").trim()
          // Hash of the chart directory only: changes elsewhere in oan-helm do not redeploy.
          def tree = sh(returnStdout: true, script: 'git -C oan-helm rev-parse --short=12 HEAD:charts/oan-sandbox').trim()
          env.CHART_ID = "oan-helm ${ref} chart ${version} tree ${tree}"
          // Images carry the chart version: eoan/sandbox-platform/oan-sandbox-api:1.0.0-dev.19
          if (!(version ==~ /[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}/)) {
            error("Chart version '${version}' is not a valid image tag")
          }
          env.TAG = version
          // Unique per build: what gets deployed, and what Rancher shows.
          env.IMAGE_TAG = "${version}-${env.BUILD_NUMBER}"
          if (!(env.IMAGE_TAG ==~ /[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}/)) {
            error("Image tag '${env.IMAGE_TAG}' is not a valid image tag")
          }
          currentBuild.description = "${env.TAG} (${env.COMMIT_TAG}) / chart ${ref}"
          echo "Chart: ${env.CHART_ID}"
        }
      }
    }

    stage('Registry') {
      steps {
        script {
          withAws {
            def account = sh(returnStdout: true, script: '$AWS sts get-caller-identity --query Account --output text').trim()
            env.ECR_REGISTRY = "${account}.dkr.ecr.${env.AWS_REGION}.amazonaws.com"
            env.API_IMAGE = "${env.ECR_REGISTRY}/${env.ECR_REPO_PREFIX}-api:${env.TAG}"
            env.WEB_IMAGE = "${env.ECR_REGISTRY}/${env.ECR_REPO_PREFIX}-web:${env.TAG}"
            echo "Images: ${env.API_IMAGE}, ${env.WEB_IMAGE}"
            sh '''
              $AWS ecr get-login-password | docker login "$ECR_REGISTRY" -u AWS --password-stdin
              for repo in "$ECR_REPO_PREFIX-api" "$ECR_REPO_PREFIX-web"; do
                $AWS ecr describe-repositories --repository-names "$repo" >/dev/null 2>&1 \
                  || $AWS ecr create-repository --repository-name "$repo" \
                       --image-scanning-configuration scanOnPush=true >/dev/null
              done
            '''
            // Build when this chart version or this commit is missing: a new develop
            // commit under the same chart version rebuilds and moves the version tag.
            def pushed = sh(returnStatus: true, script: '''
              for repo in "$ECR_REPO_PREFIX-api" "$ECR_REPO_PREFIX-web"; do
                for t in "$TAG" "$COMMIT_TAG"; do
                  $AWS ecr describe-images --repository-name "$repo" --image-ids imageTag="$t" >/dev/null 2>&1 || exit 1
                done
              done
            ''') == 0
            env.NEED_BUILD = (params.FORCE_BUILD || !pushed).toString()
            echo(env.NEED_BUILD == 'true' ? 'Images not in ECR: building.' : 'Images already in ECR: skipping build.')
          }
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
      when {
        allOf {
          environment name: 'NEED_BUILD', value: 'true'
          expression { env.BRANCH_NAME == null || env.BRANCH_NAME == 'develop' }
        }
      }
      steps {
        sh '''
          api_latest="$ECR_REGISTRY/$ECR_REPO_PREFIX-api:develop"
          web_latest="$ECR_REGISTRY/$ECR_REPO_PREFIX-web:develop"
          api_commit="$ECR_REGISTRY/$ECR_REPO_PREFIX-api:$COMMIT_TAG"
          web_commit="$ECR_REGISTRY/$ECR_REPO_PREFIX-web:$COMMIT_TAG"
          api_build="$ECR_REGISTRY/$ECR_REPO_PREFIX-api:$IMAGE_TAG"
          web_build="$ECR_REGISTRY/$ECR_REPO_PREFIX-web:$IMAGE_TAG"
          docker build -f docker/sandbox-api/Dockerfile \
            -t "$api_build" -t "$API_IMAGE" -t "$api_commit" -t "$api_latest" .
          # The browser API URL is built into the web image (one image per environment).
          docker build -t "$web_build" -t "$WEB_IMAGE" -t "$web_commit" -t "$web_latest" \
            --build-arg NEXT_PUBLIC_API_BASE_URL="https://$SANDBOX_HOSTNAME/oan" \
            --build-arg NEXT_PUBLIC_DEFAULT_COUNTRY=ET \
            --build-arg NEXT_PUBLIC_SITE_NAME="Open Agri Net" ui
          for image in "$api_build" "$API_IMAGE" "$api_commit" "$api_latest" \
                       "$web_build" "$WEB_IMAGE" "$web_commit" "$web_latest"; do
            docker push "$image"
          done
        '''
      }
    }

    stage('Mirror to GHCR') {
      when {
        allOf {
          environment name: 'NEED_BUILD', value: 'true'
          expression { params.PUSH_GHCR }
          expression { env.BRANCH_NAME == null || env.BRANCH_NAME == 'develop' }
        }
      }
      steps {
        withCredentials([usernamePassword(credentialsId: 'ghcr-creds',
                                          usernameVariable: 'GHCR_USER', passwordVariable: 'GHCR_TOKEN')]) {
          sh '''
            printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
            for c in api web; do
              src="$ECR_REGISTRY/$ECR_REPO_PREFIX-$c:$TAG"
              for t in "$IMAGE_TAG" "$TAG" develop; do
                docker tag "$src" "$GHCR_PREFIX-$c:$t"
                docker push "$GHCR_PREFIX-$c:$t"
              done
            done
          '''
        }
      }
    }

    stage('Deploy') {
      // Only develop deploys to the sandbox VM.
      when { expression { env.BRANCH_NAME == null || env.BRANCH_NAME == 'develop' } }
      steps {
        script { withAws { withCredentials([
          sshUserPrivateKey(credentialsId: 'oan-services-dev-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
        ]) {
          sh '''
            # The VM's host keys are pinned in the repo (works on any OpenSSH; accept-new
            # needs 7.6+ and vpn-agent2 has 7.4). If the VM is rebuilt, refresh the file:
            #   ssh-keyscan -t ed25519,ecdsa,rsa $SSH_HOST > deployment/jenkins/known_hosts
            SSH="ssh -i $SSH_KEY -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$WORKSPACE/deployment/jenkins/known_hosts -o ServerAliveInterval=30 $SSH_USER@$SSH_HOST"

            # Deploy the unique <chart version>-<build number> tag. When this run skipped
            # the build, reuse the newest such tag already on this commit's images, so the
            # 6-hourly timer runs find the release up to date. Images pushed before these
            # tags existed get this run's tag added (same manifest, no rebuild).
            DEPLOY_TAG=$IMAGE_TAG
            if [ "$NEED_BUILD" != true ]; then
              found=$($AWS ecr describe-images --repository-name "$ECR_REPO_PREFIX-api" \
                  --image-ids imageTag="$COMMIT_TAG" --query 'imageDetails[0].imageTags' --output text \
                | tr -d '\\r' | tr '\\t' '\\n' \
                | awk -v p="$TAG-" 'index($0, p) == 1 { n = substr($0, length(p) + 1); if (n ~ /^[0-9]+$/) print n, $0 }' \
                | sort -n | tail -n 1 | cut -d' ' -f2)
              DEPLOY_TAG=${found:-$IMAGE_TAG}
              for c in api web; do
                repo="$ECR_REPO_PREFIX-$c"
                if ! $AWS ecr describe-images --repository-name "$repo" --image-ids imageTag="$DEPLOY_TAG" >/dev/null 2>&1; then
                  manifest=$($AWS ecr batch-get-image --repository-name "$repo" --image-ids imageTag="$COMMIT_TAG" \
                    --query 'images[0].imageManifest' --output text)
                  media_type=$($AWS ecr batch-get-image --repository-name "$repo" --image-ids imageTag="$COMMIT_TAG" \
                    --query 'images[0].imageManifestMediaType' --output text | tr -d '\\r')
                  $AWS ecr put-image --repository-name "$repo" --image-tag "$DEPLOY_TAG" \
                    --image-manifest "$manifest" --image-manifest-media-type "$media_type" >/dev/null
                  echo "Tagged $repo:$COMMIT_TAG as $DEPLOY_TAG"
                fi
              done
            fi
            echo "Deploying images tagged $DEPLOY_TAG"

            # The chart at the resolved oan-helm ref.
            tar -C oan-helm/charts -czf - oan-sandbox \
              | $SSH 'rm -rf ~/oan-deploy && mkdir -p ~/oan-deploy && tar -xzf - -C ~/oan-deploy'

            # No digests: deploy.sh then clears the digest left on the release and the
            # chart renders repository:tag.
            API_DEPLOY="$ECR_REGISTRY/$ECR_REPO_PREFIX-api:$DEPLOY_TAG"
            WEB_DEPLOY="$ECR_REGISTRY/$ECR_REPO_PREFIX-web:$DEPLOY_TAG"
            $SSH "API_IMAGE='$API_DEPLOY' WEB_IMAGE='$WEB_DEPLOY' API_DIGEST='' WEB_DIGEST='' \
              CHART_DIR=\\$HOME/oan-deploy/oan-sandbox \
              CHART_ID='$CHART_ID' HOST='$SANDBOX_HOSTNAME' NAMESPACE='$NAMESPACE' RELEASE='$RELEASE' \
              INGRESS_CLASS='$INGRESS_CLASS' \
              FORCE='$FORCE_DEPLOY' bash -s" < deployment/jenkins/deploy.sh
          '''
        } } }
      }
    }
  }

  post {
    always {
      sh 'rm -rf "$DOCKER_CONFIG"'
    }
    success {
      echo "https://${env.SANDBOX_HOSTNAME}  ${env.CHART_ID}  commit ${env.COMMIT_TAG}"
    }
  }
}

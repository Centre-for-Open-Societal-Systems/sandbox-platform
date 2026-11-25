// OAN sandbox CI/CD: sandbox-platform@develop + its own chart (helm/oan-sandbox) on the
// oan-services-dev k3s VM (release oan-sandbox-1-1794475648, namespace sandbox,
// APISIX ingress), images in Amazon ECR.
//
//   1. Versions  chart = helm/oan-sandbox of this commit, values
//                helm/environments/dev/oan-sandbox.yaml; Chart lints and renders them
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
// staging (the staging branch, like oan_a2c_service's): the same Versions/Chart/Registry/Test
// stages with helm/environments/staging/oan-sandbox.yaml, then its own API and web images
// (the web image carries the staging host, so develop's cannot be promoted), tagged
//                <chart version>-staging.<build number>, staging-<commit>, staging
// and "staging → QA cluster (helm)": deployment/jenkins/deploy-cluster.sh installs release
// oan-sandbox in namespace sandbox of the QA cluster (sandbox.qa.oanstaging.com) from the
// oan-ci-deploy agent with credential oan-qa-kubeconfig (the jenkins-qa-deployer
// ServiceAccount of oan-helm docs/qa-cluster.md). It never moves develop's tags.
//
// Builds start when a PR is merged into develop. The chart lives in this repository,
// so a chart or values change is deployed like any other develop change; nothing
// is pulled from oan-helm.
//
// Jenkins setup: the sandbox.platform GitHub Organization Folder (or a Pipeline
// from SCM, branch develop); an agent with Docker and git, labelled `docker`,
// `vpn-agent` or `vpn-agent2`. Only develop and staging push images and deploy: other
// branches and PRs run Versions, Registry checks and Test. Credentials:
//   aws-ecr-creds   AWS key for ECR: either kind "AWS Credentials" or
//                   "Username with password" (access key id / secret access key);
//                   permissions in deployment/jenkins/ecr-policy.json
//   oan-services-dev-ssh  SSH username (ubuntu) + private key for the VM
//                   (oan-services-dev.pem)
//   oan-qa-kubeconfig  staging: kubeconfig file of jenkins-qa-deployer (the one a2c uses)
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
    // The oan-ci-aws agents are Spot instances: when EC2 reclaims one mid-build,
    // rerun the whole pipeline on a new agent (a stage-level retry would stay on the
    // dead one). Reruns are cheap: Registry skips images already in ECR and
    // deploy.sh skips a release already up to date (and rolls back one left
    // pending-upgrade by the cut-off deploy).
    retry(count: 2, conditions: [agent(), nonresumable()])
    disableConcurrentBuilds()
    timestamps()
    timeout(time: 90, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '30'))
  }

  // A merged PR (push to develop) starts the build through the GitHub organization
  // folder's webhook; no polling and no timer.

  parameters {
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
    CHART_DIR          = 'helm/oan-sandbox'
    // VALUES_FILE, SANDBOX_HOSTNAME and RELEASE depend on the branch: set in Versions
    // (a variable declared here could not be changed there).
    SSH_HOST           = 'ec2-13-234-239-132.ap-south-1.compute.amazonaws.com'
    NAMESPACE          = 'sandbox'
    // Helm in a container for the Chart stage: nothing to install on the agent.
    HELM = "docker run --rm -u 1000:1000 -e HOME=/tmp -v ${WORKSPACE}/helm:/helm:ro alpine/helm:3.16.3"
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
          // staging: the QA cluster. Everything else (develop, PRs, other branches): dev.
          env.STAGING = (env.BRANCH_NAME == 'staging').toString()
          if (env.STAGING == 'true') {
            env.DEPLOY_ENV       = 'staging'
            env.SANDBOX_HOSTNAME = 'sandbox.qa.oanstaging.com'
            env.RELEASE          = 'oan-sandbox'
          } else {
            env.DEPLOY_ENV       = 'dev'
            env.SANDBOX_HOSTNAME = 'sandbox.development.oanstaging.com'
            env.RELEASE          = 'oan-sandbox-1-1794475648'
          }
          // The Ingress (class apisix), image repositories and config of the release.
          env.VALUES_FILE = "helm/environments/${env.DEPLOY_ENV}/oan-sandbox.yaml"

          def version = sh(returnStdout: true,
                           script: "sed -n 's/^version: *//p' \"$CHART_DIR/Chart.yaml\"").trim()
          // Hash of helm/ (chart and environment values): a change to either redeploys.
          def tree = sh(returnStdout: true, script: 'git rev-parse --short=12 HEAD:helm').trim()
          env.CHART_ID = "sandbox-platform chart ${version} helm tree ${tree}"
          // Images carry the chart version: eoan/sandbox-platform/oan-sandbox-api:1.0.0-dev.19
          if (!(version ==~ /[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}/)) {
            error("Chart version '${version}' is not a valid image tag")
          }
          env.TAG = version
          // Unique per build: what gets deployed, and what Rancher shows.
          env.IMAGE_TAG = "${version}-${env.BUILD_NUMBER}"
          // staging images have tags of their own (their web image differs): staging-<commit>,
          // <chart version>-staging.<build>, staging. The bare chart version stays develop's.
          env.SOURCE_TAG = env.COMMIT_TAG
          env.MOVING_TAG = 'develop'
          env.DEPLOY_PREFIX = "${version}-"
          if (env.STAGING == 'true') {
            env.SOURCE_TAG = "staging-${env.COMMIT_TAG}"
            env.MOVING_TAG = 'staging'
            env.DEPLOY_PREFIX = "${version}-staging."
            env.IMAGE_TAG = "${version}-staging.${env.BUILD_NUMBER}"
          }
          if (!(env.IMAGE_TAG ==~ /[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}/)) {
            error("Image tag '${env.IMAGE_TAG}' is not a valid image tag")
          }
          currentBuild.description = "${env.TAG} (${env.COMMIT_TAG}) / helm ${tree}"
          echo "Chart: ${env.CHART_ID}"
        }
      }
    }

    stage('Chart') {
      steps {
        // Every branch and PR: the chart lints and renders with the dev values (placeholder
        // image tags and Secret name; the real ones are set by Deploy).
        sh '''
          SET="--set secret.name=lint --set api.image.tag=lint --set web.image.tag=lint"
          $HELM lint /$CHART_DIR
          $HELM lint /$CHART_DIR -f /$VALUES_FILE $SET
          $HELM template "$RELEASE" /$CHART_DIR -n "$NAMESPACE" -f /$VALUES_FILE $SET >/dev/null
        '''
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
            // staging checks only its own staging-<commit> tag.
            def pushed = sh(returnStatus: true, script: '''
              tags="$TAG $SOURCE_TAG"
              [ "$STAGING" = true ] && tags="$SOURCE_TAG"
              for repo in "$ECR_REPO_PREFIX-api" "$ECR_REPO_PREFIX-web"; do
                for t in $tags; do
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
          expression { env.BRANCH_NAME == null || env.BRANCH_NAME == 'develop' || env.BRANCH_NAME == 'staging' }
        }
      }
      steps {
        sh '''
          api_latest="$ECR_REGISTRY/$ECR_REPO_PREFIX-api:$MOVING_TAG"
          web_latest="$ECR_REGISTRY/$ECR_REPO_PREFIX-web:$MOVING_TAG"
          api_commit="$ECR_REGISTRY/$ECR_REPO_PREFIX-api:$SOURCE_TAG"
          web_commit="$ECR_REGISTRY/$ECR_REPO_PREFIX-web:$SOURCE_TAG"
          api_build="$ECR_REGISTRY/$ECR_REPO_PREFIX-api:$IMAGE_TAG"
          web_build="$ECR_REGISTRY/$ECR_REPO_PREFIX-web:$IMAGE_TAG"
          api_tags="$api_build $api_commit $api_latest"
          web_tags="$web_build $web_commit $web_latest"
          # The bare chart version (API_IMAGE / WEB_IMAGE) is develop's latest build of it only.
          if [ "$STAGING" != true ]; then
            api_tags="$api_tags $API_IMAGE"
            web_tags="$web_tags $WEB_IMAGE"
          fi
          docker build -f docker/sandbox-api/Dockerfile $(printf -- '-t %s ' $api_tags) .
          # The browser API URL is built into the web image (one image per environment).
          docker build $(printf -- '-t %s ' $web_tags) \
            --build-arg NEXT_PUBLIC_API_BASE_URL="https://$SANDBOX_HOSTNAME/oan" \
            --build-arg NEXT_PUBLIC_DEFAULT_COUNTRY=ET \
            --build-arg NEXT_PUBLIC_SITE_NAME="Open Agri Net" ui
          for image in $api_tags $web_tags; do
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
            # the build, reuse the newest such tag already on this commit's images, so a
            # rerun finds the release up to date. Images pushed before these
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

            # This commit's helm/: the chart and the environment values.
            tar -C helm -czf - oan-sandbox environments \
              | $SSH 'rm -rf ~/oan-deploy && mkdir -p ~/oan-deploy && tar -xzf - -C ~/oan-deploy'

            # No digests: deploy.sh then clears the digest left on the release and the
            # chart renders repository:tag.
            API_DEPLOY="$ECR_REGISTRY/$ECR_REPO_PREFIX-api:$DEPLOY_TAG"
            WEB_DEPLOY="$ECR_REGISTRY/$ECR_REPO_PREFIX-web:$DEPLOY_TAG"
            $SSH "API_IMAGE='$API_DEPLOY' WEB_IMAGE='$WEB_DEPLOY' API_DIGEST='' WEB_DIGEST='' \
              CHART_DIR=\\$HOME/oan-deploy/oan-sandbox \
              VALUES_FILE=\\$HOME/oan-deploy/environments/dev/oan-sandbox.yaml \
              CHART_ID='$CHART_ID' HOST='$SANDBOX_HOSTNAME' NAMESPACE='$NAMESPACE' RELEASE='$RELEASE' \
              FORCE='$FORCE_DEPLOY' bash -s" < deployment/jenkins/deploy.sh
          '''
        } } }
      }
    }

    // staging: the unique tag to deploy, resolved here because the deploy agent has no AWS
    // access. As on develop: this build's tag, or after a skipped build the newest
    // <chart version>-staging.<N> already on this commit's staging images.
    stage('Deploy tag (staging)') {
      when { branch 'staging' }
      steps {
        script { withAws {
          env.DEPLOY_TAG = sh(returnStdout: true, script: '''
            if [ "$NEED_BUILD" = true ]; then echo "$IMAGE_TAG"; exit 0; fi
            found=$($AWS ecr describe-images --repository-name "$ECR_REPO_PREFIX-api" \
                --image-ids imageTag="$SOURCE_TAG" --query 'imageDetails[0].imageTags' --output text \
              | tr -d '\\r' | tr '\\t' '\\n' \
              | awk -v p="$DEPLOY_PREFIX" 'index($0, p) == 1 { n = substr($0, length(p) + 1); if (n ~ /^[0-9]+$/) print n, $0 }' \
              | sort -n | tail -n 1 | cut -d' ' -f2)
            if [ -n "$found" ]; then echo "$found"; exit 0; fi
            # Images pushed without such a tag get this run's (same manifest, no rebuild).
            for c in api web; do
              repo="$ECR_REPO_PREFIX-$c"
              manifest=$($AWS ecr batch-get-image --repository-name "$repo" --image-ids imageTag="$SOURCE_TAG" \
                --query 'images[0].imageManifest' --output text)
              media_type=$($AWS ecr batch-get-image --repository-name "$repo" --image-ids imageTag="$SOURCE_TAG" \
                --query 'images[0].imageManifestMediaType' --output text | tr -d '\\r')
              $AWS ecr put-image --repository-name "$repo" --image-tag "$IMAGE_TAG" \
                --image-manifest "$manifest" --image-manifest-media-type "$media_type" >/dev/null
            done
            echo "$IMAGE_TAG"
          ''').trim().readLines().last()
          echo "Deploying images tagged ${env.DEPLOY_TAG}"
        } }
      }
    }

    // staging -> release oan-sandbox on the QA cluster, from the VPN deploy agent (as a2c's
    // "staging → QA cluster (helm)"). A failed health check only marks the build UNSTABLE.
    stage('staging → QA cluster (helm)') {
      when { beforeAgent true; branch 'staging' }
      agent { label 'oan-ci-deploy' }   // VPN agent with helm and kubectl; must reach the QA API
      options { timeout(time: 20, unit: 'MINUTES') }
      steps {
        checkout scm
        withCredentials([file(credentialsId: 'oan-qa-kubeconfig', variable: 'KUBECONFIG')]) {
          script {
            int rc = sh(returnStatus: true, script: '''
              API_IMAGE="$ECR_REGISTRY/$ECR_REPO_PREFIX-api:$DEPLOY_TAG" \
              WEB_IMAGE="$ECR_REGISTRY/$ECR_REPO_PREFIX-web:$DEPLOY_TAG" \
              HOST="$SANDBOX_HOSTNAME" FORCE="$FORCE_DEPLOY" \
                bash deployment/jenkins/deploy-cluster.sh
            ''')
            if (rc == 2) {
              unstable("Deployed, but https://${env.SANDBOX_HOSTNAME}/oan/health did not answer")
            } else if (rc != 0) {
              error("Staging deploy failed (exit ${rc})")
            }
          }
        }
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

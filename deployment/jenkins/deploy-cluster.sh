#!/usr/bin/env bash
# Installs or upgrades the oan-sandbox release on a cluster reached through a kubeconfig, from the deploy
# agent (label oan-ci-deploy): the staging branch on the QA cluster (qa.oanstaging.com), like
# oan_a2c_service's ci/deploy-helm-dev.sh. develop still deploys to its k3s VM over SSH (deploy.sh).
#
#   KUBECONFIG=... API_IMAGE=repo:tag WEB_IMAGE=repo:tag VALUES_FILE=... CHART_ID=... HOST=... \
#     NAMESPACE=sandbox RELEASE=oan-sandbox bash deployment/jenkins/deploy-cluster.sh
#
# Needs helm and kubectl on the agent, no AWS access: the node pulls from ECR with its own IAM role.
# The Secret named by secret.name in $VALUES_FILE and the database must already exist.
set -euo pipefail
: "${KUBECONFIG:?KUBECONFIG is required (credential oan-qa-kubeconfig)}"
: "${API_IMAGE:?}" "${WEB_IMAGE:?}" "${VALUES_FILE:?}" "${CHART_ID:?}" "${HOST:?}" "${NAMESPACE:?}" "${RELEASE:?}"
CHART_DIR=${CHART_DIR:-helm/oan-sandbox}
test -f "$VALUES_FILE" || { echo "Values file $VALUES_FILE is missing" >&2; exit 1; }

secret=$(sed -n '/^secret:/,/^[^ ]/s/^  name: *//p' "$VALUES_FILE" | tr -d '"' | head -n 1)
if [ -n "$secret" ] && ! kubectl -n "$NAMESPACE" get secret "$secret" >/dev/null 2>&1; then
  echo "Secret $secret is missing in namespace $NAMESPACE (DB_PASSWORD, JWT_*; see helm/oan-sandbox/values.yaml)." >&2
  exit 1
fi

# The release description records what was deployed, as deploy.sh does.
want="$CHART_ID api=${API_IMAGE##*:} web=${WEB_IMAGE##*:}"
# No jq on the deploy agent: the YAML form of the latest revision, one field per line.
latest=$(helm -n "$NAMESPACE" history "$RELEASE" --max 1 -o yaml 2>/dev/null || true)
have_status=$(printf '%s\n' "$latest" | sed -n 's/^ *status: *//p' | head -n 1)
have_desc=$(printf '%s\n' "$latest" | sed -n 's/^ *description: *//p' | head -n 1 | sed "s/^['\"]//; s/['\"]\$//")
echo "Deployed: ${have_status:-nothing} ${have_desc}"
if [ "${FORCE:-false}" != true ] && [ "$have_status" = deployed ] && [ "$have_desc" = "$want" ]; then
  echo "Up to date: $want"
  exit 0
fi
echo "Deploying: $want"

# --atomic only once a revision has deployed: a failed or cancelled upgrade then rolls back to it. Before that
# there is nothing to roll back to, and --atomic would uninstall the release, the uploads PVC included.
ATOMIC=()
if helm -n "$NAMESPACE" history "$RELEASE" -o yaml 2>/dev/null | grep -qE '^ *status: *(deployed|superseded)$'; then
  ATOMIC=(--atomic)
fi

# The values file and the images only (no --reuse-values): the whole release is in Git.
# 10m covers the API's start-up probe (5 min, including the database wait).
if ! helm upgrade --install "$RELEASE" "$CHART_DIR" --namespace "$NAMESPACE" -f "$VALUES_FILE" \
  --set api.image.repository="${API_IMAGE%:*}" --set-string api.image.tag="${API_IMAGE##*:}" \
  --set web.image.repository="${WEB_IMAGE%:*}" --set-string web.image.tag="${WEB_IMAGE##*:}" \
  ${ATOMIC[@]+"${ATOMIC[@]}"} --description "$want" --wait --timeout 10m; then
  echo "helm upgrade failed. Diagnostics:" >&2
  helm -n "$NAMESPACE" history "$RELEASE" --max 3 >&2 || true
  kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/instance="$RELEASE" -o wide >&2 || true
  for c in api web; do
    kubectl -n "$NAMESPACE" logs "deploy/$RELEASE-$c" --tail=100 >&2 || true
  done
  kubectl -n "$NAMESPACE" get events --sort-by=.lastTimestamp 2>/dev/null | tail -n 40 >&2 || true
  exit 1
fi
kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/instance="$RELEASE" -o wide

# Through APISIX, as partners reach it. UNSTABLE in Jenkins rather than failed: the release is deployed,
# and a DNS record or certificate that is not there yet should not roll it back.
for _ in $(seq 18); do
  if curl -sf --max-time 10 "https://$HOST/oan/health"; then
    echo
    exit 0
  fi
  sleep 10
done
echo "API health check on https://$HOST/oan/health failed (DNS, certificate or route)." >&2
exit 2

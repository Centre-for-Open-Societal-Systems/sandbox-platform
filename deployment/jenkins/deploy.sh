#!/usr/bin/env bash
# Runs on the dev k3s VM, piped over SSH by the Jenkinsfile:
#
#   ssh vm "API_IMAGE=... WEB_IMAGE=... CHART_DIR=... CHART_ID=... HOST=... bash -s" < deploy.sh
#
# Upgrades the `sandbox` release to the oan-helm chart in $CHART_DIR with the given
# images, unless that chart and those images are already deployed. The release
# (Secret, PostgreSQL, Ingress) is created by the Ansible playbook.
set -euo pipefail
: "${API_IMAGE:?}" "${WEB_IMAGE:?}" "${CHART_DIR:?}" "${CHART_ID:?}" "${HOST:?}"
NAMESPACE=${NAMESPACE:-develop}
RELEASE=${RELEASE:-sandbox}
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}

# The release description records what was deployed, e.g.
# "oan-helm main@1a2b3c4d5e6f chart 1.0.0-dev.6 api=<tag> web=<tag>".
want="$CHART_ID api=${API_IMAGE##*:} web=${WEB_IMAGE##*:}"
have=$(helm -n "$NAMESPACE" history "$RELEASE" --max 1 -o json | jq -r '.[0] | "\(.status) \(.description)"')
if [ "$have" = "deployed $want" ] && [ "${FORCE:-false}" != true ]; then
  echo "Up to date: $want"
  exit 0
fi
echo "Deployed: ${have}"
echo "Deploying: ${want}"

pull_args=()
if [ -n "${PULL_SECRET:-}" ]; then
  pull_args=(--set "api.imagePullSecrets[0].name=$PULL_SECRET" --set "web.imagePullSecrets[0].name=$PULL_SECRET")
fi

# --reset-then-reuse-values: defaults of the new chart version, plus the values
# set by Ansible on the release (hostname, database, gateway, Secret name).
helm -n "$NAMESPACE" upgrade "$RELEASE" "$CHART_DIR" --reset-then-reuse-values \
  --set api.image.repository="${API_IMAGE%:*}" --set-string api.image.tag="${API_IMAGE##*:}" \
  --set api.image.pullPolicy=IfNotPresent \
  --set web.image.repository="${WEB_IMAGE%:*}" --set-string web.image.tag="${WEB_IMAGE##*:}" \
  --set web.image.pullPolicy=IfNotPresent \
  "${pull_args[@]}" --description "$want" --wait --timeout 15m
kubectl -n "$NAMESPACE" get pods -o wide

# Through Traefik on this node, independent of DNS and the security group.
for _ in $(seq 30); do
  if curl -skf --resolve "$HOST:443:127.0.0.1" "https://$HOST/oan/health"; then
    echo
    exit 0
  fi
  sleep 10
done
echo "API health check failed" >&2
kubectl -n "$NAMESPACE" logs "deploy/$RELEASE-api" --tail=100 >&2 || true
exit 1

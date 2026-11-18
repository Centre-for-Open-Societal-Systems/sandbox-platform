#!/usr/bin/env bash
# Runs on the dev k3s VM, piped over SSH by the Jenkinsfile:
#
#   ssh vm "API_IMAGE=... WEB_IMAGE=... CHART_DIR=... VALUES_FILE=... CHART_ID=... HOST=... bash -s" < deploy.sh
#
# Upgrades $RELEASE to the chart in $CHART_DIR (helm/oan-sandbox of sandbox-platform)
# with $VALUES_FILE (helm/environments/<env>/oan-sandbox.yaml) and the given images,
# unless that chart and those images are already deployed. The release itself
# (Secret, database) must already exist.
#
# The chart's Ingress (ingress.enabled in the values file) serves $HOST:
# /oan -> API, / -> web.
set -euo pipefail
: "${API_IMAGE:?}" "${WEB_IMAGE:?}" "${CHART_DIR:?}" "${VALUES_FILE:?}" "${CHART_ID:?}" "${HOST:?}"
NAMESPACE=${NAMESPACE:-develop}
RELEASE=${RELEASE:-sandbox}
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}
test -f "$VALUES_FILE" || { echo "Values file $VALUES_FILE is missing" >&2; exit 1; }

# API_DIGEST / WEB_DIGEST (sha256:...), when set, pin the images: the chart renders
# repository@digest. Empty clears a digest left on the release, so the tag is used.
API_DIGEST=${API_DIGEST:-}
WEB_DIGEST=${WEB_DIGEST:-}
for d in "$API_DIGEST" "$WEB_DIGEST"; do
  if [ -n "$d" ] && ! [[ $d =~ ^sha256:[a-f0-9]{64}$ ]]; then
    echo "Invalid image digest: $d" >&2
    exit 1
  fi
done
short() { if [ -n "$1" ]; then printf '@%s' "${1:7:12}"; fi; }

# The release description records what was deployed, e.g.
# "sandbox-platform chart 1.0.0-dev.19 helm tree 1a2b3c4d5e6f api=<tag>@<digest> web=<tag>@<digest>".
want="$CHART_ID api=${API_IMAGE##*:}$(short "$API_DIGEST") web=${WEB_IMAGE##*:}$(short "$WEB_DIGEST")"

# A deploy cut off mid-upgrade (e.g. the Jenkins agent was a Spot instance that EC2
# reclaimed, dropping this SSH session) leaves the release pending-upgrade, and Helm
# then refuses every upgrade ("another operation is in progress"). A pending revision
# older than the upgrade timeout below is no longer running: roll back to the last
# good revision, then upgrade as usual. A younger one may still be running: stop.
PENDING_STALE_SECONDS=$((16 * 60))
latest=$(helm -n "$NAMESPACE" history "$RELEASE" --max 1 -o json | jq -r '.[0] | "\(.revision) \(.status)"')
read -r latest_rev latest_status <<<"$latest"
case "$latest_status" in
  pending-install|pending-upgrade|pending-rollback)
    created=$(kubectl -n "$NAMESPACE" get secret "sh.helm.release.v1.$RELEASE.v$latest_rev" \
      -o jsonpath='{.metadata.creationTimestamp}')
    age=$(( $(date +%s) - $(date -d "$created" +%s) ))
    if [ "$age" -lt "$PENDING_STALE_SECONDS" ]; then
      echo "Release $RELEASE revision $latest_rev is $latest_status since ${age}s ago:" \
        "another deploy may still be running. Retry after ${PENDING_STALE_SECONDS}s." >&2
      exit 1
    fi
    good=$(helm -n "$NAMESPACE" history "$RELEASE" --max 50 -o json \
      | jq -r '[.[] | select(.status == "deployed" or .status == "superseded")] | last | .revision // empty')
    if [ -z "$good" ]; then
      echo "Release $RELEASE is stuck $latest_status (revision $latest_rev) with no good revision" \
        "to roll back to; fix it by hand." >&2
      exit 1
    fi
    echo "Release $RELEASE revision $latest_rev stuck $latest_status for ${age}s; rolling back to revision $good"
    helm -n "$NAMESPACE" rollback "$RELEASE" "$good" --wait --timeout 10m
    ;;
esac

have=$(helm -n "$NAMESPACE" history "$RELEASE" --max 1 -o json | jq -r '.[0] | "\(.status) \(.description)"')
if [ "$have" = "deployed $want" ] && [ "${FORCE:-false}" != true ]; then
  echo "Up to date: $want"
  exit 0
fi
echo "Deployed: ${have}"
echo "Deploying: ${want}"

# The node pulls from ECR itself: k3s runs AWS's ecr-credential-provider with the
# VM's instance role, so no pull Secret is needed. The empty lists also clear the
# ecr-pull Secret that earlier releases reused through --reset-then-reuse-values.
# PULL_SECRET still names a Secret for clusters without the credential provider.
# --set-json, not --set 'x={}': Helm 3 merges --set {} with the reused values as
# [""], which the API server rejects (imagePullSecrets entries must be objects).
pull_args=(--set-json 'api.imagePullSecrets=[]' --set-json 'web.imagePullSecrets=[]')
if [ -n "${PULL_SECRET:-}" ]; then
  pull_args=(--set "api.imagePullSecrets[0].name=$PULL_SECRET" --set "web.imagePullSecrets[0].name=$PULL_SECRET")
fi

# Earlier deploys created the Ingress $RELEASE with kubectl; Helm only takes over an
# object that carries its release label and annotations. Idempotent.
if kubectl -n "$NAMESPACE" get ingress "$RELEASE" >/dev/null 2>&1; then
  owner=$(kubectl -n "$NAMESPACE" get ingress "$RELEASE" \
    -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}')
  if [ "$owner" != "$RELEASE" ]; then
    echo "Handing Ingress $RELEASE over to Helm release $RELEASE"
    kubectl -n "$NAMESPACE" label ingress "$RELEASE" app.kubernetes.io/managed-by=Helm --overwrite
    kubectl -n "$NAMESPACE" annotate ingress "$RELEASE" --overwrite \
      meta.helm.sh/release-name="$RELEASE" meta.helm.sh/release-namespace="$NAMESPACE"
  fi
fi

# --reset-then-reuse-values: defaults of the new chart version, then the values set
# on the release before (by Ansible: Secret name and anything not in the file), then
# $VALUES_FILE, then the images below. The file wins where it and the release differ.
helm -n "$NAMESPACE" upgrade "$RELEASE" "$CHART_DIR" --reset-then-reuse-values \
  -f "$VALUES_FILE" \
  --set api.image.repository="${API_IMAGE%:*}" --set-string api.image.tag="${API_IMAGE##*:}" \
  --set-string api.image.digest="$API_DIGEST" --set api.image.pullPolicy=IfNotPresent \
  --set web.image.repository="${WEB_IMAGE%:*}" --set-string web.image.tag="${WEB_IMAGE##*:}" \
  --set-string web.image.digest="$WEB_DIGEST" --set web.image.pullPolicy=IfNotPresent \
  "${pull_args[@]}" --description "$want" --wait --timeout 15m
kubectl -n "$NAMESPACE" get pods -o wide

# Through the ingress controller on this node (Traefik, or APISIX on hostPort
# 80/443), independent of DNS and the security group. HTTPS first; plain HTTP
# when the controller has no certificate for $HOST.
for _ in $(seq 30); do
  if curl -skf --max-time 10 --resolve "$HOST:443:127.0.0.1" "https://$HOST/oan/health" \
     || curl -sf --max-time 10 --resolve "$HOST:80:127.0.0.1" "http://$HOST/oan/health"; then
    echo
    exit 0
  fi
  sleep 10
done
echo "API health check failed" >&2
kubectl -n "$NAMESPACE" logs "deploy/$RELEASE-api" --tail=100 >&2 || true
exit 1

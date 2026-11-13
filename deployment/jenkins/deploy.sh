#!/usr/bin/env bash
# Runs on the dev k3s VM, piped over SSH by the Jenkinsfile:
#
#   ssh vm "API_IMAGE=... WEB_IMAGE=... CHART_DIR=... CHART_ID=... HOST=... bash -s" < deploy.sh
#
# Upgrades $RELEASE to the oan-helm chart in $CHART_DIR with the given images,
# unless that chart and those images are already deployed. The release itself
# (Secret, database settings) must already exist.
#
# With INGRESS_CLASS set (e.g. apisix), also applies an Ingress for $HOST:
# /oan -> API, / -> web. The chart only ships an Istio VirtualService.
set -euo pipefail
: "${API_IMAGE:?}" "${WEB_IMAGE:?}" "${CHART_DIR:?}" "${CHART_ID:?}" "${HOST:?}"
NAMESPACE=${NAMESPACE:-develop}
RELEASE=${RELEASE:-sandbox}
export KUBECONFIG=${KUBECONFIG:-$HOME/.kube/config}

# Idempotent, so it runs even when the release is up to date.
if [ -n "${INGRESS_CLASS:-}" ]; then
  # Prefix, not ImplementationSpecific: APISIX treats the latter as an exact match.
  kubectl -n "$NAMESPACE" apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: $RELEASE
  labels:
    app.kubernetes.io/instance: $RELEASE
    app.kubernetes.io/managed-by: sandbox-platform-jenkins
spec:
  ingressClassName: $INGRESS_CLASS
  rules:
    - host: $HOST
      http:
        paths:
          - path: /oan
            pathType: Prefix
            backend:
              service:
                name: $RELEASE-api
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: $RELEASE-web
                port:
                  number: 80
EOF
fi

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
# "oan-helm main@1a2b3c4d5e6f chart 1.0.0-dev.6 api=<tag>@<digest> web=<tag>@<digest>".
want="$CHART_ID api=${API_IMAGE##*:}$(short "$API_DIGEST") web=${WEB_IMAGE##*:}$(short "$WEB_DIGEST")"
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

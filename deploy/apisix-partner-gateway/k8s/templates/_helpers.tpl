{{/* The sandbox realm's issuer, as written into its tokens. */}}
{{- define "partnerGateway.issuer" -}}
{{- required "keycloak.issuer is required (e.g. https://keycloak.<domain>/realms/partner)" .Values.keycloak.issuer | trimSuffix "/" -}}
{{- end -}}

{{/* The realm's discovery document as APISIX reaches it. */}}
{{- define "partnerGateway.discovery" -}}
{{- .Values.keycloak.discovery | default (printf "%s/.well-known/openid-configuration" (include "partnerGateway.issuer" .)) -}}
{{- end -}}

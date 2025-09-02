{{/*
Generic service template for request management services
Usage: {{ include "self-service-agent.requestManagementService" (dict "serviceName" "request-manager" "serviceConfig" .Values.requestManagement.requestManager "imageKey" "requestManager" "context" .) }}
*/}}
{{- define "self-service-agent.requestManagementService" -}}
{{- if .context.Values.requestManagement.enabled }}
{{ include "self-service-agent.serviceDeployment" . }}
{{- end }}
{{- end }}

{{/*
Environment variable helpers for consistent env var generation across Knative Services and Deployments
*/}}

{{/*
Generate database environment variables from pgvector secret
*/}}
{{- define "self-service-agent.dbEnvVars" -}}
- name: POSTGRES_HOST
  valueFrom:
    secretKeyRef:
      name: pgvector
      key: host
- name: POSTGRES_PORT
  valueFrom:
    secretKeyRef:
      name: pgvector
      key: port
- name: POSTGRES_DB
  valueFrom:
    secretKeyRef:
      name: pgvector
      key: dbname
- name: POSTGRES_USER
  valueFrom:
    secretKeyRef:
      name: pgvector
      key: user
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: pgvector
      key: password
{{- end }}

{{/*
Generate common environment variables for all services
*/}}
{{- define "self-service-agent.commonEnvVars" -}}
- name: LOG_LEVEL
  value: "INFO"
- name: SQL_DEBUG
  value: "false"
- name: EXPECTED_MIGRATION_VERSION
  value: {{ .Values.database.expectedMigrationVersion | default "001" | quote }}
- name: BROKER_URL
  value: {{ if .Values.requestManagement.knative.eventing.enabled }}{{ printf "%s/%s/%s" .Values.requestManagement.knative.broker.url .Release.Namespace .Values.requestManagement.knative.broker.name | quote }}{{ else }}{{ printf "http://%s-mock-eventing.%s.svc.cluster.local:8080/%s/%s" (include "self-service-agent.fullname" .) .Release.Namespace .Release.Namespace .Values.requestManagement.knative.broker.name | quote }}{{ end }}
- name: EVENTING_ENABLED
  value: {{ .Values.requestManagement.knative.eventing.enabled | quote }}
- name: PORT
  value: "8080"
- name: HOST
  value: "0.0.0.0"
{{- end }}

{{/*
Generate Request Manager specific environment variables
*/}}
{{- define "self-service-agent.requestManagerEnvVars" -}}
- name: EVENT_MAX_RETRIES
  value: "3"
- name: EVENT_BASE_DELAY
  value: "1.0"
# Service Mesh and Security Configuration
- name: SLACK_SIGNING_SECRET
  valueFrom:
    secretKeyRef:
      name: slack-signing-secret
      key: signing-secret
      optional: true
- name: SNOW_API_KEY
  valueFrom:
    secretKeyRef:
      name: api-keys
      key: snow-integration
      optional: true
- name: HR_API_KEY
  valueFrom:
    secretKeyRef:
      name: api-keys
      key: hr-system
      optional: true
- name: MONITORING_API_KEY
  valueFrom:
    secretKeyRef:
      name: api-keys
      key: monitoring-system
      optional: true
# JWT Authentication Configuration
- name: JWT_ENABLED
  value: {{ .Values.security.jwt.enabled | default false | quote }}
- name: JWT_ISSUERS
  value: {{ .Values.security.jwt.issuers | toJson | quote }}
- name: JWT_VERIFY_SIGNATURE
  value: {{ .Values.security.jwt.validation.verifySignature | default true | quote }}
- name: JWT_VERIFY_EXPIRATION
  value: {{ .Values.security.jwt.validation.verifyExpiration | default true | quote }}
- name: JWT_VERIFY_AUDIENCE
  value: {{ .Values.security.jwt.validation.verifyAudience | default true | quote }}
- name: JWT_VERIFY_ISSUER
  value: {{ .Values.security.jwt.validation.verifyIssuer | default true | quote }}
- name: JWT_LEEWAY
  value: {{ .Values.security.jwt.validation.leeway | default 60 | quote }}
# API Key Authentication Configuration
- name: API_KEYS_ENABLED
  value: {{ .Values.security.apiKeys.enabled | default true | quote }}
- name: WEB_API_KEYS
  value: {{ .Values.security.apiKeys.webKeys | toJson | quote }}
{{- end }}

{{/*
Generate Agent Service specific environment variables
*/}}
{{- define "self-service-agent.agentServiceEnvVars" -}}
- name: LLAMA_STACK_URL
  value: {{ .Values.llama_stack_url | default "http://llamastack:8321" | quote }}
- name: DEFAULT_AGENT_ID
  value: {{ if hasKey .Values "agent" }}{{ .Values.agent.defaultAgentId | default "routing-agent" | quote }}{{ else }}"routing-agent"{{ end }}
- name: AGENT_TIMEOUT
  value: {{ if hasKey .Values "agent" }}{{ .Values.agent.timeout | default "120" | quote }}{{ else }}"120"{{ end }}
{{- end }}

{{/*
Generate Integration Dispatcher specific environment variables
*/}}
{{- define "self-service-agent.integrationDispatcherEnvVars" -}}
# Integration-specific environment variables (optional - loaded from secrets)
- name: SLACK_BOT_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "self-service-agent.fullname" . }}-integration-secrets
      key: slack-bot-token
      optional: true
- name: SLACK_SIGNING_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "self-service-agent.fullname" . }}-integration-secrets
      key: slack-signing-secret
      optional: true
# Additional SMTP configuration from secrets (matching Knative Service)
- name: SMTP_HOST
  valueFrom:
    secretKeyRef:
      name: {{ include "self-service-agent.fullname" . }}-integration-secrets
      key: smtp-host
      optional: true
- name: SMTP_PORT
  valueFrom:
    secretKeyRef:
      name: {{ include "self-service-agent.fullname" . }}-integration-secrets
      key: smtp-port
      optional: true
- name: SMTP_USERNAME
  valueFrom:
    secretKeyRef:
      name: {{ include "self-service-agent.fullname" . }}-integration-secrets
      key: smtp-username
      optional: true
- name: SMTP_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "self-service-agent.fullname" . }}-integration-secrets
      key: smtp-password
      optional: true
- name: SMTP_USE_TLS
  valueFrom:
    secretKeyRef:
      name: {{ include "self-service-agent.fullname" . }}-integration-secrets
      key: smtp-use-tls
      optional: true
- name: FROM_EMAIL
  valueFrom:
    secretKeyRef:
      name: {{ include "self-service-agent.fullname" . }}-integration-secrets
      key: from-email
      optional: true
- name: FROM_NAME
  valueFrom:
    secretKeyRef:
      name: {{ include "self-service-agent.fullname" . }}-integration-secrets
      key: from-name
      optional: true
{{- end }}

{{/*
Generate all environment variables for Request Manager
*/}}
{{- define "self-service-agent.requestManagerAllEnvVars" -}}
{{- include "self-service-agent.dbEnvVars" . }}
{{- include "self-service-agent.commonEnvVars" . }}
{{- include "self-service-agent.requestManagerEnvVars" . }}
{{- end }}

{{/*
Generate all environment variables for Agent Service
*/}}
{{- define "self-service-agent.agentServiceAllEnvVars" -}}
{{- include "self-service-agent.dbEnvVars" . }}
{{- include "self-service-agent.commonEnvVars" . }}
{{- include "self-service-agent.agentServiceEnvVars" . }}
{{- end }}

{{/*
Generate all environment variables for Integration Dispatcher
*/}}
{{- define "self-service-agent.integrationDispatcherAllEnvVars" -}}
{{- include "self-service-agent.dbEnvVars" . }}
{{- include "self-service-agent.commonEnvVars" . }}
{{- include "self-service-agent.integrationDispatcherEnvVars" . }}
{{- end }}

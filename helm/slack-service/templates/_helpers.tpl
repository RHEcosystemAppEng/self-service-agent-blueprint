{{/*
Expand the name of the chart.
*/}}
{{- define "slack-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "slack-service.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "slack-service.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "slack-service.labels" -}}
helm.sh/chart: {{ include "slack-service.chart" . }}
{{ include "slack-service.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "slack-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "slack-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the secret to use
*/}}
{{- define "slack-service.secretName" -}}
{{- printf "%s-slack-secret" (include "slack-service.fullname" .) }}
{{- end }}

{{/*
Create the name of the service to use
*/}}
{{- define "slack-service.serviceName" -}}
{{- printf "%s" (include "slack-service.fullname" .) }}
{{- end }}

{{/*
Create the name of the route to use
*/}}
{{- define "slack-service.routeName" -}}
{{- printf "%s" (include "slack-service.fullname" .) }}
{{- end }}
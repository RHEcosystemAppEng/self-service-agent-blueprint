{{- define "zammad-embed.normalizePathPrefix" -}}
{{- $p := . | default "/demo-portal" | trimSuffix "/" | trimPrefix "/" -}}
{{- printf "/%s" $p -}}
{{- end -}}

{{- define "zammad-embed.zammadHost" -}}
{{- $h := .Values.zammadRouteHost | default "" | trim -}}
{{- if $h -}}
{{- $h -}}
{{- else -}}
{{- $zr := lookup "route.openshift.io/v1" "Route" .Release.Namespace "ssa-zammad" -}}
{{- if $zr }}{{ $zr.spec.host }}{{ end -}}
{{- end -}}
{{- end -}}

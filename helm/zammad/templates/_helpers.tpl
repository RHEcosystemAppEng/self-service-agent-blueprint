{{- define "ticketingZammad.zammadNginxService" -}}
{{- printf "%s-nginx" (default .Release.Name .Values.zammad.fullnameOverride) -}}
{{- end -}}

{{- define "ticketingZammad.zammadWebsocketService" -}}
{{- printf "%s-websocket" (default .Release.Name .Values.zammad.fullnameOverride) -}}
{{- end -}}

{{- define "ticketingZammad.zammadRailsserverService" -}}
{{- printf "%s-railsserver" (default .Release.Name .Values.zammad.fullnameOverride) -}}
{{- end -}}

{{- define "ticketingZammad.edgeProxyService" -}}
{{- printf "%s-edge" (default .Release.Name .Values.zammad.fullnameOverride) -}}
{{- end -}}

{{- define "ticketingZammad.disableAttachmentsCss" -}}
.article-attachment,.attachmentPlaceholder,.attachmentPlaceholder-inputHolder,.attachmentPlaceholder-label,.attachmentUpload,.dropArea{display:none!important;pointer-events:none!important}
{{- end -}}

{{- define "ticketingZammad.edgeProxyHtmlLocation" -}}
        location {{ .location }} {
            proxy_http_version 1.1;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $forwarded_proto;
            proxy_set_header X-Forwarded-Ssl on;
            proxy_set_header X-Forwarded-Host $http_host;
            proxy_set_header Accept-Encoding "";
            proxy_read_timeout 300s;
            proxy_pass http://{{ .zammadNginx }}:8080;

            gunzip on;
            sub_filter_once on;
            sub_filter_types text/html;
            sub_filter '</head>' '{{ .headInject }}';
        }
{{- end -}}

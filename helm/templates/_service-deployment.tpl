{{/*
Generic service deployment template
Usage: {{ include "self-service-agent.serviceDeployment" (dict "serviceName" "request-manager" "serviceConfig" .Values.requestManagement.requestManager "imageKey" "requestManager" "context" .) }}
*/}}
{{- define "self-service-agent.serviceDeployment" -}}
{{- $serviceName := .serviceName -}}
{{- $serviceConfig := .serviceConfig -}}
{{- $imageKey := .imageKey -}}
{{- $context := .context -}}
{{- $fullName := include "self-service-agent.fullname" $context -}}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $fullName }}-{{ $serviceName }}
  namespace: {{ $context.Release.Namespace }}
  labels:
    {{- include "self-service-agent.labels" $context | nindent 4 }}
    app: {{ $fullName }}-{{ $serviceName }}
    component: {{ $serviceName }}
spec:
  replicas: {{ $serviceConfig.replicas | default 2 }}
  selector:
    matchLabels:
      {{- include "self-service-agent.selectorLabels" $context | nindent 6 }}
      app: {{ $fullName }}-{{ $serviceName }}
      component: {{ $serviceName }}
  template:
    metadata:
      labels:
        {{- include "self-service-agent.labels" $context | nindent 8 }}
        app: {{ $fullName }}-{{ $serviceName }}
        component: {{ $serviceName }}
        version: v1
      annotations:
        app.kubernetes.io/component: "{{ $serviceName }}"
    spec:
      serviceAccountName: {{ include "self-service-agent.serviceAccountName" $context }}
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: {{ $serviceName }}
        image: "{{ $context.Values.image.registry }}/{{ index $context.Values.image $imageKey }}:{{ $context.Values.image.tag | default $context.Chart.AppVersion }}"
        imagePullPolicy: {{ $context.Values.image.pullPolicy }}
        ports:
        - containerPort: 8080
          protocol: TCP
          name: http
        env:
        {{- if eq $serviceName "request-manager" }}
        {{- include "self-service-agent.requestManagerAllEnvVars" $context | nindent 8 }}
        {{- else if eq $serviceName "agent-service" }}
        {{- include "self-service-agent.agentServiceAllEnvVars" $context | nindent 8 }}
        {{- else if eq $serviceName "integration-dispatcher" }}
        {{- include "self-service-agent.integrationDispatcherAllEnvVars" $context | nindent 8 }}
        {{- end }}
        {{- if $context.Values.otelExporter }}
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: {{ $context.Values.otelExporter }}
        {{- end }}
        # Service-specific environment variables
        # All environment variables are now handled by the templates above
        {{- if $serviceConfig.resources }}
        resources:
          {{- if $serviceConfig.resources.requests }}
          requests:
            {{- if $serviceConfig.resources.requests.memory }}
            memory: {{ $serviceConfig.resources.requests.memory }}
            {{- end }}
            {{- if $serviceConfig.resources.requests.cpu }}
            cpu: {{ $serviceConfig.resources.requests.cpu }}
            {{- end }}
          {{- end }}
          {{- if $serviceConfig.resources.limits }}
          limits:
            {{- if $serviceConfig.resources.limits.memory }}
            memory: {{ $serviceConfig.resources.limits.memory }}
            {{- end }}
            {{- if $serviceConfig.resources.limits.cpu }}
            cpu: {{ $serviceConfig.resources.limits.cpu }}
            {{- end }}
          {{- end }}
        {{- end }}
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop:
            - ALL
          runAsNonRoot: true
          seccompProfile:
            type: RuntimeDefault
        {{- if $serviceConfig.healthChecks }}
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: {{ $serviceConfig.healthChecks.livenessProbe.initialDelaySeconds }}
          periodSeconds: {{ $serviceConfig.healthChecks.livenessProbe.periodSeconds }}
          timeoutSeconds: {{ $serviceConfig.healthChecks.livenessProbe.timeoutSeconds }}
          failureThreshold: {{ $serviceConfig.healthChecks.livenessProbe.failureThreshold }}
          successThreshold: {{ $serviceConfig.healthChecks.livenessProbe.successThreshold }}
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: {{ $serviceConfig.healthChecks.readinessProbe.initialDelaySeconds }}
          periodSeconds: {{ $serviceConfig.healthChecks.readinessProbe.periodSeconds }}
          timeoutSeconds: {{ $serviceConfig.healthChecks.readinessProbe.timeoutSeconds }}
          successThreshold: {{ $serviceConfig.healthChecks.readinessProbe.successThreshold }}
          failureThreshold: {{ $serviceConfig.healthChecks.readinessProbe.failureThreshold }}
        startupProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: {{ $serviceConfig.healthChecks.startupProbe.initialDelaySeconds }}
          periodSeconds: {{ $serviceConfig.healthChecks.startupProbe.periodSeconds }}
          timeoutSeconds: {{ $serviceConfig.healthChecks.startupProbe.timeoutSeconds }}
          failureThreshold: {{ $serviceConfig.healthChecks.startupProbe.failureThreshold }}
          successThreshold: {{ $serviceConfig.healthChecks.startupProbe.successThreshold }}
        {{- else }}
        # Default health checks if not configured in values.yaml
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          successThreshold: 1
          failureThreshold: 3
        startupProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: {{- if eq $serviceName "agent-service" }} 15{{- else if eq $serviceName "integration-dispatcher" }} 20{{- else }} 10{{- end }}
          periodSeconds: 5
          timeoutSeconds: {{- if eq $serviceName "integration-dispatcher" }} 10{{- else }} 3{{- end }}
          failureThreshold: {{- if eq $serviceName "agent-service" }} 60{{- else if eq $serviceName "integration-dispatcher" }} 30{{- else }} 30{{- end }}
        {{- end }}
      restartPolicy: Always
      terminationGracePeriodSeconds: {{- if eq $serviceName "agent-service" }} 60{{- else }} 30{{- end }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $fullName }}-{{ $serviceName }}
  namespace: {{ $context.Release.Namespace }}
  labels:
    {{- include "self-service-agent.labels" $context | nindent 4 }}
    app: {{ $fullName }}-{{ $serviceName }}
    component: {{ $serviceName }}
spec:
  type: ClusterIP
  selector:
    {{- include "self-service-agent.selectorLabels" $context | nindent 4 }}
    app: {{ $fullName }}-{{ $serviceName }}
    component: {{ $serviceName }}
  ports:
  - name: http
    port: 80
    targetPort: 8080
    protocol: TCP
{{- if $serviceConfig.autoscaling.enabled }}
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ $fullName }}-{{ $serviceName }}
  namespace: {{ $context.Release.Namespace }}
  labels:
    {{- include "self-service-agent.labels" $context | nindent 4 }}
    app: {{ $fullName }}-{{ $serviceName }}
    component: {{ $serviceName }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ $fullName }}-{{ $serviceName }}
  minReplicas: {{ $serviceConfig.autoscaling.minReplicas | default 1 }}
  maxReplicas: {{ $serviceConfig.autoscaling.maxReplicas | default 10 }}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: {{ $serviceConfig.autoscaling.targetCPUUtilization | default 70 }}
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: {{ $serviceConfig.autoscaling.targetMemoryUtilization | default 80 }}
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: {{- if eq $serviceName "agent-service" }} 30{{- else }} 60{{- end }}
      policies:
      - type: Percent
        value: {{- if eq $serviceName "agent-service" }} 100{{- else }} 50{{- end }}
        periodSeconds: 60
      - type: Pods
        value: {{- if eq $serviceName "agent-service" }} 4{{- else }} 2{{- end }}
        periodSeconds: 60
      selectPolicy: Max
{{- end }}
{{- end }}

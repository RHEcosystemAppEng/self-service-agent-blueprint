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
        # Database configuration
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
        # Common environment variables
        - name: LOG_LEVEL
          value: "INFO"
        - name: SQL_DEBUG
          value: "false"
        - name: EXPECTED_MIGRATION_VERSION
          value: {{ $context.Values.database.expectedMigrationVersion | default "001" | quote }}
        - name: BROKER_URL
          value: "{{ $context.Values.requestManagement.knative.broker.url }}/{{ $context.Release.Namespace }}/{{ $context.Values.requestManagement.knative.broker.name }}"
        - name: PORT
          value: "8080"
        - name: HOST
          value: "0.0.0.0"
        {{- if eq $serviceName "agent-service" }}
        # Agent Service specific environment variables
        - name: LLAMA_STACK_URL
          value: {{ $context.Values.llama_stack_url | quote }}
        - name: DEFAULT_AGENT_ID
          value: "routing-agent"
        - name: AGENT_TIMEOUT
          value: "120"
        {{- end }}
        {{- if eq $serviceName "integration-dispatcher" }}
        # Integration-specific environment variables (optional - loaded from secrets)
        - name: SLACK_BOT_TOKEN
          valueFrom:
            secretKeyRef:
              name: {{ $fullName }}-integration-secrets
              key: slack-bot-token
              optional: true
        - name: SLACK_SIGNING_SECRET
          valueFrom:
            secretKeyRef:
              name: {{ $fullName }}-integration-secrets
              key: slack-signing-secret
              optional: true
        # SMTP configuration from secrets
        - name: SMTP_HOST
          valueFrom:
            secretKeyRef:
              name: {{ $fullName }}-integration-secrets
              key: smtp-host
              optional: true
        - name: SMTP_PORT
          valueFrom:
            secretKeyRef:
              name: {{ $fullName }}-integration-secrets
              key: smtp-port
              optional: true
        - name: SMTP_USERNAME
          valueFrom:
            secretKeyRef:
              name: {{ $fullName }}-integration-secrets
              key: smtp-username
              optional: true
        - name: SMTP_PASSWORD
          valueFrom:
            secretKeyRef:
              name: {{ $fullName }}-integration-secrets
              key: smtp-password
              optional: true
        - name: SMTP_USE_TLS
          valueFrom:
            secretKeyRef:
              name: {{ $fullName }}-integration-secrets
              key: smtp-use-tls
              optional: true
        - name: FROM_EMAIL
          valueFrom:
            secretKeyRef:
              name: {{ $fullName }}-integration-secrets
              key: from-email
              optional: true
        - name: FROM_NAME
          valueFrom:
            secretKeyRef:
              name: {{ $fullName }}-integration-secrets
              key: from-name
              optional: true
        {{- end }}
        {{- if eq $serviceName "request-manager" }}
        # Service Mesh and Security Configuration
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
        # Agent Service Configuration
        - name: AGENT_SERVICE_HOST
          value: "{{ $fullName }}-agent-service"
        - name: AGENT_SERVICE_PORT
          value: "80"
        {{- end }}
        resources:
          requests:
            memory: {{ $serviceConfig.resources.requests.memory }}
            cpu: {{ $serviceConfig.resources.requests.cpu }}
          limits:
            memory: {{ $serviceConfig.resources.limits.memory }}
            cpu: {{ $serviceConfig.resources.limits.cpu }}
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

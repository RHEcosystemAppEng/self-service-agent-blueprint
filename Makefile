# Makefile for RAG Deployment
ifeq ($(NAMESPACE),)
ifneq (,$(filter namespace install uninstall helm-install-test helm-install-prod helm-install-demo helm-install-ticketing helm-export-demo helm-export-validate-demo ansible-apply-demo ansible-teardown-demo helm-uninstall helm-status helm-cleanup-eventing helm-cleanup-jobs deploy-email-server undeploy-email-server deploy-zammad undeploy-zammad zammad-set-token zammad-bootstrap-token zammad-trigger-autowizard print-urls verify-triggers jaeger-deploy jaeger-undeploy test-session-serialization-integration test-session-reclaim-integration test-session-background-reclaim-integration,$(MAKECMDGOALS)))
$(error NAMESPACE is not set)
endif
endif

# Auto-detect version based on git branch if VERSION is not explicitly set
# - main branch: uses base version (0.0.2) for stable builds
# - dev branch: uses '0.0.2-dev' tag (matches CI builds)
# - branches forked from dev: uses '0.0.2-dev' tag (dev builds)
# - all other branches: uses base version (0.0.2) for stable builds (default)
# Set VERSION explicitly to override this behavior (e.g., VERSION=latest)
BASE_VERSION := 0.0.13
DEV_VERSION := $(BASE_VERSION)-dev
GIT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
# Check if branch was forked from dev by comparing how close merge-bases are to branch tip
# If merge-base with dev is closer (fewer commits away) than merge-base with main, likely forked from dev
IS_FORKED_FROM_DEV := $(shell \
  BRANCH="$(GIT_BRANCH)"; \
  if [ -n "$$BRANCH" ] && [ "$$BRANCH" != "main" ] && [ "$$BRANCH" != "dev" ]; then \
    if git rev-parse --verify main >/dev/null 2>&1 && git rev-parse --verify dev >/dev/null 2>&1; then \
      MERGE_BASE_MAIN=$$(git merge-base $$BRANCH main 2>/dev/null); \
      MERGE_BASE_DEV=$$(git merge-base $$BRANCH dev 2>/dev/null); \
      if [ -n "$$MERGE_BASE_MAIN" ] && [ -n "$$MERGE_BASE_DEV" ]; then \
        DISTANCE_FROM_MAIN=$$(git rev-list --count $$MERGE_BASE_MAIN..$$BRANCH 2>/dev/null || echo "999"); \
        DISTANCE_FROM_DEV=$$(git rev-list --count $$MERGE_BASE_DEV..$$BRANCH 2>/dev/null || echo "999"); \
        if [ "$$DISTANCE_FROM_DEV" -lt "$$DISTANCE_FROM_MAIN" ]; then \
          echo "true"; \
        else \
          echo "false"; \
        fi; \
      elif [ -n "$$MERGE_BASE_DEV" ]; then \
        echo "true"; \
      elif [ -n "$$MERGE_BASE_MAIN" ]; then \
        echo "false"; \
      else \
        echo "false"; \
      fi; \
    else \
      echo "false"; \
    fi; \
  else \
    echo "false"; \
  fi \
)
# Only auto-detect if VERSION was not explicitly set by user (via env var or make arg)
ifeq ($(origin VERSION),undefined)
  ifeq ($(GIT_BRANCH),main)
    VERSION := $(BASE_VERSION)
  else ifeq ($(GIT_BRANCH),dev)
    VERSION := $(DEV_VERSION)
  else ifeq ($(IS_FORKED_FROM_DEV),true)
    # Branch was forked from dev, use dev version
    VERSION := $(DEV_VERSION)
  else
    # Default: use stable version (includes branches forked from main, branches with no connection to either, etc.)
    VERSION := $(BASE_VERSION)
  endif
else
  # VERSION was explicitly set by user, use it as-is
endif

# Replica count - can be set with REPLICA_COUNT=X to override all replica counts
# If not set, uses defaults from helm/values.yaml
REPLICA_COUNT ?=
CONTAINER_TOOL ?= podman
REGISTRY ?= quay.io/rh-ai-quickstart
PYTHON_VERSION ?= 3.12
ARCH ?= linux/amd64
# Pull policy: --policy=always for podman (pull newest); empty for docker (always pulls by default)
PULL_POLICY := $(if $(filter podman,$(CONTAINER_TOOL)),--policy=always,)
REQUEST_MGR_IMG ?= $(REGISTRY)/self-service-agent-request-manager:$(VERSION)
AGENT_SERVICE_IMG ?= $(REGISTRY)/self-service-agent-service:$(VERSION)
INTEGRATION_DISPATCHER_IMG ?= $(REGISTRY)/self-service-agent-integration-dispatcher:$(VERSION)
MCP_SNOW_IMG ?= $(REGISTRY)/self-service-agent-snow-mcp:$(VERSION)
MCP_ZAMMAD_IMG ?= $(REGISTRY)/self-service-agent-zammad-mcp:$(VERSION)
MOCK_EVENTING_IMG ?= $(REGISTRY)/self-service-agent-mock-eventing:$(VERSION)
MOCK_SERVICENOW_IMG ?= $(REGISTRY)/self-service-agent-mock-servicenow:$(VERSION)
PROMPTGUARD_IMG ?= $(REGISTRY)/self-service-agent-promptguard:$(VERSION)
ZAMMAD_BOOTSTRAP_IMG ?= $(REGISTRY)/self-service-agent-zammad-bootstrap:$(VERSION)

# For retag-all-images: tag from REGISTRY/VERSION to NEW_REGISTRY/NEW_VERSION (set both when retagging)
NEW_REGISTRY ?=
NEW_VERSION ?=

MAKEFLAGS += --no-print-directory

# Default values
POSTGRES_USER ?= postgres
POSTGRES_PASSWORD ?= rag_password
POSTGRES_DBNAME ?= rag_blueprint

# HF_TOKEN is only required if LLM_URL is not set
ifeq ($(LLM_URL),)
HF_TOKEN ?= $(shell bash -c 'read -r -p "Enter Hugging Face Token: " HF_TOKEN; echo $$HF_TOKEN')
else
HF_TOKEN ?=
endif

MAIN_CHART_NAME := self-service-agent
HELM_EXPORT_DIR ?= ansible/helm-export
TOLERATIONS_TEMPLATE=[{"key":"$(1)","effect":"NoSchedule","operator":"Exists"}]
INGRESS_PREFIX := ssa

# Slack Configuration - only when ENABLE_SLACK set to true
ifeq ($(ENABLE_SLACK),true)
ifndef SLACK_BOT_TOKEN
SLACK_BOT_TOKEN := $(shell bash -c 'read -r -p "Enter Slack Bot Token (xoxb-...): " TOKEN; echo $$TOKEN')
endif
ifndef SLACK_SIGNING_SECRET
SLACK_SIGNING_SECRET := $(shell bash -c 'read -r -p "Enter Slack Signing Secret: " SECRET; echo $$SECRET')
endif
endif

# Check if Slack should be enabled
SLACK_ENABLED := $(if $(and $(SLACK_BOT_TOKEN),$(SLACK_SIGNING_SECRET)),true,false)

# ServiceNow Configuration (use mocks by default)
SERVICENOW_INSTANCE_URL ?= http://self-service-agent-mock-servicenow:8080
SERVICENOW_API_KEY ?= now_mock_api_key
SERVICENOW_LAPTOP_REFRESH_ID ?= mock_laptop_refresh_id
SERVICENOW_LAPTOP_AVOID_DUPLICATES ?= false
SERVICENOW_LAPTOP_REQUEST_LIMITS ?=
TEST_USERS ?=

# ServiceNow Developer Portal Credentials (for waking up PDI)
SERVICENOW_DEV_PORTAL_USERNAME ?=
SERVICENOW_DEV_PORTAL_PASSWORD ?=

# PromptGuard Configuration
PROMPTGUARD_MODEL ?= llama-prompt-guard-2-86m
PROMPTGUARD_MODEL_ID ?= meta-llama/Llama-Prompt-Guard-2-86M

# LLM max output tokens (server-side; Responses API does not support per-request max_tokens yet).
# Set when enabling an LLM via LLM= so input + output stay within model context (e.g. 14k).
LLM_MAX_TOKENS ?= 2048

# Evaluation Configuration
# Enable full laptop details validation by default unless explicitly disabled
# Set VALIDATE_FULL_LAPTOP_DETAILS=false to disable validation
VALIDATE_FULL_LAPTOP_DETAILS ?= true
VALIDATE_LAPTOP_DETAILS_FLAG := $(if $(filter true,$(VALIDATE_FULL_LAPTOP_DETAILS)),--validate-full-laptop-details,--no-validate-full-laptop-details)

# Enable structured output mode for evaluations (default: false)
# Set USE_STRUCTURED_OUTPUT=true to enable Pydantic schema validation with retries
USE_STRUCTURED_OUTPUT ?= false
STRUCTURED_OUTPUT_FLAG := $(if $(filter true,$(USE_STRUCTURED_OUTPUT)),--use-structured-output,)

# Fault Injection Configuration (for testing)
FAULT_INJECTION_ENABLED ?=
FAULT_INJECTION_RATE ?=
FAULT_INJECTION_ERROR_TYPE ?=
FAULT_INJECTION_MAX_RETRIES ?=

# Export to shell so kubectl can access them
export SERVICENOW_INSTANCE_URL
export SERVICENOW_API_KEY
export SERVICENOW_LAPTOP_AVOID_DUPLICATES
export SERVICENOW_LAPTOP_REQUEST_LIMITS
export TEST_USERS

helm_pgvector_args = \
    --set pgvector.secret.user=$(POSTGRES_USER) \
    --set pgvector.secret.password=$(POSTGRES_PASSWORD) \
    --set pgvector.secret.dbname=$(POSTGRES_DBNAME)

helm_llm_service_args = \
    $(if $(HF_TOKEN),--set llm-service.secret.hf_token=$(HF_TOKEN),) \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_TOLERATION),--set-json global.models.$(LLM).tolerations='$(call TOLERATIONS_TEMPLATE,$(LLM_TOLERATION))',) \
    $(if $(SAFETY_TOLERATION),--set-json global.models.$(SAFETY).tolerations='$(call TOLERATIONS_TEMPLATE,$(SAFETY_TOLERATION))',) \
    $(if $(and $(LLM_URL),$(if $(SAFETY),,yes)),--set llm-service.enabled=false,)

helm_promptguard_args = \
    $(if $(PROMPTGUARD_ENABLED),--set promptGuard.enabled=$(PROMPTGUARD_ENABLED) \
        --set llama-stack.models.$(PROMPTGUARD_MODEL).enabled=$(PROMPTGUARD_ENABLED) \
        --set llama-stack.models.$(PROMPTGUARD_MODEL).url="http://$(MAIN_CHART_NAME)-promptguard.$(NAMESPACE).svc.cluster.local:8000/v1" \
        --set global.models.$(PROMPTGUARD_MODEL).enabled=$(PROMPTGUARD_ENABLED) \
        --set global.models.$(PROMPTGUARD_MODEL).url="http://$(MAIN_CHART_NAME)-promptguard.$(NAMESPACE).svc.cluster.local:8000/v1",) \
    $(if $(PROMPTGUARD_MODEL_ID),--set promptGuard.modelId='$(PROMPTGUARD_MODEL_ID)',) \
	$(if $(HF_TOKEN),--set promptGuard.huggingfaceToken='$(HF_TOKEN)',)

helm_llama_stack_args = \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).registerShield=true,) \
    $(if $(LLM_URL),--set global.models.$(LLM).url='$(LLM_URL)',) \
    $(if $(LLM_ID),--set global.models.$(LLM).id='$(LLM_ID)',) \
    $(if $(LLM),--set global.models.$(LLM).maxTokens=$(LLM_MAX_TOKENS),) \
    $(if $(SAFETY_URL),--set global.models.$(SAFETY).url='$(SAFETY_URL)',) \
    $(if $(SAFETY_ID),--set global.models.$(SAFETY).id='$(SAFETY_ID)',) \
    $(if $(LLM_API_TOKEN),--set global.models.$(LLM).apiToken='$(LLM_API_TOKEN)',) \
    $(if $(SAFETY_API_TOKEN),--set global.models.$(SAFETY).apiToken='$(SAFETY_API_TOKEN)',) \
    $(if $(LLAMA_STACK_ENV),--set-json llama-stack.secrets='$(LLAMA_STACK_ENV)',) \
    $(if $(LLAMASTACK_CLIENT_PORT),--set llamastack.port=$(LLAMASTACK_CLIENT_PORT),) \
    $(if $(LLAMASTACK_API_KEY),--set llamastack.apiKey='$(LLAMASTACK_API_KEY)',) \
    $(if $(LLAMASTACK_OPENAI_BASE_PATH),--set llamastack.openaiBasePath='$(LLAMASTACK_OPENAI_BASE_PATH)',) \
    $(if $(LLAMASTACK_TIMEOUT),--set llamastack.timeout=$(LLAMASTACK_TIMEOUT),) \
    $(helm_promptguard_args)

helm_request_management_args = \
    $(if $(REQUEST_MANAGEMENT),--set requestManagement.enabled=$(REQUEST_MANAGEMENT),) \
    $(if $(KNATIVE_EVENTING),--set requestManagement.knative.eventing.enabled=$(KNATIVE_EVENTING),) \
    $(if $(MOCK_EVENTING),--set requestManagement.knative.mockEventing.enabled=$(MOCK_EVENTING),) \
    $(if $(SLACK_SIGNING_SECRET),--set-string security.slack.signingSecret='$(SLACK_SIGNING_SECRET)',) \
    $(if $(SNOW_API_KEY),--set-string security.apiKeys.snowIntegration='$(SNOW_API_KEY)',) \
    $(if $(HR_API_KEY),--set-string security.apiKeys.hrSystem='$(HR_API_KEY)',)

helm_generic_args = \
	$(if $(OTEL_EXPORTER_OTLP_ENDPOINT),--set otelExporter=$(OTEL_EXPORTER_OTLP_ENDPOINT),) \
	$(if $(OTEL_EXPORTER_OTLP_ENDPOINT),--set llama-stack.otelExporter=$(OTEL_EXPORTER_OTLP_ENDPOINT),) \
	$(if $(OTEL_EXPORTER_OTLP_ENDPOINT),--set-string llama-stack.secrets.OTEL_SERVICE_NAME=llamastack,) \
	$(if $(findstring jaeger,$(OTEL_EXPORTER_OTLP_ENDPOINT)),--set-string llama-stack.secrets.OTEL_METRICS_EXPORTER=none,) \
	$(if $(findstring jaeger,$(OTEL_EXPORTER_OTLP_ENDPOINT)),--set-string llama-stack.secrets.OTEL_LOGS_EXPORTER=none,) \
	$(if $(findstring jaeger,$(OTEL_EXPORTER_OTLP_ENDPOINT)),--set-string llama-stack.secrets.OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf,) \
	$(if $(OTEL_EXPORTER_OTLP_ENDPOINT),--set mcp-servers.mcp-servers.self-service-agent-snow.env.OTEL_EXPORTER_OTLP_ENDPOINT="$(OTEL_EXPORTER_OTLP_ENDPOINT)")

helm_replica_count_args = \
	$(if $(REPLICA_COUNT),--set llamastack.postInitScaling.enabled=true,) \
	$(if $(REPLICA_COUNT),--set llamastack.postInitScaling.targetReplicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set mcp-servers.mcp-servers.self-service-agent-snow.replicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set requestManagement.kafka.replicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set requestManagement.requestManager.replicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set requestManagement.integrationDispatcher.replicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set requestManagement.agentService.replicas=$(REPLICA_COUNT),)

helm_fault_injection_args = \
	$(if $(FAULT_INJECTION_ENABLED),--set requestManagement.agentService.faultInjection.enabled=$(FAULT_INJECTION_ENABLED),) \
	$(if $(FAULT_INJECTION_RATE),--set requestManagement.agentService.faultInjection.rate=$(FAULT_INJECTION_RATE),) \
	$(if $(FAULT_INJECTION_ERROR_TYPE),--set requestManagement.agentService.faultInjection.errorType=$(FAULT_INJECTION_ERROR_TYPE),) \
	$(if $(FAULT_INJECTION_MAX_RETRIES),--set requestManagement.agentService.faultInjection.maxRetries=$(FAULT_INJECTION_MAX_RETRIES),)

COMMA := ,
helm_test_users_args = \
	$(if $(TEST_USERS),--set-string mockServiceNow.testUsers="$(subst $(COMMA),\$(COMMA),$(TEST_USERS))",)

# Demo: namespace-dependent hostnames (values-demo.yaml has the rest)
helm_demo_email_args = \
	--set-string security.email.smtpHost=test-email-server-smtp.$(NAMESPACE).svc.cluster.local \
	--set-string security.email.imapHost=test-email-server-imap.$(NAMESPACE).svc.cluster.local

# Ticketing: Zammad in-cluster URL and MCP secret wiring (exec bootstrap uses railsserver)
ZAMMAD_CREDENTIALS_SECRET ?= $(MAIN_CHART_NAME)-zammad-credentials
# Must match admin user in helm/values-zammad-deploy.yaml autoWizard.config (for zammad-bootstrap-token / UI login).
ZAMMAD_ADMIN_EMAIL ?= admin@zammad.local
ZAMMAD_ADMIN_PASSWORD ?= ZammadR0cks!
ZAMMAD_AUTOWIZARD_TOKEN ?= ssa-zammad-autowizard-9f3a2b1c

# Used only by _helm-install-ticketing-single (zammad.enabled + zammad-mcp.enabled in values-ticketing.yaml).
helm_ticketing_args = \
	--set zammad.url=$(ZAMMAD_URL) \
	--set mcp-servers.mcp-servers.zammad-mcp.image.repository=$(REGISTRY)/self-service-agent-zammad-mcp \
	--set mcp-servers.mcp-servers.zammad-mcp.image.tag=$(VERSION) \
	--set mcp-servers.mcp-servers.zammad-mcp.envSecrets.ZAMMAD_URL.name=$(ZAMMAD_CREDENTIALS_SECRET) \
	--set mcp-servers.mcp-servers.zammad-mcp.envSecrets.ZAMMAD_URL.key=zammad-url \
	--set mcp-servers.mcp-servers.zammad-mcp.envSecrets.ZAMMAD_HTTP_TOKEN.name=$(ZAMMAD_CREDENTIALS_SECRET) \
	--set mcp-servers.mcp-servers.zammad-mcp.envSecrets.ZAMMAD_HTTP_TOKEN.key=zammad-http-token

# Version target
.PHONY: version
version:
	@echo $(VERSION)

# Default target
.PHONY: help
help:
	@echo "Available targets:"
	@echo ""
	@echo "Build Commands:"
	@echo "  build-all-images                     - Build all container images (checks lockfiles first)"
	@echo "  build-agent-service-image            - Build the agent service container image (checks lockfiles first)"
	@echo "  build-integration-dispatcher-image   - Build the integration dispatcher container image (checks lockfiles first)"
	@echo "  build-mcp-snow-image                 - Build the snow MCP server container image (checks lockfiles first)"
	@echo "  build-mcp-zammad-image               - Build the Zammad MCP server container image (checks lockfiles first)"
	@echo "  build-mock-eventing-image            - Build the mock eventing service container image (checks lockfiles first)"
	@echo "  build-mock-servicenow-image          - Build the mock ServiceNow server container image (checks lockfiles first)"
	@echo "  build-zammad-bootstrap-image         - Build the Zammad bootstrap container image (checks lockfiles first)"
	@echo "  build-promptguard-image              - Build the PromptGuard service container image (checks lockfiles first)"
	@echo "  build-request-mgr-image              - Build the request manager container image (checks lockfiles first)"
	@echo "                                        💡 Tip: If you encounter QEMU issues on Mac M1/M2/M3, add USE_PIP_INSTALL=true"
	@echo ""
	@echo "Helm Commands:"
	@echo "  helm-install-test                   - Install with mock eventing service (testing/development/CI - default)"
	@echo "  helm-install-prod                   - Install with full Knative eventing (production)"
	@echo "  helm-install-demo                  - Install demo config (mock eventing, Greenmail, resource constraints)"
	@echo "  helm-install-ticketing             - Install with ticketing channel (Zammad + MCP; one-shot deploy)"
	@echo "  helm-export-demo                    - Export demo manifests to ansible/helm-export/ (from NAMESPACE, VERSION, REGISTRY, SERVICENOW_*, etc.)"
	@echo "  helm-export-validate-demo           - Export then validate with kubeconform (no cluster; CI)"
	@echo "  ansible-apply-demo                  - Export then apply demo via Ansible (requires ansible-playbook)"
	@echo "  ansible-teardown-demo               - Teardown demo namespace via Ansible (requires ansible-playbook)"
	@echo "  check-ansible                       - Verify ansible-playbook is installed"
	@echo "  helm-cleanup-eventing               - Manually clean up leftover Knative Eventing resources (Triggers, Brokers)"
	@echo "  helm-cleanup-jobs                   - Clean up leftover jobs from failed deployments"
	@echo "  helm-depend                         - Update Helm dependencies"
	@echo "  helm-list-models                    - List available models"
	@echo "  helm-status                         - Check status of the deployment"
	@echo "  helm-uninstall                      - Uninstall the RAG deployment and clean up resources"
	@echo "  install                             - Deploy to cluster (alias for helm-install; set INSTALL_MODE=test|demo|prod, default: test)"
	@echo "  uninstall                           - helm-uninstall + delete namespace"
	@echo "  verify-triggers                     - Verify all expected Knative triggers are deployed"
	@echo ""
	@echo "Dependency Commands (local dev):"
	@echo "  deps-all                            - Install dependencies for all projects"
	@echo "  deps                                - Install dependencies for self-service agent (root)"
	@echo "  deps-agent-service                   - Install dependencies for agent service"
	@echo "  deps-integration-dispatcher          - Install dependencies for integration dispatcher"
	@echo "  deps-mcp-snow                        - Install dependencies for snow MCP server"
	@echo "  deps-mcp-zammad                      - Install dependencies for Zammad MCP server"
	@echo "  deps-request-manager                 - Install dependencies for request manager"
	@echo "  deps-shared-models                   - Install dependencies for shared models"
	@echo "  deps-shared-clients                  - Install dependencies for shared clients"
	@echo "  deps-servicenow-bootstrap            - Install dependencies for ServiceNow automation scripts"
	@echo "  deps-mock-employee-data              - Install dependencies for mock employee data"
	@echo "  deps-mock-servicenow                 - Install dependencies for mock ServiceNow"
	@echo "  deps-tracing-config                  - Install dependencies for tracing-config"
	@echo "  deps-promptguard                     - Install dependencies for PromptGuard"
	@echo "  deps-evaluations                     - Install dependencies for evaluations"
	@echo ""
	@echo "Reinstall Commands:"
	@echo "  reinstall-all                       - Force reinstall dependencies for all projects"
	@echo "  reinstall                           - Force reinstall self-service agent dependencies (uv sync --reinstall)"
	@echo "  reinstall-agent-service             - Force reinstall agent service dependencies"
	@echo "  reinstall-integration-dispatcher    - Force reinstall integration dispatcher dependencies"
	@echo "  reinstall-mcp-snow                  - Force reinstall snow MCP dependencies"
	@echo "  reinstall-mcp-zammad                - Force reinstall Zammad MCP dependencies"
	@echo "  reinstall-request-manager           - Force reinstall request manager dependencies"
	@echo "  reinstall-shared-models             - Force reinstall shared models dependencies"
	@echo "  reinstall-shared-clients            - Force reinstall shared clients dependencies"
	@echo "  reinstall-servicenow-bootstrap     - Force reinstall ServiceNow automation dependencies"
	@echo "  reinstall-mock-employee-data        - Force reinstall mock employee data dependencies"
	@echo "  reinstall-mock-servicenow           - Force reinstall mock ServiceNow dependencies"
	@echo ""
	@echo "Pull Commands (pull images at REGISTRY/VERSION with --platform=\$$(ARCH)):"
	@echo "  pull-all-images                     - Pull all container images"
	@echo "  pull-request-mgr-image              - Pull request manager image"
	@echo "  pull-agent-service-image            - Pull agent service image"
	@echo "  pull-integration-dispatcher-image   - Pull integration dispatcher image"
	@echo "  pull-mcp-snow-image                 - Pull snow MCP image"
	@echo "  pull-mcp-zammad-image               - Pull Zammad MCP image"
	@echo "  pull-mock-eventing-image            - Pull mock eventing image"
	@echo "  pull-mock-servicenow-image          - Pull mock ServiceNow image"
	@echo "  pull-promptguard-image              - Pull PromptGuard image"
	@echo "  pull-zammad-bootstrap-image         - Pull Zammad bootstrap image"
	@echo ""
	@echo "Retag Commands (pull at REGISTRY/VERSION then tag -> NEW_REGISTRY/NEW_VERSION; set both NEW_* vars):"
	@echo "  retag-all-images                    - Pull all images, then retag all to NEW_REGISTRY/NEW_VERSION"
	@echo "  retag-request-mgr-image             - Retag request manager image"
	@echo "  retag-agent-service-image           - Retag agent service image"
	@echo "  retag-integration-dispatcher-image  - Retag integration dispatcher image"
	@echo "  retag-mcp-snow-image                - Retag snow MCP image"
	@echo "  retag-mcp-zammad-image              - Retag Zammad MCP image"
	@echo "  retag-mock-eventing-image           - Retag mock eventing image"
	@echo "  retag-mock-servicenow-image         - Retag mock ServiceNow image"
	@echo "  retag-promptguard-image             - Retag PromptGuard image"
	@echo "  retag-zammad-bootstrap-image        - Retag Zammad bootstrap image"
	@echo ""
	@echo "Push Commands:"
	@echo "  push-all-images                     - Push all container images to registry"
	@echo "  push-agent-service-image            - Push the agent service container image to registry"
	@echo "  push-integration-dispatcher-image   - Push the integration dispatcher container image to registry"
	@echo "  push-mcp-snow-image                 - Push the snow MCP server container image to registry"
	@echo "  push-mcp-zammad-image               - Push the Zammad MCP server container image to registry"
	@echo "  push-mock-eventing-image            - Push the mock eventing service container image to registry"
	@echo "  push-promptguard-image              - Push the PromptGuard service container image to registry"
	@echo "  push-request-mgr-image              - Push the request manager container image to registry"
	@echo ""
	@echo "Test Commands:"
	@echo "  test-all                            - Run tests for all projects"
	@echo ""
	@echo "ServiceNow PDI Commands:"
	@echo "  servicenow-wake-install                      - Install Playwright for ServiceNow PDI wake-up"
	@echo "  servicenow-wake                              - Wake up hibernating ServiceNow PDI"
	@echo "  servicenow-bootstrap                         - Run ServiceNow bootstrap setup with config file"
	@echo "  servicenow-bootstrap-validation              - Run ServiceNow bootstrap validation checks"
	@echo "  servicenow-bootstrap-create-user             - Create MCP agent user only"
	@echo "  servicenow-bootstrap-create-api-key          - Create MCP agent API key only"
	@echo "  servicenow-bootstrap-create-catalog-item     - Create PC refresh service catalog item only"
	@echo "  servicenow-bootstrap-create-evaluation-users - Create evaluation users only"
	@echo ""
	@echo "Test Email Server Commands:"
	@echo "  deploy-email-server                 - Deploy test email server (Greenmail with custom UI)"
	@echo "  undeploy-email-server               - Remove test email server from namespace"
	@echo "  deploy-zammad                       - Deploy Zammad instance (prerequisite for ticketing channel)"
	@echo "  undeploy-zammad                     - Remove Zammad instance from namespace"
	@echo "  zammad-set-token                    - Set Zammad API token in secret and restart MCP (ZAMMAD_TOKEN=xxx, NAMESPACE=)"
	@echo "  zammad-bootstrap-token              - Create API token via Zammad API (autoWizard admin); update secret and restart MCP"
	@echo "  zammad-trigger-autowizard           - Trigger autoWizard via HTTP (run before bootstrap if 401)"
	@echo ""
	@echo "Lockfile Management:"
	@echo "  check-lockfiles                     - Check if all uv.lock files are up-to-date"
	@echo "  check-requirements                  - Check if all requirements.txt files exist and are in sync with uv.lock"
	@echo "  check-uv-version                    - Check if local uv version matches CI requirement ($(UV_VERSION))"
	@echo "  update-lockfiles                    - Update all uv.lock files; export requirements.txt for dirs in REQUIREMENTS_DIRS"
	@echo "  export-requirements                - Export requirements.txt for containerized services (REQUIREMENTS_DIRS only)"
	@echo "  check-lockfile-<service>            - Check lockfile for specific service"
	@echo "  update-lockfile-<service>           - Update lockfile for specific service"
	@echo "  test-agent-service                  - Run tests for agent service"
	@echo "  test-integration-dispatcher         - Run tests for integration dispatcher"
	@echo "  test-mcp-snow                       - Run tests for snow MCP server"
	@echo "  test-mcp-zammad                     - Run tests for Zammad MCP server"
	@echo "  test-request-manager                - Run tests for request manager"
	@echo "  test-shared-models                  - Run tests for shared models"
	@echo "  test-servicenow-bootstrap          - Run tests for ServiceNow automation scripts"
	@echo "  test-mock-employee-data            - Run tests for mock employee data"
	@echo "  test-mock-servicenow               - Run tests for mock ServiceNow"
	@echo "  test-short-resp-integration-request-mgr - Run short responses integration tests with Request Manager"
	@echo "  test-short-ticket-laptop-refresh   - Run short responses integration tests for ticket-laptop-refresh flow"
	@echo "  test-long-resp-integration-request-mgr - Run long responses integration tests with Request Manager"
	@echo "  test-medium-resp-integration-request-mgr - Run medium responses integration tests with Request Manager (5 conversations)"
	@echo "  test-long-concurrent-integration-request-mgr - Run long concurrent responses integration tests with Request Manager (concurrency=4)"
	@echo "  test-session-serialization-integration - Run session serialization integration test (requires cluster, NAMESPACE=test)"
	@echo "  test-session-reclaim-integration - Run session reclaim integration test (on-demand reclaim of stuck processing)"
	@echo "  test-session-background-reclaim-integration - Run background reclaim integration test (~60s, requires cluster)"
	@echo "  generate-two-sessions                   - Generate two sessions: one for alice.johnson@company.com and one for ahmed.hassan@company.com"
	@echo ""
	@echo "Utility Commands:"
	@echo "  format                              - Run isort import sorting and Black formatting on entire codebase"
	@echo "  generate-lg-diagrams                - Generate LangGraph visualization diagrams from YAML configs (outputs to docs/images/)"
	@echo "  lint                                - Run optimized linting (global isort/flake8 + per-directory mypy + logging patterns)"
	@echo "  lint-global-tools                   - Run isort and flake8 globally on all projects"
	@echo "  lint-mypy-per-directory             - Run mypy on all projects with project-specific configs"
	@echo "  lint-<directory>                    - Run mypy on specific directory (e.g., lint-agent-service)"
	@echo "  check-logging                       - Check logging patterns (no direct imports, no print, structured logging)"
	@echo "  version                             - Print the current VERSION"
	@echo ""
	@echo "Configuration options (set via environment variables or make arguments):"
	@echo ""
	@echo "  Core Configuration:"
	@echo "    CONTAINER_TOOL                    - Container build tool (default: podman)"
	@echo "    REGISTRY                          - Container registry (default: quay.io/rh-ai-quickstart)"
	@echo "    VERSION                           - Image version tag (auto-detected from git branch if not set)"
	@echo "    NEW_REGISTRY                      - Destination registry for retag-all-images (set with NEW_VERSION)"
	@echo "    NEW_VERSION                       - Destination tag for retag-all-images (set with NEW_REGISTRY)"
	@echo "                                        - main branch: uses base version '0.0.2' (stable builds)"
	@echo "                                        - dev branch: uses '0.0.2-dev' tag (latest dev builds)"
	@echo "                                        - branches forked from dev: uses '0.0.2-dev' tag (dev builds)"
	@echo "                                        - all other branches: uses base version '0.0.2' (stable builds, default)"
	@echo "                                        - Set explicitly to override (e.g., VERSION=latest for main)"
	@echo "    NAMESPACE                         - Target namespace (required, no default)"
	@echo "    REPLICA_COUNT                     - Number of replicas for scalable services (optional)"
	@echo "                                        If set, overrides defaults from helm/values.yaml"
	@echo "                                        If not set, uses defaults from helm/values.yaml"
	@echo "                                        Applies to: llama-stack, snow MCP, kafka,"
	@echo "                                        request-manager, integration-dispatcher, and agent-service"
	@echo ""
	@echo "  Image Configuration:"
	@echo "    AGENT_SERVICE_IMG                 - Full agent service image name (default: \$${REGISTRY}/self-service-agent-service:\$${VERSION})"
	@echo "    INTEGRATION_DISPATCHER_IMG        - Full integration dispatcher image name (default: \$${REGISTRY}/self-service-agent-integration-dispatcher:\$${VERSION})"
	@echo "    MCP_SNOW_IMG                      - Full snow MCP image name (default: \$${REGISTRY}/self-service-agent-snow-mcp:\$${VERSION})"
	@echo "    MOCK_SERVICENOW_IMG               - Full mock ServiceNow image name (default: \$${REGISTRY}/self-service-agent-mock-servicenow:\$${VERSION})"
	@echo "    ZAMMAD_BOOTSTRAP_IMG              - Full Zammad bootstrap image name (default: \$${REGISTRY}/self-service-agent-zammad-bootstrap:\$${VERSION})"
	@echo "    REQUEST_MGR_IMG                   - Full request manager image name (default: \$${REGISTRY}/self-service-agent-request-manager:\$${VERSION})"
	@echo "    USE_PIP_INSTALL                   - Use pip install from requirements.txt instead of uv sync (default: false)"
	@echo "                                        ⚠️  Troubleshooting: If you encounter QEMU segmentation faults when building"
	@echo "                                        Linux AMD64 containers on Mac M1/M2/M3, set this to 'true' as a workaround."
	@echo "                                        This is especially common when using QEMU emulation for cross-platform builds."
	@echo "                                        Example: make build-agent-service-image USE_PIP_INSTALL=true"
	@echo "                                        Note: Default (uv sync) is faster and more reliable on native Linux/CI environments."
	@echo ""
	@echo "  Model Configuration:"
	@echo "    HF_TOKEN                          - Hugging Face Token (will prompt if not provided)"
	@echo "    LLM_ID                            - Model ID for LLM configuration"
	@echo "    {SAFETY,LLM}                      - Model id as defined in values (eg. llama-3-2-1b-instruct)"
	@echo "    {SAFETY,LLM}_URL                  - Model URL"
	@echo "    {SAFETY,LLM}_API_TOKEN            - Model API token for remote models"
	@echo "    {SAFETY,LLM}_TOLERATION           - Model pod toleration"
	@echo "    PROMPTGUARD_MODEL                 - PromptGuard model name (default: llama-prompt-guard-2-86m)"
	@echo ""
	@echo "  Integration Configuration:"
	@echo "    ENABLE_SLACK                      - Set to 'true' to enable Slack integration and prompt for tokens"
	@echo "    HR_API_KEY                        - HR system integration API key"
	@echo "    SLACK_BOT_TOKEN                   - Slack Bot Token (xoxb-...) for Slack integration"
	@echo "    SLACK_SIGNING_SECRET              - Slack Signing Secret for request verification"
	@echo ""
	@echo "  ServiceNow Configuration:"
	@echo "    SERVICENOW_INSTANCE_URL           - ServiceNow instance URL (default: http://self-service-agent-mock-servicenow:8080)"
	@echo "    SERVICENOW_API_KEY                 - ServiceNow API key (default: now_mock_api_key)"
	@echo "    SERVICENOW_API_KEY_HEADER         - Custom header name (default: x-sn-apikey)"
	@echo "    SERVICENOW_LAPTOP_REFRESH_ID      - ServiceNow catalog item ID for laptop refresh requests (default: mock_laptop_refresh_id)"
	@echo "    SERVICENOW_LAPTOP_AVOID_DUPLICATES - Whether to prevent creating duplicate laptop requests for the same model (default: false)"
	@echo "    SERVICENOW_LAPTOP_REQUEST_LIMITS  - Maximum number of open laptop requests allowed per user (default: None)"
	@echo "    SERVICENOW_DEV_PORTAL_USERNAME    - ServiceNow Developer Portal username for PDI wake-up (required for servicenow-wake)"
	@echo "    SERVICENOW_DEV_PORTAL_PASSWORD    - ServiceNow Developer Portal password for PDI wake-up (required for servicenow-wake)"
	@echo "    TEST_USERS                        - Comma-separated list of email addresses to add to mock employee data for testing"
	@echo ""
	@echo "  Request Management Layer:"
	@echo "    KNATIVE_EVENTING                  - Enable Knative Eventing (default: true)"
	@echo "    REQUEST_MANAGEMENT                - Enable Request Management Layer (default: true)"
	@echo ""
	@echo "  Agent Prompt Configuration:"
	@echo "    LG_PROMPT_<AGENT_NAME>            - Override prompt config for any agent (generic pattern)"
	@echo "                                        Replace <AGENT_NAME> with uppercase agent name (use _ for -)"
	@echo "    Examples:"
	@echo "      LG_PROMPT_LAPTOP_REFRESH        - Override laptop-refresh agent"
	@echo "      LG_PROMPT_ROUTING               - Override routing agent"
	@echo "      LG_PROMPT_EMAIL_UPDATE          - Override email-update agent"
	@echo "    Usage: make helm-install-test LG_PROMPT_LAPTOP_REFRESH=config/lg-prompts/custom.yaml"
	@echo ""
	@echo "  Routing Agent Configuration:"
	@echo "    DEFAULT_AGENT_ID                  - Override the default routing agent (default: routing-agent)"
	@echo "    Usage: make helm-install-test DEFAULT_AGENT_ID=my-custom-agent"
	@echo ""
	@echo "  Evaluation Configuration:"
	@echo "    VALIDATE_FULL_LAPTOP_DETAILS    - Enable full laptop details validation (default: true)"
	@echo "                                        Set to 'false' to disable: VALIDATE_FULL_LAPTOP_DETAILS=false"
	@echo "                                        When enabled, integration tests validate all laptop specification fields"
	@echo "    USE_STRUCTURED_OUTPUT           - Enable structured output mode for evaluations (default: false)"
	@echo "                                        Set to 'true' to enable: USE_STRUCTURED_OUTPUT=true"
	@echo "                                        Uses Pydantic schema validation with retries (recommended for Gemini)"

# Template build function: $(call build_template_image,IMAGE_NAME,DESCRIPTION,CONTAINERFILE,SERVICE_NAME,MODULE_NAME,BUILD_CONTEXT)
# Optional: Set USE_PIP_INSTALL=true to use pip install from requirements.txt instead of uv sync
# Optional: Set UV_VERSION=<version> to override uv version (default: $(UV_VERSION))
# Example: make build-agent-service-image USE_PIP_INSTALL=true
# Example: make build-agent-service-image UV_VERSION=0.9.27
define build_template_image
	@echo "Building $(2) using template: $(1)"
	$(CONTAINER_TOOL) build -t $(1) --platform=$(ARCH) \
		-f $(3) \
		--build-arg SERVICE_NAME=$(4) \
		--build-arg MODULE_NAME=$(5) \
		--build-arg USE_PIP_INSTALL=$(USE_PIP_INSTALL) \
		--build-arg UV_VERSION=$(UV_VERSION) \
		$(if $(6),$(6),.)
	@echo "Successfully built $(1)"
endef

# Push function: $(call push_image,IMAGE_NAME,DESCRIPTION)
define push_image
	@echo "Pushing $(2): $(1)"
	$(CONTAINER_TOOL) push $(1)
	@echo "Successfully pushed $(1)"
endef

# Pull with platform (and --policy=always for podman so we get newest build): $(call pull_image,IMAGE,DESCRIPTION)
define pull_image
	@echo "Pulling $(2): $(1) (--platform=$(ARCH)$(if $(PULL_POLICY), $(PULL_POLICY),))"
	$(CONTAINER_TOOL) pull --platform=$(ARCH) $(PULL_POLICY) $(1)
	@echo "Successfully pulled $(2): $(1)"
endef

# Retag: $(call retag_image,IMAGE_STEM,DESCRIPTION) — tags REGISTRY/STEM:VERSION -> NEW_REGISTRY/STEM:NEW_VERSION
# Requires NEW_REGISTRY and NEW_VERSION to be set.
define retag_image
	@[ -n "$(NEW_REGISTRY)" ] && [ -n "$(NEW_VERSION)" ] || (echo "Error: NEW_REGISTRY and NEW_VERSION must be set for retag targets" && exit 1)
	@echo "Retagging $(2): $(REGISTRY)/$(1):$(VERSION) -> $(NEW_REGISTRY)/$(1):$(NEW_VERSION)"
	$(CONTAINER_TOOL) tag $(REGISTRY)/$(1):$(VERSION) $(NEW_REGISTRY)/$(1):$(NEW_VERSION)
	@echo "Successfully retagged $(2)"
endef

# Generic function to get external host for a service
define GET_EXTERNAL_HOST
	if kubectl get route $(1) -n $(NAMESPACE) >/dev/null 2>&1; then \
		kubectl get route $(1) -n $(NAMESPACE) -o jsonpath='{.spec.host}'; \
	elif kubectl get ingress $(1) -n $(NAMESPACE) >/dev/null 2>&1; then \
		kubectl get ingress $(1) -n $(NAMESPACE) -o jsonpath='{.spec.rules[0].host}'; \
	fi
endef

# Generic function to print service URLs
define PRINT_SERVICE_URLS
	@echo "--- Your $(1) URLs are: ---"
	@sleep 10
	@EXTERNAL_HOST=$$($(call GET_EXTERNAL_HOST,$(2))); \
	if [ -n "$$EXTERNAL_HOST" ]; then \
		echo "  OpenAPI Schema: https://$$EXTERNAL_HOST/docs"; \
		echo "  Health: https://$$EXTERNAL_HOST/health"; \
		$(3) \
	else \
		echo "  External access not configured - using cluster-internal URLs:"; \
		echo "  OpenAPI Schema: http://$(MAIN_CHART_NAME)-$(4).$(NAMESPACE).svc.cluster.local/docs"; \
		echo "  Health: http://$(MAIN_CHART_NAME)-$(4).$(NAMESPACE).svc.cluster.local/health"; \
		$(5) \
	fi
endef

define PRINT_REQUEST_MANAGER_URL
	$(call PRINT_SERVICE_URLS,Request Manager,$(INGRESS_PREFIX)-request-manager,,request-manager,)
endef

define PRINT_INTEGRATION_DISPATCHER_URL
	@echo "--- Your Integration Dispatcher URLs are: ---"
	@sleep 10
	@EXTERNAL_HOST=$$($(call GET_EXTERNAL_HOST,$(INGRESS_PREFIX)-integration-dispatcher)); \
	if [ -z "$$EXTERNAL_HOST" ]; then \
		EXTERNAL_HOST=$$($(call GET_EXTERNAL_HOST,$(INGRESS_PREFIX)-integration-dispatcher)); \
	fi; \
	if [ -n "$$EXTERNAL_HOST" ]; then \
		echo "  OpenAPI Schema: http://$(MAIN_CHART_NAME)-integration-dispatcher.$(NAMESPACE).svc.cluster.local/docs"; \
		echo "  Health: http://$(MAIN_CHART_NAME)-integration-dispatcher.$(NAMESPACE).svc.cluster.local/health"; \
		echo "  Slack Events: https://$$EXTERNAL_HOST/slack/events"; \
		echo "  Slack Interactive: https://$$EXTERNAL_HOST/slack/interactive"; \
		echo "  Slack Commands: https://$$EXTERNAL_HOST/slack/commands"; \
	else \
		echo "  External access not configured - using cluster-internal URLs:"; \
		echo "  OpenAPI Schema: http://$(MAIN_CHART_NAME)-integration-dispatcher.$(NAMESPACE).svc.cluster.local/docs"; \
		echo "  Health: http://$(MAIN_CHART_NAME)-integration-dispatcher.$(NAMESPACE).svc.cluster.local/health"; \
		echo "  Slack Events: http://$(MAIN_CHART_NAME)-integration-dispatcher.$(NAMESPACE).svc.cluster.local/slack/events"; \
		echo "  Slack Interactive: http://$(MAIN_CHART_NAME)-integration-dispatcher.$(NAMESPACE).svc.cluster.local/slack/interactive"; \
		echo "  Slack Commands: http://$(MAIN_CHART_NAME)-integration-dispatcher.$(NAMESPACE).svc.cluster.local/slack/commands"; \
	fi
endef

# Template-specific dependency checks
# These check all common dependencies for each container template
.PHONY: check-deps-services-template
check-deps-services-template: check-lockfile-shared-models check-lockfile-shared-clients check-lockfile-agent-service check-lockfile-mock-employee-data

.PHONY: check-deps-mcp-template
check-deps-mcp-template: check-lockfile-shared-models check-lockfile-mcp-common

# Build container images
.PHONY: build-all-images
build-all-images: build-request-mgr-image build-agent-service-image build-integration-dispatcher-image build-mcp-snow-image build-mcp-zammad-image build-mock-eventing-image build-mock-servicenow-image build-promptguard-image build-zammad-bootstrap-image
	@echo "All container images built successfully!"



.PHONY: build-request-mgr-image
build-request-mgr-image: check-lockfile-request-manager check-deps-services-template
	$(call build_template_image,$(REQUEST_MGR_IMG),request manager image,Containerfile.services-template,request-manager,request_manager.main,.)

.PHONY: build-agent-service-image
build-agent-service-image: check-lockfile-agent-service check-deps-services-template
	$(call build_template_image,$(AGENT_SERVICE_IMG),agent service image,Containerfile.services-template,agent-service,agent_service.main,.)

.PHONY: build-integration-dispatcher-image
build-integration-dispatcher-image: check-lockfile-integration-dispatcher check-deps-services-template
	$(call build_template_image,$(INTEGRATION_DISPATCHER_IMG),integration dispatcher image,Containerfile.services-template,integration-dispatcher,integration_dispatcher.main,.)

.PHONY: build-promptguard-image
build-promptguard-image: check-lockfile-promptguard check-deps-services-template
	$(call build_template_image,$(PROMPTGUARD_IMG),PromptGuard service image,Containerfile.services-template,promptguard-service,promptguard_service.server,.)

.PHONY: build-mcp-snow-image
build-mcp-snow-image: check-lockfile-mcp-snow check-deps-mcp-template
	$(call build_template_image,$(MCP_SNOW_IMG),snow MCP image,Containerfile.mcp-template,mcp-servers/snow,snow.server,.)

.PHONY: build-mcp-zammad-image
build-mcp-zammad-image: check-lockfile-mcp-zammad check-deps-mcp-template
	$(call build_template_image,$(MCP_ZAMMAD_IMG),Zammad MCP image,Containerfile.mcp-template,mcp-servers/zammad,zammad_mcp.server,.)

.PHONY: build-mock-eventing-image
build-mock-eventing-image: check-lockfile-mock-eventing check-deps-services-template
	$(call build_template_image,$(MOCK_EVENTING_IMG),mock eventing service image,Containerfile.services-template,mock-eventing-service,mock_eventing_service.main,.)

.PHONY: build-mock-servicenow-image
build-mock-servicenow-image: check-lockfile-mock-servicenow check-deps-services-template
	$(call build_template_image,$(MOCK_SERVICENOW_IMG),mock ServiceNow server image,Containerfile.services-template,mock-service-now,mock_servicenow.server,.)

.PHONY: build-zammad-bootstrap-image
build-zammad-bootstrap-image: check-lockfile-zammad-bootstrap check-lockfile-mock-employee-data
	@echo "Building Zammad bootstrap image: $(ZAMMAD_BOOTSTRAP_IMG)"
	$(CONTAINER_TOOL) build -t $(ZAMMAD_BOOTSTRAP_IMG) --platform=$(ARCH) \
		-f zammad-bootstrap/Containerfile.zammad-bootstrap \
		--build-arg UV_VERSION=$(UV_VERSION) \
		--build-arg USE_PIP_INSTALL=$(USE_PIP_INSTALL) \
		.
	@echo "Successfully built $(ZAMMAD_BOOTSTRAP_IMG)"

# Push container images
.PHONY: push-all-images
push-all-images: push-request-mgr-image push-agent-service-image push-integration-dispatcher-image push-mcp-snow-image push-mcp-zammad-image push-mock-eventing-image push-mock-servicenow-image push-promptguard-image push-zammad-bootstrap-image
	@echo "All container images pushed successfully!"



.PHONY: push-request-mgr-image
push-request-mgr-image:
	$(call push_image,$(REQUEST_MGR_IMG) $(PUSH_EXTRA_AGRS),request manager image)

.PHONY: push-agent-service-image
push-agent-service-image:
	$(call push_image,$(AGENT_SERVICE_IMG) $(PUSH_EXTRA_AGRS),agent service image)

.PHONY: push-integration-dispatcher-image
push-integration-dispatcher-image:
	$(call push_image,$(INTEGRATION_DISPATCHER_IMG) $(PUSH_EXTRA_AGRS),integration dispatcher image)


.PHONY: push-mcp-snow-image
push-mcp-snow-image:
	$(call push_image,$(MCP_SNOW_IMG) $(PUSH_EXTRA_AGRS),snow MCP image)

.PHONY: push-mcp-zammad-image
push-mcp-zammad-image:
	$(call push_image,$(MCP_ZAMMAD_IMG) $(PUSH_EXTRA_AGRS),Zammad MCP image)

.PHONY: push-mock-eventing-image
push-mock-eventing-image:
	$(call push_image,$(MOCK_EVENTING_IMG) $(PUSH_EXTRA_AGRS),mock eventing service image)

.PHONY: push-mock-servicenow-image
push-mock-servicenow-image:
	$(call push_image,$(MOCK_SERVICENOW_IMG) $(PUSH_EXTRA_AGRS),mock ServiceNow server image)

.PHONY: push-zammad-bootstrap-image
push-zammad-bootstrap-image:
	$(call push_image,$(ZAMMAD_BOOTSTRAP_IMG) $(PUSH_EXTRA_AGRS),Zammad bootstrap image)

.PHONY: push-promptguard-image
push-promptguard-image:
	$(call push_image,$(PROMPTGUARD_IMG) $(PUSH_EXTRA_AGRS),PromptGuard service image)

# Pull images at REGISTRY/VERSION with --platform=$(ARCH)
.PHONY: pull-all-images
pull-all-images: pull-request-mgr-image pull-agent-service-image pull-integration-dispatcher-image pull-mcp-snow-image pull-mcp-zammad-image pull-mock-eventing-image pull-mock-servicenow-image pull-promptguard-image pull-zammad-bootstrap-image
	@echo "All images pulled successfully!"

.PHONY: pull-request-mgr-image
pull-request-mgr-image:
	$(call pull_image,$(REQUEST_MGR_IMG),request manager image)

.PHONY: pull-agent-service-image
pull-agent-service-image:
	$(call pull_image,$(AGENT_SERVICE_IMG),agent service image)

.PHONY: pull-integration-dispatcher-image
pull-integration-dispatcher-image:
	$(call pull_image,$(INTEGRATION_DISPATCHER_IMG),integration dispatcher image)

.PHONY: pull-mcp-snow-image
pull-mcp-snow-image:
	$(call pull_image,$(MCP_SNOW_IMG),snow MCP image)

.PHONY: pull-mcp-zammad-image
pull-mcp-zammad-image:
	$(call pull_image,$(MCP_ZAMMAD_IMG),Zammad MCP image)

.PHONY: pull-mock-eventing-image
pull-mock-eventing-image:
	$(call pull_image,$(MOCK_EVENTING_IMG),mock eventing service image)

.PHONY: pull-mock-servicenow-image
pull-mock-servicenow-image:
	$(call pull_image,$(MOCK_SERVICENOW_IMG),mock ServiceNow server image)

.PHONY: pull-zammad-bootstrap-image
pull-zammad-bootstrap-image:
	$(call pull_image,$(ZAMMAD_BOOTSTRAP_IMG),Zammad bootstrap image)

.PHONY: pull-promptguard-image
pull-promptguard-image:
	$(call pull_image,$(PROMPTGUARD_IMG),PromptGuard service image)

# Retag images from REGISTRY/VERSION to NEW_REGISTRY/NEW_VERSION (both NEW_* must be set)
.PHONY: retag-all-images
retag-all-images: retag-request-mgr-image retag-agent-service-image retag-integration-dispatcher-image retag-mcp-snow-image retag-mcp-zammad-image retag-mock-eventing-image retag-mock-servicenow-image retag-promptguard-image retag-zammad-bootstrap-image
	@echo "All images retagged to $(NEW_REGISTRY)/*:$(NEW_VERSION)"

.PHONY: retag-request-mgr-image
retag-request-mgr-image: pull-request-mgr-image
	$(call retag_image,self-service-agent-request-manager,request manager image)

.PHONY: retag-agent-service-image
retag-agent-service-image: pull-agent-service-image
	$(call retag_image,self-service-agent-service,agent service image)

.PHONY: retag-integration-dispatcher-image
retag-integration-dispatcher-image: pull-integration-dispatcher-image
	$(call retag_image,self-service-agent-integration-dispatcher,integration dispatcher image)

.PHONY: retag-mcp-snow-image
retag-mcp-snow-image: pull-mcp-snow-image
	$(call retag_image,self-service-agent-snow-mcp,snow MCP image)

.PHONY: retag-mcp-zammad-image
retag-mcp-zammad-image: pull-mcp-zammad-image
	$(call retag_image,self-service-agent-zammad-mcp,Zammad MCP image)

.PHONY: retag-mock-eventing-image
retag-mock-eventing-image: pull-mock-eventing-image
	$(call retag_image,self-service-agent-mock-eventing,mock eventing service image)

.PHONY: retag-mock-servicenow-image
retag-mock-servicenow-image: pull-mock-servicenow-image
	$(call retag_image,self-service-agent-mock-servicenow,mock ServiceNow server image)

.PHONY: retag-zammad-bootstrap-image
retag-zammad-bootstrap-image: pull-zammad-bootstrap-image
	$(call retag_image,self-service-agent-zammad-bootstrap,Zammad bootstrap image)

.PHONY: retag-promptguard-image
retag-promptguard-image: pull-promptguard-image
	$(call retag_image,self-service-agent-promptguard,PromptGuard service image)

# Code quality
.PHONY: lint
lint: format lint-global-tools lint-mypy-per-directory check-logging
	@echo "All directory linting completed successfully!"

# Global linting tools (isort and flake8) for projects with standard configurations
.PHONY: lint-global-tools
lint-global-tools:
	@echo "Running global linting tools (flake8 and isort)..."
	@echo "1. Running flake8 globally on all projects..."
	@uv run flake8 .
	@echo "2. Running isort globally on all projects..."
	@uv run isort --check-only --diff .
	@echo "✅ Global linting tools completed"

# Check logging patterns
.PHONY: check-logging
check-logging:
	@echo "Checking logging patterns..."
	@uv run python scripts/check_logging_patterns.py
	@echo "✅ Logging pattern checks completed"

# Per-directory mypy linting (project-specific configurations)
.PHONY: lint-mypy-per-directory
lint-mypy-per-directory: lint-shared-models lint-shared-clients lint-agent-service lint-request-manager lint-integration-dispatcher lint-mcp-snow lint-mcp-zammad lint-mock-eventing lint-tracing-config lint-evaluations lint-servicenow-bootstrap lint-mock-employee-data lint-mock-servicenow
	@echo "✅ All mypy linting completed"

# Common function for mypy linting
define lint_mypy
	@echo "Running mypy on $(1)..."
	@if [ -d "$(1)" ]; then \
		cd $(1) && uv run --with mypy mypy --strict . && echo "✅ $(1) mypy completed"; \
	else \
		echo "⚠️  $(1) directory not found, skipping..."; \
	fi
endef

# Individual directory linting targets (mypy with project-specific configurations)
.PHONY: lint-shared-models
lint-shared-models:
	$(call lint_mypy,shared-models)

.PHONY: lint-shared-clients
lint-shared-clients:
	$(call lint_mypy,shared-clients)

.PHONY: lint-agent-service
lint-agent-service:
	$(call lint_mypy,agent-service)

.PHONY: lint-request-manager
lint-request-manager:
	$(call lint_mypy,request-manager)

.PHONY: lint-integration-dispatcher
lint-integration-dispatcher:
	$(call lint_mypy,integration-dispatcher)

.PHONY: lint-mcp-snow
lint-mcp-snow:
	$(call lint_mypy,mcp-servers/snow)

.PHONY: lint-mcp-zammad
lint-mcp-zammad:
	$(call lint_mypy,mcp-servers/zammad)

.PHONY: lint-mock-eventing
lint-mock-eventing:
	$(call lint_mypy,mock-eventing-service)

.PHONY: lint-tracing-config
lint-tracing-config:
	$(call lint_mypy,tracing-config)

.PHONY: lint-evaluations
lint-evaluations:
	$(call lint_mypy,evaluations)

.PHONY: lint-servicenow-bootstrap
lint-servicenow-bootstrap:
	$(call lint_mypy,scripts/servicenow-bootstrap)

.PHONY: lint-mock-employee-data
lint-mock-employee-data:
	$(call lint_mypy,mock-employee-data)

.PHONY: lint-mock-servicenow
lint-mock-servicenow:
	$(call lint_mypy,mock-service-now)


.PHONY: format
format:
	@echo "Running isort import sorting on entire codebase..."
	uv run isort .
	@echo "Running Black formatting on entire codebase..."
	uv run black .
	@echo "Formatting completed successfully!"

.PHONY: generate-lg-diagrams
generate-lg-diagrams:
	@echo "Generating LangGraph visualizations..."
	cd agent-service && uv run python ../scripts/create_langraph_graphs.py
	@echo "LangGraph diagrams generated successfully in docs/images/"

# Deploy to cluster (install = helm install with configurable mode)
INSTALL_MODE ?= test
.PHONY: install
install:
	@if [ "$(INSTALL_MODE)" != "test" ] && [ "$(INSTALL_MODE)" != "demo" ] && [ "$(INSTALL_MODE)" != "prod" ]; then \
		echo "Error: INSTALL_MODE must be test, demo, or prod (got: $(INSTALL_MODE))"; \
		exit 1; \
	fi
	$(MAKE) helm-install-$(INSTALL_MODE)

.PHONY: uninstall
uninstall: helm-uninstall
	@echo "Removing namespace $(NAMESPACE)..."
	@kubectl delete namespace $(NAMESPACE) --ignore-not-found --timeout=120s || true
	@echo "Uninstall complete. Namespace $(NAMESPACE) removed."

# Install dependencies (local dev)
.PHONY: deps-all
deps-all: deps-shared-models deps-shared-clients deps-tracing-config deps deps-request-manager deps-agent-service deps-integration-dispatcher deps-mcp-snow deps-mcp-zammad deps-mock-eventing deps-mock-employee-data deps-mock-servicenow deps-promptguard deps-evaluations deps-servicenow-bootstrap
	@echo "All dependencies installed successfully!"

.PHONY: deps-shared-models
deps-shared-models:
	@echo "Installing shared models dependencies..."
	cd shared-models && uv sync
	@echo "Shared models dependencies installed successfully!"

.PHONY: deps-shared-clients
deps-shared-clients:
	@echo "Installing shared clients dependencies..."
	cd shared-clients && uv sync
	@echo "Shared clients dependencies installed successfully!"

.PHONY: deps
deps:
	@echo "Installing self-service agent dependencies..."
	uv sync
	@echo "Self-service agent dependencies installed successfully!"

.PHONY: reinstall
reinstall:
	@echo "Force reinstalling all dependencies with latest code..."
	@echo "Reinstalling all dependencies with uv sync..."
	uv sync --reinstall
	@echo "All dependencies reinstalled with latest code!"

.PHONY: reinstall-all
reinstall-all: reinstall-shared-models reinstall-shared-clients reinstall reinstall-request-manager reinstall-agent-service reinstall-integration-dispatcher reinstall-mcp-snow reinstall-mcp-zammad reinstall-mock-employee-data reinstall-mock-servicenow reinstall-promptguard reinstall-servicenow-bootstrap
	@echo "All project dependencies reinstalled successfully!"


.PHONY: reinstall-request-manager
reinstall-request-manager:
	@echo "Force reinstalling request manager dependencies..."
	cd request-manager && uv sync --reinstall
	@echo "Request manager dependencies reinstalled successfully!"

.PHONY: reinstall-agent-service
reinstall-agent-service:
	@echo "Force reinstalling agent service dependencies..."
	cd agent-service && uv sync --reinstall
	@echo "Agent service dependencies reinstalled successfully!"

.PHONY: reinstall-integration-dispatcher
reinstall-integration-dispatcher:
	@echo "Force reinstalling integration dispatcher dependencies..."
	cd integration-dispatcher && uv sync --reinstall
	@echo "Integration dispatcher dependencies reinstalled successfully!"

.PHONY: reinstall-mcp-snow
reinstall-mcp-snow:
	@echo "Force reinstalling snow MCP dependencies..."
	cd mcp-servers/snow && uv sync --reinstall
	@echo "Snow MCP dependencies reinstalled successfully!"

.PHONY: reinstall-mcp-zammad
reinstall-mcp-zammad:
	@echo "Force reinstalling Zammad MCP dependencies..."
	cd mcp-servers/zammad && uv sync --reinstall
	@echo "Zammad MCP dependencies reinstalled successfully!"

.PHONY: reinstall-shared-models
reinstall-shared-models:
	@echo "Force reinstalling shared models dependencies..."
	cd shared-models && uv sync --reinstall
	@echo "Shared models dependencies reinstalled successfully!"

.PHONY: reinstall-shared-clients
reinstall-shared-clients:
	@echo "Force reinstalling shared clients dependencies..."
	cd shared-clients && uv sync --reinstall
	@echo "Shared clients dependencies reinstalled successfully!"

.PHONY: reinstall-servicenow-bootstrap
reinstall-servicenow-bootstrap:
	@echo "Force reinstalling ServiceNow automation dependencies..."
	cd scripts/servicenow-bootstrap && uv sync --reinstall
	@echo "ServiceNow automation dependencies reinstalled successfully!"

.PHONY: reinstall-mock-employee-data
reinstall-mock-employee-data:
	@echo "Force reinstalling mock employee data dependencies..."
	cd mock-employee-data && uv sync --reinstall
	@echo "Mock employee data dependencies reinstalled successfully!"

.PHONY: reinstall-mock-servicenow
reinstall-mock-servicenow:
	@if echo "$(SERVICENOW_INSTANCE_URL)" | grep -q "self-service-agent-mock-servicenow"; then \
		echo "Force reinstalling mock ServiceNow dependencies..."; \
		cd mock-service-now && uv sync --reinstall; \
		echo "Mock ServiceNow dependencies reinstalled successfully!"; \
	else \
		echo "Skipping mock ServiceNow reinstallation - SERVICENOW_INSTANCE_URL does not contain 'self-service-agent-mock-servicenow'"; \
		echo "Current SERVICENOW_INSTANCE_URL: $(SERVICENOW_INSTANCE_URL)"; \
	fi

.PHONY: reinstall-promptguard
reinstall-promptguard:
	@echo "Force reinstalling PromptGuard service dependencies..."
	cd promptguard-service && uv sync --reinstall
	@echo "PromptGuard service dependencies force reinstalled successfully!"

.PHONY: deps-request-manager
deps-request-manager:
	@echo "Installing request manager dependencies..."
	cd request-manager && uv sync
	@echo "Request manager dependencies installed successfully!"

.PHONY: deps-agent-service
deps-agent-service:
	@echo "Installing agent service dependencies..."
	cd agent-service && uv sync
	@echo "Agent service dependencies installed successfully!"

.PHONY: deps-integration-dispatcher
deps-integration-dispatcher:
	@echo "Installing integration dispatcher dependencies..."
	cd integration-dispatcher && uv sync
	@echo "Integration dispatcher dependencies installed successfully!"

.PHONY: deps-mcp-snow
deps-mcp-snow:
	@echo "Installing snow MCP dependencies..."
	cd mcp-servers/snow && uv sync
	@echo "Snow MCP dependencies installed successfully!"

.PHONY: deps-mcp-zammad
deps-mcp-zammad:
	@echo "Installing Zammad MCP dependencies..."
	cd mcp-servers/zammad && uv sync
	@echo "Zammad MCP dependencies installed successfully!"

.PHONY: deps-mock-eventing
deps-mock-eventing:
	@echo "Installing mock eventing service dependencies..."
	cd mock-eventing-service && uv sync
	@echo "Mock eventing service dependencies installed successfully!"

.PHONY: deps-mock-employee-data
deps-mock-employee-data:
	@echo "Installing mock employee data dependencies..."
	cd mock-employee-data && uv sync
	@echo "Mock employee data dependencies installed successfully!"

.PHONY: deps-mock-servicenow
deps-mock-servicenow:
	@if echo "$(SERVICENOW_INSTANCE_URL)" | grep -q "self-service-agent-mock-servicenow"; then \
		echo "Installing mock ServiceNow dependencies..."; \
		cd mock-service-now && uv sync; \
		echo "Mock ServiceNow dependencies installed successfully!"; \
	else \
		echo "Skipping mock ServiceNow installation - SERVICENOW_INSTANCE_URL does not contain 'self-service-agent-mock-servicenow'"; \
		echo "Current SERVICENOW_INSTANCE_URL: $(SERVICENOW_INSTANCE_URL)"; \
	fi

.PHONY: deps-promptguard
deps-promptguard:
	@echo "Installing PromptGuard service dependencies..."
	cd promptguard-service && uv sync
	@echo "PromptGuard service dependencies installed successfully!"

.PHONY: deps-tracing-config
deps-tracing-config:
	@echo "Installing tracing-config dependencies..."
	cd tracing-config && uv sync
	@echo "Tracing-config dependencies installed successfully!"

.PHONY: deps-evaluations
deps-evaluations:
	@echo "Installing evaluations dependencies..."
	cd evaluations && uv sync
	@echo "Evaluations dependencies installed successfully!"

.PHONY: deps-servicenow-bootstrap
deps-servicenow-bootstrap:
	@echo "Installing ServiceNow automation dependencies..."
	cd scripts/servicenow-bootstrap && uv sync
	@echo "ServiceNow automation dependencies installed successfully!"

# Test code
.PHONY: test-all
test-all: test-shared-models test-shared-clients test-request-manager test-agent-service test-integration-dispatcher test-mcp-snow test-mcp-zammad test-servicenow-bootstrap test-mock-employee-data test-mock-servicenow
	@echo "All tests completed successfully!"

# Lockfile management
# Recursive make with same Makefile (for helper targets that take DIR= etc.).
MAKE_SAME := $(MAKE) -f $(firstword $(MAKEFILE_LIST))
# All directories that have uv.lock (for check-lockfiles and update-lockfiles).
# Export of requirements.txt only runs for dirs also in REQUIREMENTS_DIRS (see update_lockfile).
LOCKFILE_DIRS := shared-models shared-clients agent-service request-manager integration-dispatcher mcp-servers/mcp-common mcp-servers/snow mcp-servers/zammad mock-eventing-service mock-employee-data promptguard-service scripts/servicenow-bootstrap zammad-bootstrap

define check_lockfile
	@echo "📦 Checking $(1)..."
	@if [ -d "$(1)" ]; then \
		if (cd "$(1)" && uv lock --check); then \
			echo "✅ $(1) lockfile is up-to-date"; \
		else \
			echo "❌ $(1) lockfile needs updating"; \
			exit 1; \
		fi; \
	else \
		echo "⚠️  $(1) directory not found, skipping..."; \
	fi
endef

define update_lockfile
	@echo "📦 Updating $(1)..."
	@if [ -d "$(1)" ]; then \
		cd "$(1)" && uv lock; \
		echo "✅ $(1) lockfile updated"; \
	else \
		echo "⚠️  $(1) directory not found, skipping..."; \
	fi
	@if [ -n "$(filter $(1),$(REQUIREMENTS_DIRS))" ] && [ -d "$(1)" ] && [ -f "$(1)/uv.lock" ]; then \
		$(MAKE_SAME) _export-one-dir DIR="$(1)"; \
	fi
endef

# Helper target for check-lockfiles: check lockfile for one dir (DIR= set by caller).
.PHONY: _check-one-lockfile
_check-one-lockfile:
	$(call check_lockfile,$(DIR))

# Helper target for update-lockfiles: update lockfile (and maybe export) for one dir (DIR= set by caller).
.PHONY: _update-one-lockfile
_update-one-lockfile:
	$(call update_lockfile,$(DIR))

.PHONY: check-lockfiles
check-lockfiles: check-uv-version
	@echo "🔍 Checking uv.lock files across all services..."
	@echo
	@echo "📦 Checking root project..."
	@if uv lock --check; then \
		echo "✅ Root project lockfile is up-to-date"; \
	else \
		echo "❌ Root project lockfile needs updating"; \
		exit 1; \
	fi
	@echo
	@for dir in $(LOCKFILE_DIRS); do \
		$(MAKE_SAME) _check-one-lockfile DIR="$$dir"; \
		echo; \
	done
	@echo "🎉 All lockfiles are up-to-date!"

.PHONY: update-lockfiles
update-lockfiles: check-uv-version
	@echo "🔄 Updating all uv.lock files..."
	@echo
	@echo "📦 Updating root project..."
	@uv lock
	@echo "✅ Root project lockfile updated"
	@echo
	@for dir in $(LOCKFILE_DIRS); do \
		$(MAKE_SAME) _update-one-lockfile DIR="$$dir"; \
		echo; \
	done
	@echo "🎉 All lockfiles updated successfully!"

# Individual service lockfile targets
.PHONY: check-lockfile-root check-lockfile-shared-models check-lockfile-shared-clients check-lockfile-agent-service check-lockfile-request-manager check-lockfile-integration-dispatcher check-lockfile-mcp-common check-lockfile-mcp-snow check-lockfile-mcp-zammad check-lockfile-mock-eventing check-lockfile-mock-employee-data check-lockfile-mock-servicenow check-lockfile-promptguard check-lockfile-servicenow-bootstrap check-lockfile-zammad-bootstrap
check-lockfile-root:
	@echo "📦 Checking root project..."
	@if uv lock --check; then \
		echo "✅ Root project lockfile is up-to-date"; \
	else \
		echo "❌ Root project lockfile needs updating"; \
		exit 1; \
	fi
check-lockfile-shared-models:
	$(call check_lockfile,shared-models)

check-lockfile-shared-clients:
	$(call check_lockfile,shared-clients)

check-lockfile-agent-service:
	$(call check_lockfile,agent-service)

check-lockfile-request-manager:
	$(call check_lockfile,request-manager)

check-lockfile-integration-dispatcher:
	$(call check_lockfile,integration-dispatcher)

check-lockfile-mcp-common:
	$(call check_lockfile,mcp-servers/mcp-common)

check-lockfile-mcp-snow:
	$(call check_lockfile,mcp-servers/snow)

check-lockfile-mcp-zammad:
	$(call check_lockfile,mcp-servers/zammad)

check-lockfile-mock-eventing:
	$(call check_lockfile,mock-eventing-service)

check-lockfile-mock-employee-data:
	$(call check_lockfile,mock-employee-data)

check-lockfile-mock-servicenow:
	$(call check_lockfile,mock-service-now)

check-lockfile-promptguard:
	$(call check_lockfile,promptguard-service)

check-lockfile-servicenow-bootstrap:
	$(call check_lockfile,scripts/servicenow-bootstrap)

check-lockfile-zammad-bootstrap:
	$(call check_lockfile,zammad-bootstrap)


.PHONY: update-lockfile-shared-models update-lockfile-shared-clients update-lockfile-agent-service update-lockfile-request-manager update-lockfile-integration-dispatcher update-lockfile-mcp-common update-lockfile-mcp-snow update-lockfile-mcp-zammad update-lockfile-mock-eventing update-lockfile-mock-employee-data update-lockfile-mock-servicenow update-lockfile-promptguard update-lockfile-servicenow-bootstrap update-lockfile-zammad-bootstrap
update-lockfile-shared-models:
	$(call update_lockfile,shared-models)

update-lockfile-shared-clients:
	$(call update_lockfile,shared-clients)

update-lockfile-agent-service:
	$(call update_lockfile,agent-service)

update-lockfile-request-manager:
	$(call update_lockfile,request-manager)

update-lockfile-integration-dispatcher:
	$(call update_lockfile,integration-dispatcher)

update-lockfile-mcp-common:
	$(call update_lockfile,mcp-servers/mcp-common)

update-lockfile-mcp-snow:
	$(call update_lockfile,mcp-servers/snow)

update-lockfile-mcp-zammad:
	$(call update_lockfile,mcp-servers/zammad)

update-lockfile-mock-eventing:
	$(call update_lockfile,mock-eventing-service)

update-lockfile-mock-employee-data:
	$(call update_lockfile,mock-employee-data)

update-lockfile-mock-servicenow:
	$(call update_lockfile,mock-service-now)

update-lockfile-promptguard:
	$(call update_lockfile,promptguard-service)

update-lockfile-servicenow-bootstrap:
	$(call update_lockfile,scripts/servicenow-bootstrap)

update-lockfile-zammad-bootstrap:
	$(call update_lockfile,zammad-bootstrap)

# Full export for one directory: check, cd, uv export, add_torch_hash, echo. Single line so Make does not echo the recipe.
# Usage: $(call export_requirements,dir) or: $(MAKE) _export-one-dir DIR=<dir>
define export_requirements
	@echo "📦 Exporting requirements.txt for $(1)..."; if [ -d "$(1)" ] && [ -f "$(1)/uv.lock" ]; then cd "$(1)" && uv export --format requirements-txt --no-dev -o requirements.txt > /dev/null 2>&1 && $(call add_torch_hash,requirements.txt) && echo "✅ $(1) requirements.txt exported"; else echo "⚠️  $(1) directory or lockfile not found, skipping..."; fi
endef

# Helper target for update_lockfile: export requirements for one dir (DIR= set by caller).
.PHONY: _export-one-dir
_export-one-dir:
	$(call export_requirements,$(DIR))

# Requirements.txt management
# REQUIREMENTS_DIRS = dirs we export requirements.txt for (subset of LOCKFILE_DIRS; see Lockfile management).
# Only export/check requirements.txt for directories that are built into containers AND have uv.lock files:
# - Services: agent-service, integration-dispatcher, promptguard-service, request-manager, mock-eventing-service, mock-service-now
# - MCP servers: mcp-servers/snow
# - Dependencies copied into containers: shared-models, shared-clients, mock-employee-data
# We exclude: evaluations, scripts/servicenow-bootstrap, root directory, tracing-config (no uv.lock)
# IMPORTANT: uv version must match CI (currently 0.8.9) to ensure consistent exports
# CI uses: astral-sh/setup-uv@v5 with version: "0.8.9"
# To install locally: curl -LsSf https://astral.sh/uv/0.8.9/install.sh | sh
# Or update: uv self update (may install newer version - check with make check-uv-version)
REQUIREMENTS_DIRS := agent-service integration-dispatcher promptguard-service request-manager mock-eventing-service mock-service-now mcp-servers/snow mcp-servers/zammad shared-models shared-clients mock-employee-data zammad-bootstrap
# UV_VERSION: uv version for CI validation and container builds (default: 0.8.9, can be overridden)
UV_VERSION ?= 0.8.9
EXTRACT_TORCH_HASH_SCRIPT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))scripts/extract_torch_hash.py)
UPDATE_TORCH_HASH_SCRIPT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))scripts/update_torch_hash.py)

# Function to add/update torch hash in requirements.txt (single line so it inlines without recipe echo).
# Uses Python 3.12 (312) for hash extraction since that's what the containers use.
# Usage: $(call add_torch_hash,requirements_file_path)
define add_torch_hash
	if [ -f "uv.lock" ] && grep -q "^torch==.*+cpu" $(1) 2>/dev/null; then TORCH_HASH=$$(python3 "$(EXTRACT_TORCH_HASH_SCRIPT)" "uv.lock" "312" 2>/dev/null) && if [ -n "$$TORCH_HASH" ]; then python3 "$(UPDATE_TORCH_HASH_SCRIPT)" "$(1)" "$$TORCH_HASH" > /dev/null 2>&1 && echo "  ✅ Updated hash for torch from lockfile"; fi; fi
endef

.PHONY: check-uv-version
check-uv-version:
	@echo "🔍 Checking uv version..."
	@LOCAL_UV_VERSION=$$(uv --version 2>/dev/null | sed 's/uv //' | sed 's/ .*//' || echo ""); \
	if [ -z "$$LOCAL_UV_VERSION" ]; then \
		echo "❌ uv is not installed. Install with: curl -LsSf https://astral.sh/uv/$(UV_VERSION)/install.sh | sh"; \
		exit 1; \
	fi; \
	if [ "$$LOCAL_UV_VERSION" != "$(UV_VERSION)" ]; then \
		echo "⚠️  Warning: uv version is $$LOCAL_UV_VERSION, but CI uses $(UV_VERSION)"; \
		echo "   Different versions may produce different exports, causing CI failures"; \
		echo "   Update with: uv self update"; \
		echo "   Or install specific version: curl -LsSf https://astral.sh/uv/$(UV_VERSION)/install.sh | sh"; \
	else \
		echo "✅ uv version $$LOCAL_UV_VERSION matches CI requirement"; \
	fi


.PHONY: export-requirements
export-requirements: check-uv-version
	@echo "📦 Exporting requirements.txt for containerized services..."
	@echo
	@for dir in $(REQUIREMENTS_DIRS); do \
		$(MAKE_SAME) _export-one-dir DIR="$$dir"; \
		echo; \
	done
	@echo "🎉 All requirements.txt files exported successfully!"

.PHONY: check-requirements
check-requirements: check-uv-version
	@echo "🔍 Checking requirements.txt files are in sync with uv.lock files..."
	@echo
	@MISSING=""; \
	OUT_OF_SYNC=""; \
	for dir in $(REQUIREMENTS_DIRS); do \
		normalized_dir="$$dir"; \
		req_file="$$dir/requirements.txt"; \
		display_dir="$$dir"; \
		echo "📦 Checking $$display_dir..."; \
		if [ ! -f "$$req_file" ]; then \
			echo "❌ $$req_file is missing"; \
			MISSING="$$MISSING $$display_dir"; \
		else \
			cd "$$normalized_dir" && \
			uv export --format requirements-txt --no-dev -o /tmp/current-requirements-$$$$.txt > /dev/null 2>&1 && \
			$(call add_torch_hash,/tmp/current-requirements-$$$$.txt) && \
			grep -v '^#' requirements.txt > /tmp/existing-requirements-$$$$.txt && \
			grep -v '^#' /tmp/current-requirements-$$$$.txt > /tmp/new-requirements-$$$$.txt && \
			if ! diff -q /tmp/existing-requirements-$$$$.txt /tmp/new-requirements-$$$$.txt > /dev/null 2>&1; then \
				echo "❌ $$req_file is out of sync with uv.lock"; \
				OUT_OF_SYNC="$$OUT_OF_SYNC $$display_dir"; \
			else \
				echo "✅ $$req_file is in sync"; \
			fi && \
			rm -f /tmp/current-requirements-$$$$.txt /tmp/existing-requirements-$$$$.txt /tmp/new-requirements-$$$$.txt && \
			cd - > /dev/null 2>&1; \
		fi; \
		echo; \
	done; \
	if [ -n "$$MISSING" ]; then \
		echo "❌ Missing requirements.txt files:$$MISSING"; \
		echo "Run 'make export-requirements' to generate missing requirements.txt files"; \
		exit 1; \
	fi; \
	if [ -n "$$OUT_OF_SYNC" ]; then \
		echo "❌ Out-of-sync requirements.txt files:$$OUT_OF_SYNC"; \
		echo "Run 'make export-requirements' to regenerate requirements.txt files"; \
		exit 1; \
	fi; \
	echo "✅ All requirements.txt files are in sync with their uv.lock files"


# Test targets: sync dev deps ([dependency-groups] dev), then run pytest.
# Usage: $(call run_pytest,Display Name,dir)
define run_pytest
	@echo "Running $(1) tests..."
	cd $(2) && uv sync --group dev && uv run python -m pytest tests/
	@echo "$(1) tests completed successfully!"
endef

.PHONY: test-shared-models
test-shared-models:
	$(call run_pytest,shared models,shared-models)

.PHONY: test-shared-clients
test-shared-clients:
	$(call run_pytest,shared clients,shared-clients)

.PHONY: test-request-manager
test-request-manager:
	$(call run_pytest,request manager,request-manager)

.PHONY: test-agent-service
test-agent-service:
	$(call run_pytest,agent service,agent-service)

.PHONY: test-integration-dispatcher
test-integration-dispatcher:
	$(call run_pytest,integration dispatcher,integration-dispatcher)

.PHONY: test-mcp-snow
test-mcp-snow:
	$(call run_pytest,snow MCP,mcp-servers/snow)

.PHONY: test-mcp-zammad
test-mcp-zammad:
	$(call run_pytest,zammad MCP,mcp-servers/zammad)

.PHONY: test-servicenow-bootstrap
test-servicenow-bootstrap:
	$(call run_pytest,ServiceNow automation,scripts/servicenow-bootstrap)

.PHONY: test-mock-employee-data
test-mock-employee-data:
	$(call run_pytest,mock employee data,mock-employee-data)

.PHONY: test-mock-servicenow
test-mock-servicenow:
	$(call run_pytest,mock servicenow,mock-service-now)

.PHONY: sync-evaluations
sync-evaluations:
	@echo "Syncing evaluations libraries"
	uv --directory evaluations sync
	@echo "Syncing evaluations libraries completed successfully!"

.PHONY: check-known-bad-conversations
check-known-bad-conversations: sync-evaluations
	@echo "Running evaluation check on known bad conversations..."
	uv --directory evaluations run evaluate.py --check
	@echo "Evaluation check completed successfully!"

.PHONY: test-short-ticket-laptop-refresh
test-short-ticket-laptop-refresh:
	@echo "Running short responses integration test for ticket-laptop-refresh flow..."
	uv --directory evaluations run evaluate.py --message-timeout 1800 --timeout=1800 -n 1 --flow ticket_laptop_refresh $(VALIDATE_LAPTOP_DETAILS_FLAG) $(STRUCTURED_OUTPUT_FLAG)
	@echo "short responses integration test for ticket-laptop-refresh flow completed successfully!"

.PHONY: test-short-resp-integration-request-mgr
test-short-resp-integration-request-mgr:
	@echo "Running short responses integration test with Request Manager..."
	uv --directory evaluations run evaluate.py -n 1 --test-script chat-responses-request-mgr.py --reset-conversation $(VALIDATE_LAPTOP_DETAILS_FLAG) $(STRUCTURED_OUTPUT_FLAG)
	@echo "short responses integrations tests with Request Manager completed successfully!"

.PHONY: test-long-resp-integration-request-mgr
test-long-resp-integration-request-mgr:
	@echo "Running long responses integration test with Request Manager..."
	uv --directory evaluations run evaluate.py -n 20 --test-script chat-responses-request-mgr.py --reset-conversation --timeout=1800 --message-timeout=120 $(VALIDATE_LAPTOP_DETAILS_FLAG) $(STRUCTURED_OUTPUT_FLAG)
	@echo "long responses integrations tests with Request Manager completed successfully!"

.PHONY: test-medium-resp-integration-request-mgr
test-medium-resp-integration-request-mgr:
	@echo "Running medium responses integration test with Request Manager..."
	uv --directory evaluations run evaluate.py -n 5 --test-script chat-responses-request-mgr.py --reset-conversation --timeout=1800 --message-timeout=120 $(VALIDATE_LAPTOP_DETAILS_FLAG) $(STRUCTURED_OUTPUT_FLAG)
	@echo "medium responses integrations tests with Request Manager completed successfully!"

.PHONY: test-long-concurrent-integration-request-mgr
test-long-concurrent-integration-request-mgr:
	@echo "Running long concurrent responses integration test with Request Manager..."
	uv --directory evaluations run evaluate.py -n 10 --test-script chat-responses-request-mgr.py --reset-conversation --timeout=1800 --concurrency 4 --message-timeout 120 $(VALIDATE_LAPTOP_DETAILS_FLAG) $(STRUCTURED_OUTPUT_FLAG)
	@echo "long concurrent responses integrations tests with Request Manager completed successfully!"

# Session tests hit load-balanced service so cross-pod scenarios are exercised (2+ replicas).
# Override with REQUEST_MANAGER_URL=http://localhost:8080 for same-pod only.
REQUEST_MANAGER_URL ?= http://$(MAIN_CHART_NAME)-request-manager:80
# Stagger between sends per user; 1800 reduces created_at reorder flakiness with 2+ replicas.
STAGGER_MS ?= 1800
# Usage: $(call run_session_test,Display Name,script.py,extra_env,extra_args)
define run_session_test
	@echo "Running $(1) (requires cluster with NAMESPACE set)..."
	kubectl exec deploy/$(MAIN_CHART_NAME)-request-manager -n $(NAMESPACE) -- \
		env REQUEST_MANAGER_URL=$(REQUEST_MANAGER_URL) \
		MESSAGE_TIMEOUT=250 \
		$(3) \
		/app/.venv/bin/python /app/test/$(2) $(4)
	@echo "$(1) completed successfully!"
endef

.PHONY: test-session-serialization-integration
test-session-serialization-integration:
	$(call run_session_test,session serialization integration test,session_serialization_integration.py,STAGGER_MS=$(STAGGER_MS),--stagger-ms $(STAGGER_MS))

.PHONY: test-session-reclaim-integration
test-session-reclaim-integration:
	$(call run_session_test,session reclaim integration test,session_reclaim_integration.py,,)

.PHONY: test-session-background-reclaim-integration
test-session-background-reclaim-integration:
	@echo "Running background reclaim integration test (requires cluster with NAMESPACE set, ~60s for reclaim)..."
	@# timeout 180: background reclaim runs every 45s; worst case ~60s. 180s allows for CI variance.
	@TIMEOUT_CMD=$$(command -v timeout 2>/dev/null || command -v gtimeout 2>/dev/null || true) && \
	if [ -n "$$TIMEOUT_CMD" ]; then \
		$$TIMEOUT_CMD 180 kubectl exec deploy/$(MAIN_CHART_NAME)-request-manager -n $(NAMESPACE) -- \
			env REQUEST_MANAGER_URL=$(REQUEST_MANAGER_URL) \
			MESSAGE_TIMEOUT=250 \
			/app/.venv/bin/python /app/test/session_background_reclaim_integration.py; \
	else \
		echo "Note: timeout not found (macOS: brew install coreutils for gtimeout); running without timeout"; \
		kubectl exec deploy/$(MAIN_CHART_NAME)-request-manager -n $(NAMESPACE) -- \
			env REQUEST_MANAGER_URL=$(REQUEST_MANAGER_URL) \
			MESSAGE_TIMEOUT=250 \
			/app/.venv/bin/python /app/test/session_background_reclaim_integration.py; \
	fi
	@echo "Background reclaim integration test completed successfully!"

.PHONY: generate-two-sessions
generate-two-sessions:
	@echo "Generating session"
	uv --directory evaluations run generator.py 2 --test-script chat-responses-request-mgr.py --reset-conversation $(STRUCTURED_OUTPUT_FLAG)
	@echo "Two sessions generated successfully!"

# Create namespace and deploy
namespace:
	@kubectl create namespace $(NAMESPACE) &> /dev/null && kubectl label namespace $(NAMESPACE) modelmesh-enabled=false ||:
	@kubectl config set-context --current --namespace=$(NAMESPACE) &> /dev/null ||:

.PHONY: helm-depend
helm-depend:
	@needs_update=; \
	for pair in $$(awk '/^- name:/{n=$$3} /^  version:/{if(n){v=$$2; gsub(/"/,"",v); print n"-"v".tgz"; n=""}}' helm/Chart.lock 2>/dev/null); do \
		if [ ! -f "helm/charts/$$pair" ]; then needs_update=1; break; fi; \
	done; \
	if [ -z "$$needs_update" ] && [ -n "$$(awk '/^- name:/{n=$$3} /^  version:/{if(n){print; n=""}}' helm/Chart.lock 2>/dev/null)" ]; then \
		echo "Helm dependencies present (Chart.lock), skipping update"; \
	else \
		echo "Updating Helm dependencies"; \
		cd helm && helm dependency update; \
	fi

.PHONY: helm-list-models
helm-list-models: helm-depend
	@helm template dummy-release helm --set llm-service._debugListModels=true | grep ^model:

# Common function for helm installation with different eventing modes
define helm_install_common
	@$(eval PGVECTOR_ARGS := $(helm_pgvector_args))
	@$(eval LLM_SERVICE_ARGS := $(helm_llm_service_args))
	@$(eval LLAMA_STACK_ARGS := $(helm_llama_stack_args))
	@$(eval REQUEST_MANAGEMENT_ARGS := $(helm_request_management_args))
	@$(eval LOG_LEVEL_ARGS := $(if $(LOG_LEVEL),--set logLevel=$(LOG_LEVEL),))
	@$(eval GENERIC_ARGS := $(helm_generic_args))
	@$(eval REPLICA_COUNT_ARGS := $(helm_replica_count_args))
	@$(eval TEST_USERS_ARGS := $(helm_test_users_args))
	@$(eval LANGFUSE_ARGS := $(if $(filter true,$(ENABLE_LANGFUSE)),--set langfuse.enabled=true,))
	@$(eval FAULT_INJECTION_ARGS := $(helm_fault_injection_args))

	@echo "Creating ServiceNow credentials secret..."
	@echo "  Instance URL: $$SERVICENOW_INSTANCE_URL"
	@kubectl create secret generic $(MAIN_CHART_NAME)-servicenow-credentials \
		--from-literal=servicenow-instance-url="$${SERVICENOW_INSTANCE_URL:-}" \
		--from-literal=servicenow-api-key="$${SERVICENOW_API_KEY:-}" \
		-n $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -

	@echo "Cleaning up any existing jobs..."
	@kubectl delete job -l app.kubernetes.io/component=init -n $(NAMESPACE) --ignore-not-found || true
	@kubectl delete job -l app.kubernetes.io/name=self-service-agent -n $(NAMESPACE) --ignore-not-found || true
	@echo "Installing $(MAIN_CHART_NAME) helm chart $(1)"
	@if [ -n "$(GIT_BRANCH)" ] && [ "$(origin VERSION)" = "undefined" ]; then \
		echo "Using image version: $(VERSION) (auto-detected from branch: $(GIT_BRANCH))"; \
	else \
		echo "Using image version: $(VERSION)"; \
	fi
	@helm upgrade --install $(MAIN_CHART_NAME) helm -n $(NAMESPACE) --timeout 15m \
		--set image.requestManager=self-service-agent-request-manager \
		--set image.agentService=self-service-agent-service \
		--set image.integrationDispatcher=self-service-agent-integration-dispatcher \
		--set image.tag=$(VERSION) \
		$(PGVECTOR_ARGS) \
		$(LLM_SERVICE_ARGS) \
		$(LLAMA_STACK_ARGS) \
		--set requestManagement.integrations.slack.enabled=$(SLACK_ENABLED) \
		$(if $(filter true,$(SLACK_ENABLED)),--set security.slack.signingSecret=$(SLACK_SIGNING_SECRET) --set security.slack.botToken=$(SLACK_BOT_TOKEN),) \
		--set image.registry=$(REGISTRY) \
		--set mcp-servers.mcp-servers.self-service-agent-snow.image.repository=$(REGISTRY)/self-service-agent-snow-mcp \
		--set mcp-servers.mcp-servers.self-service-agent-snow.image.tag=$(VERSION) \
		--set-string mcp-servers.mcp-servers.self-service-agent-snow.env.SERVICENOW_LAPTOP_REFRESH_ID="$(SERVICENOW_LAPTOP_REFRESH_ID)" \
		--set-string mcp-servers.mcp-servers.self-service-agent-snow.env.SERVICENOW_LAPTOP_AVOID_DUPLICATES="$(SERVICENOW_LAPTOP_AVOID_DUPLICATES)" \
		--set-string mcp-servers.mcp-servers.self-service-agent-snow.env.SERVICENOW_LAPTOP_REQUEST_LIMITS="$(SERVICENOW_LAPTOP_REQUEST_LIMITS)" \
		--set mcp-servers.mcp-servers.self-service-agent-snow.envSecrets.SERVICENOW_INSTANCE_URL.name=$(MAIN_CHART_NAME)-servicenow-credentials \
		--set mcp-servers.mcp-servers.self-service-agent-snow.envSecrets.SERVICENOW_INSTANCE_URL.key=servicenow-instance-url \
		$(REQUEST_MANAGEMENT_ARGS) \
		$(LOG_LEVEL_ARGS) \
		$(GENERIC_ARGS) \
		$(REPLICA_COUNT_ARGS) \
		$(TEST_USERS_ARGS) \
		$(LANGFUSE_ARGS) \
		$(FAULT_INJECTION_ARGS) \
		$(DEFAULT_AGENT_ID_ARG) \
		$(if $(filter-out "",$(2)),$(2),) \
		$(EXTRA_HELM_ARGS)
	@echo "Waiting for deployments to be ready..."
	@for resource in \
		"deploy/$(MAIN_CHART_NAME)-request-manager:request manager" \
		"deploy/$(MAIN_CHART_NAME)-integration-dispatcher:integration dispatcher" \
		"deploy/$(MAIN_CHART_NAME)-agent-service:agent service" \
		"deploy/llamastack:llamastack" \
		"deploy/mcp-self-service-agent-snow:mcp-self-service-agent-snow" \
		"statefulset/pgvector:pgvector" \
		"job/$(MAIN_CHART_NAME)-db-migration:db-migration" \
		"job/$(MAIN_CHART_NAME)-init:init"; do \
		name=$${resource#*:}; \
		res=$${resource%:*}; \
		echo "  Waiting for $$name..."; \
		if echo "$$res" | grep -q "^job/"; then \
			kubectl wait --for=condition=complete --timeout=10m $$res -n $(NAMESPACE) || echo "    Job check completed (may have already run)"; \
		else \
			kubectl rollout status $$res -n $(NAMESPACE) --timeout 10m; \
		fi; \
	done
	@(kubectl get deploy/$(MAIN_CHART_NAME)-mock-eventing -n $(NAMESPACE) >/dev/null 2>&1 && echo "Waiting for mock eventing deployment..." && kubectl rollout status deploy/$(MAIN_CHART_NAME)-mock-eventing -n $(NAMESPACE) --timeout 5m || echo "Skipping mock eventing (not deployed)") && (kubectl get deploy/$(MAIN_CHART_NAME)-mock-servicenow -n $(NAMESPACE) >/dev/null 2>&1 && echo "Waiting for mock ServiceNow..." && kubectl rollout status deploy/$(MAIN_CHART_NAME)-mock-servicenow -n $(NAMESPACE) --timeout 5m || echo "Skipping mock ServiceNow (not deployed)")
	$(if $(filter true,$(PROMPTGUARD_ENABLED)),@echo "Waiting for PromptGuard deployment..." && kubectl rollout status deploy/$(MAIN_CHART_NAME)-promptguard -n $(NAMESPACE) --timeout 10m,)
	$(if $(filter true,$(ENABLE_LANGFUSE)),@echo "Waiting for Redis StatefulSet..." && kubectl rollout status statefulset/$(MAIN_CHART_NAME)-redis -n $(NAMESPACE) --timeout 10m && echo "Waiting for MinIO StatefulSet..." && kubectl rollout status statefulset/$(MAIN_CHART_NAME)-minio -n $(NAMESPACE) --timeout 10m && echo "Waiting for ClickHouse StatefulSet..." && kubectl rollout status statefulset/$(MAIN_CHART_NAME)-clickhouse -n $(NAMESPACE) --timeout 10m && echo "Waiting for LangFuse Web deployment..." && kubectl rollout status deploy/$(MAIN_CHART_NAME)-langfuse -n $(NAMESPACE) --timeout 10m && echo "Waiting for LangFuse Worker deployment (runs ClickHouse migrations)..." && kubectl rollout status deploy/$(MAIN_CHART_NAME)-langfuse-worker -n $(NAMESPACE) --timeout 10m && echo "LangFuse URL: https://$$(kubectl get route $(MAIN_CHART_NAME)-langfuse -n $(NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null || echo 'Route not found')",)
	@echo "$(MAIN_CHART_NAME) $(1) installed successfully"
endef

# Export helm chart to YAML (no cluster access); $(1) = extra helm args
define helm_export
	@rm -rf $(HELM_EXPORT_DIR)
	@mkdir -p $(HELM_EXPORT_DIR)
	@echo "Exporting $(MAIN_CHART_NAME) helm chart to $(HELM_EXPORT_DIR)..."
	@helm template $(MAIN_CHART_NAME) helm -n $(NAMESPACE) --output-dir $(HELM_EXPORT_DIR) \
		--set image.requestManager=self-service-agent-request-manager \
		--set image.agentService=self-service-agent-service \
		--set image.integrationDispatcher=self-service-agent-integration-dispatcher \
		--set image.tag=$(VERSION) \
		$(helm_pgvector_args) \
		$(helm_llm_service_args) \
		$(helm_llama_stack_args) \
		--set requestManagement.integrations.slack.enabled=$(SLACK_ENABLED) \
		$(if $(filter true,$(SLACK_ENABLED)),--set security.slack.signingSecret=$(SLACK_SIGNING_SECRET) --set security.slack.botToken=$(SLACK_BOT_TOKEN),) \
		--set image.registry=$(REGISTRY) \
		--set mcp-servers.mcp-servers.self-service-agent-snow.image.repository=$(REGISTRY)/self-service-agent-snow-mcp \
		--set mcp-servers.mcp-servers.self-service-agent-snow.image.tag=$(VERSION) \
		--set-string mcp-servers.mcp-servers.self-service-agent-snow.env.SERVICENOW_LAPTOP_REFRESH_ID="$(SERVICENOW_LAPTOP_REFRESH_ID)" \
		--set-string mcp-servers.mcp-servers.self-service-agent-snow.env.SERVICENOW_LAPTOP_AVOID_DUPLICATES="$(SERVICENOW_LAPTOP_AVOID_DUPLICATES)" \
		--set-string mcp-servers.mcp-servers.self-service-agent-snow.env.SERVICENOW_LAPTOP_REQUEST_LIMITS="$(SERVICENOW_LAPTOP_REQUEST_LIMITS)" \
		--set mcp-servers.mcp-servers.self-service-agent-snow.envSecrets.SERVICENOW_INSTANCE_URL.name=$(MAIN_CHART_NAME)-servicenow-credentials \
		--set mcp-servers.mcp-servers.self-service-agent-snow.envSecrets.SERVICENOW_INSTANCE_URL.key=servicenow-instance-url \
		$(helm_request_management_args) \
		$(if $(LOG_LEVEL),--set logLevel=$(LOG_LEVEL),) \
		$(helm_generic_args) \
		$(helm_replica_count_args) \
		$(helm_test_users_args) \
		$(if $(filter true,$(ENABLE_LANGFUSE)),--set langfuse.enabled=true,) \
		$(helm_fault_injection_args) \
		$(DEFAULT_AGENT_ID_ARG) \
		$(if $(filter-out "",$(1)),$(1),) \
		$(EXTRA_HELM_ARGS)
	@echo "Helm export complete."
endef

# Install with mock eventing service (testing/development/CI mode - default)
# Extract all LG_PROMPT_* variables and convert them to Helm --set arguments
PROMPT_OVERRIDES := $(foreach var,$(filter LG_PROMPT_%,$(.VARIABLES)),--set requestManagement.agentService.promptOverrides.lg-prompt-$(shell echo $(var:LG_PROMPT_%=%) | tr '[:upper:]' '[:lower:]' | tr '_' '-')=$($(var)))
DEFAULT_AGENT_ID_ARG := $(if $(DEFAULT_AGENT_ID),--set agent.defaultAgentId=$(DEFAULT_AGENT_ID),)

.PHONY: helm-install-test
helm-install-test: namespace helm-depend
	$(call helm_install_common,"with mock eventing service - testing/CI",\
		-f helm/values-test.yaml \
		--set requestManagement.knative.mockEventing.enabled=true \
		--set testIntegrationEnabled=true \
		$(PROMPT_OVERRIDES),\
		true)
	@$(MAKE) print-urls

# Install with demo config (Greenmail email, resource constraints, mock eventing)
.PHONY: helm-install-demo
helm-install-demo: namespace helm-depend deploy-email-server
	$(call helm_install_common,with demo config - mock eventing and Greenmail email,\
		-f helm/values-test.yaml \
		-f helm/values-demo.yaml \
		$(helm_demo_email_args) \
		$(PROMPT_OVERRIDES),\
		true)
	@$(MAKE) print-urls

# Install with ticketing channel (Zammad + MCP).
# Order: install our chart first (creates Route), deploy Zammad with FQDN from Route, then bootstrap token.
# Zammad gets correct FQDN at deploy (passed from Route host).
.PHONY: helm-install-ticketing
helm-install-ticketing: namespace helm-depend
	@echo "Step 1/4: Creating placeholder secret and installing our chart..."
	@ZAMMAD_URL="http://zammad-nginx.$(NAMESPACE).svc.cluster.local:8080"; \
	kubectl create secret generic $(ZAMMAD_CREDENTIALS_SECRET) \
		--from-literal=zammad-url="$$ZAMMAD_URL" \
		--from-literal=zammad-api-url="$$ZAMMAD_URL/api/v1" \
		--from-literal=zammad-http-token="" \
		-n $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -; \
	$(MAKE) _helm-install-ticketing-single ZAMMAD_URL="$$ZAMMAD_URL"
	@echo "Step 2/4: Deploying Zammad (auto-detects Route hostname for FQDN and embed URL)..."
	@$(MAKE) deploy-zammad NAMESPACE=$(NAMESPACE)
	@echo "Waiting for Zammad railsserver to be ready (may take 10+ minutes on first deploy)..."
	@kubectl rollout status deployment/zammad-railsserver -n $(NAMESPACE) --timeout=15m
	@echo "Step 3/4: Creating API token..."
	@ZAMMAD_URL="http://zammad-nginx.$(NAMESPACE).svc.cluster.local:8080"; \
	ZAMMAD_TOKEN=$$(kubectl get secret $(ZAMMAD_CREDENTIALS_SECRET) -n $(NAMESPACE) -o jsonpath='{.data.zammad-http-token}' 2>/dev/null | base64 -d 2>/dev/null || true); \
	if [ -z "$$ZAMMAD_TOKEN" ]; then \
		echo "Creating Zammad API token via exec..."; \
		ZAMMAD_TOKEN=$$(kubectl exec deploy/zammad-railsserver -n $(NAMESPACE) -- env ZAMMAD_ADMIN_EMAIL='$(ZAMMAD_ADMIN_EMAIL)' ZAMMAD_ADMIN_PASSWORD='$(ZAMMAD_ADMIN_PASSWORD)' ruby -rnet/http -rjson -e 'uri=URI("http://localhost:3000/api/v1/user_access_token");req=Net::HTTP::Post.new(uri);req.basic_auth(ENV["ZAMMAD_ADMIN_EMAIL"],ENV["ZAMMAD_ADMIN_PASSWORD"]);req["Content-Type"]="application/json";req.body=JSON.generate({"name"=>"mcp-agent","permission"=>["admin","ticket.agent"]});res=Net::HTTP.start(uri.hostname,uri.port){|h|h.request(req)};d=JSON.parse(res.body);t=d["token"];t ? puts(t) : ($$stderr.puts("Zammad API #{res.code}: #{res.body[0,500]}");exit 1)' ) || ZAMMAD_TOKEN=""; \
	fi; \
	if [ -n "$$ZAMMAD_TOKEN" ]; then \
		echo "✅ Token created"; \
		kubectl create secret generic $(ZAMMAD_CREDENTIALS_SECRET) \
			--from-literal=zammad-url="$$ZAMMAD_URL" \
			--from-literal=zammad-api-url="$$ZAMMAD_URL/api/v1" \
			--from-literal=zammad-http-token="$$ZAMMAD_TOKEN" \
			-n $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -; \
		echo "Restarting Zammad MCP and request manager ..."; \
		kubectl rollout restart deployment/mcp-zammad-mcp -n $(NAMESPACE) 2>/dev/null || true; \
		kubectl rollout restart deployment/$(MAIN_CHART_NAME)-request-manager -n $(NAMESPACE) 2>/dev/null || true; \
		kubectl rollout status deployment/mcp-zammad-mcp -n $(NAMESPACE) --timeout=2m 2>/dev/null || true; \
		kubectl rollout status deployment/$(MAIN_CHART_NAME)-request-manager -n $(NAMESPACE) --timeout=2m 2>/dev/null || true; \
	else \
		echo "⚠ Token creation failed (run make zammad-bootstrap-token NAMESPACE=$(NAMESPACE) after completing autoWizard)"; \
	fi
	@echo "Step 4/4: Printing checklist..."
	@$(MAKE) _helm-install-ticketing-print-checklist NAMESPACE=$(NAMESPACE)

.PHONY: _helm-install-ticketing-single
_helm-install-ticketing-single:
	@$(call helm_install_common,with ticketing config - Zammad MCP,\
		-f helm/values-test.yaml \
		-f helm/values-ticketing.yaml \
		--set mcp-servers.mcp-servers.zammad-mcp.enabled=true \
		$(helm_ticketing_args) \
		$(PROMPT_OVERRIDES),\
		true)
	@$(MAKE) print-urls

.PHONY: _helm-install-ticketing-print-checklist
_helm-install-ticketing-print-checklist:
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "🎫 Ticketing Channel - Follow-up Steps"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "  1. Zammad URLs:"
	@ZAMMAD_ROUTE=$$(oc get route ssa-zammad -n $(NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null); \
	ZAMMAD_EMBED_ROUTE=$$(oc get route ssa-zammad-embed -n $(NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null); \
	if [ -z "$$ZAMMAD_ROUTE" ]; then ZAMMAD_ROUTE=$$(oc get route -n $(NAMESPACE) -l app.kubernetes.io/instance=zammad -o jsonpath='{.items[0].spec.host}' 2>/dev/null); fi; \
	if [ -n "$$ZAMMAD_ROUTE" ]; then \
		echo "     Web UI: https://$$ZAMMAD_ROUTE"; \
		echo "     API:    https://$$ZAMMAD_ROUTE/api/v1"; \
		if [ -n "$$ZAMMAD_EMBED_ROUTE" ]; then echo "     Embed:  https://$$ZAMMAD_EMBED_ROUTE (Zammad chat widget — embed snippet + live preview)"; fi; \
	else \
		echo "     Port-forward: kubectl port-forward -n $(NAMESPACE) svc/zammad-nginx 8080:8080"; \
		echo "     Web UI: http://localhost:8080"; \
		echo "     API:    http://localhost:8080/api/v1"; \
	fi
	@echo ""
	@echo "  2. Zammad FQDN: configured at deploy (from Route host) so Route loads correctly"
	@echo ""
	@echo "  3. If token was not auto-created:"
	@echo "     - make zammad-bootstrap-token NAMESPACE=$(NAMESPACE)"
	@echo "     - Or create token in Zammad UI, then: make zammad-set-token NAMESPACE=$(NAMESPACE) ZAMMAD_TOKEN=<token>"
	@echo ""
	@echo "  4. Chat widget: Admin → Channels → Chat (agents must be available)."
	@echo "     Full chat → agent reply loop needs app integration (webhook/MCP/agent) when enabled."
	@echo ""
	@echo "  5. (Optional) Webhook trigger for Zammad → blueprint (when that integration is merged)."
	@echo ""
	@echo "  Admin login defaults: ZAMMAD_ADMIN_EMAIL / ZAMMAD_ADMIN_PASSWORD (see Makefile; must match autoWizard in helm/values-zammad-deploy.yaml)."
	@echo "  More: README.md, docs/HELM_EXPORT_ANSIBLE.md"
	@echo ""

# Install with full Knative eventing (production mode)
.PHONY: helm-install-prod
helm-install-prod: namespace helm-depend
	@echo "Installing with retry logic for triggers..."
	@for i in 1 2 3; do \
		echo "Attempt $$i of 3..."; \
		if $(MAKE) _helm-install-prod-single; then \
			echo "Installation successful, verifying broker and triggers..."; \
			EXPECTED_TRIGGERS=10; \
			ACTUAL_TRIGGERS=$$(kubectl get triggers -n $(NAMESPACE) --no-headers 2>/dev/null | wc -l); \
			if [ "$$ACTUAL_TRIGGERS" -eq "$$EXPECTED_TRIGGERS" ]; then \
				echo "✅ All $$EXPECTED_TRIGGERS triggers deployed"; \
				echo "Waiting for broker to be ready..."; \
				BROKER_NAME=$$(kubectl get broker -n $(NAMESPACE) -o jsonpath='{.items[0].metadata.name}' 2>/dev/null); \
				if [ -z "$$BROKER_NAME" ]; then \
					echo "❌ No broker found in namespace $(NAMESPACE)"; \
					if [ $$i -lt 3 ]; then \
						echo "Attempt $$i failed, waiting 30s before retry..."; \
						sleep 30; \
						continue; \
					else \
						exit 1; \
					fi; \
				else \
					echo "  Waiting for broker $$BROKER_NAME to be Ready..."; \
					if kubectl wait --for=condition=Ready broker/$$BROKER_NAME -n $(NAMESPACE) --timeout=5m 2>/dev/null; then \
						echo "✅ Broker $$BROKER_NAME is Ready"; \
						echo "Waiting for all triggers to be Ready..."; \
						ALL_READY=true; \
						for trigger in $$(kubectl get triggers -n $(NAMESPACE) -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do \
							echo "  Waiting for trigger $$trigger to be Ready..."; \
							if ! kubectl wait --for=condition=Ready trigger/$$trigger -n $(NAMESPACE) --timeout=5m 2>/dev/null; then \
								echo "❌ Trigger $$trigger failed to become Ready"; \
								ALL_READY=false; \
							else \
								echo "  ✅ Trigger $$trigger is Ready"; \
							fi; \
						done; \
						if [ "$$ALL_READY" = "true" ]; then \
							echo "✅ All triggers are Ready"; \
							$(MAKE) print-urls; \
							exit 0; \
						else \
							echo "❌ Some triggers failed to become Ready"; \
							if [ $$i -lt 3 ]; then \
								echo "Attempt $$i failed, waiting 30s before retry..."; \
								sleep 30; \
							fi; \
						fi; \
					else \
						echo "❌ Broker $$BROKER_NAME failed to become Ready"; \
						if [ $$i -lt 3 ]; then \
							echo "Attempt $$i failed, waiting 30s before retry..."; \
							sleep 30; \
						fi; \
					fi; \
				fi; \
			else \
				echo "❌ Only $$ACTUAL_TRIGGERS out of $$EXPECTED_TRIGGERS triggers deployed"; \
				if [ $$i -lt 3 ]; then \
					echo "Attempt $$i failed, waiting 30s before retry..."; \
					sleep 30; \
				fi; \
			fi; \
		else \
			echo "Installation failed on attempt $$i"; \
			if [ $$i -lt 3 ]; then \
				echo "Waiting 30s before retry..."; \
				sleep 30; \
			fi; \
		fi; \
	done; \
	echo "❌ Failed to deploy all triggers after 3 attempts"; \
	exit 1

# Single installation attempt for production
.PHONY: _helm-install-prod-single
_helm-install-prod-single:
	@$(call helm_install_common,"with full Knative eventing - production",\
		-f helm/values-production.yaml \
		--set requestManagement.knative.eventing.enabled=true,\
		false)

# Print service URLs (used after successful installation)
.PHONY: print-urls
print-urls:
	@$(PRINT_REQUEST_MANAGER_URL)
	@$(PRINT_INTEGRATION_DISPATCHER_URL)

# Verify all expected Knative triggers are deployed
.PHONY: verify-triggers
verify-triggers:
	@echo "Verifying all triggers are deployed..."
	@EXPECTED_TRIGGERS=10; \
	ACTUAL_TRIGGERS=$$(kubectl get triggers -n $(NAMESPACE) --no-headers 2>/dev/null | wc -l); \
	if [ "$$ACTUAL_TRIGGERS" -eq "$$EXPECTED_TRIGGERS" ]; then \
		echo "✅ All $$EXPECTED_TRIGGERS triggers deployed successfully"; \
		kubectl get triggers -n $(NAMESPACE) --no-headers | awk '{print "  - " $$1}'; \
	else \
		echo "❌ Only $$ACTUAL_TRIGGERS out of $$EXPECTED_TRIGGERS triggers deployed"; \
		echo ""; \
		echo "Deployed triggers:"; \
		kubectl get triggers -n $(NAMESPACE) --no-headers 2>/dev/null | awk '{print "  ✅ " $$1}' || echo "  (none)"; \
		echo ""; \
		echo "Expected triggers:"; \
		echo "  ✅ self-service-agent-integration-dispatcher-to-request-manager-trigger"; \
		echo "  ✅ self-service-agent-request-created-trigger"; \
		echo "  ✅ self-service-agent-agent-response-trigger"; \
		echo "  ✅ self-service-agent-routing-trigger"; \
		echo "  ✅ self-service-agent-agent-response-to-request-manager-trigger"; \
		echo "  ✅ self-service-agent-request-notification-trigger"; \
		echo "  ✅ self-service-agent-processing-notification-trigger"; \
		echo "  ✅ self-service-agent-database-update-trigger"; \
		echo "  ✅ self-service-agent-session-create-or-get-trigger"; \
		echo "  ✅ self-service-agent-session-ready-trigger"; \
		echo ""; \
		echo "To fix missing triggers, run:"; \
		echo "  make helm-install-prod"; \
		exit 1; \
	fi

.PHONY: helm-export-demo
helm-export-demo: helm-depend
	$(call helm_export,\
		-f helm/values-test.yaml \
		-f helm/values-demo.yaml \
		$(helm_demo_email_args) \
		$(PROMPT_OVERRIDES))
	@echo "Adding ServiceNow credentials secret to export..."
	@kubectl create secret generic $(MAIN_CHART_NAME)-servicenow-credentials \
		--from-literal=servicenow-instance-url="$${SERVICENOW_INSTANCE_URL:-http://self-service-agent-mock-servicenow:8080}" \
		--from-literal=servicenow-api-key="$${SERVICENOW_API_KEY:-now_mock_api_key}" \
		-n $(NAMESPACE) --dry-run=client -o yaml > $(HELM_EXPORT_DIR)/servicenow-credentials-secret.yaml
	@echo "Demo export complete at $(HELM_EXPORT_DIR)/"

.PHONY: helm-export-validate-demo
helm-export-validate-demo: helm-export-demo
	@command -v kubeconform >/dev/null 2>&1 || { \
		echo "Error: kubeconform not found. Install for offline manifest validation:"; \
		echo "  brew install kubeconform  # macOS"; \
		echo "  or: https://github.com/yannh/kubeconform#installation"; \
		exit 1; \
	}
	@echo "Validating exported manifests (kubeconform, no cluster required)..."
	@kubeconform -summary -ignore-missing-schemas $(HELM_EXPORT_DIR)/
	@echo "Helm export validation passed."

.PHONY: check-ansible
check-ansible:
	@command -v ansible-playbook >/dev/null 2>&1 || { \
		echo "Error: ansible-playbook not found. Install ansible (core) to run ansible-apply-demo or ansible-teardown-demo."; \
		echo "  pip install ansible-core  # or: uv pip install ansible-core"; \
		exit 1; \
	}

.PHONY: ansible-apply-demo
ansible-apply-demo: check-ansible helm-export-demo
	ansible-playbook -i localhost, ansible/playbooks/apply-demo-manifests.yml \
		-e "helm_export_dir=$(HELM_EXPORT_DIR)" \
		-e "target_namespace=$(NAMESPACE)"

.PHONY: ansible-teardown-demo
ansible-teardown-demo: check-ansible
	ansible-playbook -i localhost, ansible/playbooks/teardown-demo-manifests.yml \
		-e "target_namespace=$(NAMESPACE)"

# Uninstall the deployment and clean up
.PHONY: helm-uninstall
helm-uninstall:
	@echo "Enhanced uninstall process for $(MAIN_CHART_NAME) helm chart in namespace $(NAMESPACE)"

	@echo "Step 1: Attempting normal helm uninstall..."
	@helm uninstall --ignore-not-found $(MAIN_CHART_NAME) -n $(NAMESPACE) || echo "Normal uninstall failed, proceeding with enhanced cleanup..."

	@echo "Step 2: Manual cleanup of namespace-scoped Knative resources..."
	@echo "Cleaning up Knative Eventing resources in $(NAMESPACE) only..."
	@kubectl delete triggers -n $(NAMESPACE) --all --ignore-not-found --timeout=30s || true
	@kubectl delete broker -n $(NAMESPACE) --all --ignore-not-found --timeout=30s || true
	@echo "Cleaning up Knative-related ConfigMaps..."
	@kubectl delete configmap -n $(NAMESPACE) -l app.kubernetes.io/name=self-service-agent --ignore-not-found || true
	@echo "Force cleanup any stuck resources with finalizers..."
	@kubectl get broker -n $(NAMESPACE) -o name 2>/dev/null | xargs -r -I {} kubectl patch {} -n $(NAMESPACE) --type merge -p '{"metadata":{"finalizers":[]}}' || true
	@kubectl get trigger -n $(NAMESPACE) -o name 2>/dev/null | xargs -r -I {} kubectl patch {} -n $(NAMESPACE) --type merge -p '{"metadata":{"finalizers":[]}}' || true

	@echo "Step 3: Retry helm uninstall after cleanup..."
	@helm uninstall --ignore-not-found $(MAIN_CHART_NAME) -n $(NAMESPACE) || echo "Helm uninstall completed with manual cleanup"

	@echo "Step 4: Final cleanup of namespace $(NAMESPACE)..."
	@$(MAKE) helm-cleanup-jobs
	@$(MAKE) undeploy-email-server
	@$(MAKE) undeploy-zammad
	@echo "Removing ServiceNow credentials secret from $(NAMESPACE)"
	@kubectl delete secret $(MAIN_CHART_NAME)-servicenow-credentials -n $(NAMESPACE) --ignore-not-found || true
	@echo "Removing Zammad credentials secret from $(NAMESPACE)"
	@kubectl delete secret $(ZAMMAD_CREDENTIALS_SECRET) -n $(NAMESPACE) --ignore-not-found || true
	@echo "Removing pgvector, init job, and LangFuse PVCs from $(NAMESPACE)"
	@kubectl get pvc -n $(NAMESPACE) -o custom-columns=NAME:.metadata.name 2>/dev/null | grep -E '^(pg.*-data|self-service-agent-init-status|data-self-service-agent-(clickhouse|redis|minio)-.*)' | xargs -I {} kubectl delete pvc -n $(NAMESPACE) {} --ignore-not-found ||:
	@echo "Deleting remaining pods in namespace $(NAMESPACE)"
	@kubectl delete pods -n $(NAMESPACE) --all || true
	@echo "Checking for any remaining resources in namespace $(NAMESPACE)..."
	@echo "If you want to completely remove the namespace, run: kubectl delete namespace $(NAMESPACE)"
	@echo "Remaining resources in namespace $(NAMESPACE):"
	@$(MAKE) helm-status

# Manual cleanup for Knative Eventing resources (useful for webhook timeout issues)
.PHONY: helm-cleanup-eventing
helm-cleanup-eventing:
	@echo "Manual cleanup of Knative Eventing resources in $(NAMESPACE)..."
	@echo "Step 1: Attempting normal deletion with short timeout..."
	@kubectl delete triggers -n $(NAMESPACE) --all --ignore-not-found --timeout=10s || echo "Normal trigger deletion failed, proceeding with force cleanup..."
	@kubectl delete broker -n $(NAMESPACE) --all --ignore-not-found --timeout=10s || echo "Normal broker deletion failed, proceeding with force cleanup..."
	@kubectl delete configmap -n $(NAMESPACE) -l app.kubernetes.io/name=self-service-agent --ignore-not-found || true
	@echo "Step 2: Force cleanup any stuck resources with finalizers..."
	@echo "Attempting to patch finalizers on brokers..."
	@kubectl get broker -n $(NAMESPACE) -o name 2>/dev/null | xargs -r -I {} kubectl patch {} -n $(NAMESPACE) --type merge -p '{"metadata":{"finalizers":[]}}' --timeout=10s || echo "Patch failed, trying force delete..."
	@echo "Attempting to patch finalizers on triggers..."
	@kubectl get trigger -n $(NAMESPACE) -o name 2>/dev/null | xargs -r -I {} kubectl patch {} -n $(NAMESPACE) --type merge -p '{"metadata":{"finalizers":[]}}' --timeout=10s || echo "Patch failed, trying force delete..."
	@echo "Step 3: Force delete with zero grace period..."
	@kubectl get broker -n $(NAMESPACE) -o name 2>/dev/null | xargs -r -I {} kubectl delete {} -n $(NAMESPACE) --force --grace-period=0 || echo "Force delete failed, resource may need manual intervention"
	@kubectl get trigger -n $(NAMESPACE) -o name 2>/dev/null | xargs -r -I {} kubectl delete {} -n $(NAMESPACE) --force --grace-period=0 || echo "Force delete failed, resource may need manual intervention"
	@echo "Step 4: Final verification..."
	@echo "Remaining Knative Eventing resources in $(NAMESPACE):"
	@kubectl get broker,trigger -n $(NAMESPACE) 2>/dev/null || echo "No Knative Eventing resources found"
	@echo "Knative Eventing cleanup completed for namespace $(NAMESPACE). If resources still exist, they may require cluster admin intervention to resolve webhook issues."

# Clean up leftover jobs
.PHONY: helm-cleanup-jobs
helm-cleanup-jobs:
	@echo "Cleaning up leftover jobs in namespace $(NAMESPACE)..."
	@kubectl delete jobs -n $(NAMESPACE) -l app.kubernetes.io/name=self-service-agent --ignore-not-found || true
	@echo "Job cleanup completed for namespace $(NAMESPACE)"

# Check deployment status
.PHONY: helm-status
helm-status:
	@echo "Listing pods..."
	kubectl get pods -n $(NAMESPACE) || true

	@echo "Listing services..."
	kubectl get svc -n $(NAMESPACE) || true

	@echo "Listing routes..."
	kubectl get routes -n $(NAMESPACE) || true

	@echo "Listing secrets..."
	kubectl get secrets -n $(NAMESPACE) | grep huggingface-secret || true

	@echo "Listing pvcs..."
	kubectl get pvc -n $(NAMESPACE) || true

.PHONY: oc
export OC = ./bin/oc
oc: ## Download oc locally if necessary.
ifeq (,$(wildcard $(OC)))
ifeq (,$(shell which oc 2>/dev/null))
	@{ \
	set -e ;\
	mkdir -p $(dir $(OC)) ;\
	curl -sSLo oc.tar.gz https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/4.11.6/openshift-client-linux.tar.gz ;\
	tar -xf oc.tar.gz -C $(dir $(OC)) oc ;\
	}
else
OC = $(shell which oc)
endif
endif

# Jaeger deployment targets
.PHONY: jaeger-deploy
jaeger-deploy: namespace
	@echo "Deploying Jaeger all-in-one to namespace $(NAMESPACE)..."
	@kubectl create deployment jaeger --image=cr.jaegertracing.io/jaegertracing/jaeger:2.12.0 -n $(NAMESPACE) || echo "Deployment already exists"
	@echo "Adding network policy labels to Jaeger deployment..."
	@kubectl label deployment jaeger -n $(NAMESPACE) \
		app.kubernetes.io/instance=self-service-agent \
		app.kubernetes.io/name=self-service-agent \
		--overwrite || true
	@kubectl patch deployment jaeger -n $(NAMESPACE) --type=json -p='[{"op":"add","path":"/spec/template/metadata/labels/app.kubernetes.io~1instance","value":"self-service-agent"},{"op":"add","path":"/spec/template/metadata/labels/app.kubernetes.io~1name","value":"self-service-agent"}]' || true
	@echo "Creating network policy for Jaeger UI external access..."
	@# Network policy allows OpenShift router to access Jaeger UI on port 16686
	@# This is required because the default network policies only allow ports 8080/80
	@printf '%s\n' \
		'apiVersion: networking.k8s.io/v1' \
		'kind: NetworkPolicy' \
		'metadata:' \
		'  name: jaeger-allow-ingress' \
		'  namespace: $(NAMESPACE)' \
		'  labels:' \
		'    app: jaeger' \
		'spec:' \
		'  podSelector:' \
		'    matchLabels:' \
		'      app.kubernetes.io/instance: self-service-agent' \
		'      app.kubernetes.io/name: self-service-agent' \
		'      app: jaeger' \
		'  policyTypes:' \
		'  - Ingress' \
		'  ingress:' \
		'  - from:' \
		'    - namespaceSelector:' \
		'        matchLabels:' \
		'          network.openshift.io/policy-group: ingress' \
		'    ports:' \
		'    - protocol: TCP' \
		'      port: 16686' \
		| kubectl apply -f - || echo "Network policy creation failed, may already exist"
	@kubectl expose deployment jaeger --port=16686 --name=jaeger-ui -n $(NAMESPACE) || echo "Service already exists"
	@kubectl expose deployment jaeger --port=4318 --name=jaeger-otlp-http -n $(NAMESPACE) || echo "OTLP HTTP service already exists"
	@kubectl expose deployment jaeger --port=4317 --name=jaeger-otlp-grpc -n $(NAMESPACE) || echo "OTLP gRPC service already exists"
	@oc create route edge jaeger-ui --service=jaeger-ui -n $(NAMESPACE) || echo "Route already exists"
	@echo "✅ Jaeger deployed successfully!"
	@echo ""
	@echo "📊 Jaeger UI: https://$$(oc get route jaeger-ui -n $(NAMESPACE) -o jsonpath='{.spec.host}')"
	@echo ""
	@echo "To enable tracing in the self-service-agent, redeploy with:"
	@echo "  export OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger-otlp-http.$(NAMESPACE).svc.cluster.local:4318"
	@echo "  make helm-install-test NAMESPACE=$(NAMESPACE)"
	@echo ""
	@echo "Note: The endpoint should NOT include '/v1/traces' - the application adds this automatically"

.PHONY: jaeger-undeploy
jaeger-undeploy:
	@echo "Removing Jaeger from namespace $(NAMESPACE)..."
	@oc delete route jaeger-ui -n $(NAMESPACE) || echo "Route not found"
	@kubectl delete service jaeger-ui jaeger-otlp-http jaeger-otlp-grpc -n $(NAMESPACE) || echo "Services not found"
	@kubectl delete networkpolicy jaeger-allow-ingress -n $(NAMESPACE) || echo "Network policy not found"
	@kubectl delete deployment jaeger -n $(NAMESPACE) || echo "Deployment not found"
	@echo "✅ Jaeger removed successfully!"

# Test Email Server deployment targets
.PHONY: deploy-email-server
deploy-email-server: namespace
	@echo "Deploying test email server (Greenmail + Custom UI) to namespace $(NAMESPACE)..."
	@kubectl apply -f test-email-server/test-email-server-greenmail.yaml -n $(NAMESPACE)
	@echo "Waiting for test email server deployment to be ready..."
	@kubectl rollout status deployment/test-email-server -n $(NAMESPACE) --timeout=5m || \
		(echo "❌ Deployment failed. Check logs with: kubectl logs -n $(NAMESPACE) deployment/test-email-server -c greenmail" && exit 1)
	@echo ""
	@echo "✅ Test email server (Greenmail) deployed successfully!"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "📧 Greenmail Email Server Information"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "📬 Web UI URL:"
	@UI_ROUTE=$$(oc get route test-email-server-ui -n $(NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null); \
	echo "  https://$$UI_ROUTE"
	@echo ""
	@echo "🔐 Test User Accounts (each has separate inbox):"
	@echo "  alice.johnson@company.com     (password: testpass123)"
	@echo "  john.doe@company.com          (password: testpass123)"
	@echo "  maria.garcia@company.com      (password: testpass123)"
	@echo ""
	@echo "🚀 Deploy Quickstart with Email Integration:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "make helm-install-test NAMESPACE=$(NAMESPACE) \\"
	@echo "  EXTRA_HELM_ARGS=\"-f helm/values-demo.yaml \\"
	@echo "    --set-string security.email.smtpHost=test-email-server-smtp.$(NAMESPACE).svc.cluster.local \\"
	@echo "    --set-string security.email.imapHost=test-email-server-imap.$(NAMESPACE).svc.cluster.local\""
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

.PHONY: undeploy-email-server
undeploy-email-server:
	@echo "Removing test email server from namespace $(NAMESPACE)..."
	@kubectl delete -f test-email-server/test-email-server-greenmail.yaml -n $(NAMESPACE) --ignore-not-found 2>/dev/null || true
	@echo "✅ Test email server removed successfully!"

# Zammad deployment (prerequisite for ticketing channel)
ZAMMAD_HELM_REPO ?= https://zammad.github.io/zammad-helm
ZAMMAD_CHART_VERSION ?= 16.0.4

# ZAMMAD_FQDN: when set (e.g. from Route host), passed as extraEnv so Zammad accepts Route requests.
# Used by helm-install-ticketing which installs our chart first (creates Route), then deploys Zammad.
.PHONY: deploy-zammad
deploy-zammad: namespace
	@echo "Deploying Zammad instance to namespace $(NAMESPACE)..."
	@echo "This may take 10-15 minutes (Zammad brings elasticsearch, postgresql, redis, memcached)..."
	@helm repo add zammad $(ZAMMAD_HELM_REPO) 2>/dev/null || helm repo add zammad $(ZAMMAD_HELM_REPO) --force-update
	@helm repo update zammad
	@helm dependency update helm/zammad/
	@ZAMMAD_UID=$$(kubectl get namespace $(NAMESPACE) -o jsonpath='{.metadata.annotations.openshift\.io/sa\.scc\.uid-range}' 2>/dev/null | cut -d'/' -f1); \
	ZAMMAD_ARGS="-f helm/values-zammad-deploy.yaml --set bootstrap.image=$(ZAMMAD_BOOTSTRAP_IMG)"; \
	if [ -n "$$ZAMMAD_UID" ]; then \
		ZAMMAD_ARGS="$$ZAMMAD_ARGS --set zammad.securityContext.runAsUser=$$ZAMMAD_UID --set zammad.securityContext.runAsGroup=$$ZAMMAD_UID --set zammad.securityContext.fsGroup=$$ZAMMAD_UID"; \
		echo "OpenShift: using namespace UID $$ZAMMAD_UID for restricted SCC"; \
	fi; \
	helm upgrade --install zammad helm/zammad/ \
		-n $(NAMESPACE) \
		$$ZAMMAD_ARGS \
		--timeout 20m \
		--wait; \
	ZAMMAD_FQDN="$(ZAMMAD_FQDN)"; \
	if [ -z "$$ZAMMAD_FQDN" ]; then \
		ZAMMAD_FQDN=$$(oc get route ssa-zammad -n $(NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null); \
	fi; \
	if [ -n "$$ZAMMAD_FQDN" ]; then \
		echo "Configuring Zammad FQDN: $$ZAMMAD_FQDN"; \
		TMPFQDN=$$(mktemp); \
		echo "zammad:" > $$TMPFQDN; \
		echo "  extraEnv:" >> $$TMPFQDN; \
		echo "    - name: ZAMMAD_FQDN" >> $$TMPFQDN; \
		echo "      value: \"$$ZAMMAD_FQDN\"" >> $$TMPFQDN; \
		echo "    - name: ZAMMAD_HTTP_TYPE" >> $$TMPFQDN; \
		echo "      value: \"https\"" >> $$TMPFQDN; \
		helm upgrade zammad helm/zammad/ \
			-n $(NAMESPACE) \
			$$ZAMMAD_ARGS \
			-f $$TMPFQDN; \
		rm -f $$TMPFQDN; \
	fi; \
	helm upgrade --install zammad-embed helm/zammad-embed/ \
		-n $(NAMESPACE)
	@echo "Waiting for Zammad bootstrap Job to complete..."
	@kubectl wait job/zammad-bootstrap -n $(NAMESPACE) --for=condition=complete --timeout=10m 2>/dev/null \
		&& echo "✅ Bootstrap complete." \
		|| echo "⚠ Bootstrap Job did not complete in time — check: kubectl logs -n $(NAMESPACE) job/zammad-bootstrap"
	@echo ""
	@echo "✅ Zammad instance deployed successfully!"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "🎫 Zammad Ticketing Instance"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "📋 Next steps:"
	@ZAMMAD_ROUTE=$$(oc get route ssa-zammad -n $(NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null); \
	if [ -z "$$ZAMMAD_ROUTE" ]; then ZAMMAD_ROUTE=$$(oc get route -n $(NAMESPACE) -l app.kubernetes.io/instance=zammad -o jsonpath='{.items[0].spec.host}' 2>/dev/null); fi; \
	echo "  1. Zammad URLs:"; \
	if [ -n "$$ZAMMAD_ROUTE" ]; then \
		echo "     Web UI: https://$$ZAMMAD_ROUTE"; \
		echo "     API:    https://$$ZAMMAD_ROUTE/api/v1"; \
	else \
		echo "     No Route found - port-forward: kubectl port-forward -n $(NAMESPACE) svc/zammad-nginx 8080:8080"; \
		echo "     Web UI / API: http://localhost:8080 (and /api/v1)"; \
	fi; \
	echo ""; \
	echo "  2. Admin login:"; \
	echo "       Email:    $(ZAMMAD_ADMIN_EMAIL)"; \
	echo "       Password: $(ZAMMAD_ADMIN_PASSWORD)"; \
	echo ""; \
	echo "  3. HTTP API token for MCP: make zammad-bootstrap-token NAMESPACE=$(NAMESPACE)"; \
	echo "     If you ran this deploy via make helm-install-ticketing, token bootstrap runs next in that recipe—skip if you see success below."; \
	echo ""; \
	echo "  4. Chat widget: Admin → Channels → Chat (agents must be available for the widget to appear)."; \
	echo "  5. Main chart: zammad.enabled, zammad.url, credentials Secret (use helm-install-ticketing or manual Secret)."; \
	echo ""; \
	echo "  More: README.md, docs/HELM_EXPORT_ANSIBLE.md"
	@echo ""

.PHONY: undeploy-zammad
undeploy-zammad:
	@echo "Removing Zammad instance from namespace $(NAMESPACE)..."
	@helm uninstall zammad-embed -n $(NAMESPACE) --ignore-not-found 2>/dev/null || true
	@helm uninstall zammad -n $(NAMESPACE) --ignore-not-found 2>/dev/null || true
	@echo "Waiting for pods to terminate, then removing Zammad PVCs..."
	@sleep 5
	@kubectl delete pvc -n $(NAMESPACE) -l app.kubernetes.io/instance=zammad --ignore-not-found 2>/dev/null || true
	@for pvc in $$(kubectl get pvc -n $(NAMESPACE) -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n' | grep -E '^data-zammad-' || true); do kubectl delete pvc $$pvc -n $(NAMESPACE) --ignore-not-found; done
	@echo "✅ Zammad instance removed successfully!"

# Trigger autoWizard via HTTP (creates admin user). Run once before zammad-bootstrap-token.
# Uses GET /api/v1/getting_started/auto_wizard/:token
.PHONY: zammad-trigger-autowizard
zammad-trigger-autowizard: namespace
	@echo "Triggering autoWizard via HTTP..."; \
	RES=$$(kubectl exec deploy/zammad-railsserver -n $(NAMESPACE) -- ruby -rnet/http -e 'uri=URI("http://zammad-nginx:8080/api/v1/getting_started/auto_wizard/$(ZAMMAD_AUTOWIZARD_TOKEN)");res=Net::HTTP.get_response(uri);puts res.code' 2>/dev/null) || RES=""; \
	if [ "$$RES" = "200" ] || [ "$$RES" = "204" ]; then \
		echo "✅ autoWizard triggered (HTTP $$RES). Waiting 5s for setup..."; \
		sleep 5; \
	else \
		echo "⚠ autoWizard request returned HTTP $$RES (may already be done or system not ready)"; \
	fi

# Create Zammad API token via exec into railsserver (uses admin from autoWizard), update secret, restart MCP.
# Idempotent: if secret already has a token, skips creation. Use ZAMMAD_FORCE_BOOTSTRAP=1 to recreate.
.PHONY: zammad-bootstrap-token
zammad-bootstrap-token: namespace zammad-trigger-autowizard
	@ZAMMAD_URL="http://zammad-nginx.$(NAMESPACE).svc.cluster.local:8080"; \
	ZAMMAD_TOKEN=$$(kubectl get secret $(ZAMMAD_CREDENTIALS_SECRET) -n $(NAMESPACE) -o jsonpath='{.data.zammad-http-token}' 2>/dev/null | base64 -d 2>/dev/null || true); \
	if [ -n "$$ZAMMAD_TOKEN" ] && [ "$(ZAMMAD_FORCE_BOOTSTRAP)" != "1" ]; then \
		echo "Secret already has token (idempotent). Use ZAMMAD_FORCE_BOOTSTRAP=1 to recreate."; \
		exit 0; \
	fi; \
	echo "Creating Zammad API token via exec..."; \
	ZAMMAD_TOKEN=$$(kubectl exec deploy/zammad-railsserver -n $(NAMESPACE) -- env ZAMMAD_ADMIN_EMAIL='$(ZAMMAD_ADMIN_EMAIL)' ZAMMAD_ADMIN_PASSWORD='$(ZAMMAD_ADMIN_PASSWORD)' ruby -rnet/http -rjson -e 'uri=URI("http://localhost:3000/api/v1/user_access_token");req=Net::HTTP::Post.new(uri);req.basic_auth(ENV["ZAMMAD_ADMIN_EMAIL"],ENV["ZAMMAD_ADMIN_PASSWORD"]);req["Content-Type"]="application/json";req.body=JSON.generate({"name"=>"mcp-agent","permission"=>["admin","ticket.agent"]});res=Net::HTTP.start(uri.hostname,uri.port){|h|h.request(req)};d=JSON.parse(res.body);t=d["token"];t ? puts(t) : ($$stderr.puts("Zammad API #{res.code}: #{res.body[0,500]}");exit 1)' ) || ZAMMAD_TOKEN=""; \
	if [ -z "$$ZAMMAD_TOKEN" ]; then \
		echo "❌ Token creation failed (401 = invalid credentials)."; \
		echo "   Complete autoWizard first: visit <zammad-url>/#getting_started/auto_wizard/$(ZAMMAD_AUTOWIZARD_TOKEN)"; \
		echo "   (Port-forward: kubectl port-forward -n $(NAMESPACE) svc/zammad-nginx 8080:8080, then http://localhost:8080/...)"; \
		exit 1; \
	fi; \
	kubectl create secret generic $(ZAMMAD_CREDENTIALS_SECRET) \
		--from-literal=zammad-url="$$ZAMMAD_URL" \
		--from-literal=zammad-api-url="$$ZAMMAD_URL/api/v1" \
		--from-literal=zammad-http-token="$$ZAMMAD_TOKEN" \
		-n $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -; \
	echo "Restarting Zammad MCP..."; \
	kubectl rollout restart deployment/mcp-zammad-mcp -n $(NAMESPACE); \
	kubectl rollout status deployment/mcp-zammad-mcp -n $(NAMESPACE) --timeout=2m; \
	echo "✅ Zammad token created and MCP restarted."

.PHONY: zammad-set-token
zammad-set-token: namespace
	@if [ -z "$(ZAMMAD_TOKEN)" ]; then \
		echo "❌ Error: ZAMMAD_TOKEN is required."; \
		echo "  1. Create token in Zammad: Admin → Token Access → add HTTP Token"; \
		echo "  2. Run: make zammad-set-token NAMESPACE=$(NAMESPACE) ZAMMAD_TOKEN=<your-token>"; \
		exit 1; \
	fi
	@ZAMMAD_URL="http://zammad-nginx.$(NAMESPACE).svc.cluster.local:8080"; \
	echo "Updating Zammad credentials secret with token..."; \
	kubectl create secret generic $(ZAMMAD_CREDENTIALS_SECRET) \
		--from-literal=zammad-url="$$ZAMMAD_URL" \
		--from-literal=zammad-api-url="$$ZAMMAD_URL/api/v1" \
		--from-literal=zammad-http-token="$(ZAMMAD_TOKEN)" \
		-n $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -; \
	echo "Restarting Zammad MCP deployment..."; \
	kubectl rollout restart deployment/mcp-zammad-mcp -n $(NAMESPACE); \
	kubectl rollout status deployment/mcp-zammad-mcp -n $(NAMESPACE) --timeout=2m; \
	echo "✅ Zammad token set and MCP restarted."

# ServiceNow PDI wake-up
.PHONY: servicenow-wake-install
servicenow-wake-install: deps-servicenow-bootstrap
	@echo "Installing Playwright browsers..."
	@cd scripts/servicenow-bootstrap && uv run playwright install chromium

.PHONY: servicenow-wake
servicenow-wake: servicenow-wake-install
	@if [ -z "$(SERVICENOW_DEV_PORTAL_USERNAME)" ] || [ -z "$(SERVICENOW_DEV_PORTAL_PASSWORD)" ]; then \
		echo "❌ Error: SERVICENOW_DEV_PORTAL_USERNAME and SERVICENOW_DEV_PORTAL_PASSWORD are required"; \
		exit 1; \
	fi
	@cd scripts/servicenow-bootstrap && uv run python -m servicenow_bootstrap.wake_up_pdi

.PHONY: servicenow-bootstrap
servicenow-bootstrap:
	@echo "Running ServiceNow bootstrap setup with config..."
	@cd scripts/servicenow-bootstrap && uv run -m servicenow_bootstrap.setup --config config.json $(ARGS)
	@echo "ServiceNow bootstrap setup completed successfully!"

.PHONY: servicenow-bootstrap-validation
servicenow-bootstrap-validation:
	@echo "Running ServiceNow bootstrap validation..."
	@cd scripts/servicenow-bootstrap && uv run python -m servicenow_bootstrap.setup_validations
	@echo "ServiceNow bootstrap validation completed successfully!"

.PHONY: servicenow-bootstrap-create-user
servicenow-bootstrap-create-user:
	@echo "Creating MCP agent user..."
	@cd scripts/servicenow-bootstrap && uv run python -m servicenow_bootstrap.create_mcp_agent_user --config config.json
	@echo "MCP agent user creation completed successfully!"

.PHONY: servicenow-bootstrap-create-api-key
servicenow-bootstrap-create-api-key:
	@echo "Creating MCP agent API key..."
	@cd scripts/servicenow-bootstrap && uv run python -m servicenow_bootstrap.create_mcp_agent_api_key --config config.json
	@echo "MCP agent API key creation completed successfully!"

.PHONY: servicenow-bootstrap-create-catalog-item
servicenow-bootstrap-create-catalog-item:
	@echo "Creating PC refresh service catalog item..."
	@cd scripts/servicenow-bootstrap && uv run python -m servicenow_bootstrap.create_pc_refresh_service_catalog_item --config config.json
	@echo "PC refresh service catalog item creation completed successfully!"

.PHONY: servicenow-bootstrap-create-evaluation-users
servicenow-bootstrap-create-evaluation-users:
	@echo "Creating evaluation users..."
	@cd scripts/servicenow-bootstrap && uv run python -m servicenow_bootstrap.create_evaluation_users
	@echo "Evaluation users creation completed successfully!"

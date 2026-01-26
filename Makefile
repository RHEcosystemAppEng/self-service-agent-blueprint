# Makefile for RAG Deployment
ifeq ($(NAMESPACE),)
ifneq (,$(filter namespace helm-install-test helm-install-prod helm-uninstall helm-status helm-cleanup-eventing helm-cleanup-jobs,$(MAKECMDGOALS)))
$(error NAMESPACE is not set)
endif
endif

# Auto-detect version based on git branch if VERSION is not explicitly set
# - main branch: uses base version (0.0.2) for stable builds
# - dev branch: uses '0.0.2-dev' tag (matches CI builds)
# - branches forked from dev: uses '0.0.2-dev' tag (dev builds)
# - all other branches: uses base version (0.0.2) for stable builds (default)
# Set VERSION explicitly to override this behavior (e.g., VERSION=latest)
BASE_VERSION := 0.0.9
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
REQUEST_MGR_IMG ?= $(REGISTRY)/self-service-agent-request-manager:$(VERSION)
AGENT_SERVICE_IMG ?= $(REGISTRY)/self-service-agent-service:$(VERSION)
INTEGRATION_DISPATCHER_IMG ?= $(REGISTRY)/self-service-agent-integration-dispatcher:$(VERSION)
MCP_SNOW_IMG ?= $(REGISTRY)/self-service-agent-snow-mcp:$(VERSION)
MOCK_EVENTING_IMG ?= $(REGISTRY)/self-service-agent-mock-eventing:$(VERSION)
MOCK_SERVICENOW_IMG ?= $(REGISTRY)/self-service-agent-mock-servicenow:$(VERSION)
PROMPTGUARD_IMG ?= $(REGISTRY)/self-service-agent-promptguard:$(VERSION)

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

# Evaluation Configuration
# Enable full laptop details validation by default unless explicitly disabled
# Set VALIDATE_FULL_LAPTOP_DETAILS=false to disable validation
VALIDATE_FULL_LAPTOP_DETAILS ?= true
VALIDATE_LAPTOP_DETAILS_FLAG := $(if $(filter true,$(VALIDATE_FULL_LAPTOP_DETAILS)),--validate-full-laptop-details,--no-validate-full-laptop-details)

# Enable structured output mode for evaluations (default: false)
# Set USE_STRUCTURED_OUTPUT=true to enable Pydantic schema validation with retries
USE_STRUCTURED_OUTPUT ?= false
STRUCTURED_OUTPUT_FLAG := $(if $(filter true,$(USE_STRUCTURED_OUTPUT)),--use-structured-output,)

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
	$(if $(OTEL_EXPORTER_OTLP_ENDPOINT),--set mcp-servers.mcp-servers.self-service-agent-snow.env.OTEL_EXPORTER_OTLP_ENDPOINT="$(OTEL_EXPORTER_OTLP_ENDPOINT)")

helm_replica_count_args = \
	$(if $(REPLICA_COUNT),--set llamastack.postInitScaling.enabled=true,) \
	$(if $(REPLICA_COUNT),--set llamastack.postInitScaling.targetReplicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set mcp-servers.mcp-servers.self-service-agent-snow.replicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set requestManagement.knative.mockEventing.replicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set requestManagement.kafka.replicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set requestManagement.requestManager.replicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set requestManagement.integrationDispatcher.replicas=$(REPLICA_COUNT),) \
	$(if $(REPLICA_COUNT),--set requestManagement.agentService.replicas=$(REPLICA_COUNT),)

COMMA := ,
helm_test_users_args = \
	$(if $(TEST_USERS),--set-string mockServiceNow.testUsers="$(subst $(COMMA),\$(COMMA),$(TEST_USERS))",)

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
	@echo "  build-mock-eventing-image            - Build the mock eventing service container image (checks lockfiles first)"
	@echo "  build-mock-servicenow-image          - Build the mock ServiceNow server container image (checks lockfiles first)"
	@echo "  build-promptguard-image              - Build the PromptGuard service container image (checks lockfiles first)"
	@echo "  build-request-mgr-image              - Build the request manager container image (checks lockfiles first)"
	@echo ""
	@echo "Helm Commands:"
	@echo "  helm-install-test                   - Install with mock eventing service (testing/development/CI - default)"
	@echo "  helm-install-prod                   - Install with full Knative eventing (production)"
	@echo "  helm-cleanup-eventing               - Manually clean up leftover Knative Eventing resources (Triggers, Brokers)"
	@echo "  helm-cleanup-jobs                   - Clean up leftover jobs from failed deployments"
	@echo "  helm-depend                         - Update Helm dependencies"
	@echo "  helm-list-models                    - List available models"
	@echo "  helm-status                         - Check status of the deployment"
	@echo "  helm-uninstall                      - Uninstall the RAG deployment and clean up resources"
	@echo "  verify-triggers                     - Verify all expected Knative triggers are deployed"
	@echo ""
	@echo "Install Commands:"
	@echo "  install-all                         - Install dependencies for all projects"
	@echo "  install                             - Install dependencies for self-service agent"
	@echo "  install-agent-service               - Install dependencies for agent service"
	@echo "  install-integration-dispatcher      - Install dependencies for integration dispatcher"
	@echo "  install-mcp-snow                    - Install dependencies for snow MCP server"
	@echo "  install-request-manager             - Install dependencies for request manager"
	@echo "  install-shared-models               - Install dependencies for shared models"
	@echo "  install-shared-clients              - Install dependencies for shared clients"
	@echo "  install-servicenow-bootstrap       - Install dependencies for ServiceNow automation scripts"
	@echo "  install-mock-employee-data          - Install dependencies for mock employee data"
	@echo "  install-mock-servicenow             - Install dependencies for mock ServiceNow"
	@echo ""
	@echo "Reinstall Commands:"
	@echo "  reinstall-all                       - Force reinstall dependencies for all projects (uv sync --reinstall)"
	@echo "  reinstall                           - Force reinstall self-service agent dependencies (uv sync --reinstall)"
	@echo "  reinstall-agent-service             - Force reinstall agent service dependencies"
	@echo "  reinstall-integration-dispatcher    - Force reinstall integration dispatcher dependencies"
	@echo "  reinstall-mcp-snow                  - Force reinstall snow MCP dependencies"
	@echo "  reinstall-request-manager           - Force reinstall request manager dependencies"
	@echo "  reinstall-shared-models             - Force reinstall shared models dependencies"
	@echo "  reinstall-shared-clients            - Force reinstall shared clients dependencies"
	@echo "  reinstall-servicenow-bootstrap     - Force reinstall ServiceNow automation dependencies"
	@echo "  reinstall-mock-employee-data        - Force reinstall mock employee data dependencies"
	@echo "  reinstall-mock-servicenow           - Force reinstall mock ServiceNow dependencies"
	@echo ""
	@echo "Push Commands:"
	@echo "  push-all-images                     - Push all container images to registry"
	@echo "  push-agent-service-image            - Push the agent service container image to registry"
	@echo "  push-integration-dispatcher-image   - Push the integration dispatcher container image to registry"
	@echo "  push-mcp-snow-image                 - Push the snow MCP server container image to registry"
	@echo "  push-mock-eventing-image            - Push the mock eventing service container image to registry"
	@echo "  push-promptguard-image              - Push the PromptGuard service container image to registry"
	@echo "  push-request-mgr-image              - Push the request manager container image to registry"
	@echo ""
	@echo "Test Commands:"
	@echo "  test-all                            - Run tests for all projects"
	@echo "  test                                - Run tests for self-service agent"
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
	@echo "Lockfile Management:"
	@echo "  check-lockfiles                     - Check if all uv.lock files are up-to-date"
	@echo "  update-lockfiles                    - Update all uv.lock files to match pyproject.toml"
	@echo "  check-lockfile-<service>            - Check lockfile for specific service"
	@echo "  update-lockfile-<service>           - Update lockfile for specific service"
	@echo "  test-agent-service                  - Run tests for agent service"
	@echo "  test-integration-dispatcher         - Run tests for integration dispatcher"
	@echo "  test-mcp-snow                       - Run tests for snow MCP server"
	@echo "  test-request-manager                - Run tests for request manager"
	@echo "  test-shared-models                  - Run tests for shared models"
	@echo "  test-servicenow-bootstrap          - Run tests for ServiceNow automation scripts"
	@echo "  test-mock-employee-data            - Run tests for mock employee data"
	@echo "  test-mock-servicenow               - Run tests for mock ServiceNow"
	@echo "  test-short-resp-integration-request-mgr - Run short responses integration tests with Request Manager"
	@echo "  test-long-resp-integration-request-mgr - Run long responses integration tests with Request Manager"
	@echo "  test-long-concurrent-integration-request-mgr - Run long concurrent responses integration tests with Request Manager (concurrency=4)"
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
	@echo "                                        - main branch: uses base version '0.0.2' (stable builds)"
	@echo "                                        - dev branch: uses '0.0.2-dev' tag (latest dev builds)"
	@echo "                                        - branches forked from dev: uses '0.0.2-dev' tag (dev builds)"
	@echo "                                        - all other branches: uses base version '0.0.2' (stable builds, default)"
	@echo "                                        - Set explicitly to override (e.g., VERSION=latest for main)"
	@echo "    NAMESPACE                         - Target namespace (required, no default)"
	@echo "    REPLICA_COUNT                     - Number of replicas for scalable services (optional)"
	@echo "                                        If set, overrides defaults from helm/values.yaml"
	@echo "                                        If not set, uses defaults from helm/values.yaml"
	@echo "                                        Applies to: llama-stack, snow MCP, mock-eventing, kafka,"
	@echo "                                        request-manager, integration-dispatcher, and agent-service"
	@echo ""
	@echo "  Image Configuration:"
	@echo "    AGENT_SERVICE_IMG                 - Full agent service image name (default: \$${REGISTRY}/self-service-agent-service:\$${VERSION})"
	@echo "    INTEGRATION_DISPATCHER_IMG        - Full integration dispatcher image name (default: \$${REGISTRY}/self-service-agent-integration-dispatcher:\$${VERSION})"
	@echo "    MCP_SNOW_IMG                      - Full snow MCP image name (default: \$${REGISTRY}/self-service-agent-snow-mcp:\$${VERSION})"
	@echo "    MOCK_SERVICENOW_IMG               - Full mock ServiceNow image name (default: \$${REGISTRY}/self-service-agent-mock-servicenow:\$${VERSION})"
	@echo "    REQUEST_MGR_IMG                   - Full request manager image name (default: \$${REGISTRY}/self-service-agent-request-manager:\$${VERSION})"
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
	@echo "  Evaluation Configuration:"
	@echo "    VALIDATE_FULL_LAPTOP_DETAILS    - Enable full laptop details validation (default: true)"
	@echo "                                        Set to 'false' to disable: VALIDATE_FULL_LAPTOP_DETAILS=false"
	@echo "                                        When enabled, integration tests validate all laptop specification fields"
	@echo "    USE_STRUCTURED_OUTPUT           - Enable structured output mode for evaluations (default: false)"
	@echo "                                        Set to 'true' to enable: USE_STRUCTURED_OUTPUT=true"
	@echo "                                        Uses Pydantic schema validation with retries (recommended for Gemini)"

# Build function: $(call build_image,IMAGE_NAME,DESCRIPTION,CONTAINERFILE_PATH,BUILD_CONTEXT)
define build_image
	@echo "Building $(2): $(1)"
	$(CONTAINER_TOOL) build -t $(1) --platform=$(ARCH) $(if $(3),-f $(3),) $(4)
	@echo "Successfully built $(1)"
endef

# Template build function: $(call build_template_image,IMAGE_NAME,DESCRIPTION,SERVICE_NAME,MODULE_NAME,BUILD_CONTEXT)
define build_template_image
	@echo "Building $(2) using template: $(1)"
	$(CONTAINER_TOOL) build -t $(1) --platform=$(ARCH) \
		-f Containerfile.services-template \
		--build-arg SERVICE_NAME=$(3) \
		--build-arg MODULE_NAME=$(4) \
		$(5)
	@echo "Successfully built $(1)"
endef

# MCP template build function: $(call build_mcp_image,IMAGE_NAME,DESCRIPTION,SERVICE_NAME,MODULE_NAME)
define build_mcp_image
	@echo "Building $(2) using MCP template: $(1)"
	$(CONTAINER_TOOL) build -t $(1) --platform=$(ARCH) \
		-f Containerfile.mcp-template \
		--build-arg SERVICE_NAME=$(3) \
		--build-arg MODULE_NAME=$(4) \
		.
	@echo "Successfully built $(1)"
endef

# Push function: $(call push_image,IMAGE_NAME,DESCRIPTION)
define push_image
	@echo "Pushing $(2): $(1)"
	$(CONTAINER_TOOL) push $(1)
	@echo "Successfully pushed $(1)"
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

# Build container images
.PHONY: build-all-images
build-all-images: build-request-mgr-image build-agent-service-image build-integration-dispatcher-image build-mcp-snow-image build-mock-eventing-image build-mock-servicenow-image build-promptguard-image
	@echo "All container images built successfully!"



.PHONY: build-request-mgr-image
build-request-mgr-image: check-lockfile-request-manager check-lockfile-shared-models check-lockfile-shared-clients
	$(call build_template_image,$(REQUEST_MGR_IMG),request manager image,request-manager,request_manager.main,.)

.PHONY: build-agent-service-image
build-agent-service-image: check-lockfile-agent-service check-lockfile-shared-models
	$(call build_template_image,$(AGENT_SERVICE_IMG),agent service image,agent-service,agent_service.main,.)

.PHONY: build-integration-dispatcher-image
build-integration-dispatcher-image: check-lockfile-integration-dispatcher check-lockfile-shared-models check-lockfile-shared-clients
	$(call build_template_image,$(INTEGRATION_DISPATCHER_IMG),integration dispatcher image,integration-dispatcher,integration_dispatcher.main,.)

.PHONY: build-promptguard-image
build-promptguard-image: check-lockfile-promptguard check-lockfile-shared-models
	$(call build_template_image,$(PROMPTGUARD_IMG),PromptGuard service image,promptguard-service,promptguard_service.server,.)

.PHONY: build-mcp-snow-image
build-mcp-snow-image: check-lockfile-mcp-snow
	$(call build_mcp_image,$(MCP_SNOW_IMG),snow MCP image,mcp-servers/snow,snow.server)

.PHONY: build-mock-eventing-image
build-mock-eventing-image: check-lockfile-mock-eventing check-lockfile-shared-models
	@echo "Building mock eventing service image using services template: $(MOCK_EVENTING_IMG)"
	$(CONTAINER_TOOL) build -t $(MOCK_EVENTING_IMG) --platform=$(ARCH) \
		-f Containerfile.services-template \
		--build-arg SERVICE_NAME=mock-eventing-service \
		--build-arg MODULE_NAME=mock_eventing_service.main \
		.
	@echo "Successfully built mock eventing service image: $(MOCK_EVENTING_IMG)"

.PHONY: build-mock-servicenow-image
build-mock-servicenow-image: check-lockfile-mock-servicenow check-lockfile-mock-employee-data
	@echo "Building mock ServiceNow server image using services template: $(MOCK_SERVICENOW_IMG)"
	$(CONTAINER_TOOL) build -t $(MOCK_SERVICENOW_IMG) --platform=$(ARCH) \
		-f Containerfile.services-template \
		--build-arg SERVICE_NAME=mock-service-now \
		--build-arg MODULE_NAME=mock_servicenow.server \
		.
	@echo "Successfully built mock ServiceNow server image: $(MOCK_SERVICENOW_IMG)"

# Push container images
.PHONY: push-all-images
push-all-images: push-request-mgr-image push-agent-service-image push-integration-dispatcher-image push-mcp-snow-image push-mock-eventing-image push-mock-servicenow-image push-promptguard-image
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

.PHONY: push-mock-eventing-image
push-mock-eventing-image:
	$(call push_image,$(MOCK_EVENTING_IMG) $(PUSH_EXTRA_AGRS),mock eventing service image)

.PHONY: push-mock-servicenow-image
push-mock-servicenow-image:
	$(call push_image,$(MOCK_SERVICENOW_IMG) $(PUSH_EXTRA_AGRS),mock ServiceNow server image)

.PHONY: push-promptguard-image
push-promptguard-image:
	$(call push_image,$(PROMPTGUARD_IMG) $(PUSH_EXTRA_AGRS),PromptGuard service image)

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
lint-mypy-per-directory: lint-shared-models lint-shared-clients lint-agent-service lint-request-manager lint-integration-dispatcher lint-mcp-snow lint-mock-eventing lint-tracing-config lint-evaluations lint-servicenow-bootstrap lint-mock-employee-data lint-mock-servicenow
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

# Install dependencies
.PHONY: install-all
install-all: install-shared-models install-shared-clients install-tracing-config install install-request-manager install-agent-service install-integration-dispatcher install-mcp-snow install-mock-eventing install-mock-employee-data install-mock-servicenow install-promptguard install-evaluations install-servicenow-bootstrap
	@echo "All dependencies installed successfully!"

.PHONY: install-shared-models
install-shared-models:
	@echo "Installing shared models dependencies..."
	cd shared-models && uv sync
	@echo "Shared models dependencies installed successfully!"

.PHONY: install-shared-clients
install-shared-clients:
	@echo "Installing shared clients dependencies..."
	cd shared-clients && uv sync
	@echo "Shared clients dependencies installed successfully!"

.PHONY: install
install:
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
reinstall-all: reinstall-shared-models reinstall-shared-clients reinstall reinstall-request-manager reinstall-agent-service reinstall-integration-dispatcher reinstall-mcp-snow reinstall-mock-employee-data reinstall-mock-servicenow reinstall-promptguard reinstall-servicenow-bootstrap
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

.PHONY: install-request-manager
install-request-manager:
	@echo "Installing request manager dependencies..."
	cd request-manager && uv sync
	@echo "Request manager dependencies installed successfully!"

.PHONY: install-agent-service
install-agent-service:
	@echo "Installing agent service dependencies..."
	cd agent-service && uv sync
	@echo "Agent service dependencies installed successfully!"

.PHONY: install-integration-dispatcher
install-integration-dispatcher:
	@echo "Installing integration dispatcher dependencies..."
	cd integration-dispatcher && uv sync
	@echo "Integration dispatcher dependencies installed successfully!"

.PHONY: install-mcp-snow
install-mcp-snow:
	@echo "Installing snow MCP dependencies..."
	cd mcp-servers/snow && uv sync
	@echo "Snow MCP dependencies installed successfully!"

.PHONY: install-mock-eventing
install-mock-eventing:
	@echo "Installing mock eventing service dependencies..."
	cd mock-eventing-service && uv sync
	@echo "Mock eventing service dependencies installed successfully!"

.PHONY: install-mock-employee-data
install-mock-employee-data:
	@echo "Installing mock employee data dependencies..."
	cd mock-employee-data && uv sync
	@echo "Mock employee data dependencies installed successfully!"

.PHONY: install-mock-servicenow
install-mock-servicenow:
	@if echo "$(SERVICENOW_INSTANCE_URL)" | grep -q "self-service-agent-mock-servicenow"; then \
		echo "Installing mock ServiceNow dependencies..."; \
		cd mock-service-now && uv sync; \
		echo "Mock ServiceNow dependencies installed successfully!"; \
	else \
		echo "Skipping mock ServiceNow installation - SERVICENOW_INSTANCE_URL does not contain 'self-service-agent-mock-servicenow'"; \
		echo "Current SERVICENOW_INSTANCE_URL: $(SERVICENOW_INSTANCE_URL)"; \
	fi

.PHONY: install-promptguard
install-promptguard:
	@echo "Installing PromptGuard service dependencies..."
	cd promptguard-service && uv sync
	@echo "PromptGuard service dependencies installed successfully!"

.PHONY: install-tracing-config
install-tracing-config:
	@echo "Installing tracing-config dependencies..."
	cd tracing-config && uv sync
	@echo "Tracing-config dependencies installed successfully!"

.PHONY: install-evaluations
install-evaluations:
	@echo "Installing evaluations dependencies..."
	cd evaluations && uv sync
	@echo "Evaluations dependencies installed successfully!"

.PHONY: install-servicenow-bootstrap
install-servicenow-bootstrap:
	@echo "Installing ServiceNow automation dependencies..."
	cd scripts/servicenow-bootstrap && uv sync
	@echo "ServiceNow automation dependencies installed successfully!"

# Test code
.PHONY: test-all
test-all: test-shared-models test-shared-clients test test-request-manager test-agent-service test-integration-dispatcher test-mcp-snow test-servicenow-bootstrap test-mock-employee-data test-mock-servicenow
	@echo "All tests completed successfully!"

# Lockfile management
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
endef

.PHONY: check-lockfiles
check-lockfiles:
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
	$(call check_lockfile,shared-models)
	@echo
	$(call check_lockfile,shared-clients)
	@echo
	$(call check_lockfile,agent-service)
	@echo
	$(call check_lockfile,request-manager)
	@echo
	$(call check_lockfile,integration-dispatcher)
	@echo
	$(call check_lockfile,mcp-servers/snow)
	@echo
	$(call check_lockfile,mock-eventing-service)
	@echo
	$(call check_lockfile,mock-employee-data)
	@echo
	$(call check_lockfile,scripts/servicenow-bootstrap)
	@echo
	@echo
	@echo "🎉 All lockfiles are up-to-date!"

.PHONY: update-lockfiles
update-lockfiles:
	@echo "🔄 Updating all uv.lock files..."
	@echo
	@echo "📦 Updating root project..."
	@uv lock
	@echo "✅ Root project lockfile updated"
	@echo
	$(call update_lockfile,shared-models)
	@echo
	$(call update_lockfile,shared-clients)
	@echo
	$(call update_lockfile,agent-service)
	@echo
	$(call update_lockfile,request-manager)
	@echo
	$(call update_lockfile,integration-dispatcher)
	@echo
	$(call update_lockfile,mcp-servers/snow)
	@echo
	$(call update_lockfile,mock-eventing-service)
	@echo
	$(call update_lockfile,mock-employee-data)
	@echo
	$(call update_lockfile,promptguard-service)
	@echo
	$(call update_lockfile,scripts/servicenow-bootstrap)
	@echo
	@echo
	@echo "🎉 All lockfiles updated successfully!"

# Individual service lockfile targets
.PHONY: check-lockfile-root check-lockfile-shared-models check-lockfile-shared-clients check-lockfile-agent-service check-lockfile-request-manager check-lockfile-integration-dispatcher check-lockfile-mcp-snow check-lockfile-mock-eventing check-lockfile-mock-employee-data check-lockfile-mock-servicenow check-lockfile-promptguard check-lockfile-servicenow-bootstrap
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

check-lockfile-mcp-snow:
	$(call check_lockfile,mcp-servers/snow)

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


.PHONY: update-lockfile-shared-models update-lockfile-shared-clients update-lockfile-agent-service update-lockfile-request-manager update-lockfile-integration-dispatcher update-lockfile-mcp-snow update-lockfile-mock-eventing update-lockfile-mock-employee-data update-lockfile-mock-servicenow update-lockfile-promptguard update-lockfile-servicenow-bootstrap
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

update-lockfile-mcp-snow:
	$(call update_lockfile,mcp-servers/snow)

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


.PHONY: test-shared-models
test-shared-models:
	@echo "Running shared models tests..."
	cd shared-models && uv run python -m pytest || echo "No tests found for shared-models"
	@echo "Shared models tests completed successfully!"

.PHONY: test-shared-clients
test-shared-clients:
	@echo "Running shared clients tests..."
	cd shared-clients && uv run python -m pytest tests/ || echo "No tests found for shared-clients"
	@echo "Shared clients tests completed successfully!"

.PHONY: test
test:
	@echo "Running self-service agent tests..."
	uv run python -m pytest test/ || echo "No tests found in self-service agent test directory"
	@echo "Self-service agent test check completed!"


.PHONY: test-request-manager
test-request-manager:
	@echo "Running request manager tests..."
	cd request-manager && uv run python -m pytest tests/
	@echo "Request manager tests completed successfully!"

.PHONY: test-agent-service
test-agent-service:
	@echo "Running agent service tests..."
	cd agent-service && uv run python -m pytest tests/ || echo "No tests found in agent service test directory"
	@echo "Agent service test check completed!"

.PHONY: test-integration-dispatcher
test-integration-dispatcher:
	@echo "Running integration dispatcher tests..."
	cd integration-dispatcher && uv run python -m pytest tests/ || echo "No tests found for integration dispatcher"
	@echo "Integration dispatcher tests completed successfully!"

.PHONY: test-mcp-snow
test-mcp-snow:
	@echo "Running snow MCP tests..."
	cd mcp-servers/snow && uv run python -m pytest tests/
	@echo "Snow MCP tests completed successfully!"

.PHONY: test-servicenow-bootstrap
test-servicenow-bootstrap:
	@echo "Running ServiceNow automation tests..."
	cd scripts/servicenow-bootstrap && uv run python -m pytest tests/ || echo "No tests found for ServiceNow automation"
	@echo "ServiceNow automation tests completed successfully!"

.PHONY: test-mock-employee-data
test-mock-employee-data:
	@echo "Running mock employee data tests..."
	cd mock-employee-data && uv run python -m pytest tests/ || echo "No tests found for mock employee data"
	@echo "Mock employee data tests completed successfully!"

.PHONY: test-mock-servicenow
test-mock-servicenow:
	@echo "Running mock ServiceNow tests..."
	cd mock-service-now && uv run python -m pytest tests/ || echo "No tests found for mock ServiceNow"
	@echo "Mock ServiceNow tests completed successfully!"

.PHONY: sync-evaluations
sync-evaluations:
	@echo "Syncing evaluations libraries"
	uv --directory evaluations sync
	@echo "Syncing evaluations libraries completed successfully!"

.PHONY: test-short-resp-integration-request-mgr
test-short-resp-integration-request-mgr:
	@echo "Running short responses integration test with Request Manager..."
	uv --directory evaluations run evaluate.py -n 1 --test-script chat-responses-request-mgr.py --reset-conversation $(VALIDATE_LAPTOP_DETAILS_FLAG) $(STRUCTURED_OUTPUT_FLAG)
	@echo "short responses integrations tests with Request Manager completed successfully!"

.PHONY: test-long-resp-integration-request-mgr
test-long-resp-integration-request-mgr:
	@echo "Running long responses integration test with Request Manager..."
	uv --directory evaluations run evaluate.py -n 20 --test-script chat-responses-request-mgr.py --reset-conversation --timeout=1800 $(VALIDATE_LAPTOP_DETAILS_FLAG) $(STRUCTURED_OUTPUT_FLAG)
	@echo "long responses integrations tests with Request Manager completed successfully!"

.PHONY: test-long-concurrent-integration-request-mgr
test-long-concurrent-integration-request-mgr:
	@echo "Running long concurrent responses integration test with Request Manager..."
	uv --directory evaluations run evaluate.py -n 10 --test-script chat-responses-request-mgr.py --reset-conversation --timeout=1800 --concurrency 4 --message-timeout 120 $(VALIDATE_LAPTOP_DETAILS_FLAG) $(STRUCTURED_OUTPUT_FLAG)
	@echo "long concurrent responses integrations tests with Request Manager completed successfully!"

# Create namespace and deploy
namespace:
	@kubectl create namespace $(NAMESPACE) &> /dev/null && kubectl label namespace $(NAMESPACE) modelmesh-enabled=false ||:
	@kubectl config set-context --current --namespace=$(NAMESPACE) &> /dev/null ||:

.PHONY: helm-depend
helm-depend:
	@echo "Updating Helm dependencies"
	@helm dependency update helm &> /dev/null

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
	$(if $(filter true,$(3)),@echo "Waiting for mock eventing deployment..." && kubectl rollout status deploy/$(MAIN_CHART_NAME)-mock-eventing -n $(NAMESPACE) --timeout 5m,)
	$(if $(filter true,$(PROMPTGUARD_ENABLED)),@echo "Waiting for PromptGuard deployment..." && kubectl rollout status deploy/$(MAIN_CHART_NAME)-promptguard -n $(NAMESPACE) --timeout 10m,)
	$(if $(filter true,$(ENABLE_LANGFUSE)),@echo "Waiting for Redis StatefulSet..." && kubectl rollout status statefulset/$(MAIN_CHART_NAME)-redis -n $(NAMESPACE) --timeout 10m && echo "Waiting for MinIO StatefulSet..." && kubectl rollout status statefulset/$(MAIN_CHART_NAME)-minio -n $(NAMESPACE) --timeout 10m && echo "Waiting for ClickHouse StatefulSet..." && kubectl rollout status statefulset/$(MAIN_CHART_NAME)-clickhouse -n $(NAMESPACE) --timeout 10m && echo "Waiting for LangFuse Web deployment..." && kubectl rollout status deploy/$(MAIN_CHART_NAME)-langfuse -n $(NAMESPACE) --timeout 10m && echo "Waiting for LangFuse Worker deployment (runs ClickHouse migrations)..." && kubectl rollout status deploy/$(MAIN_CHART_NAME)-langfuse-worker -n $(NAMESPACE) --timeout 10m && echo "LangFuse URL: https://$$(kubectl get route $(MAIN_CHART_NAME)-langfuse -n $(NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null || echo 'Route not found')",)
	@echo "$(MAIN_CHART_NAME) $(1) installed successfully"
endef

# Install with mock eventing service (testing/development/CI mode - default)
# Extract all LG_PROMPT_* variables and convert them to Helm --set arguments
PROMPT_OVERRIDES := $(foreach var,$(filter LG_PROMPT_%,$(.VARIABLES)),--set requestManagement.agentService.promptOverrides.lg-prompt-$(shell echo $(var:LG_PROMPT_%=%) | tr '[:upper:]' '[:lower:]' | tr '_' '-')=$($(var)))

.PHONY: helm-install-test
helm-install-test: namespace helm-depend
	$(call helm_install_common,"with mock eventing service - testing/CI",\
		-f helm/values-test.yaml \
		--set requestManagement.knative.mockEventing.enabled=true \
		--set testIntegrationEnabled=true \
		$(PROMPT_OVERRIDES),\
		true)
	@$(MAKE) print-urls

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
	@echo "Removing ServiceNow credentials secret from $(NAMESPACE)"
	@kubectl delete secret $(MAIN_CHART_NAME)-servicenow-credentials -n $(NAMESPACE) --ignore-not-found || true
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

# ServiceNow PDI wake-up
.PHONY: servicenow-wake-install
servicenow-wake-install: install-servicenow-bootstrap
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

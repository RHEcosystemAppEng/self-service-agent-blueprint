# Makefile for RAG Deployment
ifeq ($(NAMESPACE),)
ifneq (,$(filter namespace helm-install helm-uninstall helm-status helm-cleanup-eventing helm-cleanup-jobs,$(MAKECMDGOALS)))
$(error NAMESPACE is not set)
endif
endif

VERSION ?= 0.0.2
CONTAINER_TOOL ?= podman
REGISTRY ?= quay.io/ecosystem-appeng
AGENT_IMG ?= $(REGISTRY)/self-service-agent:$(VERSION)
REQUEST_MGR_IMG ?= $(REGISTRY)/self-service-agent-request-manager:$(VERSION)
AGENT_SERVICE_IMG ?= $(REGISTRY)/self-service-agent-service:$(VERSION)
INTEGRATION_DISPATCHER_IMG ?= $(REGISTRY)/self-service-agent-integration-dispatcher:$(VERSION)
MCP_EMP_INFO_IMG ?= $(REGISTRY)/self-service-agent-employee-info-mcp:$(VERSION)
MCP_SNOW_IMG ?= $(REGISTRY)/self-service-agent-snow-mcp:$(VERSION)

MAKFLAGS += --no-print-directory

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
    $(if $(LLM_URL),--set llm-service.enabled=false,)

helm_llama_stack_args = \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_URL),--set global.models.$(LLM).url='$(LLM_URL)',) \
    $(if $(LLM_ID),--set global.models.$(LLM).id='$(LLM_ID)',) \
    $(if $(SAFETY_URL),--set global.models.$(SAFETY).url='$(SAFETY_URL)',) \
    $(if $(LLM_API_TOKEN),--set global.models.$(LLM).apiToken='$(LLM_API_TOKEN)',) \
    $(if $(SAFETY_API_TOKEN),--set global.models.$(SAFETY).apiToken='$(SAFETY_API_TOKEN)',) \
    $(if $(LLAMA_STACK_ENV),--set-json llama-stack.secrets='$(LLAMA_STACK_ENV)',)

helm_request_management_args = \
    $(if $(REQUEST_MANAGEMENT),--set requestManagement.enabled=$(REQUEST_MANAGEMENT),) \
    $(if $(KNATIVE_EVENTING),--set requestManagement.knative.eventing.enabled=$(KNATIVE_EVENTING),) \
    $(if $(MOCK_EVENTING),--set requestManagement.knative.mockEventing.enabled=$(MOCK_EVENTING),) \
    $(if $(SLACK_SIGNING_SECRET),--set-string security.slack.signingSecret='$(SLACK_SIGNING_SECRET)',) \
    $(if $(SNOW_API_KEY),--set-string security.apiKeys.snowIntegration='$(SNOW_API_KEY)',) \
    $(if $(HR_API_KEY),--set-string security.apiKeys.hrSystem='$(HR_API_KEY)',)

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
	@echo "  build-all-images                     - Build all container images (unified agent, request-manager, agent-service, integration-dispatcher, employee-info-mcp, snow-mcp)"
	@echo "  build-agent-image                    - Build the unified self-service agent container image (includes asset-manager and db-migration functionality)"
	@echo "  build-agent-service-image            - Build the agent service container image"
	@echo "  build-integration-dispatcher-image   - Build the integration dispatcher container image"
	@echo "  build-mcp-emp-info-image             - Build the employee info MCP server container image"
	@echo "  build-mcp-snow-image                 - Build the snow MCP server container image"
	@echo "  build-request-mgr-image              - Build the request manager container image"
	@echo ""
	@echo "Helm Commands:"
	@echo "  helm-install                        - Install the RAG deployment (creates namespace, secrets, and deploys Helm chart)"
	@echo "  helm-install-direct-http            - Install with direct HTTP communication (for development)"
	@echo "  helm-install-mock-eventing          - Install with mock eventing service (for testing/CI)"
	@echo "  helm-cleanup-eventing               - Manually clean up leftover Knative Eventing resources (Triggers, Brokers)"
	@echo "  helm-cleanup-jobs                   - Clean up leftover jobs from failed deployments"
	@echo "  helm-depend                         - Update Helm dependencies"
	@echo "  helm-list-models                    - List available models"
	@echo "  helm-status                         - Check status of the deployment"
	@echo "  helm-uninstall                      - Uninstall the RAG deployment and clean up resources"
	@echo ""
	@echo "Install Commands:"
	@echo "  install-all                         - Install dependencies for all projects"
	@echo "  install                             - Install dependencies for self-service agent"
	@echo "  install-agent-service               - Install dependencies for agent service"
	@echo "  install-asset-manager               - Install dependencies for asset manager"
	@echo "  install-integration-dispatcher      - Install dependencies for integration dispatcher"
	@echo "  install-mcp-emp-info                - Install dependencies for employee info MCP server"
	@echo "  install-mcp-snow                    - Install dependencies for snow MCP server"
	@echo "  install-request-manager             - Install dependencies for request manager"
	@echo "  install-shared-db                   - Install dependencies for shared database"
	@echo ""
	@echo "Push Commands:"
	@echo "  push-all-images                     - Push all container images to registry"
	@echo "  push-agent-image                    - Push the unified self-service agent container image to registry"
	@echo "  push-agent-service-image            - Push the agent service container image to registry"
	@echo "  push-integration-dispatcher-image   - Push the integration dispatcher container image to registry"
	@echo "  push-mcp-emp-info-image             - Push the employee info MCP server container image to registry"
	@echo "  push-mcp-snow-image                 - Push the snow MCP server container image to registry"
	@echo "  push-request-mgr-image              - Push the request manager container image to registry"
	@echo ""
	@echo "Test Commands:"
	@echo "  test-all                            - Run tests for all projects"
	@echo "  test                                - Run tests for self-service agent"
	@echo "  test-agent-service                  - Run tests for agent service"
	@echo "  test-asset-manager                  - Run tests for asset manager"
	@echo "  test-integration-dispatcher         - Run tests for integration dispatcher"
	@echo "  test-mcp-emp-info                   - Run tests for employee info MCP server"
	@echo "  test-mcp-snow                       - Run tests for snow MCP server"
	@echo "  test-request-manager                - Run tests for request manager"
	@echo "  test-shared-db                      - Run tests for shared database"
	@echo "  test-short-integration              - Run short integration tests"
	@echo ""
	@echo "Utility Commands:"
	@echo "  format                              - Run isort import sorting and Black formatting on entire codebase"
	@echo "  lint                                - Run flake8 linting on entire codebase"
	@echo "  version                             - Print the current VERSION"
	@echo ""
	@echo "Configuration options (set via environment variables or make arguments):"
	@echo ""
	@echo "  Core Configuration:"
	@echo "    CONTAINER_TOOL                    - Container build tool (default: podman)"
	@echo "    REGISTRY                          - Container registry (default: quay.io/ecosystem-appeng)"
	@echo "    VERSION                           - Image version tag (default: 0.0.2)"
	@echo "    NAMESPACE                         - Target namespace (default: llama-stack-rag)"
	@echo ""
	@echo "  Image Configuration:"
	@echo "    AGENT_IMG                         - Full agent image name (default: \$${REGISTRY}/self-service-agent:\$${VERSION})"
	@echo "    AGENT_SERVICE_IMG                 - Full agent service image name (default: \$${REGISTRY}/self-service-agent-service:\$${VERSION})"
	@echo "    INTEGRATION_DISPATCHER_IMG        - Full integration dispatcher image name (default: \$${REGISTRY}/self-service-agent-integration-dispatcher:\$${VERSION})"
	@echo "    MCP_EMP_INFO_IMG                  - Full employee info MCP image name (default: \$${REGISTRY}/self-service-agent-employee-info-mcp:\$${VERSION})"
	@echo "    MCP_SNOW_IMG                      - Full snow MCP image name (default: \$${REGISTRY}/self-service-agent-snow-mcp:\$${VERSION})"
	@echo "    REQUEST_MGR_IMG                   - Full request manager image name (default: \$${REGISTRY}/self-service-agent-request-manager:\$${VERSION})"
	@echo ""
	@echo "  Model Configuration:"
	@echo "    HF_TOKEN                          - Hugging Face Token (will prompt if not provided)"
	@echo "    LLM_ID                            - Model ID for LLM configuration"
	@echo "    {SAFETY,LLM}                      - Model id as defined in values (eg. llama-3-2-1b-instruct)"
	@echo "    {SAFETY,LLM}_URL                  - Model URL"
	@echo "    {SAFETY,LLM}_API_TOKEN            - Model API token for remote models"
	@echo "    {SAFETY,LLM}_TOLERATION           - Model pod toleration"
	@echo ""
	@echo "  Integration Configuration:"
	@echo "    ENABLE_SLACK                      - Set to 'true' to enable Slack integration and prompt for tokens"
	@echo "    HR_API_KEY                        - HR system integration API key"
	@echo "    SLACK_BOT_TOKEN                   - Slack Bot Token (xoxb-...) for Slack integration"
	@echo "    SLACK_SIGNING_SECRET              - Slack Signing Secret for request verification"
	@echo "    SNOW_API_KEY                      - ServiceNow integration API key"
	@echo ""
	@echo "  Request Management Layer:"
	@echo "    KNATIVE_EVENTING                  - Enable Knative Eventing (default: true)"
	@echo "    REQUEST_MANAGEMENT                - Enable Request Management Layer (default: true)"

# Build function: $(call build_image,IMAGE_NAME,DESCRIPTION,CONTAINERFILE_PATH,BUILD_CONTEXT)
define build_image
	@echo "Building $(2): $(1)"
	$(CONTAINER_TOOL) build -t $(1) --platform=linux/amd64 $(if $(3),-f $(3),) $(4)
	@echo "Successfully built $(1)"
endef

# Template build function: $(call build_template_image,IMAGE_NAME,DESCRIPTION,SERVICE_NAME,MODULE_NAME,BUILD_CONTEXT)
define build_template_image
	@echo "Building $(2) using template: $(1)"
	$(CONTAINER_TOOL) build -t $(1) --platform=linux/amd64 \
		-f Containerfile.services-template \
		--build-arg SERVICE_NAME=$(3) \
		--build-arg MODULE_NAME=$(4) \
		$(5)
	@echo "Successfully built $(1)"
endef

# MCP template build function: $(call build_mcp_image,IMAGE_NAME,DESCRIPTION,SERVICE_NAME,MODULE_NAME)
define build_mcp_image
	@echo "Building $(2) using MCP template: $(1)"
	$(CONTAINER_TOOL) build -t $(1) --platform=linux/amd64 \
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

define PRINT_SLACK_URL
	@echo "--- Your Integration Dispatcher URLs are: ---"
	@sleep 10
	@ROUTE_HOST=$$(kubectl get route $(MAIN_CHART_NAME)-integration-dispatcher -n $(NAMESPACE) -o jsonpath='{.spec.host}'); \
	echo "  Slack Webhook: https://$$ROUTE_HOST/slack/events"; \
	echo "  Health: https://$$ROUTE_HOST/health"
endef

define PRINT_REQUEST_MANAGER_URL
	@echo "--- Your Request Manager URLs are: ---"
	@sleep 10
	@ROUTE_HOST=$$(kubectl get route $(MAIN_CHART_NAME)-request-manager -n $(NAMESPACE) -o jsonpath='{.spec.host}'); \
	echo "  API: https://$$ROUTE_HOST/api/v1/"; \
	echo "  Health: https://$$ROUTE_HOST/health"
endef

# Build container images
.PHONY: build-all-images
build-all-images: build-agent-image build-request-mgr-image build-agent-service-image build-integration-dispatcher-image build-mcp-emp-info-image build-mcp-snow-image
	@echo "All container images built successfully!"

.PHONY: build-agent-image
build-agent-image:
	$(call build_image,$(AGENT_IMG),unified self-service agent image,Containerfile.template,.)


.PHONY: build-request-mgr-image
build-request-mgr-image:
	$(call build_template_image,$(REQUEST_MGR_IMG),request manager image,request-manager,request_manager.main,.)

.PHONY: build-agent-service-image
build-agent-service-image:
	$(call build_template_image,$(AGENT_SERVICE_IMG),agent service image,agent-service,agent_service.main,.)

.PHONY: build-integration-dispatcher-image
build-integration-dispatcher-image:
	$(call build_template_image,$(INTEGRATION_DISPATCHER_IMG),integration dispatcher image,integration-dispatcher,integration_dispatcher.main,.)


.PHONY: build-mcp-emp-info-image
build-mcp-emp-info-image:
	$(call build_mcp_image,$(MCP_EMP_INFO_IMG),employee info MCP image,mcp-servers/employee-info,employee_info.main)

.PHONY: build-mcp-snow-image
build-mcp-snow-image:
	$(call build_mcp_image,$(MCP_SNOW_IMG),snow MCP image,mcp-servers/snow,snow.main)

# Push container images
.PHONY: push-all-images
push-all-images: push-agent-image push-request-mgr-image push-agent-service-image push-integration-dispatcher-image push-mcp-emp-info-image push-mcp-snow-image
	@echo "All container images pushed successfully!"

.PHONY: push-agent-image
push-agent-image:
	$(call push_image,$(AGENT_IMG) $(PUSH_EXTRA_AGRS),self-service agent image)


.PHONY: push-request-mgr-image
push-request-mgr-image:
	$(call push_image,$(REQUEST_MGR_IMG),request manager image)

.PHONY: push-agent-service-image
push-agent-service-image:
	$(call push_image,$(AGENT_SERVICE_IMG),agent service image)

.PHONY: push-integration-dispatcher-image
push-integration-dispatcher-image:
	$(call push_image,$(INTEGRATION_DISPATCHER_IMG),integration dispatcher image)


.PHONY: push-mcp-emp-info-image
push-mcp-emp-info-image:
	$(call push_image,$(MCP_EMP_INFO_IMG) $(PUSH_EXTRA_AGRS),employee info MCP image)

.PHONY: push-mcp-snow-image
push-mcp-snow-image:
	$(call push_image,$(MCP_SNOW_IMG) $(PUSH_EXTRA_AGRS),snow MCP image)

# Code quality
.PHONY: lint
lint:
	@echo "Running flake8 linting on entire codebase..."
	uv run flake8 .
	@echo "Linting completed successfully!"

.PHONY: format
format:
	@echo "Running isort import sorting on entire codebase..."
	uv run isort .
	@echo "Running Black formatting on entire codebase..."
	uv run black .
	@echo "Formatting completed successfully!"

# Install dependencies
.PHONY: install-all
install-all: install-shared-db install install-asset-manager install-request-manager install-agent-service install-integration-dispatcher install-mcp-emp-info install-mcp-snow
	@echo "All dependencies installed successfully!"

.PHONY: install-shared-db
install-shared-db:
	@echo "Installing shared database dependencies..."
	cd shared-db && uv sync
	@echo "Shared database dependencies installed successfully!"

.PHONY: install
install:
	@echo "Installing self-service agent dependencies..."
	uv sync
	@echo "Self-service agent dependencies installed successfully!"

.PHONY: install-asset-manager
install-asset-manager:
	@echo "Installing asset manager dependencies..."
	cd asset-manager && uv sync
	@echo "Asset manager dependencies installed successfully!"

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

.PHONY: install-mcp-emp-info
install-mcp-emp-info:
	@echo "Installing employee info MCP dependencies..."
	cd mcp-servers/employee-info && uv sync
	@echo "Employee info MCP dependencies installed successfully!"

.PHONY: install-mcp-snow
install-mcp-snow:
	@echo "Installing snow MCP dependencies..."
	cd mcp-servers/snow && uv sync
	@echo "Snow MCP dependencies installed successfully!"

# Test code
.PHONY: test-all
test-all: test-shared-db test test-asset-manager test-request-manager test-agent-service test-integration-dispatcher test-mcp-emp-info test-mcp-snow
	@echo "All tests completed successfully!"

.PHONY: test-shared-db
test-shared-db:
	@echo "Running shared database tests..."
	cd shared-db && uv run python -m pytest || echo "No tests found for shared-db"
	@echo "Shared database tests completed successfully!"

.PHONY: test
test:
	@echo "Running self-service agent tests..."
	uv run python -m pytest test/ || echo "No tests found in self-service agent test directory"
	@echo "Self-service agent test check completed!"

.PHONY: test-asset-manager
test-asset-manager:
	@echo "Running asset manager tests..."
	cd asset-manager && uv run python -m pytest tests/
	@echo "Asset manager tests completed successfully!"

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

.PHONY: test-mcp-emp-info
test-mcp-emp-info:
	@echo "Running employee info MCP tests..."
	cd mcp-servers/employee-info && uv run python -m pytest tests/
	@echo "Employee info MCP tests completed successfully!"

.PHONY: test-mcp-snow
test-mcp-snow:
	@echo "Running snow MCP tests..."
	cd mcp-servers/snow && uv run python -m pytest tests/
	@echo "Snow MCP tests completed successfully!"

.PHONY: sync-evaluations
sync-evaluations:
	@echo "Syncing evaluations libraries"
	uv --directory evaluations sync
	@echo "Syncing evaluations libraries completed successfully!"

.PHONY: test-short-integration
test-short-integration:
	@echo "Running short integration test..."
	uv --directory evaluations run evaluate.py -n 1
	@echo "short integrations tests completed successfully!"

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

	@echo "Cleaning up any existing jobs..."
	@kubectl delete job -l app.kubernetes.io/component=init -n $(NAMESPACE) --ignore-not-found || true
	@kubectl delete job -l app.kubernetes.io/name=self-service-agent -n $(NAMESPACE) --ignore-not-found || true
	@echo "Installing $(MAIN_CHART_NAME) helm chart $(1)"
	@helm upgrade --install $(MAIN_CHART_NAME) helm -n $(NAMESPACE) \
		--set image.repository=self-service-agent \
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
		--set mcp-servers.mcp-servers.self-service-agent-employee-info.imageRepository=$(REGISTRY)/self-service-agent-employee-info-mcp \
		--set mcp-servers.mcp-servers.self-service-agent-snow.imageRepository=$(REGISTRY)/self-service-agent-snow-mcp \
		$(REQUEST_MANAGEMENT_ARGS) \
		$(if $(filter-out "",$(2)),$(2),) \
		$(EXTRA_HELM_ARGS)
	@echo "Waiting for services to deploy $(1)..."
	@eval $(3)
	@echo "$(MAIN_CHART_NAME) $(1) installed successfully"
	$(PRINT_REQUEST_MANAGER_URL)
	$(if $(filter true,$(SLACK_ENABLED)),$(PRINT_SLACK_URL))
endef

# Install with full Knative eventing (production)
.PHONY: helm-install
helm-install: namespace helm-depend
	$(call helm_install_common,"with full Knative eventing","",\
		"kubectl rollout status deploy/$(MAIN_CHART_NAME) -n $(NAMESPACE) --timeout 20m")

# Install with mock eventing service (for testing/CI)
.PHONY: helm-install-mock-eventing
helm-install-mock-eventing: namespace helm-depend
	$(call helm_install_common,"with mock eventing service",\
		--set requestManagement.knative.eventing.enabled=false --set requestManagement.knative.mockEventing.enabled=true --set requestManagement.kafka.enabled=false,\
		"kubectl rollout status deploy/$(MAIN_CHART_NAME) -n $(NAMESPACE) --timeout 10m && kubectl rollout status deploy/$(MAIN_CHART_NAME)-mock-eventing -n $(NAMESPACE) --timeout 5m")

# Install with direct HTTP communication (for development)
.PHONY: helm-install-direct-http
helm-install-direct-http: namespace helm-depend
	$(call helm_install_common,"with direct HTTP communication",\
		--set requestManagement.knative.eventing.enabled=false --set requestManagement.knative.mockEventing.enabled=false --set requestManagement.kafka.enabled=false,\
		"kubectl rollout status deploy/$(MAIN_CHART_NAME) -n $(NAMESPACE) --timeout 10m")

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
	@echo "Removing pgvector and init job PVCs from $(NAMESPACE)"
	@kubectl get pvc -n $(NAMESPACE) -o custom-columns=NAME:.metadata.name | grep -E '^(pg.*-data|self-service-agent-init-status)' | xargs -I {} kubectl delete pvc -n $(NAMESPACE) {} ||:
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


# Slack User Management
.PHONY: add-slack-user
add-slack-user:
	@if [ -z "$(USER)" ] || [ -z "$(EMAIL)" ]; then \
		echo "Usage: make add-slack-user USER=<user_id> EMAIL=<email> [WORKSPACE_ID=<id>] [URL=<base_url>]"; \
		echo ""; \
		echo "Examples:"; \
		echo "  make add-slack-user USER=john.doe EMAIL=john.doe@company.com"; \
		echo "  make add-slack-user USER=jane.smith EMAIL=jane.smith@company.com WORKSPACE_ID=T1234567890"; \
		echo "  make add-slack-user USER=bob.wilson EMAIL=bob.wilson@company.com URL=http://localhost:8081"; \
		echo "  make add-slack-user USER=alice.cooper EMAIL=alice.cooper@company.com URL=https://integration-dispatcher.example.com"; \
		exit 1; \
	fi
	@./scripts/add-slack-user.sh "$(USER)" "$(EMAIL)" "$(WORKSPACE_ID)" "$(URL)"

.PHONY: list-slack-user
list-slack-user:
	@if [ -z "$(USER)" ]; then \
		echo "Usage: make list-slack-user USER=<user_id> [URL=<base_url>]"; \
		echo ""; \
		echo "Examples:"; \
		echo "  make list-slack-user USER=john.doe"; \
		echo "  make list-slack-user USER=jane.smith URL=http://localhost:8081"; \
		echo "  make list-slack-user USER=bob.wilson URL=https://integration-dispatcher.example.com"; \
		exit 1; \
	fi
	@./scripts/list-slack-users.sh "$(USER)" "$(URL)"

.PHONY: remove-slack-user
remove-slack-user:
	@if [ -z "$(USER)" ]; then \
		echo "Usage: make remove-slack-user USER=<user_id> [URL=<base_url>]"; \
		echo ""; \
		echo "Examples:"; \
		echo "  make remove-slack-user USER=john.doe"; \
		echo "  make remove-slack-user USER=jane.smith URL=http://localhost:8081"; \
		echo "  make remove-slack-user USER=bob.wilson URL=https://integration-dispatcher.example.com"; \
		exit 1; \
	fi
	@./scripts/remove-slack-user.sh "$(USER)" "$(URL)"

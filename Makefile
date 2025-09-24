# Makefile for RAG Deployment
ifeq ($(NAMESPACE),)
ifneq (,$(filter namespace helm-install helm-uninstall helm-status,$(MAKECMDGOALS)))
$(error NAMESPACE is not set)
endif
endif

VERSION ?= 0.0.2
CONTAINER_TOOL ?= podman
REGISTRY ?= quay.io/ecosystem-appeng
AGENT_IMG ?= $(REGISTRY)/self-service-agent:$(VERSION)
ASSET_MGR_IMG ?= $(REGISTRY)/self-service-agent-asset-manager:$(VERSION)
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

# Version target
.PHONY: version
version:
	@echo $(VERSION)

# Default target
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  build-all-images            - Build all container images (agent, asset-manager, employee-info-mcp, snow-mcp)"
	@echo "  build-agent-image           - Build the self-service agent container image"
	@echo "  build-asset-mgr-image       - Build the asset manager container image"
	@echo "  build-mcp-emp-info-image    - Build the employee info MCP server container image"
	@echo "  build-mcp-snow-image        - Build the snow MCP server container image"
	@echo "  format                      - Run isort import sorting and Black formatting on entire codebase"
	@echo "  helm-depend                 - Update Helm dependencies"
	@echo "  helm-install                - Install the RAG deployment (creates namespace, secrets, and deploys Helm chart)"
	@echo "  helm-list-models            - List available models"
	@echo "  helm-status                 - Check status of the deployment"
	@echo "  helm-uninstall              - Uninstall the RAG deployment and clean up resources"
	@echo "  install-all                 - Install dependencies for all projects"
	@echo "  install                     - Install dependencies for self-service agent"
	@echo "  install-asset-manager       - Install dependencies for asset manager"
	@echo "  install-mcp-emp-info        - Install dependencies for employee info MCP server"
	@echo "  install-mcp-snow            - Install dependencies for snow MCP server"
	@echo "  lint                        - Run flake8 linting on entire codebase"
	@echo "  push-all-images             - Push all container images to registry"
	@echo "  push-agent-image            - Push the self-service agent container image to registry"
	@echo "  push-asset-mgr-image        - Push the asset manager container image to registry"
	@echo "  push-mcp-emp-info-image     - Push the employee info MCP server container image to registry"
	@echo "  push-mcp-snow-image         - Push the snow MCP server container image to registry"
	@echo "  test-all                    - Run tests for all projects"
	@echo "  test                        - Run tests for self-service agent"
	@echo "  test-asset-manager          - Run tests for asset manager"
	@echo "  test-mcp-emp-info           - Run tests for employee info MCP server"
	@echo "  test-mcp-snow               - Run tests for snow MCP server"
	@echo "  test-short-integration      - Run short integration tests"
	@echo "  test-short-resp-integration - Run short responses integration tests (no employee ID)"
	@echo "  version                     - Print the current VERSION"
	@echo ""
	@echo "Configuration options (set via environment variables or make arguments):"
	@echo "  CONTAINER_TOOL           - Container build tool (default: podman)"
	@echo "  REGISTRY                 - Container registry (default: quay.io/ecosystem-appeng)"
	@echo "  VERSION                  - Image version tag (default: 0.0.2)"
	@echo "  AGENT_IMG                - Full agent image name (default: \$${REGISTRY}/self-service-agent:\$${VERSION})"
	@echo "  ASSET_MGR_IMG            - Full asset manager image name (default: \$${REGISTRY}/self-service-asset-manager:\$${VERSION})"
	@echo "  MCP_EMP_INFO_IMG         - Full employee info MCP image name (default: \$${REGISTRY}/self-service-agent-employee-info-mcp:\$${VERSION})"
	@echo "  MCP_SNOW_IMG             - Full snow MCP image name (default: \$${REGISTRY}/self-service-agent-snow-mcp:\$${VERSION})"
	@echo "  NAMESPACE                - Target namespace (default: llama-stack-rag)"
	@echo "  HF_TOKEN                 - Hugging Face Token (will prompt if not provided)"
	@echo "  {SAFETY,LLM}             - Model id as defined in values (eg. llama-3-2-1b-instruct)"
	@echo "  LLM_ID                   - Model ID for LLM configuration"
	@echo "  {SAFETY,LLM}_URL         - Model URL"
	@echo "  {SAFETY,LLM}_API_TOKEN   - Model API token for remote models"
	@echo "  {SAFETY,LLM}_TOLERATION  - Model pod toleration"
	@echo "  SLACK_BOT_TOKEN          - Slack Bot Token (xoxb-...) for Slack integration"
	@echo "  SLACK_SIGNING_SECRET     - Slack Signing Secret for request verification"
	@echo "  ENABLE_SLACK             - Set to 'true' to enable Slack integration and prompt for tokens"

# Build function: $(call build_image,IMAGE_NAME,DESCRIPTION,CONTAINERFILE_PATH,BUILD_CONTEXT)
define build_image
	@echo "Building $(2): $(1)"
	$(CONTAINER_TOOL) build -t $(1) --platform=linux/amd64 $(if $(3),-f $(3),) $(4)
	@echo "Successfully built $(1)"
endef

# Push function: $(call push_image,IMAGE_NAME,DESCRIPTION)
define push_image
	@echo "Pushing $(2): $(1)"
	$(CONTAINER_TOOL) push $(1)
	@echo "Successfully pushed $(1)"
endef

define PRINT_SLACK_URL
	@echo "--- Your Slack Event URL is: ---"
	@sleep 10
	@echo "  https://$$(oc get route $(MAIN_CHART_NAME)-slack -n $(NAMESPACE) -o jsonpath='{.spec.host}')/slack/events"
endef

# Build container images
.PHONY: build-all-images
build-all-images: build-agent-image build-asset-mgr-image build-mcp-emp-info-image build-mcp-snow-image
	@echo "All container images built successfully!"

.PHONY: build-agent-image
build-agent-image:
	$(call build_image,$(AGENT_IMG),self-service agent image,Containerfile,.)

.PHONY: build-asset-mgr-image
build-asset-mgr-image:
	$(call build_image,$(ASSET_MGR_IMG),asset manager image,asset-manager/Containerfile,asset-manager/)

.PHONY: build-mcp-emp-info-image
build-mcp-emp-info-image:
	$(call build_image,$(MCP_EMP_INFO_IMG),employee info MCP image,mcp-servers/employee-info/Containerfile,mcp-servers/employee-info/)

.PHONY: build-mcp-snow-image
build-mcp-snow-image:
	$(call build_image,$(MCP_SNOW_IMG),snow MCP image,mcp-servers/snow/Containerfile,mcp-servers/snow/)

# Push container images
.PHONY: push-all-images
push-all-images: push-agent-image push-asset-mgr-image push-mcp-emp-info-image push-mcp-snow-image
	@echo "All container images pushed successfully!"

.PHONY: push-agent-image
push-agent-image:
	$(call push_image,$(AGENT_IMG) $(PUSH_EXTRA_AGRS),self-service agent image)

.PHONY: push-asset-mgr-image
push-asset-mgr-image:
	$(call push_image,$(ASSET_MGR_IMG) $(PUSH_EXTRA_AGRS),asset manager image)

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
install-all: install install-asset-manager install-mcp-emp-info install-mcp-snow
	@echo "All dependencies installed successfully!"

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
test-all: test test-asset-manager test-mcp-emp-info test-mcp-snow
	@echo "All tests completed successfully!"

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

.PHONY: test-short-resp-integration
test-short-resp-integration:
	@echo "Running short responses integration test..."
	uv --directory evaluations run evaluate.py -n 1 --no-employee-id --test-script="chat-responses.py"
	@echo "short responses integrations tests completed successfully!"

# Create namespace and deploy
namespace:
	@kubectl create namespace $(NAMESPACE) &> /dev/null && kubectl label namespace $(NAMESPACE) modelmesh-enabled=false ||:
	@kubectl get namespaces &> /dev/null ||:

.PHONY: helm-depend
helm-depend:
	@echo "Updating Helm dependencies"
	@helm dependency update helm &> /dev/null

.PHONY: helm-list-models
helm-list-models: helm-depend
	@helm template dummy-release helm --set llm-service._debugListModels=true | grep ^model:

.PHONY: helm-install
helm-install: namespace helm-depend
	@$(eval PGVECTOR_ARGS := $(call helm_pgvector_args))
	@$(eval LLM_SERVICE_ARGS := $(call helm_llm_service_args))
	@$(eval LLAMA_STACK_ARGS := $(call helm_llama_stack_args))

	@echo "Installing $(MAIN_CHART_NAME) helm chart"
	@helm upgrade --install $(MAIN_CHART_NAME) helm -n $(NAMESPACE) \
		$(PGVECTOR_ARGS) \
		$(LLM_SERVICE_ARGS) \
		$(LLAMA_STACK_ARGS) \
		--set slack.enabled=$(SLACK_ENABLED) \
		$(if $(filter true,$(SLACK_ENABLED)),--set slack.botToken=$(SLACK_BOT_TOKEN) --set slack.signingSecret=$(SLACK_SIGNING_SECRET),) \
		--set image.registry=$(REGISTRY) \
		--set mcp-servers.mcp-servers.self-service-agent-employee-info.imageRepository=$(REGISTRY)/self-service-agent-employee-info-mcp \
		--set mcp-servers.mcp-servers.self-service-agent-snow.imageRepository=$(REGISTRY)/self-service-agent-snow-mcp \
		$(EXTRA_HELM_ARGS)
	@echo "Waiting for model services and llamastack to deploy. It may take around 10-15 minutes depending on the size of the model..."
	@kubectl rollout status deploy/$(MAIN_CHART_NAME) -n $(NAMESPACE) --timeout 20m
	@echo "$(MAIN_CHART_NAME) installed successfully"
	$(if $(filter true,$(SLACK_ENABLED)),$(PRINT_SLACK_URL))

# Uninstall the deployment and clean up
.PHONY: helm-uninstall
helm-uninstall:
	@echo "Uninstalling $(MAIN_CHART_NAME) helm chart"
	@helm uninstall --ignore-not-found $(MAIN_CHART_NAME) -n $(NAMESPACE)
	@echo "Removing pgvector PVCs from $(NAMESPACE)"
	@kubectl get pvc -n $(NAMESPACE) -o custom-columns=NAME:.metadata.name | grep -E '^(pg)-data' | xargs -I {} kubectl delete pvc -n $(NAMESPACE) {} ||:
	@echo "Deleting remaining pods in namespace $(NAMESPACE)"
	@kubectl delete pods -n $(NAMESPACE) --all
	@echo "Checking for any remaining resources in namespace $(NAMESPACE)..."
	@echo "If you want to completely remove the namespace, run: kubectl delete namespace $(NAMESPACE)"
	@echo "Remaining resources in namespace $(NAMESPACE):"
	@$(MAKE) helm-status

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

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
ASSET_MGR_IMG ?= $(REGISTRY)/self-service-asset-manager:$(VERSION)
MCP_EMP_INFO_IMG ?= $(REGISTRY)/self-service-agent-employee-info-mcp:$(VERSION)

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

helm_pgvector_args = \
    --set pgvector.secret.user=$(POSTGRES_USER) \
    --set pgvector.secret.password=$(POSTGRES_PASSWORD) \
    --set pgvector.secret.dbname=$(POSTGRES_DBNAME)

helm_llm_service_args = \
    $(if $(HF_TOKEN),--set llm-service.secret.hf_token=$(HF_TOKEN),) \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_TOLERATION),--set-json global.models.$(LLM).tolerations='$(call TOLERATIONS_TEMPLATE,$(LLM_TOLERATION))',) \
    $(if $(SAFETY_TOLERATION),--set-json global.models.$(SAFETY).tolerations='$(call TOLERATIONS_TEMPLATE,$(SAFETY_TOLERATION))',)

helm_llama_stack_args = \
    $(if $(LLM),--set global.models.$(LLM).enabled=true,) \
    $(if $(SAFETY),--set global.models.$(SAFETY).enabled=true,) \
    $(if $(LLM_URL),--set global.models.$(LLM).url='$(LLM_URL)',) \
    $(if $(LLM_ID),--set global.models.$(LLM).id='$(LLM_ID)',) \
    $(if $(SAFETY_URL),--set global.models.$(SAFETY).url='$(SAFETY_URL)',) \
    $(if $(LLM_API_TOKEN),--set global.models.$(LLM).apiToken='$(LLM_API_TOKEN)',) \
    $(if $(SAFETY_API_TOKEN),--set global.models.$(SAFETY).apiToken='$(SAFETY_API_TOKEN)',) \
    $(if $(LLAMA_STACK_ENV),--set-json llama-stack.secrets='$(LLAMA_STACK_ENV)',)

# Default target
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  build-all-images            - Build all container images (agent, asset-manager, employee-info-mcp)"
	@echo "  build-agent-image           - Build the self-service agent container image"
	@echo "  build-asset-mgr-image       - Build the asset manager container image"
	@echo "  build-mcp-emp-info-image    - Build the employee info MCP server container image"
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
	@echo "  lint                        - Run flake8 linting on entire codebase"
	@echo "  push-all-images             - Push all container images to registry"
	@echo "  push-agent-image            - Push the self-service agent container image to registry"
	@echo "  push-asset-mgr-image        - Push the asset manager container image to registry"
	@echo "  push-mcp-emp-info-image     - Push the employee info MCP server container image to registry"
	@echo "  test-all                    - Run tests for all projects"
	@echo "  test                        - Run tests for self-service agent"
	@echo "  test-asset-manager          - Run tests for asset manager"
	@echo "  test-mcp-emp-info           - Run tests for employee info MCP server"
	@echo ""
	@echo "Configuration options (set via environment variables or make arguments):"
	@echo "  CONTAINER_TOOL           - Container build tool (default: podman)"
	@echo "  REGISTRY                 - Container registry (default: quay.io/ecosystem-appeng)"
	@echo "  VERSION                  - Image version tag (default: 0.0.2)"
	@echo "  AGENT_IMG                - Full agent image name (default: \$${REGISTRY}/self-service-agent:\$${VERSION})"
	@echo "  ASSET_MGR_IMG            - Full asset manager image name (default: \$${REGISTRY}/self-service-asset-manager:\$${VERSION})"
	@echo "  MCP_EMP_INFO_IMG         - Full employee info MCP image name (default: \$${REGISTRY}/self-service-agent-employee-info-mcp:\$${VERSION})"
	@echo "  NAMESPACE                - Target namespace (default: llama-stack-rag)"
	@echo "  HF_TOKEN                 - Hugging Face Token (will prompt if not provided)"
	@echo "  {SAFETY,LLM}             - Model id as defined in values (eg. llama-3-2-1b-instruct)"
	@echo "  LLM_ID                   - Model ID for LLM configuration"
	@echo "  {SAFETY,LLM}_URL         - Model URL"
	@echo "  {SAFETY,LLM}_API_TOKEN   - Model API token for remote models"
	@echo "  {SAFETY,LLM}_TOLERATION  - Model pod toleration"

# Build function: $(call build_image,IMAGE_NAME,DESCRIPTION,CONTAINERFILE_PATH,BUILD_CONTEXT)
define build_image
	@echo "Building $(2): $(1)"
	$(CONTAINER_TOOL) build -t $(1) $(if $(3),-f $(3),) $(4)
	@echo "Successfully built $(1)"
endef

# Push function: $(call push_image,IMAGE_NAME,DESCRIPTION)
define push_image
	@echo "Pushing $(2): $(1)"
	$(CONTAINER_TOOL) push $(1)
	@echo "Successfully pushed $(1)"
endef

# Build container images
.PHONY: build-all-images
build-all-images: build-agent-image build-asset-mgr-image build-mcp-emp-info-image
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

# Push container images
.PHONY: push-all-images
push-all-images: push-agent-image push-asset-mgr-image push-mcp-emp-info-image
	@echo "All container images pushed successfully!"

.PHONY: push-agent-image
push-agent-image:
	$(call push_image,$(AGENT_IMG),self-service agent image)

.PHONY: push-asset-mgr-image
push-asset-mgr-image:
	$(call push_image,$(ASSET_MGR_IMG),asset manager image)

.PHONY: push-mcp-emp-info-image
push-mcp-emp-info-image:
	$(call push_image,$(MCP_EMP_INFO_IMG),employee info MCP image)

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
install-all: install install-asset-manager install-mcp-emp-info
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

# Test code
.PHONY: test-all
test-all: test test-asset-manager test-mcp-emp-info
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

# Create namespace and deploy
namespace:
	@oc create namespace $(NAMESPACE) &> /dev/null && oc label namespace $(NAMESPACE) modelmesh-enabled=false ||:
	@oc project $(NAMESPACE) &> /dev/null ||:

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
		$(EXTRA_HELM_ARGS)
	@echo "Waiting for model services and llamastack to deploy. It may take around 10-15 minutes depending on the size of the model..."
	@oc rollout status deploy/$(MAIN_CHART_NAME) -n $(NAMESPACE)
	@echo "$(MAIN_CHART_NAME) installed successfully"

# Uninstall the deployment and clean up
.PHONY: helm-uninstall
helm-uninstall:
	@echo "Uninstalling $(MAIN_CHART_NAME) helm chart"
	@helm uninstall --ignore-not-found $(MAIN_CHART_NAME) -n $(NAMESPACE)
	@echo "Removing pgvector PVCs from $(NAMESPACE)"
	@oc get pvc -n $(NAMESPACE) -o custom-columns=NAME:.metadata.name | grep -E '^(pg)-data' | xargs -I {} oc delete pvc -n $(NAMESPACE) {} ||:
	@echo "Deleting remaining pods in namespace $(NAMESPACE)"
	@oc delete pods -n $(NAMESPACE) --all
	@echo "Checking for any remaining resources in namespace $(NAMESPACE)..."
	@echo "If you want to completely remove the namespace, run: oc delete project $(NAMESPACE)"
	@echo "Remaining resources in namespace $(NAMESPACE):"
	@$(MAKE) helm-status

# Check deployment status
.PHONY: helm-status
helm-status:
	@echo "Listing pods..."
	oc get pods -n $(NAMESPACE) || true

	@echo "Listing services..."
	oc get svc -n $(NAMESPACE) || true

	@echo "Listing routes..."
	oc get routes -n $(NAMESPACE) || true

	@echo "Listing secrets..."
	oc get secrets -n $(NAMESPACE) | grep huggingface-secret || true

	@echo "Listing pvcs..."
	oc get pvc -n $(NAMESPACE) || true

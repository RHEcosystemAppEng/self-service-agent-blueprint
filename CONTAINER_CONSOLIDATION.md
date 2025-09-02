# Container Image Consolidation

## Overview

This document describes the consolidation of three separate container images into a single unified image that can be executed in different ways via Kubernetes deployments.

## Previous State

Previously, the system used three separate container images:

1. **`self-service-agent-db-migration`** - Database migration container
2. **`self-service-agent-asset-manager`** - Asset registration container  
3. **`self-service-agent`** - Main service container

## Consolidated Approach

All three use cases now use the existing repository image: **`self-service-agent`**

### Unified Containerfile

The new `Containerfile.template` includes:
- All source code from asset-manager, shared-clients, and shared-db
- All dependencies installed via `uv sync`
- Proper Python path configuration
- Default command that can be overridden

### Execution Modes

The same image is used with different commands in different deployments:

#### 1. Database Migration (Job)
```yaml
image: "quay.io/ecosystem-appeng/self-service-agent:0.0.2"
command: ["python", "shared-db/scripts/migrate.py"]
```

#### 2. Asset Registration (Init Job)
```yaml
image: "quay.io/ecosystem-appeng/self-service-agent:0.0.2"
command: ["python", "-m", "asset_manager.script.register_assets"]
```

#### 3. Main Service (Deployment)
```yaml
image: "quay.io/ecosystem-appeng/self-service-agent:0.0.2"
command: ["./scripts/containers/entrypoint.sh"]
```

## Benefits

1. **Reduced Build Complexity**: Only one image to build and maintain
2. **Consistent Dependencies**: All services use the same dependency versions
3. **Simplified CI/CD**: Single build pipeline instead of three
4. **Reduced Storage**: One image instead of three (with shared layers)
5. **Easier Debugging**: Same environment across all services
6. **Faster Development**: Changes to shared code don't require rebuilding multiple images

## Implementation Details

### Files Modified

1. **`Containerfile.template`** - New unified container definition
2. **`Makefile`** - Updated build targets and removed separate image builds
3. **`helm/values.yaml`** - Updated to use repository image for all services
4. **`helm/templates/db-migration-job.yaml`** - Uses repository image with migration command
5. **`helm/templates/init-job.yaml`** - Uses repository image with asset registration command
6. **`helm/templates/deployment.yaml`** - Uses repository image with main service command

### Files Removed

1. **`asset-manager/Containerfile`** - No longer needed (functionality in unified image)
2. **`shared-db/Containerfile`** - No longer needed (functionality in unified image)

### Files Renamed

1. **`Containerfile.template`** → **`Containerfile.services-template`** - Renamed to avoid confusion with new unified template

### Build Process

To build the unified image using the Makefile:
```bash
# Build the unified image (includes asset-manager and db-migration functionality)
make build-agent-image

# Build all images
make build-all-images

# Push the unified image
make push-agent-image

# Push all images
make push-all-images
```

Or build directly with podman:
```bash
# Build the unified image
podman build -f Containerfile.template -t quay.io/ecosystem-appeng/self-service-agent:0.0.2 .

# Push to registry
podman push quay.io/ecosystem-appeng/self-service-agent:0.0.2
```

### Deployment

The Helm chart automatically uses the appropriate command for each service type based on the deployment template.

## Current Containerfile Structure

```
./Containerfile                    # Original main service (kept for reference)
./Containerfile.template           # New unified container (replaces 3 separate builds)
./Containerfile.services-template  # Template for individual services (request-manager, agent-service, integration-dispatcher)
./Containerfile.mcp-template       # MCP server template (unchanged)
```

## Migration Steps

1. Build and push the unified image
2. Update the Helm values to use the unified image
3. Deploy the updated chart
4. Verify all three services work correctly
5. Remove the old separate image builds from CI/CD

## Rollback Plan

If issues arise, you can quickly rollback by:
1. Reverting the Helm values to use separate images
2. Rebuilding the separate images
3. Redeploying with the original configuration

## Testing

Before deploying to production:
1. Test database migration with the unified image
2. Test asset registration with the unified image  
3. Test main service functionality
4. Verify all health checks pass
5. Test scaling and restart scenarios

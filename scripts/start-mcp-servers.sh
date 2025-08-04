#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
EMPLOYEE_INFO_PORT=8001
SERVICENOW_PORT=8002
NETWORK_NAME="mcp-network"

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if podman is installed
check_podman() {
    if ! command -v podman &> /dev/null; then
        print_error "podman is not installed. Please install podman first."
        exit 1
    fi
    print_success "podman is available"
}

# Function to create network if it doesn't exist
create_network() {
    if ! podman network exists "$NETWORK_NAME" &> /dev/null; then
        print_info "Creating podman network: $NETWORK_NAME"
        podman network create "$NETWORK_NAME"
        print_success "Network created: $NETWORK_NAME"
    else
        print_info "Network already exists: $NETWORK_NAME"
    fi
}

# Function to build container image
build_image() {
    local service_name=$1
    local context_dir=$2
    local image_name="mcp-${service_name}:latest"
    
    print_info "Building image for $service_name..."
    
    if [ ! -d "$context_dir" ]; then
        print_error "Directory $context_dir does not exist"
        exit 1
    fi
    
    cd "$context_dir"
    podman build -t "$image_name" -f Containerfile .
    cd - > /dev/null
    
    print_success "Built image: $image_name"
}

# Function to start MCP server container
start_server() {
    local service_name=$1
    local port=$2
    local image_name="mcp-${service_name}:latest"
    local container_name="mcp-${service_name}"
    
    print_info "Starting $service_name on port $port..."
    
    # Stop and remove existing container if running
    if podman ps -a --format "{{.Names}}" | grep -q "^${container_name}$"; then
        print_warning "Stopping existing container: $container_name"
        podman stop "$container_name" || true
        podman rm "$container_name" || true
    fi
    
    # Start new container
    podman run -d \
        --name "$container_name" \
        --network "$NETWORK_NAME" \
        -p "${port}:8000" \
        --restart unless-stopped \
        "$image_name"
    
    print_success "Started $service_name container: $container_name"
}

# Function to check if service is healthy
check_health() {
    local service_name=$1
    local port=$2
    local max_attempts=30
    local attempt=1
    
    print_info "Checking health of $service_name..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "http://localhost:${port}/health" > /dev/null 2>&1; then
            print_success "$service_name is healthy"
            return 0
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            print_warning "$service_name health check failed after $max_attempts attempts"
            return 1
        fi
        
        sleep 2
        attempt=$((attempt + 1))
    done
}

# Function to show status
show_status() {
    print_info "MCP Servers Status:"
    echo ""
    
    echo -e "${BLUE}Employee Info Server:${NC}"
    echo "  URL: http://localhost:$EMPLOYEE_INFO_PORT"
    echo "  Container: mcp-employee-info"
    echo "  Status: $(podman ps --format "{{.Status}}" --filter name=mcp-employee-info 2>/dev/null || echo "Not running")"
    echo ""
    
    echo -e "${BLUE}ServiceNow Server:${NC}"
    echo "  URL: http://localhost:$SERVICENOW_PORT"
    echo "  Container: mcp-servicenow"
    echo "  Status: $(podman ps --format "{{.Status}}" --filter name=mcp-servicenow 2>/dev/null || echo "Not running")"
    echo ""
    
    echo -e "${BLUE}Available Tools:${NC}"
    echo "  Employee Info:"
    echo "    - lookup_employee_info"
    echo "    - get_laptop_age"
    echo "    - list_employees_with_old_laptops"
    echo ""
    echo "  ServiceNow:"
    echo "    - submit_laptop_request"
    echo "    - check_request_status"
    echo "    - list_all_requests"
    echo "    - update_request_status"
    echo ""
}

# Function to stop all servers
stop_servers() {
    print_info "Stopping MCP servers..."
    
    for container in mcp-employee-info mcp-servicenow; do
        if podman ps --format "{{.Names}}" | grep -q "^${container}$"; then
            print_info "Stopping $container..."
            podman stop "$container"
            podman rm "$container"
            print_success "Stopped $container"
        else
            print_info "$container is not running"
        fi
    done
}

# Function to show logs
show_logs() {
    local service_name=${1:-"all"}
    
    if [ "$service_name" = "all" ]; then
        echo -e "${BLUE}Employee Info Logs:${NC}"
        podman logs mcp-employee-info 2>/dev/null || echo "Container not running"
        echo ""
        echo -e "${BLUE}ServiceNow Logs:${NC}"
        podman logs mcp-servicenow 2>/dev/null || echo "Container not running"
    else
        podman logs "mcp-${service_name}" 2>/dev/null || echo "Container not running"
    fi
}

# Main function
main() {
    local command=${1:-"start"}
    
    case "$command" in
        "start")
            print_info "Starting MCP servers with podman..."
            check_podman
            create_network
            
            # Build and start employee-info server
            build_image "employee-info" "mcp-servers/employee-info"
            start_server "employee-info" "$EMPLOYEE_INFO_PORT"
            
            # Build and start servicenow server
            build_image "servicenow" "mcp-servers/servicenow"
            start_server "servicenow" "$SERVICENOW_PORT"
            
            # Wait a moment for services to start
            sleep 5
            
            # Check health (optional, will warn if failed)
            check_health "employee-info" "$EMPLOYEE_INFO_PORT" || true
            check_health "servicenow" "$SERVICENOW_PORT" || true
            
            show_status
            ;;
        "stop")
            stop_servers
            ;;
        "status")
            show_status
            ;;
        "logs")
            show_logs "${2}"
            ;;
        "restart")
            stop_servers
            sleep 2
            main "start"
            ;;
        "help"|"-h"|"--help")
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  start    - Build and start all MCP servers (default)"
            echo "  stop     - Stop all MCP servers"
            echo "  restart  - Restart all MCP servers"
            echo "  status   - Show status of MCP servers"
            echo "  logs     - Show logs for all servers or specific server"
            echo "           Usage: $0 logs [employee-info|servicenow]"
            echo "  help     - Show this help message"
            echo ""
            echo "Ports:"
            echo "  Employee Info: http://localhost:$EMPLOYEE_INFO_PORT"
            echo "  ServiceNow:    http://localhost:$SERVICENOW_PORT"
            ;;
        *)
            print_error "Unknown command: $command"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Check if script is being sourced or executed
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
#!/bin/bash

# ServiceNow PDI Hibernation Detection and Wake-up Script
# This script checks if a ServiceNow PDI is hibernating and wakes it up if needed

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MAX_WAKE_POLL_ATTEMPTS=20  # maximum polling attempts to check if instance is awake

# Function to log with timestamp and color
log() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date +'%Y-%m-%d %H:%M:%S')] ${message}${NC}" >&2
}

log_info() {
    log "${BLUE}" "INFO: $1"
}

log_success() {
    log "${GREEN}" "SUCCESS: $1"
}

log_warning() {
    log "${YELLOW}" "WARNING: $1"
}

log_error() {
    log "${RED}" "ERROR: $1"
}

# Function to check if ServiceNow instance is hibernating
check_hibernation_status() {
    local base_url="$1"
    local api_key="$2"

    log_info "Checking hibernation status for: $base_url"

    local response
    local http_code

    # Make API call and capture both response and HTTP status code
    response=$(curl -s -w "\n%{http_code}" \
        -H "x-sn-apikey: $api_key" \
        -H "Accept: application/json" \
        "$base_url/api/now/ui/user/current_user" 2>/dev/null || echo "000")

    # Split response and HTTP code
    http_code=$(echo "$response" | tail -n1)
    log_info "HTTP Status Code: $http_code"

    body=$(echo "$response" | sed '$d')

    if [[ "$http_code" == "200" ]]; then
        if echo "$body" | grep -q "Instance Hibernating page"; then
            log_warning "Instance is hibernating"
            echo "hibernating"
        else
            log_success "Instance is awake and responding"
            echo "awake"
        fi
    elif [[ "$http_code" == "502" ]]; then
        log_warning "Instance is waking up, not ready yet"
        echo "waking_up"
    else
        log_error "API call failed with HTTP $http_code"
        log_error "Response: $body"
        echo "error"
    fi
}

# Function to wake up ServiceNow instance
wake_up_instance() {
    log_info "Waking up ServiceNow instance..."

    # Run the servicenow-wake command
    if make servicenow-wake; then
        log_success "Wake-up command executed successfully"
        return 0
    else
        log_error "Wake-up command failed"
        return 1
    fi
}

# Function to wait for instance to be awake
wait_for_instance_awake() {
    local base_url="$1"
    local api_key="$2"
    local attempt=1
    local delay=5

    log_info "Waiting for instance to fully wake up (max ${MAX_WAKE_POLL_ATTEMPTS} attempts)..."

    while [[ $attempt -le $MAX_WAKE_POLL_ATTEMPTS ]]; do
        log_info "Checking status... (attempt: ${attempt}/${MAX_WAKE_POLL_ATTEMPTS})"

        local status=$(check_hibernation_status "$base_url" "$api_key")

        case $status in
            "hibernating")
                log_info "Instance still hibernating, attempt $attempt..."
                ;;
            "awake")
                log_success "Instance is now fully awake!"
                return 0
                ;;
            "error")
                log_warning "API check failed, attempt $attempt..."
                ;;
            "waking_up")
                log_info "The instance is waking up, attempt $attempt..."
                ;;
        esac

        attempt=$((attempt + 1))

        # Add a short sleep between attempts to avoid overwhelming the API
        if [[ $attempt -le $MAX_WAKE_POLL_ATTEMPTS ]]; then
            sleep "$delay"
            delay=$(( delay + 5 ))
        fi
    done

    log_error "Instance did not wake up within ${MAX_WAKE_POLL_ATTEMPTS} attempts"
    return 1
}

# Main function
main() {
    log_info "Starting ServiceNow PDI hibernation check..."

    # Validate all required environment variables
    local missing_vars=()

    [[ -z "${SERVICENOW_INSTANCE_URL:-}" ]] && missing_vars+=("SERVICENOW_INSTANCE_URL")
    [[ -z "${SERVICENOW_API_KEY:-}" ]] && missing_vars+=("SERVICENOW_API_KEY")
    [[ -z "${SERVICENOW_DEV_PORTAL_USERNAME:-}" ]] && missing_vars+=("SERVICENOW_DEV_PORTAL_USERNAME")
    [[ -z "${SERVICENOW_DEV_PORTAL_PASSWORD:-}" ]] && missing_vars+=("SERVICENOW_DEV_PORTAL_PASSWORD")

    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "Required environment variables not set:"
        for var in "${missing_vars[@]}"; do
            log_error "  $var"
        done
        exit 1
    fi

    local base_url="$SERVICENOW_INSTANCE_URL"
    local api_key="$SERVICENOW_API_KEY"

    # Remove trailing slash from URL if present
    base_url="${base_url%/}"

    log_info "ServiceNow Instance URL: $base_url"

    # Initial hibernation check
    local initial_status=$(check_hibernation_status "$base_url" "$api_key")

    case $initial_status in
        "hibernating")
            log_warning "Instance is hibernating - attempting to wake it up"

            if wake_up_instance; then
                # Wait for instance to become fully awake
                if wait_for_instance_awake "$base_url" "$api_key"; then
                    log_success "Instance successfully awakened!"
                    exit 0
                else
                    log_error "Instance failed to wake up within the polling attempts"
                    exit 1
                fi
            else
                log_error "Wake-up command failed"
                exit 1
            fi
            ;;
        "awake")
            log_success "Instance is already awake - no action needed"
            exit 0
            ;;
        "waking_up")
            log_info "Instance is already waking up - waiting for it to be fully awake"
            if wait_for_instance_awake "$base_url" "$api_key"; then
                log_success "Instance is now fully awake!"
                exit 0
            else
                log_error "Instance failed to wake up within the polling attempts"
                exit 1
            fi
            ;;
        "error")
            log_error "Failed to check hibernation status"
            exit 1
            ;;
        *)
            log_error "Unexpected hibernation status: $initial_status"
            exit 1
            ;;
    esac
}

# Show help message
show_help() {
    cat << EOF
ServiceNow PDI Hibernation Detection and Wake-up Script

This script checks if a ServiceNow Personal Developer Instance (PDI) is hibernating
and automatically wakes it up if needed.

REQUIRED ENVIRONMENT VARIABLES:
  SERVICENOW_INSTANCE_URL        - Base URL of your ServiceNow instance
  SERVICENOW_API_KEY            - API key for ServiceNow instance
  SERVICENOW_DEV_PORTAL_USERNAME - ServiceNow Developer Portal username (for wake-up)
  SERVICENOW_DEV_PORTAL_PASSWORD - ServiceNow Developer Portal password (for wake-up)

USAGE:
  $0 [OPTIONS]

OPTIONS:
  -h, --help    Show this help message and exit

EXAMPLES:
  # Check and wake up instance if hibernating
  export SERVICENOW_INSTANCE_URL="https://dev12345.service-now.com"
  export SERVICENOW_API_KEY="your-api-key"
  export SERVICENOW_DEV_PORTAL_USERNAME="your-username"
  export SERVICENOW_DEV_PORTAL_PASSWORD="your-password"
  $0

EXIT CODES:
  0 - Success (instance awake or successfully awakened)
  1 - Failure (instance hibernating and could not wake up, or other error)

EOF
}

# Parse command line arguments
if [[ $# -gt 0 ]]; then
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
fi

# Run main function
main "$@"

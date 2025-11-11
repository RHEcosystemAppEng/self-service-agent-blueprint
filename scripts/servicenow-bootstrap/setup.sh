#!/bin/bash

# ServiceNow PDI Setup Automation Helper Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.json"
EXAMPLE_CONFIG="$SCRIPT_DIR/config.example.json"

echo "🤖 ServiceNow PDI Setup Automation"
echo "=================================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    echo "Please install Python 3.7 or later."
    exit 1
fi

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "📋 Configuration file not found."

    if [ -f "$EXAMPLE_CONFIG" ]; then
        echo "📋 Copying example configuration..."
        cp "$EXAMPLE_CONFIG" "$CONFIG_FILE"
        echo "✅ Created $CONFIG_FILE"
        echo ""
        echo "⚠️  Please edit $CONFIG_FILE with your ServiceNow instance details:"
        echo "   - instance_url: Your ServiceNow PDI URL"
        echo "   - admin_username: Your admin username (usually 'admin')"
        echo "   - admin_password: Your admin password"
        echo ""
        echo "Then run this script again."
        exit 0
    else
        echo "❌ Example configuration file not found: $EXAMPLE_CONFIG"
        exit 1
    fi
fi

# Install requirements if needed
echo "📦 Checking Python dependencies..."
if ! python3 -c "import requests" &> /dev/null; then
    echo "📦 Installing required Python packages..."
    pip3 install -r "$SCRIPT_DIR/requirements.txt"
fi

# Check if configuration has required fields
echo "📋 Validating configuration..."
if ! python3 -c "
import json, sys
try:
    with open('$CONFIG_FILE') as f:
        config = json.load(f)

    # Check required fields
    required = ['instance_url', 'admin_username', 'admin_password']
    missing = [f for f in required if not config.get('servicenow', {}).get(f)]

    if missing:
        print(f'❌ Missing required fields in servicenow section: {missing}')
        sys.exit(1)

    if 'your-instance' in config['servicenow']['instance_url']:
        print('❌ Please update the instance_url in your config.json')
        sys.exit(1)

    print('✅ Configuration valid')
except Exception as e:
    print(f'❌ Configuration error: {e}')
    sys.exit(1)
"; then
    echo "Please fix the configuration issues above and try again."
    exit 1
fi

echo ""
echo "🚀 Starting ServiceNow setup automation..."
echo ""

# Run the main setup script
python3 "$SCRIPT_DIR/setup_servicenow.py" --config "$CONFIG_FILE" "$@"
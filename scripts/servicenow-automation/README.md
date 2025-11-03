# ServiceNow PDI Setup Automation

This directory contains automation scripts to help set up a ServiceNow Personal Development Instance (PDI) for testing the Blueprint's integration with ServiceNow.

## 🎯 What This Automates

The scripts automate most of the manual steps described in the [ServiceNow Setup Guide](../../guides/SERVICE_NOW_SETUP.md):

### ✅ Fully Automated Steps
- **User Creation**: Creates the MCP Agent user with proper identity type
- **Password Generation**: Generates secure passwords automatically
- **Role Assignment**: Assigns necessary roles for API access
- **API Key Creation**: Creates and configures REST API keys
- **Authentication Profiles**: Sets up API Key and Basic Auth profiles
- **API Access Policies**: Creates policies for Service Catalog, Table, and UI APIs
- **Catalog Item Creation**: Creates the PC Refresh catalog item
- **Catalog Variables**: Sets up "Requested for" and "Laptop Choices" variables
- **Choice Options**: Populates laptop choice options

### ⚠️ Manual Steps Still Required
1. **ServiceNow PDI Creation**: You must manually create your PDI instance
2. **Flow Designer Configuration**: Set up the fulfillment flow
3. **Access Controls**: Configure "Available for" and "Not available for" settings
4. **Catalog Publishing**: Publish the catalog item
5. **Testing**: Verify everything works in the Service Portal

## 📋 Prerequisites

1. **Python 3.12+** and **uv** package manager:
   ```bash
   # Install uv if you haven't already
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **ServiceNow PDI Instance**:
   - Follow Step 1 of the [ServiceNow Setup Guide](../../guides/SERVICE_NOW_SETUP.md)
   - Note your instance URL and admin credentials

3. **Admin Access**: You need admin credentials for your ServiceNow instance

## 🚀 Quick Start

### 1. Setup Configuration

Copy the example configuration and fill in your details:

```bash
cd scripts/servicenow-automation
cp config.example.json config.json
```

Edit `config.json` with your ServiceNow instance details:

```json
{
  "servicenow": {
    "instance_url": "https://dev12345.service-now.com",
    "admin_username": "admin",
    "admin_password": "your-admin-password"
  }
}
```

### 2. Install Dependencies

Install the project and its dependencies using uv:

```bash
cd scripts/servicenow-automation
uv sync
```

For development dependencies (optional):
```bash
uv sync --group dev
```

### 3. Run Complete Setup

Execute the main orchestration script:

```bash
uv run setup-servicenow --config config.json
```

The script will:
- Show you what it will do
- Ask for confirmation
- Execute all steps in sequence
- Save generated credentials to `config.json`

### 4. Verify Results

1. Log into your ServiceNow instance
2. Check that the MCP Agent user was created
3. Verify API keys and authentication profiles exist
4. Test the PC Refresh catalog item

## 📜 Individual Scripts

You can also run individual automation modules using Python's module syntax:

### User Automation
```bash
uv run python -m servicenow_automation.user_automation --config config.json
```
Creates the MCP Agent user, generates password, and assigns roles.

### API Automation
```bash
uv run python -m servicenow_automation.api_automation --config config.json
```
Sets up API keys, authentication profiles, and access policies.

### Catalog Automation
```bash
uv run python -m servicenow_automation.catalog_automation --config config.json
```
Creates the PC Refresh catalog item with variables and choices.

## ⚙️ Configuration Options

### Complete Configuration Example

```json
{
  "servicenow": {
    "instance_url": "https://dev12345.service-now.com",
    "admin_username": "admin",
    "admin_password": "your-admin-password",
    "agent_user": {
      "user_id": "mcp_agent",
      "first_name": "MCP",
      "last_name": "Agent",
      "password": "auto-generated-will-be-saved-here"
    },
    "api_key_name": "MCP Agent API Key",
    "api_key_token": "auto-generated-will-be-saved-here"
  },
  "catalog": {
    "name": "PC Refresh",
    "short_description": "Flow to request a PC refresh",
    "laptop_choices": [
      "Apple MacBook Air M3",
      "Apple MacBook Pro 14 M3 Pro",
      "Lenovo ThinkPad T14 Gen 5 Intel",
      "Lenovo ThinkPad P1 Gen 7"
    ]
  }
}
```

### Customizing Laptop Choices

The laptop choices in the configuration match the ServiceNow codes used in the knowledge base at `agent-service/config/knowledge_bases/laptop-refresh/`. You can modify the list but ensure the values match what's expected by your agent.

## 🔧 Advanced Usage

### Skip Specific Steps

```bash
# Skip user creation (if already done)
uv run setup-servicenow --config config.json --skip-user

# Skip API setup
uv run setup-servicenow --config config.json --skip-api

# Skip catalog creation
uv run setup-servicenow --config config.json --skip-catalog

# Run without confirmation prompts
uv run setup-servicenow --config config.json --no-confirm
```

### Re-running Scripts

The scripts are designed to be idempotent - you can run them multiple times safely. They will:
- Skip creation if items already exist
- Update existing configurations where appropriate
- Not duplicate data

## 🛠️ Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Verify your admin username and password
   - Check that your instance URL is correct
   - Ensure you have admin privileges

2. **API Not Found Errors**
   - Some ServiceNow versions might have different API names
   - Check your ServiceNow version compatibility

3. **Permission Denied**
   - Ensure your admin user has sufficient privileges
   - Some operations might require specific roles

4. **Categories Not Found**
   - The script looks for Hardware, Laptops, and Hardware Asset categories
   - If these don't exist, the catalog item will be created without categories
   - You can manually assign categories later

### Debug Mode

For more detailed output, you can modify the scripts to enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🔐 Security Considerations

1. **Credential Storage**:
   - Never commit `config.json` to version control
   - Store credentials securely
   - Consider using environment variables for sensitive data

2. **API Keys**:
   - The generated API keys have significant privileges
   - Rotate them regularly
   - Monitor their usage

3. **Network Security**:
   - Ensure HTTPS is used for all communications
   - Consider VPN if required by your organization

## 🧪 Testing the Setup

After running the automation:

1. **Test User Login**:
   ```bash
   # Try authenticating with the created user
   curl -u "mcp_agent:generated_password" \
        "https://your-instance.service-now.com/api/now/table/sys_user?sysparm_limit=1"
   ```

2. **Test API Key**:
   ```bash
   # Try using the API key
   curl -H "x-sn-apikey: your_api_key" \
        "https://your-instance.service-now.com/api/now/table/sys_user?sysparm_limit=1"
   ```

3. **Test Service Portal**:
   - Log into the Service Portal
   - Navigate to Service Catalog
   - Find the PC Refresh item
   - Test the request flow

## 📚 Related Documentation

- [ServiceNow Setup Guide](../../guides/SERVICE_NOW_SETUP.md) - Manual setup instructions
- [ServiceNow REST API Documentation](https://docs.servicenow.com/bundle/utah-application-development/page/integrate/inbound-rest/concept/c_RESTAPI.html)
- [Blueprint Documentation](../../README.md) - Main project documentation

## 🤝 Contributing

If you find issues or want to improve the automation:

1. Test your changes thoroughly
2. Update this README if needed
3. Consider backward compatibility
4. Add appropriate error handling

## 👨‍💻 Development

This project uses modern Python tooling with uv for package management:

### Development Setup
```bash
# Clone and navigate to the project
cd scripts/servicenow-automation

# Install with development dependencies
uv sync --group dev

# Run linting and formatting
uv run black src/ tests/
uv run flake8 src/ tests/
uv run isort src/ tests/

# Run type checking
uv run mypy src/

# Run tests (when available)
uv run pytest
```

### Project Structure
```
scripts/servicenow-automation/
├── pyproject.toml              # Project configuration and dependencies
├── README.md                   # This file
├── config.example.json         # Example configuration
├── src/servicenow_automation/  # Main package
│   ├── __init__.py
│   ├── setup.py              # Main entry point
│   ├── user_automation.py    # User management automation
│   ├── api_automation.py     # API configuration automation
│   └── catalog_automation.py # Catalog setup automation
└── tests/                     # Test directory
    └── __init__.py
```

## 📝 License

This automation is part of the Self-Service Agent Blueprint project and follows the same license terms.
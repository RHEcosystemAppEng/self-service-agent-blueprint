# ServiceNow PDI Bootstrap - Manual Setup

This guide describes the manual steps required to bootstrap a PDI (Personal Development Instance) that can be used to test the Blueprint's integration with ServiceNow. Creating a PDI is offered for free (at least at the time of writing this document).

## Table of Contents

1. [Signup + PDI New Instance](#step-1---signup--pdi-new-instance)
2. [Create a new "PC Refresh" Service Catalog](#step-2---create-a-new-pc-refresh-service-catalog)
3. [Create an AI Agent user](#step-3---create-an-ai-agent-user)
4. [Create API Key and API Configuration](#step-4---create-api-key-and-api-configuration)

## Step 1 - Signup + PDI New Instance

This step establishes your development environment by creating a free ServiceNow Personal Development Instance (PDI). A PDI provides you with a fully functional ServiceNow instance that you can use for testing, development, and learning without affecting any production systems. This is essential for the self-service agent blueprint as it gives you a sandboxed environment where you can safely configure catalogs, users, and API access without any risk or cost.

1. **Sign up for ServiceNow Developer Hub**
   - First, [sign up](https://signon.servicenow.com/x_snc_sso_auth.do?pageId=sign-up) to ServiceNow's Developer Hub.

2. **Request a new instance**
   - Log in to the [developer hub](https://developer.servicenow.com/dev.do#!/)
   - Click "Request Instance"
   - Select "Yokohama" as the instance release version
   - **Note:** It may take a few minutes until your new instance is available.

3. **Access your instance**
   - Click on "Instance URL" to log in to your new instance as an admin
   - **Tip:** You can always return to this link if you forget your instance credentials.

## Step 2 - Create a new "PC Refresh" Service Catalog

This step creates the service catalog that your AI agent will interact with to fulfill laptop refresh requests. The service catalog acts as the user-facing interface where employees can request new laptops, and it defines the workflow that gets triggered when requests are submitted. By configuring specific laptop choices and request fields, you're essentially creating the structured data that the AI agent can understand and process, enabling it to automatically handle laptop refresh requests according to your organization's hardware options and approval processes.

1. **Open Catalog Builder**
   - Click "All" in the top left corner
   - Search for "Catalog Builder"
   - Click the link (should open the builder in a new tab)

2. **Create new catalog**
   - Click "Build from scratch"
   - Select "Standard" template
   - Click "Continue"

3. **Configure the catalog sections**
   Configure the following under each section:
   ### Details
   - **Item name:** `PC Refresh`
   - **Short description:** `Flow to request a PC refresh`

   ### Location
   - **Catalogs:** Browse → Select "Service Catalog" → Click "Save selection"
   - **Categories:** Browse → Search for "Laptops" -> Select "Laptops" -> Click Add (Repeat this step for "Hardware", "Hardware Asset") → Click "Save selection"

   ### Questions
   - **First Question (Requested for):**
     - Click "Insert new question"
     - **Question Type:** Choice
     - **Question subtype:** Requested for
     - **Question label:** `Who is this request for?`
     - Click "Additional details" tab
     - Verify **Source table** is set to "User" and **Reference qualifier type** is set to "Simple"
     - Click "Insert question"

   - **Second Question (Laptop Choices):**
     - Click "Insert new question"
     - **Question Type:** Choice
     - **Question subtype:** Dropdown (fixed values)
     - **Question label:** `Laptop Choices`
     - Check "Mandatory" field
     - Click "Choices" tab
     - Add the following laptop options:
       - Apple MacBook Air M3
       - Apple MacBook Pro 14 M3 Pro
       - Lenovo ThinkPad T14 Gen 5 Intel
       - Lenovo ThinkPad P1 Gen 7
       - Apple MacBook Air M2
       - Apple MacBook Pro 14 M3
       - Lenovo ThinkPad T14 Gen 4 Intel
       - Lenovo ThinkPad P16s Gen 2
       - Apple MacBook Pro 16 M3 Max
       - Lenovo ThinkPad T14s Gen 5 AMD
       - Lenovo ThinkPad P16 Gen 2
       - Lenovo ThinkPad T14 Gen 5 AMD
       - Lenovo ThinkPad P1 Gen 6
     - Click "Insert question"
     
Each time you add a laptop option, if you don't provide a value, one will be generated from the name. The values must match the `ServiceNow Code` value specified in the knowledge base. The default values generated will match what was used in the knowledge based in [agent-service/config/knowledge_bases/](../agent-service/config/knowledge_bases/laptop-refresh)

   ### Settings
   - **Submit button label:** Choose "Request"
   - Check "Hide 'Add to cart' button"
   - Check "Hide quantity selector"

   ### Access
   - **Available for:** Browse → Select "All ACME Corporation employees" → Click "Save selection"
     - Note: "All ACME Corporation employees" is ServiceNow's generic Employee user criteria

   ### Fulfillment
   - **Process engine:** Select "Flow Designer flow"
   - **Selected flow:** Select "Service Catalog item request"

   ### Review and submit
   - Check all the above details are correct
   - Click "Submit" (you can still go back and edit later if needed)
   - **Note:** After submitting, it may take a few moments for the catalog status to change from "Publishing" to "Published"

## Step 3 - Create an AI Agent user

This step creates a dedicated service account for your AI agent to authenticate and interact with ServiceNow APIs. By creating a specific user with the "AI Agent" identity type, you're establishing proper security boundaries and audit trails for all automated actions performed by the blueprint. This user account will be used by the MCP (Model Context Protocol) server to authenticate API calls, ensuring that all AI-driven interactions with ServiceNow are properly tracked and attributed to the automated system rather than a human user.

1. **Navigate to Users**
   - Click "All" in the top left corner
   - Search for "Users"
   - Scroll until you see "Organization"
   - Click "Users" link directly under it

2. **Create new user**
   - Click "New"
   - **User ID:** `mcp_agent`
   - **First Name:** `MCP`
   - **Last Name:** `Agent`
   - **Identity type:** AI Agent
   - Click "Submit"

3. **Set password and configure user**
   - Click "Search" and enter "MCP"
   - Click "mcp_agent"
   - Click "Set Password"
   - Click "Generate"
   - **Important:** Copy the generated password and store it somewhere safe
   - Click "Save Password"
   - Click "Close"
   - Uncheck "Password needs reset"
   - Click "Update"

## Step 4 - Create API Key and API Configuration

This final step establishes the authentication and authorization framework that allows your AI agent to securely access ServiceNow's REST APIs. You'll create API keys for authentication, configure authentication profiles to define how the system validates incoming requests, and set up access policies that specify which APIs the agent can use. This layered security approach ensures that your AI agent has precisely the permissions it needs to read service catalogs, submit requests, and query tables, while preventing unauthorized access to sensitive ServiceNow functionality.

1. **Create API Key**
   - Click "All" in the top left corner
   - Search for "REST API Key"
   - Click "New"
   - **Name:** `MCP Agent API Key`
   - **User:** Search and select "MCP Agent"
   - Click "Submit"
   - After the new key is created, click "MCP Agent API Key"
   - On the right of the "Token" field, click the Lock symbol to view the API Key secret
   - **Important:** Store this value somewhere safe

2. **Create API Key Authentication Profile**
   - Click "All" in the top left corner
   - Search for "Inbound Authentication Profile"
   - Click "New"
   - Select "Create API Key authentication profiles"
   - **Name:** `API Key`
   - **Auth Parameter:** Click search and select "x-sn-apikey", "Auth Header"
   - Click "Submit"

3. **Create Service Catalog API Access Policy**
   - Click "All" in the top left corner
   - Search for "REST API Access Policies"
   - Click "New"
   - **Name:** `MCP Agent - SC`
   - **REST API:** Service Catalog API
   - Double click "Insert new row..." and search/select "API Key", and click the green checkmark to add
   - Click "Submit"

4. **Create Table API Access Policy**
   - Click "All" in the top left corner
   - Search for "REST API Access Policies"
   - Click "New"
   - **Name:** `MCP Agent - Tables`
   - **REST API:** Table API
   - Double click "Insert new row..." and search/select "API Key", and click the green checkmark to add
   - Click "Submit"

5. **Create UI GlideRecord API Access Policy**
   - Click "All" in the top left corner
   - Search for "REST API Access Policies"
   - Click "New"
   - **Name:** `MCP Agent - UI`
   - **REST API:** UI GlideRecord API
   - Double click "Insert new row..." and search/select "API Key", and click the green checkmark to add
   - Click "Submit"


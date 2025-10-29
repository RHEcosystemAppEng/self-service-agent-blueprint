# ServiceNow PDI (Personal Development Instance) Setup Guide

This guide describes the steps required to create a PDI (Personal Development Instance) that can be used to test the Blueprint's integration with ServiceNow. Creating a PDI is offered for free (at least at the time of writing this document).

## Table of Contents

1. [Signup + PDI New Instance](#step-1---signup--pdi-new-instance)
2. [Create a new "PC Refresh" Service Catalog](#step-2---create-a-new-pc-refresh-service-catalog)
3. [Create an AI Agent user](#step-3---create-an-ai-agent-user)
4. [Create API Key and API Configuration](#step-4---create-api-key-and-api-configuration)

## Step 1 - Signup + PDI New Instance

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

   ### Settings
   - **Submit button label:** Choose "Request"
   - Check "Hide 'Add to cart' button"
   - Check "Hide quantity selector"

   ### Access
   - **Available for:** Browse → Select "Any User" → Click "Save selection"
   - **Not available for:** Browse → Select "Guest User" → Click "Save selection"

   ### Fulfillment
   - **Process engine:** Select "Flow Designer flow"
   - **Selected flow:** Select "Service Catalog item request"

   ### Review and submit
   - Check all the above details are correct
   - Click "Submit" (you can still go back and edit later if needed)
   - **Note:** After submitting, it may take a few moments for the catalog status to change from "Publishing" to "Published"

## Step 3 - Create an AI Agent user

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

1. **Create API Key**
   - Click "All" in the top left corner
   - Search for "API Keys"
   - Click "New"
   - **Name:** `MCP Agent API Key`
   - **User:** Search and select "MCP Agent"
   - Click "Submit"
   - After the new key is created, click "MCP Agent API Key"
   - On the right of the "Token" field, click the Lock symbol to view the API Key secret
   - **Important:** Store this value somewhere safe

2. **Create API Key Authentication Profile**
   - Click "All" in the top left corner
   - Search for "Authentication Profiles"
   - Click "New"
   - Select "Create API Key authentication profiles"
   - **Name:** `API Key`
   - **Auth Parameter:** Click search and select "x-sn-apikey", "Auth Header"
   - Click "Submit"

3. **Create Basic Auth Authentication Profile** (Optional)
   - Click "All" in the top left corner
   - Search for "Authentication Profiles"
   - Click "New"
   - Select "Create standard http authentication profiles"
   - **Name:** `Basic Auth`
   - Click "Submit"
   - **Note:** This step is optional if you require Basic Auth access to your APIs

4. **Create Service Catalog API Access Policy**
   - Click "All" in the top left corner
   - Search for "API Access Policies"
   - Click "New"
   - **Name:** `MCP Agent - SC`
   - **REST API:** Service Catalog API
   - Double click "Insert new row..." and search/select "API Key"
   - Repeat and select "Basic Auth" (if created in step 3)
   - Click "Submit"

5. **Create Table API Access Policy**
   - Click "All" in the top left corner
   - Search for "API Access Policies"
   - Click "New"
   - **Name:** `MCP Agent - Tables`
   - **REST API:** Table API
   - Double click "Insert new row..." and search/select "API Key"
   - Repeat and select "Basic Auth" (if created in step 3)
   - Click "Submit"

6. **Create UI GlideRecord API Access Policy**
   - Click "All" in the top left corner
   - Search for "API Access Policies"
   - Click "New"
   - **Name:** `MCP Agent - UI`
   - **REST API:** UI GlideRecord API
   - Double click "Insert new row..." and search/select "API Key"
   - Repeat and select "Basic Auth" (if created in step 3)
   - Click "Submit"


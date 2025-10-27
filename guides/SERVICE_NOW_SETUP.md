# ServiceNow PDI (Personal Development Instance) Setup Guide

- This guide describes the steps required in order to create a PDI (Personal Development Instance) that can be used in order to test the Blueprint's integration with ServiceNow.
- Creating a PDI is an offered for free (at least for the time of writing this doc).

## Step 1 - Signup + PDI New Instance
1. First you should [sign up](https://signon.servicenow.com/x_snc_sso_auth.do?pageId=sign-up) to ServiceNow's Developer hub.

2. Login into the [developer hub](https://developer.servicenow.com/dev.do#!/) -> Click "Request Instance" -> Select "Yokohama" as the instance release version. Note: it may take a few minutes until your new instance is available.

3. Click on "Instance URL" in order to log in to your new instance as a admin (you can always go back to this link in case you forget your instance credentials).

## Step 2 - Create a new "PC Refresh" Service Catalog
1. Click "All" in the top left corner -> Search for "Catalog Builder" -> Click the link (should open the build in a new tab).
2. Click "Build from scratch" -> Select "Standard" template -> Click "Continue"
3. Configure the following under each section:
### Details
- Item name: PC Refresh
- Short description: Flow to request a PC refresh
### Location
- Catalogs -> Browse -> Select "Service Catalog" -> Click "Save selection"
- Categories -> Browse -> Select "Laptops", "Hardware", "Hardware Asset" -> Click "Save selection"
### Questions
- Click "Insert new question" -> For "Question Type" select "Choice" -> For "Question subtype" select "Requested for" -> For "Question label" type "Who is this request for?" -> Click "Additional details" tab -> Check that "Source table" is set to "User" & "Reference qualifier type" is set to "Simple" -> Click "Insert question" 
- Click "Insert new question" -> For "Question Type" select "Choice" -> For "Question subtype" select "Dropdown (fixed values)" -> For "Question label" type "Laptop Choices" -> Check "Mandatory" field -> Click "Choices" tab -> Add the following options "Apple MacBook Air M3" , "Apple MacBook Pro 14 M3 Pro" , "Lenovo ThinkPad T14 Gen 5 Intel" , "Lenovo ThinkPad P1 Gen 7" , "Apple MacBook Air M2" , "Apple MacBook Pro 14 M3" , "Lenovo ThinkPad T14 Gen 4 Intel" , "Lenovo ThinkPad P16s Gen 2" , "Apple MacBook Pro 16 M3 Max" , "Lenovo ThinkPad T14s Gen 5 AMD" , "Lenovo ThinkPad P16 Gen 2" , "Lenovo ThinkPad T14 Gen 5 AMD" , "Lenovo ThinkPad P1 Gen 6" -> Click "Insert question"
### Settings 
- Choose "Request" as "Submit button label" -> Check "Hide 'Add to cart' button" & "Hide quantity selector"
### Access
- Available for -> Browse -> Select "Any User" -> Click "Save selection"
- Not available for -> Browse -> Select "Guest User" -> Click "Save selection"
### Fulfillment 
- Process engine -> For "Process engine" select "Flow Designer flow" -> For "Selected flow" select "Service Catalog item request"
### Review and submit
- Check all the above details are correct -> Click "Submit" (If needed you can still go back and edit later). After submitting, it may take a few moments until the catalog stats changes from "Publishing" to "Published". 
## Step 3 - Create a AI Agent user + Setup API Key
1. Click "All" in the top left corner -> Search for "Users" -> Scroll till you see "Organization", Click "Users" link directly under it
2. Click "New" -> For "User ID" enter "mcp_agent" -> For "First Name" enter "MCP" -> For "Last Name" enter "Agent" -> For "Identity type" select "AI Agent" - Click "Submit"
3. Click "Search" and enter "MCP" -> Click "mcp_agent" -> Click "Set Password" -> Click "Generate" -> Copy the generated password and store somewhere safe -> Click "Save Password" -> Click "Close" -> Uncheck "Password needs reset" -> Click "Update"

TODO snc_internal, cmdb_read roles
TODO API Key, API Profile, API Key Access




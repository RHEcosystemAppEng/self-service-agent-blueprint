# Self-Service Agent Slack Bot

A Slack bot that provides self-service capabilities through AI agents, allowing users to interact with various services (like laptop refresh requests) directly within Slack.

## Setup and Deployment

Follow these steps to configure the Slack app and deploy the service.

### Step 1: Create Your Slack App & Get Credentials

You must create the Slack app first to get the **Bot Token**, which is required for the deployment.

1.  **Create a New App:**

    - Go to the [Slack API Console](https://api.slack.com/apps) and click **"Create New App"**.
    - Choose **"From scratch"**, enter an app name (e.g., `Self-Service Agent`), and select your workspace.

2.  **Configure Bot Token Scopes:**

    - In the app's settings, go to **"OAuth & Permissions"**.
    - Scroll down to **"Scopes"** -\> **"Bot Token Scopes"** and add the following permissions:
      - `chat:write` (to send messages)
      - `users:read` (to View messages and other content in direct messages that app has been added to)
      - `users:read.email` (to get user email addresses)
      - `im:history` (to see direct messages)

3.  **Configure App Display Settings:**

    - Go to **"App Home"** in the left sidebar.
    - Under the **"Show Tabs"** section, make sure **"Messages Tab"** is enabled and check **"Allow users to send Slash commands and messages from the messages tab"**.
    - Scroll down and check **"Always Show My Bot as Online"**.

4.  **Get the Signing Secret:**

    - Go to **"Basic Information"** in the left sidebar of your Slack app settings.
    - Scroll down to **"App Credentials"** section.
    - Copy the **"Signing Secret"**. Keep it safe for the deployment step.

5.  **Install the App and Get the Token:**

    - At the top of the **"OAuth & Permissions"** page, click **"Install to Workspace"** and authorize it.
    - After installation, **copy the "Bot User OAuth Token"**. It will start with `xoxb-`. Keep it safe for the next step.


### Step 2: Deploy the Application with Helm

You can deploy the Slack bot using the provided `Makefile`, which will help you set up the necessary Kubernetes resources via Helm. The deployment process will require your Slack Bot Token and Signing Secret.

**To deploy:**

1. **Option 1: Deploy with Slack prompts**

    Set `ENABLE_SLACK=true` and the script will prompt your Slack credentials:

    ```bash
    make helm-install NAMESPACE=<your-namespace> \
      LLM=llama-4-scout-17b-16e-w4a16 \
      LLM_ID=llama-4-scout-17b-16e-w4a16 \
      LLM_URL=<llm-url>  \
      LLM_API_TOKEN=<your-api-token> \
      ENABLE_SLACK=true
    ```

2. **Option 2: Deploy with pre-set Slack credentials**

    Export your Slack credentials as environment variables:

    ```bash
    export SLACK_BOT_TOKEN="xoxb-your-bot-token-here"
    export SLACK_SIGNING_SECRET="your-signing-secret-here"
    
    make helm-install NAMESPACE=<your-namespace> \
      LLM=llama-4-scout-17b-16e-w4a16 \
      LLM_ID=llama-4-scout-17b-16e-w4a16 \
      LLM_URL=<llm-url>  \
      LLM_API_TOKEN=<your-api-token>
    ```

3. **Option 3: Deploy without Slack integration**

    Deploy without Slack support:

    ```bash
    make helm-install NAMESPACE=<your-namespace> \
      LLM=llama-4-scout-17b-16e-w4a16 \
      LLM_ID=llama-4-scout-17b-16e-w4a16 \
      LLM_URL=<llm-url>  \
      LLM_API_TOKEN=<your-api-token>
    ```

### Step 3: Connect Slack to Your Deployed Bot

Once the deployment is complete, you need to get the public URL and give it to Slack.

1.  **Get the Public URL from the Route:**

    ```bash
    oc get route <slack-service-chart-name> -n <your-namespace> -o jsonpath='{.spec.host}'
    ```

2.  **Configure Slack's Event Subscriptions:**

    - Go back to your Slack App's settings page and click on **"Event Subscriptions"**.
    - Enable the toggle at the top.
    - In the **Request URL** field, paste the host you got from the previous command and add `/slack/events` at the end. It should look like this:
      `<route-url>.../slack/events`
    - Under **"Subscribe to bot events"**, add the following events:
      - `message.im`
    - You sould see that the URL is verified
    - Go to OAuth & Permissions to reinstall the Bot to the workspace

3.  **Configure Slash Commands:**

    - In the app's settings, go to **"Features"** > **"Slash Commands"** in the left sidebar.
    - Click **"Create New Command"** button.
    - Input the command information:
      - **Command:** `/reset`
      - **Request URL:** `<route-url>.../slack/events` (use the same URL from step 1)
      - **Short Description:** `Reset the current conversation session`
    - Click **"Save"** button.

4.  **Save your changes.**

### Step 4: Add the Bot to a Channel

1.  Search in apps `Your-Bot-Name` to add the bot.
2.  Start a conversation with the bot.

## Local Development (Optional)

For testing on your local machine without deploying to a cluster.

1.  **Run dependent services** (`ollama`, `llamastack`) as described in the `asset-manager` README.
2.  **Build the `slack-service` image:**
    ```bash
    podman build -t slack-service -f slack-service/Containerfile .
    ```
3.  **Run the container:**
    ```bash
    podman run -d \
      --name slack-bot \
      -p 3000:8000 \
      -e SLACK_BOT_TOKEN="xoxb-your-bot-token-here" \
      -e SLACK_SIGNING_SECRET="your-signing-secret-here" \
      -e LLAMASTACK_SERVICE_HOST="127.0.0.1" \
      slack-service
    ```
4.  **Use `ngrok` to get a public URL:**
    ```bash
    ngrok http 3000
    ```
5.  Use the public `ngrok` URL in your Slack App's **Request URL** field.

## API Reference

### Endpoints

- `POST /slack/events`: Handles all incoming events and interactions from Slack.
- `GET /health`: A health check endpoint for Kubernetes liveness and readiness probes.

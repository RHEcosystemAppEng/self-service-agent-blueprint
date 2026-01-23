# Llama-4-Scout-17B-16E Journey

The it-self-service-agent quickstart supports the [meta-llama/Meta-Llama-3-70B](https://huggingface.co/meta-llama/Meta-Llama-3-70B)
model by default for both the small and big prompting approaches. Unfortunately the resources to host this model are significant enough
to pose a challenge for some.

Smaller models pose greater challenges with respect to tool calling, the use of knowledge bases and with reasoning in general and
are not as suitable for a multi-turn agentic workflow. However, we wanted people to be able to experience the it-self-service-agent quickstart
with a smaller model even if the experience will not be as good and not all aspects of the quickstart could be exercised.

This document takes you through the journey when using the [Llama-4-Scout-17B-16E](https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E)
model. Some of the limitations include:

* Only the small prompting approach can be used. There is a version of the small prompt
  [lg-prompt-small-scout.yaml](https://github.com/rh-ai-quickstart/it-self-service-agent/blob/main/agent-service/config/lg-prompts/lg-prompt-small-scout.yaml)
  which has been tweaked for better behavior with Llama-4-Scout-17B-16E.
* The current integration with PromptGuard does not work with the small prompt approach. This is because
  the requests crafted by the small prompt approach are sent to the model versus the raw user requests and the
  crafted requests are often flagged by the safety models as unsafe. This is an area for future investigation for us even though
  the small prompt approach makes the agent more resistant to prompt injection style attacks
* The agent may be slower and less consistent in its responses. Slower as more retries may be needed to complete tool calls and
  knowledge base lookups and less consistent due to the generally lower capability of the smaller model.

## Requirements

The requirements are the same as specified in the main [README.md](../../README.md#requirements),
except that Llama-4-Scout-17B-16E is substituted for Meta-Llama-3-70B.

## Deploy

This section walks you through deploying and testing the laptop refresh agent on OpenShift.

### Clone the repository

First, get the repository URL by clicking the green **Code** button at the top of this page, then clone and navigate to the project directory:

```bash
# Clone the repository
git clone https://github.com/rh-ai-quickstart/it-self-service-agent.git

# Navigate to the project directory (directory name matches repository name)
cd it-self-service-agent
```

**Expected outcome:**
- ✓ Repository cloned to local machine
- ✓ Working directory set to project root

### Deploy to OpenShift

#### Step 1: choose your deployment mode

For first deployment, we recommend **Testing Mode (Mock Eventing)**:
- No Knative operators required
- Tests event-driven patterns
- Simpler than production infrastructure

For detailed information about deployment modes, see the [Deployment Mode Guide](guides/DEPLOYMENT_MODE_GUIDE.md).

#### Step 2: set required environment variables


```bash
# Set your namespace
export NAMESPACE=your-namespace

# Set LLM configuration
export LLM=llama-4-scout-17b-16e-w4a16
export LLM_ID=llama-4-scout-17b-16e-w4a16
export LLM_API_TOKEN=your-api-token
export LLM_URL=https://your-llm-endpoint/v1
export LG_PROMPT_LAPTOP_REFRESH=/app/agent-service/config/lg-prompts/lg-prompt-small-scout.yaml

# Set hugging face token, set to 1234 as not needed unless
# you want to use locally hosted LLM
export HF_TOKEN=1234

```

Setting LG_PROMPT_LAPTOP_REFRESH as shown above ensures that we are using the small prompt approach
tuned for Llama-4-Scout-17B-16E.

#### Step 3: build container images (optional)

If using pre-built images, which is recommended until later steps, **skip this step**.

```bash
# Build all images
# Set container registry. Make sure this is set when you run
# helm-install-test in later steps
export REGISTRY=quay.io/your-org

make build-all-images

# Push to registry
make push-all-images
```

**Expected outcome:** All images built and pushed to registry

#### Step 4: deploy with Helm

```bash
# Login to OpenShift
oc login --server=https://your-cluster:6443

# Create namespace if needed
oc new-project $NAMESPACE

# Deploy in testing mode (Mock Eventing)
make helm-install-test NAMESPACE=$NAMESPACE
```

**Expected outcome:**
- ✓ Helm chart deployed successfully
- ✓ All pods running
- ✓ Routes created

#### Step 5: verify deployment

```bash
# Check deployment status
make helm-status NAMESPACE=$NAMESPACE

# Check pods
oc get pods -n $NAMESPACE

# Check routes
oc get routes -n $NAMESPACE
```

**Expected outcome:**
- All pods in Running state
- Routes accessible
- Agent service initialization completed successfully

**You should now be able to:**
- ✓ Deploy the system to OpenShift
- ✓ Monitor pods and services
- ✓ Troubleshoot deployment issues

---

### Interact with the CLI


Follow the same steps in the main [README.md](../../README.md#interact-with-the-cli)
for interacting with the CLI then return to this flow.

---

### Integration with Slack (optional)

Follow the same steps in the main [README.md](../../README.md#integration-with-slack-optional)
for integration with Slack then return to this flow.

---

### Integration with real ServiceNow (optional)

Follow the same steps in the main [README.md](../../README.md#integration-with-real-servicenow-optional)
for integration with ServiceNow then return to this flow.

---

### Integration with email (optional)


Follow the same steps in the main [README.md](../../README.md#integration-with-email-optional)
for integration with email then return to this flow.

---

### Run evaluations

The evaluation framework validates agent behavior against business requirements and quality metrics. Generative AI agents are non-deterministic by nature, meaning their responses can vary across conversations even with identical inputs. Multiple different responses can all be "correct," making traditional software testing approaches insufficient. This probabilistic behavior creates unique challenges:

- **Sensitivity to Change**: Small changes to prompts, models, or configurations can introduce subtle regressions that are difficult to detect through manual testing
- **Business Requirements Validation**: Traditional testing can't verify that agents correctly follow domain-specific policies and business rules across varied conversations
- **Quality Assurance Complexity**: Manual testing is time-consuming and can't cover the wide range of conversation paths and edge cases
- **Iterative Development**: Without automated validation, it's difficult to confidently make improvements without risking regressions

The evaluation framework addresses these challenges by combining predefined test conversations with AI-generated scenarios, applying metrics to assess both conversational quality and business process compliance. This was a crucial tool in the development of this quickstart, enabling PR validation, model comparison, prompt evaluation, and identification of common conversation failures.

This section walks you through generating conversations with the deployed system and evaluating them. More detailed information on the evaluation system is in the [Evaluation Framework Guide](guides/EVALUATIONS_GUIDE.md).

#### Step 1: configure evaluation environment

Start by setting up your environment with the references to the LLM that will be used for evaluation. In most
cases you will need to use a model which is as strong or stronger than the model used for the agent.
In the Llama-4-Scout-17B-16E journey you can run evaluations, however, the Llama-4-Scout-17B-16E is not
"strong" enough to catch many of the common failures in the laptop-refresh conversations. We'll cover
that in more detail in later sections.

The LLM_XXX environment variables should already have been set in the earlier steps:

```bash
cd evaluations/

# Set LLM endpoint for evaluation (can use different model than agent)
export LLM_API_TOKEN=your-api-token
export LLM_URL=https://your-evaluation-llm-endpoint
export LLM_ID=llama-4-scout-17b-16e-w4a16

uv venv
source .venv/bin/activate
uv sync
```

#### Step 2: run predefined conversation flows

Execute the predefined conversation flows against your deployed agent:

```bash
# Run predefined conversations
python run_conversations.py --reset-conversation
```

This runs the pre-defined conversations in [evaluations/conversations_config/conversations/](evaluations/conversations_config/conversations/).

**Expected outcome:**
- ✓ Conversations executed against deployed agent
- ✓ Results saved to `results/conversation_results/`
- ✓ Files like `success-flow-1.json`, `edge-case-ineligible.json`

Review a conversation result:
```bash
cat results/conversation_results/success-flow-1.json
```

You should see the complete conversation with agent responses at each turn. This is how you can test conversation flows
that can be defined in advance.

#### Step 3: generate synthetic test conversations

In addition to pre-defined flows we want to be able to test conversations with more variability.
Create additional test scenarios using the conversation generator (generate.py):

```bash
# Generate 5 synthetic conversations
python generator.py 5 --max-turns 20 --reset-conversation
```

**Expected outcome:**
- ✓ 5 generated conversations saved to `results/conversation_results/`
- ✓ Diverse scenarios with varied user inputs

#### Step 4: evaluate all conversations

Run the evaluation metrics against all conversation results:

```bash
# Evaluate with business metrics
python deep_eval.py
```

**Expected outcome:**
- ✓ Each conversation evaluated against 15 metrics
- ✓ Results saved to `results/deep_eval_results/`
- ✓ Aggregate metrics in `deepeval_all_results.json`

#### Step 5: review evaluation results

The results were displayed on the screen at the end of the run and are
also stored in results/deep_eval_results/deepeval_all_results.json.

```bash
# View evaluation summary
cat results/deep_eval_results/deepeval_all_results.json
```

**Key metrics to review:**

Standard Conversational Metrics:
- **Turn Relevancy**: Are responses relevant to user messages? (Threshold: > 0.8)
- **Role Adherence**: Do agents stay within their roles? (Threshold: > 0.5)
- **Conversation Completeness**: Were all user requests addressed? (Threshold: > 0.8)

Laptop Refresh Process Metrics:
- **Information Gathering**: Did agent collect required data? (Threshold: > 0.8)
- **Policy Compliance**: Did agent follow 3-year refresh policy correctly? (Threshold: > 0.8)
- **Option Presentation**: Were laptop options shown correctly? (Threshold: > 0.8)
- **Process Completion**: Were tickets created successfully? (Threshold: > 0.8)
- **User Experience**: Was agent helpful and clear? (Threshold: > 0.8)

Quality Assurance Metrics:
- **Flow Termination**: Does conversation end properly? (Threshold: > 0.8)
- **Ticket Number Validation**: ServiceNow format (REQ prefix)? (Threshold: 1.0)
- **Correct Eligibility Validation**: Accurate 3-year policy timeframe? (Threshold: 1.0)
- **No Errors Reported**: No system problems? (Threshold: 1.0)
- **Correct Laptop Options for Location**: All region-specific models presented? (Threshold: 1.0)
- **Confirmation Before Ticket Creation**: Agent requests approval before creating ticket? (Threshold: 1.0)
- **Return to Router After Task Completion**: Proper routing when user says no? (Threshold: > 1.0)

Each of these metrics is defined in [evaluations/get_deepeval_metrics.py](evaluations/get_deepeval_metrics.py). Metrics tell a judge LLM how to evaluate the conversation. As an example:

```python
        ConversationalGEval(
            name="Policy Compliance",
            threshold=0.8,
            model=custom_model,
            evaluation_params=[TurnParams.CONTENT, TurnParams.ROLE],
            evaluation_steps=[
                "First, review the laptop refresh policy in the additional context below to understand the eligibility criteria. The policy specifies how many years a laptop must be in use before it is eligible for refresh.",
                "Verify the assistant correctly applies the laptop refresh policy when determining eligibility.",
                "If the agent states the laptop age (e.g., '2 years and 11 months old', '5 years old', '3.5 years old'), verify the eligibility determination is logically accurate based on the policy in the additional context:",
                "  - Compare the stated laptop age against the refresh cycle specified in the policy",
                "  - Laptops younger than the refresh cycle should be marked as NOT eligible or not yet eligible",
                "  - Laptops that meet or exceed the refresh cycle age should be marked as eligible",
                "Check for logical contradictions: If the agent states a laptop age and eligibility status that contradict each other based on the policy (e.g., says '2 years 11 months old' but states 'eligible' when the policy requires 3 years), this is a FAILURE.",
                "Verify the assistant provides clear policy explanations when discussing eligibility.",
                f"\n\nadditional-context-start\n{default_context}\nadditional-context-end",
            ],
        ),
```

When metrics fail, the rationale for the failure will be explained by the judge LLM. An easy way to see an example of this is to run

```
python evaluate.py --check
```

which runs known bad conversations to validate that they are flagged as bad by the metrics. The known bad conversations are in
[evaluations/results/known_bad_conversation_results/](evaluations/results/known_bad_conversation_results). An example of a failure
would be:

```bash
   ⚠️ wrong_eligibility.json: 1/15 metrics failed (as expected: False)
      Failed metrics:
        • Policy Compliance [Conversational GEval] (score: 0.000) - The conversation completely fails to meet the criteria because the assistant incorrectly determines the user's eligibility for a laptop refresh, stating the laptop is eligible when it is only 2 years and 11 months old, which is less than the 3-year refresh cycle specified in the policy.

```

Running python evaluate.py --check validates that your model is strong enough to catch the cases covered by the metrics.
Since we are using Llama-4-Scout-17B-16E in this journey you will notice that Scout is not strong enough to catch all of the
failing conversations.

```text
📊 CONVERSATION SUMMARY:
   • Total conversations: 11
   • Passing conversations: 4
   • Failing conversations: 7

✅ PASSING CONVERSATIONS:
   • missing-laptop-details.json: 15/15 metrics passed (100.0%)
   • no-ticket-number.json: 15/15 metrics passed (100.0%)
   • not-all-laptop-options.json: 15/15 metrics passed (100.0%)
   • wrong_eligibility.json: 15/15 metrics passed (100.0%)

❌ FAILING CONVERSATIONS:
   • allowed_invalid_user-laptop-selection.json: 7/15 metrics failed (46.7%)
   • bad_laptop_options.json: 1/15 metrics failed (6.7%)
   • did-not-confirm-service-now-creation.json: 1/15 metrics failed (6.7%)
   • fail-route-back-to-router.json: 1/15 metrics failed (6.7%)
   • incomplete.json: 1/15 metrics failed (6.7%)
   • missing_laptop_options2.json: 1/15 metrics failed (6.7%)
   • wrong-selection.json: 2/15 metrics failed (13.3%)

🎉 OVERALL RESULT: 7/11 KNOWN BAD CONVERSATIONS FAILED AS EXPECTED
```

So while we can run the evaluations, some failures would not be identified. This illustrates that often
you will need a stronger model for evaluations than you may need for the agent, particularly if you are using the small prompt
approach.

#### Step 6: run complete evaluation pipeline

In the earlier steps we ran each of the evaluation components on their own. Most often we want to run the full pipeline
on a PR or after having made significant changes. You can do this with evaluate.py.

Run the full pipeline in one command (this will take a little while):

```bash
# Complete pipeline: predefined + generated + evaluation
python evaluate.py --num-conversations 5 --reset-conversation
```

**Expected outcome:**
- ✓ Predefined flows executed
- ✓ 5 synthetic conversations generated
- ✓ All conversations evaluated
- ✓ Comprehensive results report with aggregate metrics
- ✓ Identification of failing conversations for debugging


The [Makefile](Makefile) includes a number of targets that can be used to run evaluations either on PRs or on a scheduled basis:

```bash
# Run a quick evaluation with 1 synthetic conversation
make test-short-resp-integration-request-mgr

# Run evaluation with 20 synthetic conversations
make test-long-resp-integration-request-mgr

# Run evaluation with 4 concurrent sessions for a total of 40 synthetic conversations
make test-long-concurrent-integration-request-mgr
```

These targets automatically:
- Set up the evaluation environment
- Run predefined conversations
- Generate synthetic conversations (1, 20, or 40 depending on target)
- Execute all evaluation metrics
- Display results with pass/fail status

**You should now be able to:**
- ✓ Execute evaluation pipelines
- ✓ Generate synthetic test conversations
- ✓ Evaluate agent performance with business metrics
- ✓ Identify areas for improvement
- ✓ Validate agent behavior before production deployment
- ✓ Catch regressions when updating prompts or models
- ✓ Configure your CI to run evaluations

---

### Follow the flow with tracing

Follow the same steps in the main [README.md](../../README.md#follow-the-flow-with-tracing)
for following the flow with tracing then return to this flow.

---

### Trying out smaller prompts

In the Llama-4-Scout-17B-16E journey we are already using the [multi-part prompt](agent-service/config/lg-prompts/lg-prompt-small-scout.yaml) in which each of the prompts are more limited instead of the [large prompt](agent-service/config/lg-prompts/lg-prompt-big.yaml) which handles the full conversation flow. A multi-part prompt gives you more control over the flow, may be able to be run with a smaller model and may require fewer tokens (due to the smaller prompts being sent to the model). On the other hand it may be less flexible and may only handle flows that you have planned for in advance. You can read more about the advantages and disadvantages of the two approaches in the [Prompt Configuration Guide](guides/PROMPT_CONFIGURATION_GUIDE.md).

While we can't try it out since Llama-4-Scout-17B-16E cannot support the big prompt approach, we'll cover what differences you might
see between the big and small prompt approaches.

**Behavioral Differences:**

While the conversation may seem similar when using the two prompts, the multi-part prompt is more tightly controlled. For example, if you ask a random question it will be handled within the confines of the known states.

**Multi-part prompt example:**
```
User: what is the fastest bird in the world
Agent: Please let me know if you'd like to proceed with reviewing the available laptop options (yes/no).
```

**Big prompt example:**
```
User: what is the fastest bird in the world
Agent: I'm happy to help you with your question, but I specialize in laptop refresh and replacement requests. If you'd like to know more about the fastest bird in the world, I can offer to send you back to the routing agent who can connect you with the right specialist. Would you like me to do that?
```

With the big prompt, we had to specifically instruct it not to answer random questions, whereas the multi-part prompt naturally stays within its defined states.

**Cost Comparison:**

Another important consideration is token usage and cost. The multi-part prompt uses fewer total tokens since each individual prompt sent to the model is smaller, although it makes more requests to the LLM as it flows through different states.

As an example, these are the token count for an evaluation run with 20 generated conversations using the small prompt approach:

```
App Tokens (from chat agents):
  Input tokens: 180,043
  Output tokens: 35,818
  Total tokens: 215,861
  API calls: 326
```

Similarly, these are the token count for an evaluation run with 20 generated conversations using the big prompt approach:
```
 App Tokens (from chat agents):
  Input tokens: 630,648
  Output tokens: 31,282
  Total tokens: 661,930
  API calls: 154
```

As you can see, the big prompt approach uses almost 3.5 times as many input tokens as the small prompt approach. They both use a
similar number of output tokens. This makes sense since they provide similar responses to the end user and pull similar
information from the knowledge bases and MCP servers.

On the other hand, you can see that the small prompt made 2.1 times as many requests (API calls).

---

### Setting up PromptGuard (optional)

The current PromptGuard implementation does not work with the small prompting approach and since the Llama-4-Scout-17B-16E
cannot support the big prompt approach we are not able to experiment with PromptGuard in this journey. You may still want to
read through the PromptGuard section in the main
[README.md](../../README.md#setting-up-promptguard-optional)
even though you cannot follow the steps outlined.

---
### Setting up safety shields (optional)

Follow the same steps in the main [README.md](../../README.md#setting-up-safety-shields-optional)
for setting up Safety shields then return to this flow.

---

### Recommended next steps

**For Development Teams:**
1. Review the [Contributing Guide](docs/CONTRIBUTING.md) for development setup and workflow
2. Explore the component documentation in [Going deeper: component documentation](#going-deeper-component-documentation) for deeper technical details
3. Review the evaluation framework to understand quality metrics
4. Experiment with customizing the laptop refresh agent prompts
5. Set up observability and monitoring for your deployment

**For Organizations Planning Production Deployment:**
1. Plan your transition from testing mode to production mode (Knative Eventing)
2. Identify your first use case for customization
3. Establish evaluation criteria and quality metrics for your use case
4. Plan integration with your existing IT service management systems

**For Customizing to Your Use Case:**
1. Review the laptop refresh implementation as a reference in the [Component Guide](guides/COMPONENT_GUIDE.md)
2. Start with agent configuration and knowledge base development
3. Build MCP servers for your external systems
4. Develop use-case-specific evaluation metrics

---

### Delete

You can stop the deployed quickstart by running:

```bash
make helm-uninstall NAMESPACE=$NAMESPACE
```

This will remove all deployed services, pods, and resources from your namespace.


---

## Technical details

### Performance & scaling

The Self-Service Agent quickstart is designed for scalability using standard Kubernetes and cloud-native patterns. All core components can be scaled using familiar Kubernetes techniques—horizontal pod autoscaling, replica sets, and resource limits—without requiring custom scaling logic or architectural changes.

**Component Scaling:** The quickstart's services follow standard cloud-native design principles. The services can scale both vertically (multiple uvicorn workers per pod) and horizontally (multiple pod replicas) to handle increased load. MCP servers specifically use stateless streaming HTTP so that they can scale in the same way (unlike the Server-Sent Events transport whose state limits how you can scale).

**Infrastructure Scaling:** For supporting infrastructure components, apply industry-standard scaling techniques. PostgreSQL databases can leverage connection pooling, read replicas, and vertical scaling following standard PostgreSQL best practices. When using production mode with Knative Eventing, Apache Kafka benefits from standard Kafka scaling strategies including partitioning, consumer groups, and multi-broker clusters. These are well-documented patterns with extensive ecosystem support.

**Performance Optimization:** Analysis of some evaluation runs shows that 99.7% of request processing time is spent in Llama Stack inference, with the request-manager and event delivery adding only negligible overhead (~12ms total). This means performance optimization efforts should focus primarily on LLM inference scaling—using GPU acceleration to start and selecting appropriately-sized models. The quickstart's architecture ensures that scaling Llama Stack directly translates to end-to-end performance improvements without infrastructure bottlenecks.

For comprehensive scaling guidance, detailed performance characteristics, component-by-component scaling analysis, configuration examples for different deployment sizes, and links to Red Hat and Llama Stack documentation, see the **[Performance and Scaling Guide](guides/PERFORMANCE_SCALING_GUIDE.md)**.

---

### Security

Security is a key aspect of production deployments. While this quickstart works to avoid common security issues, the security requirements and
implementation will often be specific to your organization. A few aspects that you will need to extend the quickstart if/when you use it in production
would include:

1. **Management of sensitive information in logs and traces**: The quickstart does not currently redact information from logs or traces. This means
that you will either need to manage access to traces and logs to account for potentially sensitive information like employee name and email address
or extend it to redact information based on your organizations policies.
2. **Credential management**: Credentials are set in the quickstart in order to make it easy for people to get started and easily deploy the quickstart.
When deploying to production you will need to manage credentials in accordance with your organizations requirements including potentially managing
them through vaults and planning for credential rotation. For enhanced security, you should consider managing project-managed secrets (Slack, HuggingFace,
ServiceNow, HR) by creating Kubernetes secrets beforehand instead of passing them via Helm `--set` flags, which avoids exposure in shell history and
Helm release history. These more advanced techniques are not covered in the quickstart.
3. **Database, Kafka configuration**: Production configuration and security hardening for components like the database and Kafka, are not covered
as they will often be existing components within an organization which have already been configured and hardened to meet the organizations requirements
for scaling and security.
4. **Network security**: While access to pods within the deployment has been restricted by network policy to only other pods within the deployment
namespace with the exception of the kafka namespace and the route which allows slack to communicate with the deployment,
you should review and apply any standard network policies that your organization has for OpenShift deployments.

---

### Going deeper: component documentation

Now that you have the system running, you can dive deeper into specific components and concepts.

For detailed component information, see the [Component Guide](guides/COMPONENT_GUIDE.md).

#### Guides

Step-by-step guides for integrations, deployment, and advanced features:

- [Component Overview](guides/COMPONENT_GUIDE.md) - Comprehensive guide to all system components
- [Deployment Modes](guides/DEPLOYMENT_MODE_GUIDE.md) - Understanding testing vs production deployment modes
- [Prompt Configuration](guides/PROMPT_CONFIGURATION_GUIDE.md) - Agent prompt engineering guide
- [Evaluation Framework](guides/EVALUATIONS_GUIDE.md) - Comprehensive evaluation framework documentation
- [Slack Integration](guides/SLACK_SETUP.md) - Set up Slack integration
- [Email Integration](guides/EMAIL_SETUP.md) - Configure email integration
- [ServiceNow Setup (Automated)](guides/SERVICE_NOW_BOOTSTRAP_AUTOMATED.md) - Automated ServiceNow configuration
- [ServiceNow Setup (Manual)](guides/SERVICE_NOW_BOOTSTRAP_MANUAL.md) - Manual ServiceNow configuration
- [Safety Shields](guides/SAFETY_SHIELDS_GUIDE.md) - Content moderation and safety configuration
- [Performance & Scaling](guides/PERFORMANCE_SCALING_GUIDE.md) - Scaling guidance and best practices
- [Authentication](guides/AUTHENTICATION_GUIDE.md) - Authentication patterns and configuration
- [Integration Development](guides/INTEGRATION_GUIDE.md) - Building custom integrations

#### Technical documentation

Detailed technical documentation for developers:

- [Tracing Implementation](docs/TRACING_IMPLEMENTATION.md) - OpenTelemetry tracing details
- [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAMS.md) - System architecture diagrams
- [API Reference](docs/API_REFERENCE.md) - API documentation
- [Contributing Guide](docs/CONTRIBUTING.md) - Development setup and contribution guidelines
- [Development Guidelines](docs/GUIDELINES.md) - Code standards and best practices

---

**Thank you for using the Self-Service Agent Quickstart!** We hope this guide helps you successfully deploy AI-driven IT process automation in your organization.

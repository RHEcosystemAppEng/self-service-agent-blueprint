# Test Scripts for Self-Service Agent

Simple scripts that we can use to test out pieces as we build
up the initial functionality

To run in pod using terminal you mus use 

```
/app/.venv/bin/python XXX
```

where XXX is the script name


## test.py

Simple script that validates we can:
* connect to Llama Stack
* List the registered models
* Make a simple request to an agent

## chat.py

Simple command line chat interface. It can be run after
the helm deploy completes by using:

```
kubectl exec -it deploy/self-service-agent -- python /app/test/chat.py
```

## chat-request-mgr.py

Command line chat interface that uses the Request Manager API
for agent mode (LlamaStack-based) conversations. Run with:

```bash
# Using environment variables
REQUEST_MANAGER_URL=https://your-request-manager \
USER_ID=your-user-id \
python test/chat-request-mgr.py

# Or with command line arguments
python test/chat-request-mgr.py --user-id your-user-id --request-manager-url https://your-request-manager
```

## chat-responses-request-mgr.py

Command line chat interface that uses the Request Manager API
for responses mode (LangGraph-based) conversations. This provides
advanced conversation management with persistent threads. Run with:

```bash
# Using environment variables
REQUEST_MANAGER_URL=https://your-request-manager \
USER_ID=your-user-id \
python test/chat-responses-request-mgr.py

# Or with command line arguments
python test/chat-responses-request-mgr.py --user-id your-user-id --request-manager-url https://your-request-manager --debug
```

### Features
- **LangGraph State Machine**: Advanced conversation management
- **Persistent Threads**: Conversation state maintained across sessions
- **Debug Mode**: Detailed logging and response information
- **Session Management**: Automatic session and thread handling
- **Interactive Mode**: Full conversation testing
- **Test Mode**: Automated testing for CI/CD

## chat-responses.py

Legacy responses mode test client (deprecated in favor of chat-responses-request-mgr.py).

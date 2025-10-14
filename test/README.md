# Scripts used by eval framework to test conversation flows

To run in pod using terminal you mus use 

```
/app/.venv/bin/python XXX
```

where XXX is the script name

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

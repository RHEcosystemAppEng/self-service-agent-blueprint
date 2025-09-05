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

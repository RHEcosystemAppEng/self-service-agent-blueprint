# Test Scripts for Self-Service Agent

Simple scripts that we can use to test out pieces as we build
up the initial functionality


## test.py

Simple script that validates we can:
* connect to Llama Stack
* List the registered models
* Make a simple request to an agent

## chat.py

Simple command line chat interface. It can be run after
the helm deploy completes by using:

```
oc exec -it deploy/self-service-agent -- python /app/test/chat.py
```

# Transitional test files

Simple scripts that we can use to test out pieces as we build
up the initial functionality

Must be run using python in:

```
/app/.venv/bin/python
```

## test.py

Simple script that validates we can:
* connect to Llama Stack
* List the registered models
* Make a simple request to an agent

## chat.py

Simple command line chat interface. It can be run after
the helm deploy completes by using:

```
oc exec -it deploy/self-service-agent -- python test/chat.py
```

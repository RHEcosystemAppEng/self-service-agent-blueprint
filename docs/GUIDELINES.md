# AI self-service IT Agent - Standard Processes and Practices
## Code Practices

### Python
#### Code Formatting/Hygiene

- All python code should be formatted using black
- All code be clean based on running flake8 with this config
- Follow PEP 8 style guidelines
- Use type hints for function parameters and return values
- Document functions and classes with docstrings

`black` and `flake8` should be added as development dependencies to the project, then they should be run locally to format and check the code.

Every time you want to format and check the code:
- `uv run black .`
- `uv run flake8 .`

### Project structure
For each kickstart/blueprint there will be a single GitHub repository. Different modules will be managed through the use of subdirectories.
Common components are an exception to this and re-use of components in architecture-charts is both desirable and expected.

#### Module structure
- UV is a fast Python package manager and workflow tool. 
- At the moment it seems to be state of the art for project packaging and virtual environment management. 
- The recommended project structure is similar to modern Python packaging best practices, with a clear separation between your source code and project configuration:

```
your-module/
└───src/
│   └───your_package/
│       │   __init__.py
│       │   ... (main code)
└───tests/ (optional)
│   └───... (test code)
│   pyproject.toml
│   README.md (optional)
│   uv.lock
```

- Each module (for instance backend, frontend, core, util, …) will be contained in a different directory of the root source code project directory.
- **Note on Containerfiles**: This project uses centralized Containerfile templates at the repository root (`Containerfile.services-template`, `Containerfile.mcp-template`) rather than individual Containerfiles per module. The Makefile build system uses these templates with build arguments to create images for each module.
- Some references:
  - [Python project structures](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
  - [UV project structures](https://docs.astral.sh/uv/guides/projects/)
  - [UV application package](https://docs.astral.sh/uv/concepts/projects/init/#packaged-applications)

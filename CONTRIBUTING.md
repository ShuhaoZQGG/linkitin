# Contributing to linkit

Thank you for your interest in contributing!

## Getting Started

1. Fork the repository and clone your fork.
2. Create a virtual environment and install dev dependencies:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

3. Create a feature branch: `git checkout -b my-feature`

## Running Tests

```sh
python -m pytest tests/
```

## Code Style

- Follow existing code patterns
- Keep functions focused and small
- Add type hints to new code
- Do not commit cookie files or credentials

## Submitting a Pull Request

1. Ensure all tests pass
2. Update `README.md` if you add new public API methods
3. Open a PR with a clear description of the change

## Reporting Issues

Open a GitHub issue with steps to reproduce, expected behavior, and actual behavior.
macOS version and Chrome version are helpful when reporting authentication issues.

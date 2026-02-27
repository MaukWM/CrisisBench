Ensure pre-commit is run when you are done making changes with

```bash
uv run pre-commit run ...
```

Fix any mypy issues immediately if issues arise in pre-commit. Audit issues should be raised with the developer.

When creating __init__ files for modules, never define __all__ import simplifications, just import other files the way they are.

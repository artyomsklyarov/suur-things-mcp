"""`python -m suur_things_mcp` — same entry point as the console script.

Exists so the launchd service fallback (`<python> -m suur_things_mcp dashboard
--no-open`) works when no `uvx` binary is available.
"""

from .server import main

if __name__ == "__main__":
    main()

# services/mcp

Diocle as an [MCP](https://modelcontextprotocol.io) server, so any coding agent can have its COBOL-to-Java conversion checked against the original. No model calls here: the agent brings its own Java, and GnuCOBOL decides.

| Tool | Does |
|---|---|
| `analyze_cobol(source)` | Programs, input/output files, record layouts derived from copybooks, and legacy-arithmetic findings. `source` is a directory or an allowed GitHub URL. |
| `verify_conversion(legacy, program, java_dir, main_class?, cases?, seed?)` | Runs the COBOL (GnuCOBOL 3.2) and the Java on the same generated inputs; returns mismatched fields and example diffs. |
| `certify_conversion(legacy, program, java_dir, main_class?)` | 1,000 inputs from a secret random seed, revealed only in the result. |
| `cobol_lessons()` | The proven-lessons skill (`skills/cobol-to-java-semantics/SKILL.md`). |

The verify tools compile and execute the code you point them at. Run the server locally, for your own agent.

## Run

Needs GnuCOBOL 3.2 (`cobc`) and a JDK on the PATH.

```sh
cd services/mcp
python3 -m venv .venv && .venv/bin/pip install -e ../analyzer -e ../verifier -e '.[dev]'
.venv/bin/python -m pytest
```

Client configuration (any MCP client that launches stdio servers):

```json
{
  "mcpServers": {
    "diocle": {
      "command": "/path/to/Diocle/services/mcp/.venv/bin/python",
      "args": ["-m", "diocle_mcp.server"]
    }
  }
}
```

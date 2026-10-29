# Install Culture-Fit locally

Culture-Fit is a **Human-in-the-Loop (HITL)** dashboard for identifying when people need to intervene in agent collaboration and who has authority to decide. Download and extract the source ZIP to get a `culture-fit/` folder. You can run the local dashboard and MCP server from that folder. Data from the public web demo is not included.

## Choose a download

| Download | Contents | Use it when |
|---|---|---|
| `culture-fit-source.zip` | Python API, dashboard, MCP/A2A adapters, Skill, launchers, and public synthetic experiments | You want to run Culture-Fit on your computer |
| `culture-fit-skill.zip` | `arbiter-coordination/SKILL.md` and a Python helper that uses only the standard library | You want to connect an agent Skill to an existing Culture-Fit server |

The Skill ZIP does not include the dashboard server. Start the server from the full source package first. Neither ZIP includes personal databases, login credentials, Slack tokens, submission reports, videos, or screenshots.

## Prerequisites

You need an internet connection and `uv`. Follow the [official uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/) for your operating system, then reopen your terminal. If uv is missing, the launchers print the installation link and exit. They do not automatically run a remote installer.

The project requires Python 3.11 or newer. `uv sync --frozen` prepares the Python environment and dependencies using the supplied `uv.lock`. If a compatible Python installation is missing, uv may download one depending on its configuration. The first run can take a little longer.

## macOS

Open a terminal, change to the extracted folder, and run the launcher. Quote paths that contain spaces.

```bash
cd "/Users/your-name/Downloads/culture-fit"
bash ./start-macos.sh
```

The launcher locates the project relative to the script itself, so you can also run `bash "/absolute/path/culture-fit/start-macos.sh"` from another directory.

## Windows

Open PowerShell and change to the extracted folder.

```powershell
Set-Location -LiteralPath 'C:\Users\your-name\Downloads\culture-fit'
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-windows.ps1
```

The execution policy option applies only to that PowerShell process. If your organization's policy blocks the script, use the manual commands below or contact your administrator instead of changing the managed policy.

```powershell
uv sync --frozen
uv run --frozen python scripts/package_downloads.py
uv run --frozen uvicorn arbiter.app:app --host 127.0.0.1 --port 8787
```

The launcher uses syntax compatible with Windows PowerShell 5.1 and PowerShell 7. **Execution on Windows hardware has not yet been verified**; `pwsh` was unavailable in the development environment. The separate public deployment module, `arbiter.deployment`, uses Linux file locking. These local launchers run `arbiter.app`.

## Open the dashboard, stop the server, or change the port

Once the server starts, open **http://127.0.0.1:8787/workspace** in your browser. Keep the terminal open while using the dashboard and press `Ctrl+C` to stop it. The server listens only on your computer's loopback address by default.

If another program is using port 8787, choose a different port:

```bash
# macOS
ARBITER_PORT=8790 bash ./start-macos.sh
```

```powershell
# Windows
$env:ARBITER_PORT = '8790'
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-windows.ps1
```

Update the browser URL and your clients' API URL to `http://127.0.0.1:8790` as well. Local data is stored in the project's `.runtime/arbiter.sqlite3` by default. The download does not contain an existing database.

## Connect an agent through MCP

Keep the dashboard server running, then configure your agent's MCP client to launch the stdio server below. Use **absolute paths** for the uv executable and project folder, and pass each argument as a separate array item.

```json
{
  "mcpServers": {
    "culture-fit": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/culture-fit", "run", "--frozen", "python", "-m", "arbiter.mcp_server"],
      "env": {"ARBITER_API_URL": "http://127.0.0.1:8787"}
    }
  }
}
```

On Windows, replace the project path with a JSON-escaped path such as `C:\\Users\\your-name\\Downloads\\culture-fit`. If the client cannot find `uv`, replace `command` with the absolute path returned by `command -v uv` on macOS or `(Get-Command uv).Source` on Windows. Configuration formats vary between clients. Codex uses a `mcp_servers` TOML table, so follow its configuration format instead of pasting this JSON directly.

After connecting, instruct the agent to **register a conversation → record new messages → evaluate authority for the exact scope and action → query the next action**. Connecting MCP does not automatically collect Slack messages or other conversations. Record delegations, priority rules, and human decisions in the dashboard.

- [MCP connection and tool reference](mcp-connection.md)
- [OpenClaw Skill connection](openclaw-connection.md)
- [Slack receiver setup](slack-connection.md)
- [A2A connection](a2a-connection.md)

For the verified OpenClaw version, 2026.3.11, use Skill directory registration. Do not assume that version supports `mcp.servers` configuration. The connection guide explains how to extract the Skill ZIP and register its folder through `skills.load.extraDirs`.

## Additional setup by feature

| Feature | Additional setup |
|---|---|
| Synthetic scenarios, conversation import, and delegation/priority records | Start the local server |
| Live model briefs and Codex scenarios | Install and sign in to Codex CLI separately, with available model usage |
| MCP tool use by a real agent | Configure that agent's MCP connection and model access |
| Live Slack event reception | Install your Slack app and configure tokens, allowed channels, and Socket Mode |

Installing locally does not create external accounts or grant approval on an owner's behalf. Installation checks do not automatically call a model or send Slack messages. The public web demo provides an isolated synthetic example for each visitor; new model calls and live Slack reception are disabled there.

## Rebuild the downloads

Developers can rebuild both ZIP files from the project directory with the commands below. The packager uses only Python's standard library. It does not call a model or publish a release.

```bash
python scripts/package_downloads.py --list-only
python scripts/package_downloads.py
```

The outputs are `frontend/downloads/culture-fit-source.zip` and `frontend/downloads/culture-fit-skill.zip`. File lists and SHA-256 hashes are recorded in `.runtime/download-package-manifest.json`. The packager uses an explicit allowlist and never includes generated ZIPs inside another ZIP. Both launchers run this packaging step after preparing the environment, so the local download page can serve both files from an extracted source package. Rebuild the packages after changing the local API or UI to include those changes in the downloads.

## Build a Docker image

The supplied Dockerfile runs the public demo with an isolated synthetic sandbox for each visitor. The source ZIP excludes nested ZIP files, so **generate the downloads before building the Docker image**. This provides the files required by the Dockerfile's `COPY` instructions.

```bash
python scripts/package_downloads.py
docker build -t culture-fit .
```

If a `python` command is unavailable, prepare the environment and use `uv run --frozen python scripts/package_downloads.py`. See the [Railway deployment guide](railway-deployment.md) for persistent storage, visitor isolation, and HTTPS settings.

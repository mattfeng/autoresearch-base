# autoresearch-base

A small **uv-installable Python generator** that uses **Jinja2 templates** to
create a *second*, experiment-only Pi devcontainer inside an existing Git
repository. The main devcontainer remains untouched.

Designed to complement [mattfeng/devcontainer-base](https://github.com/mattfeng/devcontainer-base):
use that configurator for the regular development container, and use this
separate `configure-autoresearch` command for the `autoresearch/` folder.

## Generated architecture

```text
my-project/
├── .devcontainer/             # Existing, writable main development container
├── src/
├── pyproject.toml
└── autoresearch/
    ├── .devcontainer/
    │   ├── devcontainer.json   # Independent Pi devcontainer
    │   ├── Dockerfile
    │   ├── entrypoint.sh       # Root startup, then unprivileged node
    │   ├── init-firewall.py    # Fail-closed outbound firewall
    │   └── firewall-allowlist.txt # Hosts resolved at container startup
    ├── .pi/extensions/
    │   └── experiments.ts      # Pi: run/list/compare tools
    ├── experiments/
    │   ├── run.sh              # Logged shell-command execution entrypoint
    │   └── benchmark.py       # Optional executable smoke test
    ├── results/               # Only host-project writable output path for Pi
    ├── run-pi.sh              # Restricted Pi launcher
    ├── AGENTS.md              # Experiment instructions
    └── README.md
```

## Installation and setup

**To develop this project locally:**

```bash
cd autoresearch-base
uv sync --extra dev
uv run configure-autoresearch --workspace /path/to/my-project/autoresearch
```

**To run the generator directly with `uvx` from a local checkout:**

```bash
uvx --from /path/to/autoresearch-base configure-autoresearch \
  --workspace /path/to/my-project/autoresearch
```

**After you publish your fork on GitHub:**

```bash
uvx --from git+https://github.com/OWNER/autoresearch-base.git \
  configure-autoresearch --workspace ./autoresearch
```

Run the last command **from the parent repository's root**. The destination
folder can exist or be created by the generator, and must be an immediate child
of the repository. The tool does not need to find or modify the parent's
`.devcontainer/` directory.

Use `--dry-run` to inspect planned files. Rerunning preserves files whose
contents match the templates. It refuses to overwrite edited files without
`--force` (which replaces generated files).

## Next steps

1. Open `my-project/autoresearch` **as its own folder** in Visual Studio Code.
2. Choose **Dev Containers: Reopen in Container**. This builds a separate image.
3. Verify that `/project` and `/workspace/autoresearch` are read-only, while
   `/results` is writable (instructions in generated `README.md`).
4. Run the bundled smoke test:

   ```bash
   mkdir -p /results/manual-smoke
   bash experiments/run.sh /results/manual-smoke 'python3 /workspace/autoresearch/experiments/benchmark.py --project /project --output "$RUN_DIR" --seed 42'
   cat /results/manual-smoke/metrics.json
   ```

5. Configure Pi authentication and start `./run-pi.sh`. The custom Pi extension
   provides `run_experiment`, `list_experiments`, and `compare_experiments`.
6. Tell Pi which experiment file to use, for example: “Use `/project/experiment.py`;
   inspect its `--help` and run a small experiment.” No runner edits or prescribed
   CLI are needed. Customize the container runtime for your project's dependencies.

## Isolation boundaries

| Container path | Permissions | Purpose |
|---|---|---|
| `/project` | **Read-only bind mount** | Complete parent repository |
| `/workspace/autoresearch` | **Read-only bind mount** | Scripts, prompts, Pi extension |
| `/results` | **Read/write bind mount** | Host `autoresearch/results/` |
| `/home/node/.pi` | Persistent named volume | Pi authentication/settings/sessions |

The parent project is mounted from `${localWorkspaceFolder}/..`, so the folder
opened by Dev Containers must be `my-project/autoresearch`, not `my-project`.
The same physical `results` folder is reachable read-only via `/project` and
writable via `/results`. This is intentional.

The Pi launcher exposes file-browsing tools (`read`, `grep`, `find`, `ls`) and
the three custom experiment tools, with `--no-mcp` and an explicit extension
load. It does not expose Pi's built-in `bash`, `edit`, or `write` tools, but
`run_experiment` accepts arbitrary shell commands, including CLI `--help`.
This is general shell execution with logging, not a read-only tool boundary.
Commands start in a fresh `/results/<uuid>` directory, with `$RUN_DIR` exported
for output paths. Command text, timing, exit status, and logs are recorded.
`metrics.json` is optional; numeric metrics enable `compare_experiments`.

The experiment process receives a reduced environment that omits model API
credentials, and runs with a timeout. Project source and runner mounts are
read-only. Docker drops all capabilities except `NET_ADMIN`, `SETUID`, `SETGID`,
and `SETPCAP` needed by the root startup entrypoint. It installs the firewall,
then runs the container command as `node` with all capability bounding bits
dropped. Pi and experiment commands have no firewall capabilities or sudo.
No-new-privileges and a PID limit remain enabled; no Docker socket is mounted.
Container writable layers and Pi's persistent state still exist; only the
results mount writes back into the repository.

**Security caveats:** a read-only mount does not hide secrets in the repository,
and model-selected commands can still use allowed network services, read Pi's
persistent credentials, or write to container-private storage. A reduced
environment is not credential isolation. This is a practical source-protection
model, not a hostile-code sandbox. Do not expose sensitive credentials to commands.
GPU access is not enabled.

## Outbound firewall

The generated Pi container enables an outbound allowlist by default, covering
both Pi itself and all experiment commands. Root startup installs restrictive
IPv4 and IPv6 filter rules **before** resolving allowlisted hosts. Startup stops
if configuration or resolution fails, leaving restrictive rules in place.
The firewall allows loopback, inbound responses to permitted connections,
TCP/UDP DNS on port 53 to IPv4 nameservers in `/etc/resolv.conf`, and outbound
IPv4 TCP port 443 to the startup-resolved A records of allowlisted hosts.
Other outbound traffic is rejected; external IPv6 is blocked. Docker NAT rules
are preserved. There are no SSH, host-gateway, or broad GitHub CIDR exceptions.

Defaults cover Pi/model/auth (`api.anthropic.com`, `api.openai.com`,
`auth.openai.com`, `chatgpt.com`, `pi.dev`), packages (`registry.npmjs.org`,
`pypi.org`, `files.pythonhosted.org`), GitHub (`github.com`, `api.github.com`,
`raw.githubusercontent.com`, `objects.githubusercontent.com`), and editor
services (`marketplace.visualstudio.com`, `vscode.blob.core.windows.net`,
`update.code.visualstudio.com`), not blanket telemetry access.

To add a provider or dataset service, edit
`autoresearch/.devcontainer/firewall-allowlist.txt` **on the host or in your
regular development devcontainer**, then rebuild the Pi container. Use one
hostname per line; blank lines and comments are accepted. The image bakes the
allowlist and startup scripts into root-owned `/usr/local/lib/autoresearch/`;
editing a mounted copy does not change the active policy. The agent cannot
edit that policy or acquire firewall capabilities.

This is an IP allowlist, not domain-level security or total network isolation:
shared IPs can expose other services, permitted services can receive exfiltrated
data, and allowed DNS can carry exfiltration. Only IPv4 HTTPS is supported
externally; DNS address rotation requires a container restart to resolve again.
Image builds are not filtered by this runtime firewall. Commands can still read
accessible credential files; do not treat reduced environments as secret isolation.

For manual checks inside the Pi container, use `curl` if available:

```bash
curl --noproxy '*' --connect-timeout 10 -I https://api.openai.com
curl --noproxy '*' --connect-timeout 10 -I https://example.com
curl --noproxy '*' --connect-timeout 10 -6 -I 'https://[2606:4700:4700::1111]'
```

Any HTTP status from the first command establishes reachability (do not use
`-f`); the second and third should fail to connect. These are manual checks,
not a guarantee against the IP-sharing and exfiltration limitations above.

## Scientific experiments

The generated benchmark counts Python source files for a zero-dependency smoke
test. It is **not** a research metric. Real experiments should:

- use immutable evaluation data, fixed budgets, and correctness gates;
- direct temporary files, caches, checkpoints, logs, and plots to `/results`;
- record seeds, metrics, code revision, package versions, and hardware details;
- replicate promising runs to quantify measurement noise;
- reserve held-out validation for finalists rather than optimize directly on it.

If your main devcontainer has specialized dependencies, extend the generated
Pi Dockerfile with the same toolchain, or use the same runtime base image as
your main development container. The two containers do **not** automatically
share installed packages or Python virtual environments. `UV_CACHE_DIR` and
`UV_PROJECT_ENVIRONMENT` are set to writable locations under `/results`.

## Working on the generator

```bash
uv sync --extra dev
uv run pytest
```

Jinja2 templates live under `src/autoresearch_base/templates/`. The command-line
entry point is `configure-autoresearch` in `src/autoresearch_base/cli.py`.
Templates are included in the installed Python package.

## Upstream references

- [devcontainer-base](https://github.com/mattfeng/devcontainer-base)
- [Pi extension reference](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md)
- [Pi command-line options](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md)
- [Dev Container metadata reference](https://containers.dev/implementors/json_reference/)

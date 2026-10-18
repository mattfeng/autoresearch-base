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
    │   ├── init-node.py        # Initialize node's Pi settings, then exec command
    │   ├── pi-settings.json    # Model/thinking seed baked into the image
    │   └── firewall-allowlist.txt # Hosts resolved at container startup
    ├── results/               # Experiment outputs within the writable workspace
    ├── AGENTS.md              # Experiment instructions
    ├── .autoresearch.json     # Saved read-only selections and GPU choice
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

`--workspace` chooses the experiment folder; its parent must exist. The folder
must be nonexistent, empty (with no hidden entries either), or an existing
autoresearch workspace. Non-empty unrelated directories are rejected before
the picker opens, even with `--force` or `--dry-run`. Existing workspaces are
recognized by valid `.autoresearch.json` settings or their original generated
`AGENTS.md`/devcontainer layout.

There is no immediate-child-of-repository requirement, and the parent's
`.devcontainer/` is not modified.

By default, setup opens an interactive file browser with saved selections
prechecked. For a nonexistent or empty workspace, browsing starts in its
parent; existing autoresearch workspaces start inside themselves. Choose only
the files and directories experiments need—there is **no whole-parent mount
by default**.

For example, given `/host/project/math/` and `/host/project/pyproject.toml`:

```bash
configure-autoresearch --workspace /host/project/math-experiments
```

In the browser for a new workspace, use `ls`, `toggle math`, `toggle pyproject.toml`, then
`selected` to review and `done` to confirm. Optionally select `uv.lock` too.
The picker prints the exact host-to-container mapping:

| Selected host path | Container path |
|---|---|
| `/host/project/math` | `/project/math` |
| `/host/project/pyproject.toml` | `/project/pyproject.toml` |

Browser commands are `ls`, `up`, `cd NAME/INDEX/PATH`, `toggle INDEX/PATH`,
`select .` (select the current directory), `selected`, `done`, and `cancel`.
Navigate down with `cd` and back up with `up`; toggle either files or directories.
Enter a number list directly to toggle multiple entries: `1,3,5-8` selects
entries 1, 3, and 5 through 8. `toggle 1,3,5-8` does the same;
`select 1,3,5-8` only adds entries. Use no spaces within number lists.
Repeated or overlapping indices count once; invalid or out-of-range batches
leave the selection unchanged.
Selecting a directory exposes **all its descendants**, including secrets.
Symlinks resolve to their canonical sources; duplicate and covered selections
collapse. Selections outside the workspace's parent are supported, but shift
the common ancestor used for `/project` targets: review the displayed mapping.
Selecting nothing leaves `/project` empty.

Successful generation saves canonical, workspace-relative selections as
`read_only` and the GPU selection as a canonical string in `gpus` in
`.autoresearch.json`, keeping sibling paths portable when the tree moves.
The GPU string is `none`, `all`, or a comma-separated list of device identifiers.
On regeneration, legacy saved booleans migrate from `true` to `all` and `false`
to `none`; missing `gpus` defaults to `none`.
To bypass only the source picker, repeat `--read-only PATH`; relative paths are
resolved against the **workspace**, not the shell's working directory, and
override the saved list:

```bash
configure-autoresearch --workspace /host/project/math-experiments \
  --read-only ../math --read-only ../pyproject.toml
configure-autoresearch --workspace /host/project/math-experiments --non-interactive
```

Interactive setup asks for a GPU selection: `all`, `none`, or comma-separated
numeric indices or NVIDIA GPU UUIDs (`GPU-...` or `MIG-...` identifiers).
For example, `0,2` selects only those indices. Enter keeps the saved selection,
or `none` for a new configuration or settings without `gpus`; `cancel`, `quit`,
or `q` cancels setup. `--read-only` alone does not skip this prompt.
Pass `--gpus VALUE` to skip the GPU prompt and override the saved/default choice
in either mode. A value is required:

```bash
configure-autoresearch --workspace /host/project/math-experiments --gpus all
configure-autoresearch --workspace /host/project/math-experiments --gpus none
configure-autoresearch --workspace /host/project/math-experiments --gpus 0,2
configure-autoresearch --workspace /host/project/math-experiments --gpus GPU-uuid
```

`--non-interactive` skips all prompts, reuses saved selections and the saved GPU
choice (missing `gpus` means `none`), and requires a saved configuration unless
explicit `--read-only` choices are supplied. With explicit source choices and no
saved configuration, GPU access defaults to `none`.

Cancellation or EOF before generation writes nothing; no setup files or choices
are written until successful generation. `--dry-run` previews without writing,
including settings. Rerunning preserves matching generated files. After source
and GPU choices, interactive setup lists changed files and obsolete files and
asks before replacing/removing them (default: no). Declining or EOF writes nothing.
`--force` skips this confirmation; non-interactive updates still require `--force`.
Interactive `--dry-run` previews changes without asking for overwrite permission.

Regeneration removes obsolete `run-pi.sh`, `experiments/run.sh`,
`.pi/extensions/research-tools.ts`, and `.pi/extensions/experiments.ts` only
with overwrite confirmation or `--force`. Review local edits first. Symlinks at these
paths are rejected, even with `--force`; remove them yourself after review.
Experiments now run through Pi's built-in Bash tool.

Regeneration removes the obsolete project `.pi/settings.json`. Modified settings
require confirmation or `--force`; review the old file and migrate desired choices
to node's `~/.pi/agent/settings.json` before removal.
No project settings file is generated in the new layout.

## Next steps

The generated image includes `fd`, `htop`, `vim`, zsh, and Oh My Zsh. Both the `node` account
and VS Code's default terminal use zsh. Image defaults provide `HOME=/home/node`
and `SHELL=/bin/zsh`, including for `docker exec --user node`. The root firewall
entrypoint explicitly sets `HOME=/root` and `SHELL=/bin/bash` for startup only.
Oh My Zsh is installed/configured as node; root does not source node's shell setup.
Automatic Oh My Zsh updates are disabled.
Regenerate existing workspaces (review local edits before `--force`), rebuild
the container, and open a new terminal to apply shell changes.
Do not change the final Dockerfile `USER root`: the entrypoint needs root to
install the firewall, then drops to `node` with the correct home and no capabilities.
VS Code uses `remoteUser: node`. A plain `docker exec` otherwise defaults to root;
for a node shell use `docker exec --user node -it CONTAINER /bin/zsh -l`.
Docker executes the specified command; `SHELL` does not replace an explicit `bash`.
For direct root access, explicitly override the node environment:
`docker exec --user root --env HOME=/root --env SHELL=/bin/bash --env USER=root --env LOGNAME=root -it CONTAINER /bin/bash -l`.
Rebuild/recreate to discard completion caches created under the wrong identity;
do not disable Oh My Zsh's completion security checks.

1. Open `my-project/autoresearch` **as its own folder** in Visual Studio Code.
2. Choose **Dev Containers: Reopen in Container**. This builds a separate image.
3. Verify that selected source mounts are read-only and `/workspace/autoresearch`
   and its `results/` subdirectory are writable (instructions in generated `README.md`).
4. Configure OpenAI API authentication for Pi (for example, `OPENAI_API_KEY`)
   in a node shell, then run `pi` from the container workspace directory.
   The configured `openai` provider requires OpenAI API credentials; an OpenAI
   Codex login alone does not authenticate it.
   After the root firewall setup, `setpriv` drops to node with no capabilities;
   `.devcontainer/init-node.py` initializes node's global
   `~/.pi/agent/settings.json` before executing the container command.
   A new user receives `defaultProvider: openai`, `defaultModel: gpt-6-astra`,
   and `defaultThinkingLevel: high`. Child-agent defaults are
   `subagents.defaultModel: openai/gpt-6.1-sol` and
   `subagents.defaultThinking: medium`; `subagents.agentOverrides.worker`
   sets `model: openai/gpt-6.1-sol` and `thinking: medium`.
   Models must be available in your installed Pi/provider catalog and account;
   these defaults do not add them to the catalog.
   Existing settings and `auth.json` are preserved: the provider/model pair is
   seeded only if neither key exists; thinking and nested subagent defaults are
   filled only when missing, preserving existing values.
   Malformed existing settings stop startup rather than being overwritten.
   Root's Pi settings are untouched. Pi provides its built-in `read`, `bash`,
   `edit`, and `write` tools plus the bundled pi-subagents extension tools.
5. Tell Pi the experiment file and goals in chat, for example: “Use
   `/project/experiment.py`; inspect its source and `--help`, discover its
   configuration and output conventions, and run a small experiment.”
   No prescribed CLI or metrics format is needed. Customize the container
   runtime for your project's dependencies.

The image installs Pi plus `pi-subagents`, `pi-parallel-sessions`, `pi-web-access`,
and `pi-powerline-footer` with `npm install --global`. These are the image-bundled
equivalents of the corresponding `npm:` Pi packages. Extensions live under
`/usr/local/lib/node_modules`, outside the mounted `/home/node/.pi` volume.
Startup appends their absolute sources to node's persistent settings `packages`
array if absent, preserving user-installed package entries.
`pi-web-access` remains subject to the existing outbound firewall; search-provider
and fetched-site hosts must be allowed, with provider credentials configured as needed.

Startup also seeds `~/.pi/agent/keybindings.json` with
`"app.session.rename": "alt+r"` when that action is absent. Existing bindings,
including custom rename shortcuts, are preserved; malformed files stop startup.

The seed `.devcontainer/pi-settings.json` is editable from the host/development
container and baked with `init-node.py` into root-owned
`/usr/local/lib/autoresearch/`. Regenerate the workspace (review local edits before
`--force`), rebuild the image, and recreate the container to apply the bundled
package and updated seed. Startup fills missing defaults, not existing user
choices; rebuilding does not forcibly switch an existing provider/model pair.
To change active choices, edit `~/.pi/agent/settings.json` or use Pi's `/settings`
**inside a node shell**. The `/home/node/.pi` volume persists settings,
authentication, and sessions across rebuilds. No project extension or project
settings file is required.

Root startup also runs `.devcontainer/init-gpu.py` before dropping privileges.
It detects numeric GIDs of top-level NVIDIA character devices where group membership
grants additional read or write access, and adds `node` to those in-container
groups. Read-only and write-only group permissions are supported; no GID is hardcoded.
Membership survives `setpriv --init-groups` and applies to new VS Code terminals. Capability restrictions
remain unchanged; no privileged mode or device permission changes are needed.
Regenerate, rebuild, and recreate existing containers to apply this fix.

## Isolation boundaries

| Container path | Permissions | Purpose |
|---|---|---|
| Selected paths under `/project` | **Read-only bind mounts** | Only explicitly selected files/directories |
| `/workspace/autoresearch` | **Read/write bind mount** | Entire host workspace: scripts, prompts, and results |
| `/workspace/autoresearch/results` | Writable subdirectory, not a separate mount | Host `autoresearch/results/` |
| `/home/node/.pi` | Persistent named volume | Pi authentication/settings/sessions |

Open the generated workspace itself in Dev Containers, not its parent. Source
mounts use portable workspace-relative paths from `.autoresearch.json`; the
generated README lists their exact targets. `/project` is only a root-owned
mount-parent scaffold when nothing is selected. Unselected parent files are
not exposed. The entire workspace is mounted read/write, including its normal
`results/` subdirectory; there is no top-level `/results` directory or mount.
If a broad selected directory also contains the workspace, that read-only alias
does not prevent writes through `/workspace/autoresearch`.

`TRACKIO_DIR` defaults to `/workspace/<workspace-folder-name>/trackio`, including for
Pi-launched experiments. For `--workspace experiments/`, Trackio stores local
project data in `/workspace/experiments/trackio`, shared across runs.
Launch the dashboard in the same container to use that default. An explicit
`TRACKIO_DIR` override is preserved. Trackio must be installed in your runtime.
The container sets `TRACKIO_STORAGE_MODE=jsonl` and `TRACKIO_SQLITE_MMAP_SIZE=0`.
The generated `AGENTS.md` reserves Trackio for full training runs. Other
experiment results belong in appropriate files under `results/`, not Trackio.

Run `pi` directly from `/workspace/autoresearch`. Pi's default tools are
`read`, `bash`, `edit`, and `write`; Bash executes ordinary shell commands with
the container user's permissions and inherits Pi's environment, including any
credentials available there.

The container configuration supplies shared defaults:
`XDG_CACHE_HOME=/workspace/autoresearch/results/.cache`,
`UV_CACHE_DIR=/workspace/autoresearch/results/.cache/uv`,
`UV_PROJECT_ENVIRONMENT=/tmp/autoresearch/.venv`, and
`JAX_COMPILATION_CACHE_DIR=/workspace/autoresearch/results/.cache/jax`.
`PYTHONPATH=/project:/project/src` and `PYTHONDONTWRITEBYTECODE=1` support imports
without writing bytecode to source mounts; the image sets `TMPDIR=/tmp`.
These are container defaults, not per-command overrides.

Use `results/` as the recommended output folder and discover the project's
commands, configuration, and artifact conventions through chat and inspection.
There are no automatic run directories, logs, metadata records, or rankings;
choose output paths and record any experiment evidence explicitly.

Only selected source inputs under `/project` are read-only; the workspace is
writable. Docker drops all capabilities except `NET_ADMIN`, `SETUID`, `SETGID`,
and `SETPCAP` needed by the root startup entrypoint. It installs the firewall,
then runs the container command as `node` with all capability bounding bits
dropped. Pi and experiment commands have no firewall capabilities or sudo.
No-new-privileges and a PID limit remain enabled; no Docker socket is mounted.
Container writable layers and Pi's persistent state still exist. Writes anywhere
in the mounted workspace, not just `results/`, propagate back to the host.

**Security caveats:** a read-only mount does not hide secrets in the repository.
Model-selected Bash commands inherit Pi's environment, including credentials,
and can use allowed network services, read Pi's persistent credentials, modify
workspace files on the host, or write to container-private storage.
This protects selected source mounts, not the workspace, and is not a hostile-code
sandbox. Do not expose sensitive credentials to commands.

### Optional NVIDIA GPU access

GPU access defaults to `none`, which omits Docker's GPU runtime argument.
Selecting `all` adds `--gpus=all`; a subset such as `0,2` adds the literal runtime
argument `--gpus="device=0,2"` to expose only the selected devices. UUID selections
(`GPU-...` or `MIG-...`) use the same comma-separated `device=` form. These are
Docker runtime selections, not GPU discovery or hardware validation by setup.
This is Linux/Docker NVIDIA GPU passthrough, not Apple Metal or macOS GPU support.
The Docker host needs compatible NVIDIA GPUs, drivers, and the NVIDIA Container
Toolkit. Setup does not detect GPUs or install drivers, the toolkit, or CUDA.
Scientific workloads may also need user-provided CUDA-enabled runtime dependencies.
After regenerating with a different GPU choice, recreate the devcontainer to apply
the changed runtime arguments; restarting the existing container is not enough.
When enabled, optionally run `nvidia-smi` inside the recreated container to inspect
GPU visibility.

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
Image builds are not filtered by this runtime firewall. Commands inherit Pi's
environment and can read accessible credential files; neither is secret isolation.

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

For scientific experiments:

- use immutable evaluation data, fixed budgets, and correctness gates;
- use `/workspace/autoresearch/results` for experiment artifacts; shared cache and environment defaults are configured separately;
- record seeds, metrics, code revision, package versions, and hardware details;
- replicate promising runs to quantify measurement noise;
- reserve held-out validation for finalists rather than optimize directly on it.

If your main devcontainer has specialized dependencies, extend the generated
Pi Dockerfile with the same toolchain, or use the same runtime base image as
your main development container. The two containers do **not** automatically
share installed packages or Python virtual environments. `uv run` and `uv sync`
use `/tmp/<workspace-folder-name>/.venv` by default; this environment is temporary
and can be recreated after container replacement or `/tmp` cleanup.
For standalone creation, use `uv venv "$UV_PROJECT_ENVIRONMENT"`; plain
`uv venv` does not use `UV_PROJECT_ENVIRONMENT`. The uv cache stays under
`/workspace/<workspace-folder-name>/results/.cache/uv`.

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
- [Pi command-line options](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md)
- [Dev Container metadata reference](https://containers.dev/implementors/json_reference/)

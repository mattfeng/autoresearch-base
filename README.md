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
    │   └── Dockerfile
    ├── .pi/extensions/
    │   └── experiments.ts      # Pi: run/list/compare tools
    ├── experiments/
    │   ├── run.sh              # Fixed-command trusted execution entrypoint
    │   └── benchmark.py       # Executable smoke test; replace with real benchmark
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
   bash experiments/run.sh /results/manual-smoke 42
   cat /results/manual-smoke/metrics.json
   ```

5. Configure Pi authentication and start `./run-pi.sh`. The custom Pi extension
   provides `run_experiment`, `list_experiments`, and `compare_experiments`.
6. Replace `experiments/benchmark.py` and modify `experiments/run.sh` to use your
   project's actual Python environment, metrics, and correctness checks.

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

The Pi launcher uses a strict read-only tool allowlist (`read`, `grep`, `find`,
`ls`), the three custom experiment tools, `--no-mcp`, and an explicit extension
load. It does **not** expose Pi's `bash`, `edit`, or `write` tools. Experiments
always execute the fixed trusted `experiments/run.sh`; the model never supplies
shell text or a filesystem path.

The experiment process receives a reduced environment that omits model API
credentials, and runs with a timeout. Project source and runner mounts are
read-only. Docker starts with capabilities dropped, no new privileges, and no
Docker socket. Container writable layers and Pi's persistent state still exist;
only the results mount writes back into the repository.

**Security caveats:** a read-only mount does not hide secrets in the repository,
and trusted benchmark code can still perform network requests or write to
container-private storage. This is a practical source-protection model, not a
hostile-code sandbox. Do not run untrusted experiment code with host credentials.
Network restrictions and GPU access are intentionally left for later hardening.

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

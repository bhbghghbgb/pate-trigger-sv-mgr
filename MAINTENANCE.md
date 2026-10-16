# MAINTENANCE.md

Engineering reference for `pate-trigger-sv-mgr` (Palworld dedicated-server
auto-restarter). Last updated by the 2026-10 dependency/security pass.

## Layout

Single project at the repo root — no sub-packages, sub-repos or nested build files.

| Path | What it is |
| --- | --- |
| `main.py` | The whole service: starts/monitors/kills the server, runs the backup job, uploads to Discord. All tunables are the constants at the top. |
| `LoggingStuff.py` | Logging setup + Discord webhook plumbing. Reads `secrets.json` at import time. |
| `Pipfile` / `Pipfile.lock` | pipenv definition and hash-pinned lock — the dependency source of truth. |
| `Start server.bat` / `Backup save.bat` | Server launcher and WinRAR archiving; both are copied into the Palworld server directory. |
| `secrets.template.json` | Template for `secrets.json` (gitignored). |

The service is Windows-only: `CREATE_NEW_CONSOLE`, `CTRL_BREAK_EVENT` and `Rar.exe`
are not portable. `main.py` uses `asyncio.TaskGroup`, so Python 3.11+ is required.

## Toolchain

- **Python 3.14** — matches `python_version` in the `Pipfile`.
- **pipenv** (recent) — required; only it can write a `Pipfile.lock`.
- **uv** — optional, for ad-hoc tooling (`uvx`).

Nothing the project requires was missing during the last pass. The repo defines no
linter, formatter, type checker, test suite or CI.

## Re-locking dependencies

```bash
pipenv lock --python 3.14   # regenerate Pipfile.lock (hash-pinned, rewrites _meta.hash)
pipenv verify               # -> "Pipfile.lock is up-to-date."
pipenv sync --dev           # install exactly the lock, hash-checked
pipenv run pip list         # show what got installed
```

- Raise the `[packages]` floors in the `Pipfile` first, then re-lock. Never hand-edit
  `Pipfile.lock`; a stale `_meta.hash` makes pipenv silently re-resolve on install.
- `uv pip compile` / `uv lock` cannot be used: they emit `requirements.txt` / `uv.lock`.
- To retarget Python, change `python_version` in `[requires]` and re-lock; all current
  dependencies allow `>= 3.10`, so 3.13 and 3.14 resolve to the same set.

## Compile / lint

```bash
python -m compileall main.py LoggingStuff.py                              # byte-compile, executes nothing
uvx ruff@latest check --isolated --no-cache main.py LoggingStuff.py     # ad-hoc lint
```

`compileall` writes gitignored `__pycache__`; `uvx` keeps ruff out of the project's
dependencies. Current ruff output is 8 findings, all cosmetic or deliberate and left
unfixed: 1 unsorted import block, 1 blind `except Exception` in the log thread,
2 blocking `open()` calls inside async functions, 4 `global` statements that assign
nothing. Nothing is broken.

## Windows `.bat` entry points

- `Start server.bat` — `cd .\Pal\Binaries\Win64` then `PalServer-Win64-Test-Cmd.exe
  -port=8211 -players=4 -useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS`.
  Server options are configured here; referenced by `PROCESS_EXECUTOR` and launched with
  `PROCESS_EXECUTOR_CWD` as working directory.
- `Backup save.bat` — rotates `Saved.rar` to `Saved1/2/3.rar` and archives `.\Pal\Saved`
  via `Rar.exe a -ma5 -m5 -s -r -ep -tsmca`; referenced by
  `PROCESS_DATA_BACKUP_EXECUTOR`, whose stdout is captured into `Backup save.log`
  (`PROCESS_DATA_BACKUP_EXECUTOR_LOG`) and uploaded to Discord.

Both must be copied into the Palworld server directory; all paths are the constants at
the top of `main.py`.

## `secrets.template.json`

- Copy it to `secrets.json` and fill in `DISCORD_WEBHOOK_URL` and
  `ROLE_TO_PING_FOR_ATTENTION`.
- `secrets.json` is gitignored — **never commit it**. The template's fake webhook URL
  and role are safe to keep tracked.
- `LoggingStuff.py` opens it at import time, so even `import main` fails with
  `FileNotFoundError` if it is missing. Commenting out the `addHandler` line in
  `setup_logging()` (per the README) does not remove that read, so the file must exist
  even when Discord logging is disabled.

## Gotchas

- `secrets.json` is opened relative to the current working directory — always run the
  service from the repo root.
- Discord caps messages at 2000 chars; `MESSAGE_LENGTH_LIMIT_INDEX = 1997` plus the
  ⤵️/↪️ split indicators stays under it. Keep the two in sync.
- `rate_limit_retry=True` blocks (sync) or sleeps (async) on HTTP 429; the async upload
  runs on the event loop, so a rate limit stalls the monitor loop.
- `discord-webhook` needs the `async` extra for `AsyncDiscordWebhook`, and that extra is
  what pulls in `httpx`, `httpcore`, `anyio` and `h11`.
- The lock installs on Python 3.14 / Windows without a compiler: `psutil` ships
  `cp37-abi3` wheels and `charset-normalizer` has native `cp314` wheels.

## Dependencies (2026-10 pass)

`Pipfile` went from unpinned `*` to explicit floors of the current latest releases, and
`python_version` from 3.12 to 3.14.

| Package | Before | After |
| --- | --- | --- |
| anyio | 4.2.0 | 4.15.1 |
| certifi | 2024.2.2 | 2026.7.22 |
| charset-normalizer | 3.3.2 | 3.5.2 |
| discord-webhook | 1.3.1 | 1.4.1 |
| h11 | 0.14.0 | 0.16.0 |
| httpcore | 0.16.3 | 1.0.9 |
| httpx | 0.23.3 | 0.28.1 |
| idna | 3.6 | 3.20 |
| psutil | 5.9.8 | 7.2.2 |
| requests | 2.31.0 | 2.34.2 |
| urllib3 | 2.2.0 | 2.8.0 |
| rfc3986 | 1.5.0 | dropped (requests >= 2.32 no longer needs it) |
| sniffio | 1.3.0 | dropped (anyio 4.15 no longer needs it) |
| typing-extensions | — | 4.16.0 (added: anyio on python < 3.15) |

No source change was needed: both modules byte-compile and import on 3.14 without
deprecation warnings, and every `psutil` / `discord-webhook` API the code calls is
unchanged. This clears the open Dependabot advisories for anyio, h11, urllib3, idna,
requests and certifi.

Upstream `discord-webhook` (now `lovvskillz/python-discord-webhook`) has only reached
1.4.1 — there is no 2.x or 3.x release, so there are no 3.x renames to chase. The 1.0.0
breaks (single `url: str`, no `remove_files` argument, arg-less `edit()`/`delete()`) are
already handled by the code, and 1.1.0–1.4.1 are additive.

## Left unfixed, and why

- **Ruff findings** — cosmetic or intentional; changing them adds churn to a project
  with no tests, and nothing is broken.
- **`secrets.json` read at import time** — env vars or a lazy/optional load is a product
  decision, not a dependency fix.
- **Blocking `open()` in async functions** (`webhook_file_upload`,
  `process_data_backup_job`) — would need `asyncio.to_thread`; behaviour-neutral here.
- **No tests, lint config or CI** — adding tooling was out of scope for this pass.
# offpeak-bekci

[![Hermes](https://img.shields.io/badge/hermes-%E2%89%A50.22.2-6E56CF?logo=opensourceinitiative&logoColor=white)](https://hermes-agent.nousresearch.com/docs)
[![Plugin catalog](https://img.shields.io/badge/catalog-listed-2ea44f?logo=github&logoColor=white)](https://github.com/NousResearch/hermes-agent/tree/main/plugin-catalog)
[![Version](https://img.shields.io/badge/version-0.1.5-blue)](./CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-116%20passing-brightgreen)](./tests)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Languages](https://img.shields.io/badge/lang-en%20%7C%20tr-lightgrey)](./README.tr.md)
[![Off-peak only](https://img.shields.io/badge/runs-off--peak%20only-8957e5)](https://ollama.com/pricing)
[![Measure-only](https://img.shields.io/badge/middleware-measure--only-informational)](./README.md#disclosure--what-it-reads-where-it-writes-what-it-keeps)

Makes Ollama Cloud's **off-peak window visible and actionable**: a status-bar chip shows the
countdown and the queue item counts, a one-shot notice fires `on_bildirim_dk` minutes before the
window opens, and approval is only ever taken from the user. On the body side an `llm_execution`
middleware — only for Ollama Cloud calls and only inside the peak window — measures the per-minute
call rate; with `kuru_kosu: true` (default) it **measures and never sleeps**.

## Install from the catalog (recommended)

```bash
hermes plugins install offpeak-bekci     # listed in the official Hermes plugin catalog
hermes plugins enable offpeak-bekci
```

The catalog entry pins `0.1.5` and ships the same tree as the source install below.
Set `dil: tr` under `config.yaml → offpeak-bekci:` for Turkish command output.

![Status-bar chip](docs/rozet.png)

Chip: window/countdown · `APPROVED/TOTAL` counter · quota state. (Image cropped from a real desktop
status bar at measurement time; `docs/rozet.png`.)

> Turkish documentation: [`README.tr.md`](README.tr.md). Command output is English by default and
> Turkish when `dil: tr` is set.

## Install — one line

```bash
git clone https://github.com/onkanat/hermes-offpeak-bekci && hermes-offpeak-bekci/tools/kur.sh && hermes plugins enable offpeak-bekci
```

`tools/kur.sh` copies the repo into `$HERMES_HOME/plugins/offpeak-bekci` (idempotent, no remote
download), prints the sha256 of the shipped surface and verifies it with `hermes plugins validate`.

The desktop half (the chip) is installed separately — a single file:

```bash
mkdir -p ~/.hermes/desktop-plugins/offpeak-bekci
cp desktop/plugin.js ~/.hermes/desktop-plugins/offpeak-bekci/plugin.js
# then: enable it under Settings ▸ Plugins · ⌘K → "Reload desktop plugins"
```

The chip reads its state through `/offpeak-durum json`, so update the server and desktop halves
**together** (same version). For another profile: `HERMES_HOME=~/.hermes/profiles/<profile> tools/kur.sh`.
Changing a value needs **no code edit**: settings live in `config.yaml` → the `offpeak-bekci:` block.

Catalog entry: see `plugin-catalog/offpeak-bekci.yaml` — submitted as PR
[#139797](https://github.com/NousResearch/hermes-agent/pull/139797) (review in progress). Until it
is listed, the source install above applies.

## Commands

| Command | What it does |
| --- | --- |
| `/offpeak-durum` | Window, countdown, sliding-window rate, quota and queue counters. **Default: readable report**; `/offpeak-durum json` is the machine output (the desktop chip reads that). |
| `/offpeak-onayla <id,id>` | Marks queue items as `onaylı`/approved (the user is the **only** approver). |
| `/offpeak-kur` | Prints the off-peak cron job that would be installed **in full** (job name, schedule, the whole prompt, monitor, workdir, toolsets, delivery) plus `plan_hash`. **Installs nothing.** |
| `/offpeak-kur onayla <plan_hash> [duraklat]` | Continues only if `plan_hash` matches; leaves the install **request** to the session, and the agent's own `cronjob_manage` tool installs it (host-dependent — see *Where is the request auto-delivered?*). |
| `/offpeak-kaldir` | Lists offpeak jobs in this profile (id · schedule · state · next run). |
| `/offpeak-kaldir onayla <job_id>` | Leaves a removal **request** to the session, only with an id from that list (host-dependent — see *Where is the request auto-delivered?*). |

Why "request"? The plugin API has no surface to **create** a cron job (`register_command`,
hooks and middleware exist; a job installer does not). Installation is therefore left to the
session as a user-approved message; the agent's cron tool makes the decision and the record.
**The plugin never writes `jobs.json` under any circumstance — it only reads it.**

### Where is the request auto-delivered? (measured limit)

`ctx.inject_message(…)` is routed by the core depending on the host
(`hermes_cli/plugins_injection.py:18-32`):

| Host | What happens |
| --- | --- |
| **Classic CLI** (terminal REPL — the core installs the CLI reference here) | The request enters the CLI queue, return is `True`; the agent installs it when the command finishes. |
| **Ink TUI (`hermes --tui`) / desktop panel** | The core asks for a **persistent `session_key`**. That key is not given to the command handler (no session field on `PluginContext`; the `pre_command` hook is not invoked on the desktop `command.dispatch` path) → return is `False`. |
| **Gateway session** (when `session_key` or `origin` was handed to the plugin beforehand) | The request is queued into that session — **but** the core first asks a gate: `plugins.entries.offpeak-bekci.allow_gateway_injection: true` (default **off**). If off, a warning is printed and the return is `False` (`hermes_cli/plugins.py:622-630`). |

So on the desktop/Ink host the command falls into the "could not be left to the session in this
channel" branch and prints the parameters to install as **a single line of JSON**: the job is still
installed through the agent's cron tool, the only difference being that the user passes the request
to the agent (paste the JSON, or use `cronjob_manage`).

The only in-process way to read the session key is `gateway.session_context.get_session_env`, and
that module is **not public surface** for a plugin: the core's own checker reports an artificial
`from gateway.session_context import get_session_env` import as a finding
(`private_import_findings`), while `hermes_constants.get_hermes_home` does not. Per rule 9 that path
is not used; hence on the desktop the command handler cannot reach the key and auto-delivery does
not work (the resolution is a user/core decision: either a public read surface, or
`allow_gateway_injection` + the key). Regression tests: `tests/test_kurulum.py::HostKanaliTest`
(plus the wording side, `HostBeyaniTest`). Measured: core source lines, the core's own injection
tests, and a real probe run. Not measured: the real Hermes.app host delivery (the plugin side
catches it with a stub).

Dry run (try the job without keeping it):

```text
/offpeak-kur onayla <plan_hash> duraklat     # creates the job with paused:true, never scheduled
hermes cron list                             # the job is visible
/offpeak-kaldir onayla <job_id>              # undo
```

## Disclosure — what it reads, where it writes, what it keeps

**Reads:** only the single local file named by the `kuyruk_dosyasi` setting (default
`~/.hermes/offpeak-bekci/kuyruk.md`) — to count pending/approved/run items. The install commands
additionally **read-only** the cron store (`<profile>/cron/jobs.json`); the store path is derived
from **public surface** (`hermes_constants.get_hermes_home()`), the core's private `cron.jobs`
module is **not imported** (catalog rule 9). `load_jobs()` is deliberately unused: that call runs
`ensure_dirs()`, which creates directories (a side effect).

**Writes:** (1) the local JSONL log named by the `olcum_dosyasi` setting (default
`~/.hermes/offpeak-bekci/olcum.jsonl`): measurement/alert/approval records; (2) when the user runs
`/offpeak-onayla`, **only** `kuyruk_dosyasi` — the plugin does not generate the file's content, it
is the user's own file, and the write is atomic (temp file + `os.replace`). It writes nowhere else;
`jobs.json`, `config.yaml` and site files are **out of scope**.

**Keeps (settings):** the table below. The single source of truth is `plugin.yaml` →
`config_schema`; code defaults are read from there. A given install's own values live in
`config.yaml` → the `offpeak-bekci:` block; no user-specific path is baked into the plugin.

**Does not:** no network calls, no telemetry, never reads or writes secrets/passwords/tokens, never
runs a shell or spawns processes, never downloads remote code, never self-updates, never touches
another profile or machine. The desktop half (`desktop/plugin.js`) uses only the plugin SDK
surface: no prototype patching, no `eval`, no DOM querying.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `dil` | `en` | Language of command descriptions, command output and notices: `en` or `tr`. |
| `kuru_kosu` | `true` | While `true` it measures/records and **never sleeps**. |
| `kuyruk_dosyasi` | `~/.hermes/offpeak-bekci/kuyruk.md` | Path of the queue ledger (the single read source). |
| `schedule` | `5 18 * * 1-5` | Opening of the off-peak window (cron, UTC) — used in the `/offpeak-kur` plan. |
| `on_bildirim_dk` | `30` | How long before the window the notice starts (minutes). |
| `hedef_hiz_dk` | `6` | Max calls per minute during peak (sliding `pencere_sn` window). |
| `erteleme_tavani_sn` | `30.0` | Max sleep for a single request (delay ceiling). |
| `pencere_sn` | `60.0` | Length of the sliding rate window (seconds). |
| `kota_tavani` | `120` | Max calls per quota window; exceeding it writes an alert record (the request is not cancelled). |
| `kota_penceresi_sn` | `3600.0` | Quota counter window (seconds). |
| `kota_token_gun` | `0` | Daily fresh-token ceiling; `0` = no ceiling. |
| `cache_read_tavani_gun` | `0` | Daily cache-read token ceiling; `0` = no ceiling. |
| `off_peak_only_isler` | `[]` | Names of jobs that must only run off-peak (a declaration). |
| `olcum_dosyasi` | `~/.hermes/offpeak-bekci/olcum.jsonl` | Measurement/alert log (JSONL, local). |

## Development

```bash
python3 -m unittest discover -s tests -t .   # python gates
node --test tests/desktop/plugin.test.mjs    # desktop gates
node tools/build-desktop.mjs --check         # is the embedded plugin.js stale? (EXIT=0)
hermes plugins validate . --install-deps     # manifest validation
```

Dry-run/measurement tools: `tools/kuru_kosu_olcum.py` (dry-run measurement against the live config).

Limit: it never **writes** to a real queue ledger for measurement purposes; the install commands
never create a job without user approval and never change the `kuru_kosu` setting.

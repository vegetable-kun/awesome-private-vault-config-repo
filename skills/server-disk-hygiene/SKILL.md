---
name: server-disk-hygiene
description: "Reclaim disk space on a small Linux host, tier by tier."
version: 1
metadata:
  hermes:
    tags: [devops, disk, cleanup, storage]
    related_skills: [hermes-gateway-config, docker-compose-service-deploy]
---

# Server Disk Hygiene

## When to Use

- `df` shows the root filesystem above ~85%, or free space is low enough that the next install or
  build will fail.
- The user asks what junk can be removed, or asks for a cleanup plan before other work.
- Before an operation that needs headroom (an update, a build, a database migration).

Disk pressure on a small host is urgent (installs, builds and databases all fail) but deleting the
wrong tree is unrecoverable. This procedure is **read-only until the user approves a tier**.

## Procedure

0. **Pin the reclaim target before scanning.** Ask what number of GB must be freed (or infer it
   from the task). Every later step exists to reach that number, and the scan stops as soon as
   the candidate list can already cover it. If the user names a target, size the tiers so the
   recommended combination clears it with margin.
1. **Size first, always.** `df -h /` then `du -h -d1 ~ | sort -rh | head -15`. Also check
   `free -h` — a full disk and memory pressure often co-occur on small hosts, and the memory
   reading sets how aggressive you can be about caches.
2. **Fan out one level** into every directory above ~500M. Two levels is enough; deeper is noise.
   Compare the sum against `df` used bytes: a large gap means root-owned trees the unprivileged
   `du` skipped (see the containerd/Docker pitfall), so escalate to one privileged fan-out
   rather than guessing where the missing space is.
3. **Classify every candidate into exactly one tier** (see below) before proposing anything. Do
   not present an undifferentiated list — the user cannot triage a wall of paths and will either
   approve blindly or approve nothing.
4. **Propose the plan as tiers plus one recommended combination.** Tier 1 is the safe default;
   tier 2 items each carry a one-line "you must decide this" note and its exact GB. Close with a
   single combination that hits the target (and the alternative combination if one big tier-2
   item is approved instead). Then wait for approval — do not start deleting during the scan.
5. **After deleting, re-measure** (`df -h /`) and report before/after as a table. Deleting caches
   frees space only once nothing holds the files open.

Concrete probe commands for every step live in `references/host-reclaim-probes.md` — including
the git-lfs reclaim recipe (§10), duplicate-copy detection (§11) and the post-delete
verification block (§12).

## The three tiers

| Tier | Definition | Examples |
|---|---|---|
| **1 — regenerable** | Download/build caches. Deleting costs only re-download time; nothing installed breaks. | `~/.npm/_cacache`, `~/.npm/_npx`, `~/.cache/pip`, `~/.cache/uv`, `~/.cache/pnpm`, `~/.local/share/pnpm`, `~/.cache/node-gyp`, `/var/cache/apt`, `journalctl --vacuum-time=7d` |
| **2 — needs confirmation** | Real data or a dead project you cannot identify. Ask; never assume. | abandoned project checkouts, `*.bak` dirs, unknown `data/` trees, duplicate browser binaries not in use, snap packages (core22/ngrok/snapd), `/opt` application directories (QQ/NapCat/alibabacloud) |
| **3 — off-limits** | Deleting breaks something. Name it and say why so the user does not "help" you. | active DBs, live venvs, app session stores, git object stores (unless the user opts into `git gc`) |

## Pitfalls

- **Do not delete a venv a script references.** Grep the cron configs and skills for the path first
  (`grep -rl "<venv-path>" ~/.hermes/cron/ ~/.hermes/skills/`). A legacy venv can look unused while
  every scheduled job still hardcodes its interpreter — deleting it breaks jobs silently at their
  next run, not at cleanup time.
- **A grep miss is not proof of disuse — check leases and open files before deleting an environment.**
  A running process can hold an environment with no text reference anywhere: the linkage is an mmap
  plus a runtime `sys.path` entry, so `grep -rn <path> ~/.hermes` returns nothing while the tree is
  in active use. Never `rm -rf` a venv/generation until you have asked the app whether it is leased
  *and* checked which PIDs have its files mapped — deleting pulls `.so` files out from under a live
  process. Two traps: an empty `.leases/` directory does not mean unheld (a lease file that exists
  but cannot be locked counts as held), and releasing a lease does not unmap the files, so a
  process stays exposed until it next loads from the tree. Restarting the gateway is not enough —
  interactive sessions and dashboards launched from another shell keep the old tree mapped. Full
  probe commands live in the `hermes-gateway-config` skill, in its `dependency-environment`
  reference under `references/`.
- **A deleted-looking `*.bak` beside a script is tier 1.** Cron self-repair and update runs leave
  `*.bak-<epoch>` copies next to the file they replaced; they are dead weight once the replacement
  is verified working. Confirm the live file still imports what it needs, then remove the backup.
- **Browser driver caches are tier 2, not tier 1.** `~/.cache/ms-playwright` and
  `~/.cache/puppeteer` are binary downloads, so they *look* regenerable — but if the host has
  browser automation configured, removing them breaks that feature and forces a large re-download.
  Classify by whether anything on the host drives a browser.
- **snap packages are tier 2, not tier 1.** snapd installs core22 (base runtime), snapd itself,
  and application snaps (ngrok etc.) under `/snap` and `/var/snap`. They look like system packages
  but are user-managed. Removing snapd requires removing all snaps first (`snap remove`), then
  `apt remove --purge snapd`, then `rm -rf /snap /var/snap`. snapd is a system service — removing
  it may affect lxd-installer and other snap-dependent packages. Always confirm before removing.
- **`/opt` application directories are tier 2.** QQ (561M), NapCat (93M), alibabacloud (204M) etc.
  are root-owned and require `sudo rm -rf`. They may be in active use (QQ for NapCat bot, etc.).
  Always check if the application is running before deleting (`ps aux | grep -i <name>`).
- **A browser cache can hold several versions; delete the ones no installed client pins.** Each
  Playwright client ships a `browsers.json` naming the exact chromium revision it wants
  (node: `node_modules/playwright-core/browsers.json`; python:
  `site-packages/playwright/driver/package/browsers.json`). Diff the revisions against the
  directories in `~/.cache/ms-playwright`; every revision not named by any installed client is
  a stale duplicate and is safe to remove while keeping the pinned one. Keep the Hermes-bundled
  `~/.hermes/tools/chromium-*` separate — the browser CLI resolves its own copy and may prefer a
  revision that no `browsers.json` mentions.
- **A file's size is not its reclaimable size.** Before promising space from a database, a
  session store or a snapshot, measure the actual free space inside it (sqlite: `PRAGMA
  freelist_count` × `page_size`); a 400 MB file can hold only a few MB of reclaimable slack
  while a stale *copy* of that file elsewhere on disk is the real waste. Delete the copies and
  the pre-fix snapshots, not the live file.
- **Orphaned sidecars and retired backups are tier 1.** Retired WAL/shm generation directories,
  superseded DB snapshots left behind by a maintenance run, and `*.retired-*` manifests are dead
  weight the app no longer reads. Confirm no process holds them, then delete.
- **`du` on the home directory under-reports total usage.** If `df` shows far more used than `du ~`
  accounts for, the remainder is outside home (`/var`, `/usr`, `/opt`) — run `du -h -d1 /` before
  concluding the home scan was complete.
- **Disk pressure and memory pressure often co-occur on small hosts.** Always check `free -h`
  alongside `df -h`. A full disk plus low available memory means the host is under resource
  pressure — be more conservative about deleting caches (they will need re-downloading) and
  prioritize deleting large dead trees over regenerable caches. On a 2G host, QQ (4 zygotes,
  ~440M) and Hermes gateway (~188M) are the top memory consumers; cleaning disk alone won't
  help if memory is the bottleneck.
- **Unprivileged `du` on `/var` hides the single biggest consumer on container hosts.** With the
  containerd snapshotter, image layers live in `/var/lib/containerd`, not `/var/lib/docker`, and
  they are root-only: `du /var` can read ~0.9 GB while the truth is several GB. Always compare
  against `docker system df` (which reports real reclaimable bytes) and re-run the fan-out with
  `sudo -n du -xhd2 /var` when the numbers disagree.
- **Root-owned directories require `sudo`.** `/opt`, `/snap`, `/var/lib/docker`, `/var/lib/containerd`
  are root-owned. `rm -rf` without `sudo` will fail silently (Permission denied) and leave the
  directory intact. Always check ownership (`ls -ld`) before attempting deletion, and use
  `sudo rm -rf` for root-owned paths.
- **A dangling image does not free its shared layers.** `docker system df -v` splits each image
  into SHARED and UNIQUE size; a `<none>` dangling image that shares 800 MB with a live image
  only yields its UNIQUE bytes on removal. Quote the unique-size number, not the total.
- **An anonymous Docker volume with zero container links can still be the only copy of user data.**
  `docker volume prune` deletes exactly those volumes, and they are often leftovers from before
  the app moved to a bind mount — a chat client's session profiles, a bot's login state. Always
  read the volume's contents before pruning: `sudo -n ls /var/lib/docker/volumes/<id>/_data`.
  If it holds recognisable app state, treat it as tier 2 and list it, never sweep it with the
  prune command.
- **A git-lfs working tree restores real blobs unless the smudge filter is explicitly skipped.**
  Deleting an LFS-tracked directory and running `git checkout -- <path>` re-materialises the
  full binaries (and re-downloads them), so the deletion appears to bounce back. Override the
  filters first (`filter.lfs.smudge`/`filter.lfs.process` → `--skip`, `filter.lfs.required` →
  false), check out to get pointer stubs, then unset the overrides so the repo behaves normally
  again. `LFS_SKIP_SMUDGE=1` alone is not sufficient when a process filter is configured.
  The LFS object store under `.git/lfs` is a cache of the remote: verify the remote already has
  every object (`git lfs push --dry-run <remote> <branch>` printing nothing) before deleting it.
- **Capture `git status` before deleting inside a repo, so pre-existing changes are not
  attributed to the cleanup.** A working tree can already be dirty — moved-out files, untracked
  build output — before you touch anything. Snapshot the status first and report only the
  deltas you caused.
- **Batch privileged probes into one command.** Each `sudo` call can pause for approval, and a
  loop that runs `sudo` per path stalls the scan until the approval window times out. Combine
  the whole privileged fan-out into a single `sudo -n du …` invocation.
- **Report reclaim in the units the user cares about**: percentage points plus GB freed, not file
  counts.
- **`find … -exec rm -rf {} +` and bare recursive-delete patterns can be hard-blocked** by the
  runtime's guard (it reads any recursive delete as a possible removal of the agent's own
  interpreter). It is refused outright and cannot be approved around. Enumerate the paths
  yourself and delete them **one explicit `rm -rf path` per line** — that is also more
  reviewable, because the user can see exactly what goes.
- **`pkill -f <pattern>` can kill your own shell.** The pattern matches the pkill command's
  own argument list, so the agent's command line becomes a match and the session dies with
  signal 15 mid-command. Prefer killing by explicit PID captured from `ps`, or match a
  pattern that cannot appear in your own command line (e.g. `pkill -f '[g]it-lfs'`).
- **Do not use a single `rm -rf` with a wildcard when the wildcard is the argument.** `rm -rf
  "$dir"/*` fails on a non-matching glob and, under some shells, can expand to the parent.

## Interaction rules for this user

- **Analysis first, deletion on approval.** They ask for analysis and a plan; do not start deleting
  as part of the scan.
- **Deliver the plan as soon as the target is coverable.** The scan is a means to the number, not
  the deliverable: once the candidate list can already satisfy the requested GB, stop probing and
  hand over the plan. Continued exploration after the target is reachable reads as stalling.
- **Put the verdict first and keep it scannable.** Open with one line stating where the space
  actually is (which trees dominate) and that the obvious suspect is a red herring, then the
  tiered tables with exact sizes. Finish with one recommended combination and a one-line reply
  token so the user can approve in a single message.
- **Prefer the minimal, reversible tier.** If two options both unblock the situation, offer the
  smaller one first and state the cost of the smaller one honestly (e.g. a workaround that a future
  upgrade may undo).
- **Keep agent-runtime internals in tier 2 or 3** unless the file is provably orphaned. That tree
  holds live sessions, cron jobs and credentials.
- **Ask about the big discretionary tier-2 items explicitly, one question each.** A stopped
  service stack, an unused SDK, or a duplicated project directory is the user's call to make —
  name the exact GB and the exact consequence of deleting it, then let them pick.
- **An approval that names a subset is a scope boundary, not a hint.** When the user picks items
  out of your tiers ("do A's X, plus B4 and B5"), delete exactly those and nothing else, even
  when adjacent garbage is obvious and tempting. Resolve the shorthand by listing the exact paths
  in your report as you go, so any drift from the approval is visible immediately.
- **When the approved subset cannot reach the stated target, say so with numbers.** Report the
  actual free space after the deletions, the exact shortfall against the goal, and the remaining
  candidates with their sizes — then stop and let the user choose. Do not silently widen the
  scope to close the gap.
- **Within an approved group, keep the member that holds active work and delete the
  reconstructible ones.** When a tier-2 group is approved as a whole (duplicate copies of a
  project), the copies that can be re-fetched from a remote or a published artefact are the
  expendable ones; a checkout that is the only copy of in-progress work is not. State which one
  you kept and why.
# Host reclaim probes

Ordered commands for the disk-hygiene procedure. Each block is one step; run the next only if
the previous block leaves the target uncovered.

## 1. Baseline

```bash
df -h /
free -h
du -xhd1 /home/ecs-assist-user 2>/dev/null | sort -rh | head -15
```

`free -h` matters: a full disk and memory pressure co-occur on small hosts, and the memory
reading sets how aggressive you can be about caches and swap files.

## 2. Root-level fan-out, then close the df/du gap

```bash
du -xhd1 / 2>/dev/null | sort -rh | head -20
```

Compare the total with `df` used bytes. If they disagree by GBs, the difference is root-owned
trees the unprivileged scan could not read. Escalate once:

```bash
sudo -n du -xhd2 /var 2>/dev/null | sort -rh | head -25
```

Put all privileged probing in that one command — a per-path `sudo` loop stalls on approval
prompts.

## 3. Docker / containerd

```bash
sudo -n docker system df -v
sudo -n docker ps -a
sudo -n docker images
sudo -n docker volume ls
```

Read `docker system df` as the source of truth for reclaimable bytes. With the containerd
snapshotter the disk usage sits in `/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs`,
which is why `du /var/lib/docker` can look empty. Quote each dangling image's UNIQUE size, not
its total — shared layers survive the removal of any single image.

Deletion that keeps live stacks intact:

```bash
sudo -n docker image prune -a      # drops dangling + unused images
sudo -n docker container prune     # stopped containers only
sudo -n docker volume prune        # unused volumes; check bind-mounted data first
```

Never prune a volume or image whose container is the user's live service; list first.

## 4. Package and download caches (tier 1)

```bash
du -xhd1 ~/.cache 2>/dev/null | sort -rh | head -12
du -xhd1 ~/.npm 2>/dev/null | sort -rh | head -5
du -xhd1 ~/.local/share 2>/dev/null | sort -rh | head -6
sudo -n du -xsh /var/cache/apt /var/log 2>/dev/null
journalctl --disk-usage
```

Typical tier-1 targets: `~/.npm/_cacache`, `~/.npm/_npx`, `~/.cache/pip`, `~/.cache/uv`,
`~/.cache/node-gyp`, `~/.cache/torch`, `~/.local/share/NuGet`, `/var/cache/apt/archives`,
`journalctl --vacuum-time=7d`.

## 5. Browser binaries — map clients to revisions first

```bash
ls ~/.cache/ms-playwright ~/.cache/puppeteer
du -sh ~/.cache/ms-playwright/* ~/.cache/puppeteer/*
```

Then collect the revision each installed client pins:

```bash
find / -maxdepth 9 -path "*playwright-core/browsers.json" 2>/dev/null
find / -maxdepth 9 -path "*playwright/driver/package/browsers.json" 2>/dev/null
```

Each file lists `{"name": "chromium", "revision": NNNN}`. Any `chromium-NNNN` directory not
named by any client is a stale duplicate. Keep the Hermes-bundled
`~/.hermes/tools/chromium-*` untouched — the browser CLI resolves it independently.

## 6. Databases and session stores — measure slack, not size

```bash
python3 -c "
import sqlite3
c=sqlite3.connect('file:<db>?mode=ro',uri=True)
p=c.execute('pragma page_size').fetchone()[0]
f=c.execute('pragma freelist_count').fetchone()[0]
t=c.execute('pragma page_count').fetchone()[0]
print('total_MB',t*p/1048576,'free_MB',f*p/1048576)"
```

Small `free_MB` next to a large `total_MB` means the live file is not the waste. Look for copies
and pre-fix snapshots instead:

```bash
find ~ -xdev \( -name "*.db" -o -name "*.bak*" -o -name "*pre-*snapshot*" \) -size +50M 2>/dev/null
```

A snapshot named for the operation it protected (e.g. a pre-repair DB copy) is tier 1 once the
repair is verified; the live DB is tier 3.

## 7. Swap files

```bash
swapon --show --bytes
ls -lh /swapfile*
```

A swap file showing 0 bytes used is a candidate for shrinking, but removing it shrinks the
safety net on a host whose RAM is smaller than the swap. Present it as tier 2 with the exact
delta in swap capacity.

## 8. Snap

```bash
snap list --all
```

Rows whose Notes column says `disabled` are superseded revisions and are removable via
`snap remove <name> --revision=<rev>`.

## 9. Git object stores (tier 2, needs consent)

```bash
cd <repo> && git count-objects -vH
git for-each-ref | wc -l
```

Many remote-tracking refs and dozens of packs usually mean a re-clone or an aggressive gc would
shrink the store, but this rewrites the checkout's history — never do it unprompted.

## 10. Git-LFS artifacts — reclaiming the blobs without breaking the checkout

Large binaries committed through LFS appear twice on disk: the working-tree copy and the object
store under `.git/lfs`. Probe both, and confirm the remote already holds every object:

```bash
cd <repo>
du -sh .git/lfs <tracked-dir>
git lfs ls-files | wc -l
git lfs push --dry-run <remote> <branch>   # no output = remote has every object
```

Empty output from `git lfs push --dry-run` is the safety check: only then is `.git/lfs`
re-downloadable. If the remote is missing objects, this is tier 2, not tier 1.

To strip the working tree back to pointer stubs so `git status` stays clean:

```bash
rm -rf <tracked-dir> .git/lfs
git config filter.lfs.smudge "git-lfs smudge --skip -- %f"
git config filter.lfs.process "git-lfs filter-process --skip"
git config filter.lfs.required false
git checkout -- <tracked-dir>
git config --unset filter.lfs.smudge
git config --unset filter.lfs.process
git config --unset filter.lfs.required
git status -sb          # must stay clean
```

`LFS_SKIP_SMUDGE=1` alone does not work when a process filter is configured — the checkout
re-materialises the real binaries and the deletion appears to bounce back. Unset the filter
overrides afterwards so later clones and pulls behave normally.

## 11. Duplicate copies of one project — find the true duplicates before deleting

When several directories hold the same artefact, diff them instead of guessing:

```bash
diff -rq <copy-a> <copy-b> | head        # empty = byte-identical
ls -l <copy>                             # per-file sizes
```

Identify which copy is authoritative (a git remote, a build manifest, a handover doc) and which
are published/reconstructible. Keep the checkout that holds in-progress work; delete the copies
that a remote or a published artefact can restore.

## 12. Verify nothing broke after deleting

```bash
df -h /
ps -eo pid,comm,etime --sort=-rss | head -5
tail -3 ~/.hermes/logs/gateway.log
```

Re-check that the runtimes the surviving trees depend on are still present (a bundled node or
python under `~/.hermes/tools/`, the browser revision the browser CLI resolves), and that the
gateway log still shows normal traffic.

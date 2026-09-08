#!/usr/bin/env python3
"""Deterministic backlog picker for the orchestration loop.

The judgment (how to implement an item) belongs to the /backlog skill and its
fan-out. The mechanical part (parse the queue, pick the next actionable item,
flip a status) is deterministic, so per the fleet's determinism test it lives
here as a plain CLI rather than in a prompt.

Data file: BACKLOG.md (found by walking up from this script). Item format:

    ### WEB-ADMIN-1
    - priority: P0
    - epic: admin-rebuild
    - repo: web
    - title: <one line>
    - accept: <one-line acceptance criterion>
    - deps: none            # or comma-separated IDs
    - status: open          # open | in-progress | pr-open | done | blocked
    - pr: -                 # or a PR url

Commands:
    backlog.py next [--epic E]    print the next actionable item (or NONE)
    backlog.py list [--status S] [--epic E]  list items, optionally filtered
    backlog.py start <ID>         open -> in-progress
    backlog.py done <ID> <PR_URL> in-progress -> pr-open, record the PR
    backlog.py block <ID> <why>   -> blocked (why appended to title note)
    backlog.py repo-path <repo>   print the working directory for a repo tag
"""
import os
import re
import subprocess
import sys
from pathlib import Path

PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
SATISFIED = {"pr-open", "done"}  # a dep counts as met once its PR is open

# Site root, resolved once (single source of truth for every repo path below and
# for loop_worktree.SITE_ROOT, which imports it). Precedence:
#   1. $SITE_ROOT env override (lets a fork point the loop at its own checkout)
#   2. derived from this script's location: <site_root>/specs/_shared/tooling/backlog.py
#      -> parents[3]. This is how it stays portable with zero config.
#   3. the legacy literal, only if derivation doesn't look like a site root.
def _site_root() -> Path:
    env = os.environ.get("SITE_ROOT")
    if env:
        return Path(env)
    derived = Path(__file__).resolve().parents[3]
    # The repo root is three levels up from this vendored tool; fall back to it rather than a
    # hardcoded absolute path (which would leak a username into a public repo).
    return derived


SITE_ROOT = _site_root()

# repo tag -> working directory. This is a standalone repo, so the map only needs
# this repo and its specs; the picker falls through to "?" for any other tag.
REPO_PATHS = {
    "specs": str(SITE_ROOT / "specs"),
    "ballast": str(SITE_ROOT),
}


def repo_path(repo: str) -> str:
    return REPO_PATHS.get(repo, "")


FIELDS = ("priority", "epic", "repo", "title", "accept", "deps", "status", "pr")


def find_backlog() -> Path:
    for d in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
        candidate = (d if d.is_dir() else d.parent) / "BACKLOG.md"
        if candidate.is_file():
            return candidate
    sys.exit("error: BACKLOG.md not found above this script.")


def parse(text: str) -> list[dict]:
    items, current, in_fence = [], None, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        head = re.match(r"^###\s+(\S+)\s*$", line)
        if head:
            current = {"id": head.group(1)}
            items.append(current)
            continue
        if line.startswith("## "):  # section heading ends any item block
            current = None
            continue
        field = re.match(r"^\s*-\s+(\w+):\s*(.*)$", line)
        if field and current is not None and field.group(1) in FIELDS:
            current[field.group(1)] = field.group(2).strip()
    return items


def deps_of(item: dict) -> list[str]:
    raw = item.get("deps", "none").strip()
    if raw.lower() in ("none", "-", ""):
        return []
    return [d.strip() for d in raw.split(",") if d.strip()]


def pick_next(items: list[dict], epic: str | None = None) -> dict | None:
    # Dependency satisfaction is computed across ALL items (a dep may live in
    # another epic); only the candidate set is narrowed by --epic, so a dedicated
    # review loop never starves behind unrelated P0 product work.
    status = {it["id"]: it.get("status", "open") for it in items}
    candidates = []
    for idx, it in enumerate(items):
        if it.get("status", "open") != "open":
            continue
        if epic and it.get("epic") != epic:
            continue
        if all(status.get(d) in SATISFIED for d in deps_of(it)):
            candidates.append((PRIORITY_RANK.get(it.get("priority", "P3"), 3), idx, it))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[0][2]


def render(it: dict) -> str:
    repo = it.get("repo", "?")
    lines = [
        f"ID: {it['id']}",
        f"priority: {it.get('priority', '?')}",
        f"epic: {it.get('epic', '?')}",
        f"repo: {repo}",
        f"repo_path: {repo_path(repo) or '?'}",
        f"title: {it.get('title', '')}",
        f"accept: {it.get('accept', '')}",
        f"deps: {it.get('deps', 'none')}",
        f"status: {it.get('status', 'open')}",
    ]
    return "\n".join(lines)


def set_fields(path: Path, item_id: str, updates: dict[str, str]) -> None:
    """Rewrite the named `- key:` lines inside the ### item_id block."""
    out, in_block, in_fence, applied = [], False, False, set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        head = re.match(r"^###\s+(\S+)\s*$", line)
        if head and not in_fence:
            in_block = head.group(1) == item_id
        elif line.startswith("## ") and not in_fence:
            in_block = False
        if in_block and not in_fence:
            field = re.match(r"^(\s*-\s+)(\w+):\s*(.*)$", line)
            if field and field.group(2) in updates:
                line = f"{field.group(1)}{field.group(2)}: {updates[field.group(2)]}"
                applied.add(field.group(2))
        out.append(line)
    missing = set(updates) - applied
    if missing:
        sys.exit(f"error: could not update {sorted(missing)} on {item_id} (id/fields present?)")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]

    if cmd == "repo-path":
        if len(sys.argv) < 3:
            sys.exit("usage: backlog.py repo-path <repo>")
        print(repo_path(sys.argv[2]))
        return

    path = find_backlog()
    items = parse(path.read_text(encoding="utf-8"))
    by_id = {it["id"]: it for it in items}

    if cmd == "next":
        epic = sys.argv[sys.argv.index("--epic") + 1] if "--epic" in sys.argv else None
        nxt = pick_next(items, epic)
        print("NONE" if nxt is None else render(nxt))
    elif cmd == "list":
        want = None
        if "--status" in sys.argv:
            want = sys.argv[sys.argv.index("--status") + 1]
        epic = sys.argv[sys.argv.index("--epic") + 1] if "--epic" in sys.argv else None
        for it in items:
            st = it.get("status", "open")
            if want and st != want:
                continue
            if epic and it.get("epic") != epic:
                continue
            print(f"{it.get('priority', '??')} {it['id']:<22} {st:<12} {it.get('title', '')}")
    elif cmd == "start":
        item_id = sys.argv[2]
        if by_id.get(item_id, {}).get("status") != "open":
            sys.exit(f"error: {item_id} is not 'open' (status={by_id.get(item_id, {}).get('status')})")
        set_fields(path, item_id, {"status": "in-progress"})
        print(f"{item_id} -> in-progress")
    elif cmd == "done":
        item_id, pr = sys.argv[2], sys.argv[3]
        set_fields(path, item_id, {"status": "pr-open", "pr": pr})
        print(f"{item_id} -> pr-open ({pr})")
    elif cmd == "block":
        item_id, why = sys.argv[2], " ".join(sys.argv[3:])
        set_fields(path, item_id, {"status": "blocked"})
        print(f"{item_id} -> blocked: {why}")
    elif cmd == "close":
        set_fields(path, sys.argv[2], {"status": "done"})
        print(f"{sys.argv[2]} -> done")
    elif cmd == "publish":
        msg = " ".join(sys.argv[2:]) or "chore(specs): update backlog"
        publish_to_master(path, msg)
    else:
        sys.exit(f"unknown command: {cmd}\n{__doc__}")


# ── Concurrency-safe merge (fixes the publish lost-update clobber) ──────────
# Two loop sessions each run `publish`, snapshotting the whole BACKLOG.md. The
# original code copied the shared checkout's copy over master, so the later
# publish erased the earlier one's changes. The first fix merged per item with
# "highest status wins" — but the lifecycle is NOT monotone: an owner UNBLOCK
# (blocked -> open) ranks downward, so a stale copy still holding `blocked`
# out-ranked master's fresh `open` and silently reverted it on every publish
# (CICD-4; ee9e35a reverted 17a5edc, then again after a55119d re-applied it).
#
# The real fix is a 3-way merge against the BASE (the shared checkout's HEAD
# version of BACKLOG.md): per item, if OUR copy is unchanged from base, master
# is authoritative (we never re-assert state we didn't touch); if only we
# changed it, our block wins regardless of rank (so an unblock or note edit we
# made publishes too); if BOTH sides changed it, the higher lifecycle rank
# wins, master on ties. Rank-only merging remains the fallback when no base is
# available.

_STATUS_RANK = {"open": 0, "in-progress": 1, "blocked": 2, "pr-open": 3, "done": 4}


def _block_status_rank(block: str) -> int:
    m = re.search(r"^\s*-\s+status:\s*(\S+)", block, re.MULTILINE)
    return _STATUS_RANK.get(m.group(1).strip(), 0) if m else 0


def _split_backlog(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split into (preamble through '## Items', [(id, raw_block), ...]).
    Item blocks only appear after '## Items', so the fenced example in the
    preamble never collides with real items."""
    lines = text.splitlines(keepends=True)
    try:
        items_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "## Items")
    except StopIteration:
        return text, []
    preamble = "".join(lines[: items_idx + 1])
    blocks: list[tuple[str, str]] = []
    cur_id, cur = None, []
    for ln in lines[items_idx + 1 :]:
        h = re.match(r"^###\s+(\S+)\s*$", ln)
        if h:
            if cur_id is not None:
                blocks.append((cur_id, "".join(cur)))
            cur_id, cur = h.group(1), [ln]
        elif cur_id is not None:
            cur.append(ln)
    if cur_id is not None:
        blocks.append((cur_id, "".join(cur)))
    return preamble, blocks


def _merge_preamble(master_pre: str, ours_pre: str) -> str:
    """Carry over any epic bullets we added that master does not have yet."""
    master_slugs = set(re.findall(r"^-\s+\*\*([A-Za-z0-9-]+)\*\*", master_pre, re.MULTILINE))
    add: list[str] = []
    capturing = False
    for ln in ours_pre.splitlines(keepends=True):
        m = re.match(r"^-\s+\*\*([A-Za-z0-9-]+)\*\*", ln)
        if m:
            capturing = m.group(1) not in master_slugs
            if capturing:
                add.append(ln)
        elif capturing and ln.startswith((" ", "\t")) and ln.strip():
            add.append(ln)  # continuation line of a captured epic bullet
        else:
            capturing = False
    if not add:
        return master_pre
    idx = master_pre.rfind("## Items")
    return master_pre[:idx] + "".join(add) + "\n" + master_pre[idx:]


def merge_backlogs(master_text: str, ours_text: str, base_text: str | None = None) -> str:
    """Merge our BACKLOG.md onto the latest master without clobbering concurrent
    edits. With ``base_text`` (the shared checkout's HEAD copy) this is a 3-way
    merge: master wins for items we did not touch, our block wins for items only
    we changed (including backward moves like an unblock), and a true both-sides
    conflict falls back to the higher lifecycle rank (master on ties). Without a
    base, falls back to rank-only merging. Items only we have are appended."""
    master_pre, master_blocks = _split_backlog(master_text)
    ours_pre, ours_blocks = _split_backlog(ours_text)
    if not master_blocks:
        return ours_text  # master has no parseable Items section; fall back to ours
    base_blocks: dict[str, str] | None = None
    if base_text is not None:
        base_blocks = {bid: blk.rstrip("\n") for bid, blk in _split_backlog(base_text)[1]}
    merged: dict[str, str] = {}
    order: list[str] = []
    for bid, blk in master_blocks:
        merged[bid] = blk
        order.append(bid)
    for bid, blk in ours_blocks:
        if bid not in merged:
            merged[bid] = blk
            order.append(bid)
            continue
        if base_blocks is not None and bid in base_blocks:
            base_blk = base_blocks[bid]
            if blk.rstrip("\n") == base_blk:
                continue  # we never touched it; master is authoritative
            if merged[bid].rstrip("\n") == base_blk:
                merged[bid] = blk  # only we changed it (advance, unblock, or edit)
                continue
            # both sides changed it: higher lifecycle rank wins, master on ties
        if _block_status_rank(blk) > _block_status_rank(merged[bid]):
            merged[bid] = blk
    pre = _merge_preamble(master_pre, ours_pre)
    body = "\n\n".join(merged[bid].rstrip("\n") for bid in order)
    return pre.rstrip("\n") + "\n\n" + body + "\n"


def publish_to_master(backlog_path: Path, msg: str) -> None:
    """Persist BACKLOG.md to specs master via a throwaway worktree, so we never
    commit in the shared specs checkout (a concurrent session may have it on
    another branch). The shared copy is MERGED onto latest master (see
    merge_backlogs), not copied over it, so concurrent publishes never clobber
    each other."""
    specs = REPO_PATHS["specs"]
    wt = os.path.join(specs, "..", ".backlog-publish-wt")

    def git(args, cwd=specs):
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)

    git(["worktree", "remove", "--force", wt])  # clear any stale worktree
    git(["fetch", "origin", "-q"])
    # 3-way base: the version of BACKLOG.md our working copy started from (the
    # shared checkout's HEAD). Lets the merge tell "we changed this item" apart
    # from "our copy is just stale" (CICD-4). None if unreadable -> rank-only.
    base = git(["show", "HEAD:BACKLOG.md"])
    base_text = base.stdout if base.returncode == 0 and base.stdout else None
    # Base on origin/master (the shared checkout's local master ref is stale because
    # it sits on a feature branch), detached, and push HEAD:master. One retry if a
    # concurrent push lands between fetch and push.
    try:
        for attempt in (1, 2):
            git(["worktree", "remove", "--force", wt])
            git(["fetch", "origin", "-q"])
            add = git(["worktree", "add", "--detach", wt, "origin/master"])
            if add.returncode != 0:
                sys.exit(f"publish: worktree add failed: {add.stderr.strip()}")
            master_file = os.path.join(wt, "BACKLOG.md")
            merged = merge_backlogs(
                Path(master_file).read_text(encoding="utf-8"),
                Path(backlog_path).read_text(encoding="utf-8"),
                base_text,
            )
            Path(master_file).write_text(merged, encoding="utf-8")
            git(["add", "BACKLOG.md"], cwd=wt)
            commit = git(["commit", "-m", msg], cwd=wt)
            if commit.returncode != 0:
                print(commit.stdout.strip() or commit.stderr.strip() or "nothing to publish")
                return
            push = git(["push", "origin", "HEAD:master"], cwd=wt)
            if push.returncode == 0:
                print("published to master")
                return
            if attempt == 2:
                print(f"push failed: {push.stderr.strip()}")
    finally:
        git(["worktree", "remove", "--force", wt])
        git(["worktree", "prune"])


if __name__ == "__main__":
    main()

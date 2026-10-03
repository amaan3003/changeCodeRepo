"""Capture Git changes as JSON for the documentation team. No AI or API keys."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote


class DetectionError(Exception):
    """An actionable error, such as missing Git history."""


def git(repo, *args, input_bytes=None):
    """Read this checkout without running repository scripts or external diff tools."""
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        input=input_bytes, capture_output=True,
    )
    if result.returncode:
        raise DetectionError(
            "Git could not read the repository or commit. Check --repo-dir and "
            "commit IDs. In GitHub Actions, use fetch-depth: 0; an old force-pushed "
            "commit may need to be fetched explicitly."
        )
    return result.stdout


def commit_sha(repo, ref):
    return git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()


def detect_changes(repo_dir, before=None, after="HEAD", repository=None, branch=None):
    """Return the net file changes between two commits, including multi-commit pushes."""
    repo = Path(repo_dir).resolve()
    after_sha = commit_sha(repo, after)
    repository_url = f"https://github.com/{quote(repository, safe='/')}" if repository else None

    # Local runs compare the latest commit with its first parent by default.
    # A zero SHA from GitHub means a newly created branch: compare to an empty tree.
    if before is None:
        parents = git(repo, "rev-list", "--parents", "-n", "1", after_sha).decode().split()[1:]
        before_sha = parents[0] if parents else None
    else:
        before_sha = None if before == "0" * 40 else commit_sha(repo, before)
    baseline = before_sha or git(repo, "hash-object", "-t", "tree", "--stdin", input_bytes=b"").decode().strip()

    # Null separators keep filenames with spaces, tabs, or newlines intact.
    # Renames are deliberately represented as a deletion plus an addition.
    entries = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-status", "-z", baseline, after_sha).split(b"\0")
    entries = entries[:-1] if entries[-1] == b"" else entries
    labels = {"A": "added", "M": "modified", "D": "deleted", "T": "type_changed"}
    files = []
    for index in range(0, len(entries), 2):
        status = entries[index].decode("ascii")
        path = os.fsdecode(entries[index + 1])
        # Deleted files only exist in the old commit; other links show the new version.
        file_sha = before_sha if status == "D" else after_sha
        files.append({
            "path": path,
            "status": labels.get(status, status),
            "file_url": f"{repository_url}/blob/{file_sha}/{quote(path, safe='/')}" if repository_url and file_sha else None,
        })

    raw_diff = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--no-color", "--unified=3", baseline, after_sha, "--")
    if len(raw_diff) > 2_000_000:
        raise DetectionError("Diff exceeds the 2 MB demo limit. Compare a smaller change; nothing was silently truncated.")
    if branch is None:
        branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").decode().strip()
        branch = None if branch == "HEAD" else branch
    return {
        "schema_version": 1,
        "repository": repository,
        "repository_url": repository_url,
        "commit_url": f"{repository_url}/commit/{after_sha}" if repository_url else None,
        "branch": branch,
        "before_sha": before_sha,
        "after_sha": after_sha,
        "comparison": "commits" if before_sha else "empty_tree",
        "changed_file_count": len(files),
        "files": files,
        "diff": raw_diff.decode("utf-8", errors="replace"),
        "notes": [
            "This is the net diff across the commit range, not a natural-language explanation.",
            "Renames appear as deleted and added files. Binary changes have a summary, not binary contents.",
            "Non-UTF-8 diff bytes are replaced for JSON compatibility.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", default=".", help="Path to a local Git checkout")
    parser.add_argument("--repository", help="GitHub owner/repo label (optional for local runs)")
    parser.add_argument("--before", help="Commit before the change; defaults to the push event or latest commit's parent")
    parser.add_argument("--after", help="Commit after the change; defaults to the push event or HEAD")
    parser.add_argument("--output", default=".changes/changes.json", help="JSON output path, relative to your current directory")
    args = parser.parse_args(argv)
    try:
        event = {}
        if os.environ.get("GITHUB_EVENT_NAME") == "push":
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
            if event.get("deleted"):
                print("Branch deletion: no code snapshot to analyze.")
                return 0
        payload = detect_changes(
            args.repo_dir,
            before=args.before or event.get("before") or os.environ.get("BEFORE_SHA") or None,
            after=args.after or event.get("after") or os.environ.get("GITHUB_SHA") or "HEAD",
            repository=args.repository or os.environ.get("GITHUB_REPOSITORY"),
            branch=(event.get("ref") or os.environ.get("GITHUB_REF", "")).removeprefix("refs/heads/") or None,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(f"Detected {payload['changed_file_count']} changed file(s). Handoff saved to {output.resolve()}")
        return 0
    except (DetectionError, OSError, ValueError, KeyError) as exc:
        print(f"Change detector stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

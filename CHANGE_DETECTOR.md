# GitHub change detector

This is the Python component of the documentation bot. GitHub Actions starts it on
branch pushes. It compares the code before and after the push and saves a JSON
handoff for the team working on change interpretation and documentation generation.
It does not call Gemini, access MongoDB, generate documentation, or create PRs.

## What happens on a push

1. `.github/workflows/detect-changes.yml` checks out the repository and its history.
2. GitHub provides the before/after commit IDs in the push event.
3. `main.py` compares those commits and writes `.changes/changes.json`.
4. The workflow uploads that JSON as a `repo-changes-...` artifact on the Actions run.

Open **Actions > Detect repository changes > a completed run > Artifacts** to download
the JSON. It is not automatically sent to the Deno server. A later workflow step can
read `.changes/changes.json` and pass it to the team's processing code.

The workflow runs on branch pushes, not local saves or tags. It needs to exist on the
pushed branch. In this test repo it is installed on `main`, so **Run workflow** is
also available under the workflow's Actions page for manual testing.
Only read access to the repository is needed; no API secrets or pip packages are required.

## Run locally

Requirements: Git and Python 3.11 or newer. From the repository root:

```sh
python main.py
python tests/test_change_detector.py
```

Local runs compare the latest commit to its first parent. Compare another range with:

```sh
python main.py --before BEFORE_COMMIT_SHA --after AFTER_COMMIT_SHA
```

Use `--repo-dir PATH` to inspect a different local checkout, `--repository owner/repo`
to set its label, and `--output PATH` to choose the JSON output location. The default
output is `.changes/changes.json`, relative to the current working directory. The
script runs once and exits; GitHub Actions supplies the automatic trigger.

## JSON handoff

- `schema_version`: 1.
- `repository`: owner/repo from GitHub, or an optional local label.
- `repository_url`: clickable GitHub repository location, or null without a repository label.
- `commit_url`: link to the exact new commit, or null without a repository label.
- `branch`: event branch, local branch, or null for a detached local checkout.
- `before_sha`, `after_sha`: compared commits.
- `comparison`: `commits`, or `empty_tree` for a new branch/initial snapshot.
- `changed_file_count`: number of files with net changes.
- `files`: objects with `path`, `status`, and `file_url`. `path` is the location inside
  the repository, such as `server/main.ts`. `file_url` links to that file at the exact
  compared commit. For deleted files, it links to the old commit where the file existed.
  Links are null without a repository label; spaces and special URL characters are encoded.
- `diff`: raw unified Git diff with added and removed lines.
- `notes`: interpretation details.

For a multi-commit push, the JSON includes the net change across the whole push.
Changes that cancel each other out inside that range do not appear in the net diff.
New branches have no before commit, so every current file is reported as added.
Renames appear as deletion plus addition. Binary files have a change summary, without
their contents. Non-UTF-8 diff bytes use replacement characters. Uncommitted changes
are not included. Diffs above 2 MB fail explicitly instead of being silently truncated.

The workflow tries to fetch old force-push baselines; if GitHub no longer makes an
old commit available, the run fails with a missing-history error. Branch deletion is
skipped. The JSON contains raw repository changes, so treat it like the source code.

References: [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
[artifact uploads](https://github.com/actions/upload-artifact).

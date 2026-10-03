# Change detector demo

Every branch push runs the Python change detector through GitHub Actions.
The detector compares the commits before and after the push and saves a JSON report.
There is no Gemini or MongoDB integration in this component.

## Try it in your browser

1. Open `demo.txt` on the `main` branch.
2. Click the pencil, change the text, and commit directly to `main`.
3. Open **Actions > Detect repository changes** and select the newest run.
4. Wait for the green check, then download the **repo-changes-...** artifact.
5. Extract `changes.json`. Look for `demo.txt`, its `modified` status, and the old/new lines in `diff`.

The report also includes the repository name, repository URL, commit URL, and a direct
link for each changed file. Deleted-file links point to the previous commit.

Your teammates can feed the JSON into their documentation-processing component.
The workflow saves an artifact; it does not automatically call their server.

## Run locally

Requires Git and Python 3.11+. No pip packages or API keys are needed.

```sh
python main.py --repository amaan3003/changeCodeRepo
python tests/test_change_detector.py
```

Output: `.changes/changes.json`. See `CHANGE_DETECTOR.md` for the JSON fields and comparison behaviour.

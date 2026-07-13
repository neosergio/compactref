# Releasing

Publishing a GitHub Release publishes to PyPI. A tag on its own does
nothing, so a stray `git push --tags` cannot ship a version by accident.

PyPI version numbers are immutable. A version that uploads half-finished,
or uploads wrong, cannot be replaced — only yanked and superseded. Hence
the rehearsal below.

## 1. Bump the version in both places

The version is declared twice:

- `pyproject.toml` — what PyPI actually publishes.
- `src/compactref/__init__.py` — `__version__`, what the package reports
  about itself.

They must agree with the release tag. The publish workflow refuses to
upload otherwise, which is the point: a wheel whose metadata contradicts
its own `__version__` is worse than a failed release.

## 2. Write the changelog entry

Add a section to [CHANGELOG.md](CHANGELOG.md). If the release changes
what an existing reference resolves to, say so in bold: callers store
these in databases.

## 3. Merge to `main`

CI must be green. The package job builds the wheel, installs it somewhere
with no source tree to fall back on, and makes it produce a reference —
so a wheel that builds but does not work fails here rather than on PyPI.

## 4. Check the Trusted Publisher (first release, or after any change)

PyPI and TestPyPI are separate services with separate accounts, separate
projects and separate publisher configs. A publisher registered on one
grants nothing on the other, and the `environment` claim differs between
them. **Each has to be configured, and verified, on its own — run this
twice:**

Actions → **Verify publish setup** → Run workflow → `environment`:

| Run | Checks the publisher at | Do it before |
| --- | --- | --- |
| `testpypi` | https://test.pypi.org/manage/project/compactref/settings/publishing/ | the rehearsal in step 5 |
| `pypi` | https://pypi.org/manage/project/compactref/settings/publishing/ | the release in step 6 |

Verifying only `pypi` leaves the rehearsal to fail on an unconfigured
TestPyPI publisher, and verifying only `testpypi` leaves the same trap
waiting on the release itself, where it is far more expensive.

Neither run uploads anything. Each prints the claims GitHub will send to
that index — including the `environment`, which differs between the two —
so you can compare them against the form.

The publisher form wants the workflow *file name*, `publish.yml`, not the
`name:` inside it. Leaving the environment box blank while the job
declares one is the usual cause of `invalid-publisher`.

## 5. Rehearse on TestPyPI

Actions → **Publish** → Run workflow → `target`: `testpypi`.

(The two workflows name this input differently: **Verify publish setup**
takes `environment`, **Publish** takes `target`.)

This runs the same build and the same upload path against a throwaway
index. `skip-existing` is set, so re-running a version already up there
skips rather than failing on the upload.

Then install what it published, from a clean environment:

```bash
pip install --index-url https://test.pypi.org/simple/ compactref==X.Y.Z
```

## 6. Cut the release

Draft a GitHub Release, tag it `vX.Y.Z`, check it over, and publish.

That fires `publish.yml`, which verifies the tag against `pyproject.toml`
and `__version__`, builds, runs `twine check --strict`, and uploads to
PyPI through Trusted Publishing. No API token is stored in the repository.

## If the upload fails

`invalid-publisher: valid token, but no corresponding publisher` means the
index received a good token and found nobody vouching for it — the
publisher config does not match the claims. Step 4 prints both sides.

An OIDC failure *after* a successful Trusted Publishing flow (a 504 on the
attestation step, say) is transient. Check whether the version landed
before re-running:

```bash
curl -s https://pypi.org/pypi/compactref/json | python -c \
  "import json,sys; print(sorted(json.load(sys.stdin)['releases']))"
```

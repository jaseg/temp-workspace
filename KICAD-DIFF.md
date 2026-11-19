# Visual KiCad diff (downstream addition)

This fork of Forgejo shows KiCad files (`.kicad_sch`, `.kicad_pcb`, `.kicad_sym`, `.kicad_mod`) in
commit, compare and pull request diffs with the [kicad-diff](../../tree/claude/determined-lamport-s6gkox)
viewer: a semantic visual diff that sorts changes into electrical, value/property and layout
changes. The usual source diff stays one click away (the "source"/"rendered" toggle).

## Building

The feature is compiled in with the `kicaddiff` build tag:

```bash
make TAGS="bindata sqlite sqlite_unlock_notify kicaddiff" build
```

Without the tag, nothing changes: KiCad files get the normal text diff and the viewer's
JavaScript chunk is never loaded.

## What the patch changes

New files:

- `modules/kicaddiff/`: `IsKiCadFile` and the `Enabled` build-tag switch
- `routers/web/repo/compare_kicad.go`: template data for the viewer; files are fetched from
  `/{owner}/{repo}/media/commit/{sha}/{path}` so LFS-tracked files work
- `templates/repo/diff/kicad_diff.tmpl`: `<lazy-webc tag="kicad-diff" old-src=… new-src=…>`
- `web_src/js/vendor/kicad-diff/`: the viewer, synced with `build/sync-kicad-diff.sh`
- `web_src/css/features/kicad-diff.css`: maps the viewer's colours onto the Forgejo theme
- `tests/e2e/kicad-diff.test.e2e.ts` and `tests/e2e/kicad-diff/`: end-to-end test and fixtures

One-line hooks in existing files:

- `routers/web/repo/compare.go`: `setKiCadCompareContext(…)` in `setCompareContext`
- `templates/repo/diff/box.tmpl`: `$isKiCad` joins `$showFileViewToggle`, plus an `else if` branch
- `web_src/js/webcomponents/lazy-webc.js`: registers the lazily loaded `kicad-diff` element
- `web_src/css/index.css`: imports the CSS file
- `tests/e2e/declare_repos_test.go`: declares the `kicad-diff-test` repository

## Updating the viewer

```bash
build/sync-kicad-diff.sh <path to a kicad-diff checkout>
```

The copied version is recorded in `web_src/js/vendor/kicad-diff/VERSION`.

## Moving to a new Forgejo release

The first commit of this branch is the plain tree of a Forgejo release, imported without history.
To move to a newer release, create a commit with that release's tree and cherry-pick the commits
after the import onto it; conflicts can only occur in the hooks listed above.

## Testing

```bash
go test -tags kicaddiff ./modules/kicaddiff
make TEST_TAGS="sqlite sqlite_unlock_notify kicaddiff" test-e2e-sqlite#kicad-diff.test.e2e.ts
```

## Known limitation

Inherited from Forgejo: for pull requests from forks, both versions are fetched from the head
repository (the same applies to the image diff), so LFS files of the base may not resolve.

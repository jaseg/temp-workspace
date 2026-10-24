# BeatSaverVoting for Beat Saber 1.44.1

[Top-Cat/BeatSaverVoting](https://github.com/Top-Cat/BeatSaverVoting) (MIT), imported as a squashed subtree from
upstream `master` at `5616be4` (targets 1.41.1; the last BeatMods release, 2.4.6, stops at 1.40.8). It adds
BeatSaver up/downvote buttons and the map's rating to the results screen, and vote icons to the level list.

Changes against upstream:

- `BeatSaverVoting.csproj` is an SDK-style project that builds against the 1.44.1 assemblies in `mod/refs`
  (see `mod/README.md`); set `BeatSaberRefs` to use another location.
- `manifest.json`: game version 1.44.1.
- `VotingUI.cs`: a vote that fails with an HTTP status not in the error table shows "Error <code>" instead of
  throwing.

Everything the mod binds by name at runtime (the `LevelListTableCell.SetDataFromLevelAsync` patch and its parameter
names, `_favoritesBadgeImage`, `LevelCollectionTableView._tableView`, `ButtonStaticAnimations` clips,
`PlatformLeaderboardsModel._platform`) is unchanged in 1.44.1.

## Build and install

```sh
dotnet build ports/BeatSaverVoting/BeatSaverVoting -c Release
```

Copy `bin/Release/net472/BeatSaverVoting.dll` into the instance's `Plugins/`; it loads on the next game start.
Checked on the Frame (2026-10-24): the rating shows on the results screen and voting works.

To pull a newer upstream:
`git subtree pull --prefix=ports/BeatSaverVoting https://github.com/Top-Cat/BeatSaverVoting.git master --squash`.

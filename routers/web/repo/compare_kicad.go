// Copyright 2026 The kicad-diff Authors.
// SPDX-License-Identifier: GPL-3.0-or-later

package repo

import (
	"net/url"

	"forgejo.org/modules/git"
	"forgejo.org/modules/kicaddiff"
	"forgejo.org/modules/setting"
	"forgejo.org/services/context"
	"forgejo.org/services/gitdiff"
)

// mediaCommitURL is the URL prefix of files at a commit, served with LFS content resolved.
func mediaCommitURL(owner, name string, commit *git.Commit) string {
	return setting.AppSubURL + "/" + url.PathEscape(owner) + "/" + url.PathEscape(name) + "/media/commit/" + url.PathEscape(commit.ID.String())
}

// setKiCadCompareContext sets the context data used by the visual KiCad diff (repo/diff/kicad_diff).
func setKiCadCompareContext(ctx *context.Context, before, head *git.Commit, headOwner, headName string) {
	ctx.Data["IsKiCadFile"] = func(diffFile *gitdiff.DiffFile) bool {
		return kicaddiff.IsKiCadFile(diffFile.Name)
	}
	if !kicaddiff.Enabled {
		return
	}
	ctx.Data["KiCadMediaPath"] = mediaCommitURL(headOwner, headName, head)
	if before != nil {
		ctx.Data["KiCadBeforeMediaPath"] = mediaCommitURL(headOwner, headName, before)
	}
}

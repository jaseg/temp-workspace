// Copyright 2026 The kicad-diff Authors.
// SPDX-License-Identifier: GPL-3.0-or-later

// Package kicaddiff decides which files get the visual KiCad diff in diff views.
// It is compiled in with the "kicaddiff" build tag (TAGS="... kicaddiff").
package kicaddiff

import (
	"path"
	"strings"
)

// IsKiCadFile reports whether a file is shown with the visual KiCad diff.
func IsKiCadFile(name string) bool {
	if !Enabled {
		return false
	}
	switch strings.ToLower(path.Ext(name)) {
	case ".kicad_sch", ".kicad_pcb", ".kicad_sym", ".kicad_mod":
		return true
	}
	return false
}

// Copyright 2026 The kicad-diff Authors.
// SPDX-License-Identifier: GPL-3.0-or-later

package kicaddiff

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestIsKiCadFile(t *testing.T) {
	for name, kicad := range map[string]bool{
		"board.kicad_pcb":           true,
		"hw/Main Sheet.KICAD_SCH":   true,
		"lib/parts.kicad_sym":       true,
		"lib/fp.pretty/R.kicad_mod": true,
		"board.kicad_pro":           false,
		"README.md":                 false,
	} {
		assert.Equal(t, kicad && Enabled, IsKiCadFile(name), name)
	}
}

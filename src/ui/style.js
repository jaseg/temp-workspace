// Shared stylesheet of the <kicad-diff> UI. Colours are CSS custom properties (--kd-*) so a host
// page (e.g. Forgejo) can map them onto its own theme.

export const STYLE = `
:host {
  --kd-bg: #ffffff; --kd-fg: #1f2328; --kd-muted: #656d76; --kd-border: #d0d7de; --kd-panel: #f6f8fa;
  --kd-accent: #0969da; --kd-hover: rgba(127, 127, 127, .12); --kd-warn-bg: #fff8c5; --kd-warn-fg: #6a4b00;
  --kd-electrical: #e6177a; --kd-metadata: #e08600; --kd-layout: #2a9fb8;
  --kd-font: system-ui, -apple-system, "Segoe UI", sans-serif;
  display: flex; flex-direction: column; min-height: 320px; height: 100%;
  font: 13px/1.4 var(--kd-font); color: var(--kd-fg); background: var(--kd-bg);
  border: 1px solid var(--kd-border); border-radius: 6px; overflow: hidden;
}
:host([data-ui-theme="dark"]) {
  --kd-bg: #0d1117; --kd-fg: #e6edf3; --kd-muted: #8d96a0; --kd-border: #30363d; --kd-panel: #161b22;
  --kd-accent: #4493f8; --kd-warn-bg: #3b2e00; --kd-warn-fg: #f2cc60;
  --kd-electrical: #ff4fa3; --kd-metadata: #ffb020; --kd-layout: #47c6e0;
}
* { box-sizing: border-box; }
button, select, input { font: inherit; color: inherit; }
.toolbar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 6px 8px; border-bottom: 1px solid var(--kd-border); background: var(--kd-panel); }
.toolbar .spacer { flex: 1; }
.seg { display: inline-flex; border: 1px solid var(--kd-border); border-radius: 6px; overflow: hidden; }
.seg button { border: 0; border-right: 1px solid var(--kd-border); background: transparent; padding: 3px 10px; cursor: pointer; }
.seg button:last-child { border-right: 0; }
.seg button[aria-pressed="true"] { background: var(--kd-accent); color: #fff; }
.btn { border: 1px solid var(--kd-border); border-radius: 6px; background: var(--kd-bg); padding: 3px 10px; cursor: pointer; }
.btn:hover, .seg button:hover:not([aria-pressed="true"]) { background: var(--kd-hover); }
.btn:disabled { opacity: .5; cursor: default; }
.banner { padding: 6px 10px; background: var(--kd-warn-bg); color: var(--kd-warn-fg); border-bottom: 1px solid var(--kd-border); }
.banner:empty { display: none; }
.main { flex: 1; display: flex; min-height: 0; }
.views { flex: 1; display: flex; min-width: 0; position: relative; }
.views kd-viewport { flex: 1; min-width: 0; }
.views kd-viewport + kd-viewport { border-left: 1px solid var(--kd-border); }
.views .caption { position: absolute; top: 6px; padding: 1px 6px; border-radius: 4px; font-size: 11px; background: var(--kd-panel); color: var(--kd-muted); border: 1px solid var(--kd-border); pointer-events: none; }
.side { width: 260px; flex: none; border-left: 1px solid var(--kd-border); background: var(--kd-panel); overflow: auto; display: flex; flex-direction: column; }
.side section { padding: 8px; border-bottom: 1px solid var(--kd-border); }
.side h3 { margin: 0 0 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--kd-muted); }
.layers label { display: flex; align-items: center; gap: 6px; padding: 1px 0; cursor: pointer; white-space: nowrap; }
.swatch { width: 12px; height: 12px; border-radius: 2px; flex: none; border: 1px solid rgba(127,127,127,.4); }
.empty { padding: 24px; color: var(--kd-muted); }
.pick { display: grid; grid-template-columns: auto 1fr; gap: 6px 10px; align-items: center; max-width: 520px; }
.hidden { display: none !important; }
@media (max-width: 700px) {
  .main { flex-direction: column; }
  .side { width: auto; max-height: 40%; border-left: 0; border-top: 1px solid var(--kd-border); }
}
`;

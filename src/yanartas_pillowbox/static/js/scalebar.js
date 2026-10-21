// Scale bar for the 2D previews (their views are in mm): a bar about SPAN px long, as long as
// a round length (1, 2 or 5 times a power of ten mm), labelled, in the stage's corner.

const SPAN = 110; // px: the bar's length, about

/** A scale bar for a preview's stage (absolutely placed: the stage is position: relative). */
export function scaleBar() {
  const el = document.createElement("div");
  el.className = "scalebar";
  el.setAttribute("aria-hidden", "true");
  el.innerHTML = '<span class="label"></span><span class="bar"></span>';
  el.hidden = true;
  return el;
}

/** Show the scale for `mmPerPx` (mm per screen pixel; none: hidden). */
export function updateScaleBar(el, mmPerPx) {
  if (!(mmPerPx > 0) || !Number.isFinite(mmPerPx)) {
    el.hidden = true;
    return;
  }
  const want = SPAN * mmPerPx;
  const p = 10 ** Math.floor(Math.log10(want));
  const length = [5, 2, 1].map((k) => k * p).find((v) => v <= want) ?? p;
  el.querySelector(".bar").style.width = `${length / mmPerPx}px`;
  el.querySelector(".label").textContent = length >= 1 ? `${length} mm` : `${+(length * 1000).toFixed(0)} µm`;
  el.hidden = false;
}

/** Its styles, for the previews' shadow roots. */
export const SCALEBAR_STYLE = `
  .scalebar { position: absolute; left: 10px; bottom: 8px; display: flex; flex-direction: column;
              align-items: flex-start; gap: 2px; pointer-events: none; font-size: 11px;
              color: var(--text-muted); font-family: var(--mono, monospace); }
  .scalebar[hidden] { display: none; }
  .scalebar .bar { height: 5px; border: 1.5px solid var(--text-muted); border-top: none; }
`;

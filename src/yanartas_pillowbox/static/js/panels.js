// Panel layout: draggable dividers between the panels (role="separator", also moved with the
// arrow keys; double-click resets) and maximizing one preview to fill the layout area (its
// header button, or Escape, restores). Divider positions are remembered per viewer in
// localStorage when it is available. The previews refit through their own ResizeObservers.

const KEY = "pb-layout";
const MIN = 160; // px: the smallest a preview panel gets
const STEP = 16; // px per arrow key press (Shift: 4×)

// Per divider (data-split): the axis it resizes along, the smallest sizes of the panels
// before and after it, and how the size is applied. The sidebar keeps its width in px when
// the window resizes; the others keep the first panel's share of the space.
const SPLITS = {
  sidebar: { axis: "x", min: [240, 320], px: true },
  previews: { axis: "y", min: [MIN, MIN] },
  lower: { axis: "x", min: [MIN, MIN] },
};

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {}; // (no storage in private windows, sandboxes, …)
  }
}

function save(sizes) {
  try {
    localStorage.setItem(KEY, JSON.stringify(sizes));
  } catch {
    // (sizes then last only as long as the page)
  }
}

/** Set up the dividers and maximizing inside `layout` (the <main> holding the panels). */
export function initPanels(layout) {
  const sizes = load();
  for (const splitter of layout.querySelectorAll(".splitter")) {
    initSplitter(splitter, sizes);
  }

  layout.addEventListener("pb-maximize", (e) => {
    maximize(layout, e.target.hasAttribute("maximized") ? null : e.target);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !e.defaultPrevented && layout.dataset.maximized) {
      maximize(layout, null);
    }
  });
}

/** Show `panel` alone in the layout area, or (null) all panels again. */
function maximize(layout, panel) {
  layout.querySelector("[maximized]")?.removeAttribute("maximized");
  if (!panel) {
    delete layout.dataset.maximized;
    return;
  }
  panel.setAttribute("maximized", "");
  layout.dataset.maximized = panel.id;
  // (Stacked layout on narrow screens: the page scrolls, bring the panel into view.)
  panel.scrollIntoView({ block: "nearest" });
}

function initSplitter(splitter, sizes) {
  const name = splitter.dataset.split;
  const split = SPLITS[name];
  const prev = splitter.previousElementSibling;
  const next = splitter.nextElementSibling;
  const container = splitter.parentElement;
  const dim = split.axis === "x" ? "width" : "height";
  const client = split.axis === "x" ? "clientX" : "clientY";

  splitter.tabIndex = 0;
  splitter.setAttribute("role", "separator");
  // (A divider between columns is a vertical line.)
  splitter.setAttribute("aria-orientation", split.axis === "x" ? "vertical" : "horizontal");

  /** Current sizes of the two panels, in px. */
  const measure = () => [prev.getBoundingClientRect()[dim], next.getBoundingClientRect()[dim]];

  const apply = (value) => {
    if (value == null) {
      container.style.removeProperty(`--${name}-a`);
      container.style.removeProperty(`--${name}-b`);
    } else if (split.px) {
      // (Still clamped by CSS when the window gets narrower.)
      container.style.setProperty(`--${name}-a`, `clamp(${split.min[0]}px, ${value}px, `
        + `max(${split.min[0]}px, 100% - var(--split) - ${split.min[1]}px))`);
    } else {
      container.style.setProperty(`--${name}-a`, `${value}fr`);
      container.style.setProperty(`--${name}-b`, `${1 - value}fr`);
    }
  };

  /** Give the first panel `a` px of the `total` both share. */
  const resize = (a, total) => {
    const [minA, minB] = split.min;
    a = Math.round(Math.min(Math.max(a, minA), Math.max(minA, total - minB)));
    sizes[name] = split.px ? a : a / total;
    apply(sizes[name]);
    updateAria();
  };

  const updateAria = () => {
    const [a, b] = measure();
    const total = a + b;
    if (!total) return; // (hidden: stacked or maximized)
    const pct = (v) => Math.round((v / total) * 100);
    splitter.setAttribute("aria-valuemin", pct(split.min[0]));
    splitter.setAttribute("aria-valuemax", pct(Math.max(split.min[0], total - split.min[1])));
    splitter.setAttribute("aria-valuenow", pct(a));
  };

  apply(sizes[name]);
  splitter.addEventListener("focus", updateAria);

  let drag = null; // {pos, a, total} where the drag started
  splitter.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault(); // (no text selection while dragging)
    splitter.setPointerCapture(e.pointerId);
    const [a, b] = measure();
    drag = { pos: e[client], a, total: a + b };
    splitter.classList.add("dragging");
    splitter.focus({ preventScroll: true });
  });
  splitter.addEventListener("pointermove", (e) => {
    if (drag && splitter.hasPointerCapture(e.pointerId)) {
      resize(drag.a + e[client] - drag.pos, drag.total);
    }
  });
  const end = () => {
    if (!drag) return;
    drag = null;
    splitter.classList.remove("dragging");
    save(sizes);
  };
  splitter.addEventListener("pointerup", end);
  splitter.addEventListener("pointercancel", end);
  splitter.addEventListener("lostpointercapture", end);

  splitter.addEventListener("dblclick", () => {
    delete sizes[name];
    apply(null);
    save(sizes);
    requestAnimationFrame(updateAria); // (after the layout settles)
  });

  splitter.addEventListener("keydown", (e) => {
    const [a, b] = measure();
    const step = e.shiftKey ? STEP * 4 : STEP;
    const back = split.axis === "x" ? "ArrowLeft" : "ArrowUp";
    const forward = split.axis === "x" ? "ArrowRight" : "ArrowDown";
    let to;
    if (e.key === back) to = a - step;
    else if (e.key === forward) to = a + step;
    else if (e.key === "Home") to = 0;
    else if (e.key === "End") to = a + b;
    else return;
    e.preventDefault();
    resize(to, a + b);
    save(sizes);
  });
}

const ICONS = {
  // (Arrows out to the corners; in from them to restore.)
  maximize: '<path d="M9 2.5h4.5V7M7 13.5H2.5V9M13.5 2.5 9.5 6.5M2.5 13.5l4-4"/>',
  restore: '<path d="M14 6.5H9.5V2M2 9.5h4.5V14M9.5 6.5 14 2.5M6.5 9.5 2 13.5"/>',
};

/** Maximize/restore button for a preview's header: asks the layout (pb-maximize event) and
 *  follows the host's `maximized` attribute, which the layout sets. */
export function maximizeButton(host) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "max";
  button.setAttribute("aria-label", "Maximize");
  const sync = () => {
    const on = host.hasAttribute("maximized");
    button.setAttribute("aria-pressed", String(on));
    button.title = on ? "Restore (Esc)" : "Maximize";
    button.innerHTML = `<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor"
      stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${ICONS[on ? "restore" : "maximize"]}</svg>`;
  };
  sync();
  new MutationObserver(sync).observe(host, { attributes: true, attributeFilter: ["maximized"] });
  button.addEventListener("click", () => {
    host.dispatchEvent(new CustomEvent("pb-maximize", { bubbles: true, composed: true }));
  });
  return button;
}

/** Styles for maximizeButton(), for the previews' shadow roots. */
export const MAXIMIZE_STYLE = `
  button.max { display: inline-grid; place-items: center; padding: 2px 5px; }
  button.max svg { position: static; width: 14px; height: 1.4em; display: block; }
`;

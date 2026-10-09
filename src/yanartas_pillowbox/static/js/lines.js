// Line styles shared by the previews: every line is black and the types differ only in
// dashing (matching the SVG export). Dash patterns here are in screen pixels.

export const LINE_STYLES = {
  cut: { label: "Cut", dash: null },
  mountain: { label: "Mountain fold", dash: [9, 4.5, 1.5, 4.5] }, // dash-dot
  valley: { label: "Valley fold", dash: [9, 6] }, // dashed
};

/** Small inline SVG showing a line style, for legends. */
export function lineSwatch(dash, width = 30) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("width", width);
  svg.setAttribute("height", 8);
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("swatch");
  const line = document.createElementNS(NS, "line");
  Object.entries({ x1: 0, y1: 4, x2: width, y2: 4, stroke: "currentColor", "stroke-width": 1.6 })
    .forEach(([k, v]) => line.setAttribute(k, v));
  if (dash) line.setAttribute("stroke-dasharray", dash.join(" "));
  svg.append(line);
  return svg;
}

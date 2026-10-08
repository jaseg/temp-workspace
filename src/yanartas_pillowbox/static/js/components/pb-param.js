// <pb-param>: one labelled configuration input (number, checkbox, select, text or color)
// with unit, optional action button, help text and an inline validation message. Built from a field spec served by
// /api/defaults. Emits a bubbling "pb-change" event whenever the user edits the value.

let uid = 0;

export class PbParam extends HTMLElement {
  #spec = null;
  #input = null;
  #hex = null;
  #error = null;

  set spec(spec) {
    this.#spec = spec;
    this.#render();
  }

  get spec() {
    return this.#spec;
  }

  get name() {
    return this.#spec?.name;
  }

  /** Current value in its JSON type. Unparsable numbers are sent as the raw string so the
   *  server can report them ("must be a number") like any other validation error. */
  get value() {
    const kind = this.#spec.kind;
    if (kind === "bool") return this.#input.checked;
    if (kind === "float") {
      const raw = this.#input.value.trim();
      const n = Number(raw);
      return raw !== "" && Number.isFinite(n) ? n : this.#input.value;
    }
    if (kind === "color") return this.#hex.value.trim();
    return this.#input.value;
  }

  set value(v) {
    const kind = this.#spec.kind;
    if (kind === "bool") this.#input.checked = Boolean(v);
    else if (kind === "color") {
      this.#hex.value = v;
      if (/^#[0-9a-f]{6}$/i.test(v)) this.#input.value = v.toLowerCase();
    } else this.#input.value = v;
  }

  /** Focus the field's input and bring it into view. */
  focusInput() {
    if (this.hidden) return;
    const target = this.#spec.kind === "color" ? this.#hex : this.#input;
    target.scrollIntoView({ block: "nearest", behavior: "smooth" });
    target.focus({ preventScroll: true });
  }

  set error(message) {
    this.#error.textContent = message || "";
    this.classList.toggle("invalid", Boolean(message));
    const target = this.#spec.kind === "color" ? this.#hex : this.#input;
    if (message) target.setAttribute("aria-invalid", "true");
    else target.removeAttribute("aria-invalid");
  }

  #render() {
    const spec = this.#spec;
    const id = `pb-param-${spec.name}-${++uid}`;
    this.replaceChildren();

    const row = el("div", "row");
    const label = el("label");
    label.htmlFor = id;
    label.textContent = spec.label;
    const control = el("div", "control");
    row.append(label, control);

    const emit = () => this.dispatchEvent(new CustomEvent("pb-change", {
      bubbles: true, detail: { name: spec.name, value: this.value },
    }));

    if (spec.kind === "float") {
      const input = el("input");
      Object.assign(input, { type: "number", id, inputMode: "decimal" });
      input.step = spec.step ?? "any";
      if (spec.min !== undefined) input.min = spec.min;
      if (spec.max !== undefined) input.max = spec.max;
      input.addEventListener("input", emit);
      control.append(input);
      this.#input = input;
    } else if (spec.kind === "bool") {
      const input = el("input");
      Object.assign(input, { type: "checkbox", id });
      input.addEventListener("change", emit);
      control.append(input);
      this.#input = input;
    } else if (spec.kind === "choice") {
      const select = el("select");
      select.id = id;
      for (const c of spec.choices) select.append(new Option(c.label, c.value));
      select.addEventListener("change", emit);
      control.append(select);
      this.#input = select;
    } else if (spec.kind === "color") {
      const picker = el("input");
      Object.assign(picker, { type: "color", title: spec.label });
      picker.setAttribute("aria-label", `${spec.label} color picker`);
      const hex = el("input", "hex");
      Object.assign(hex, { type: "text", id, maxLength: 7, spellcheck: false });
      picker.addEventListener("input", () => { hex.value = picker.value.toUpperCase(); emit(); });
      hex.addEventListener("input", () => {
        if (/^#[0-9a-f]{6}$/i.test(hex.value.trim())) picker.value = hex.value.trim().toLowerCase();
        emit();
      });
      control.append(picker, hex);
      this.#input = picker;
      this.#hex = hex;
    } else {
      const input = el("input");
      Object.assign(input, { type: "text", id });
      if (spec.maxLength) input.maxLength = spec.maxLength;
      input.addEventListener("input", emit);
      control.append(input);
      this.#input = input;
    }
    if (spec.unit) control.append(Object.assign(el("span", "unit"), { textContent: spec.unit }));
    if (spec.action) {
      // Optional per-field action (e.g. "maximize"); the app decides what it does.
      const button = el("button", "action");
      Object.assign(button, { type: "button", textContent: spec.action.label, title: spec.action.title });
      button.addEventListener("click", () => this.dispatchEvent(new CustomEvent("pb-action", {
        bubbles: true, detail: { name: spec.name, action: spec.action.id },
      })));
      control.append(button);
      row.classList.add("has-action");
    }

    this.append(row);
    if (spec.help) this.append(Object.assign(el("div", "help"), { textContent: spec.help }));
    this.#error = el("div", "error");
    this.#error.id = `${id}-error`;
    this.#error.setAttribute("aria-live", "polite");
    (this.#hex ?? this.#input).setAttribute("aria-describedby", this.#error.id);
    this.append(this.#error);
  }
}

function el(tag, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return node;
}

customElements.define("pb-param", PbParam);

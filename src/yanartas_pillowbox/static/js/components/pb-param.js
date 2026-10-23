// <pb-param>: one labelled configuration input (number, text or select) with unit, optional
// action button, help text and an inline validation message. Built from a field spec served
// by /api/defaults. Emits a bubbling "pb-change" event whenever the user edits the value.

let uid = 0;

export class PbParam extends HTMLElement {
  #spec = null;
  #input = null;
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
    if (this.#spec.kind === "float") {
      const raw = this.#input.value.trim();
      const n = Number(raw);
      return raw !== "" && Number.isFinite(n) ? n : this.#input.value;
    }
    return this.#input.value;
  }

  set value(v) {
    this.#input.value = v;
  }

  /** Locked: set by something else (a preset), not editable here. */
  set locked(on) {
    this.#input.disabled = Boolean(on);
    this.classList.toggle("locked", Boolean(on));
    this.title = on ? "Set by the preset above: choose Custom to change it" : "";
  }

  get locked() {
    return this.#input.disabled;
  }

  /** Focus the field's input and bring it into view. */
  focusInput() {
    this.#input.scrollIntoView({ block: "nearest", behavior: "smooth" });
    this.#input.focus({ preventScroll: true });
  }

  set error(message) {
    this.#error.textContent = message || "";
    this.classList.toggle("invalid", Boolean(message));
    if (message) this.#input.setAttribute("aria-invalid", "true");
    else this.#input.removeAttribute("aria-invalid");
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
    } else if (spec.kind === "text") {
      const input = el("input");
      Object.assign(input, { type: "text", id, spellcheck: false, autocomplete: "off" });
      input.addEventListener("input", emit);
      control.append(input);
      this.#input = input;
    } else {
      const select = el("select");
      select.id = id;
      // Choices with a "group" go into <optgroup>s of that name, in order of appearance.
      const optgroups = new Map();
      for (const c of spec.choices) {
        if (c.group && !optgroups.has(c.group)) {
          optgroups.set(c.group, Object.assign(el("optgroup"), { label: c.group }));
          select.append(optgroups.get(c.group));
        }
        (c.group ? optgroups.get(c.group) : select).append(new Option(c.label, c.value));
      }
      select.addEventListener("change", emit);
      control.append(select);
      this.#input = select;
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
    this.#input.setAttribute("aria-describedby", this.#error.id);
    this.append(this.#error);
  }
}

function el(tag, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return node;
}

customElements.define("pb-param", PbParam);

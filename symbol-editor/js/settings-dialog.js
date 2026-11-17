// <symbol-settings>: a dialog for the symbol-wide settings (name, footprint, pin length ...).
//
// Call dialog.open(settings). On "Save" it writes into that settings object
// and fires a "settings-changed" event.

const FIELDS = [
  { key: 'name', label: 'Symbol name' },
  { key: 'reference', label: 'Reference prefix' },
  { key: 'footprint', label: 'Footprint (Library:Footprint)' },
  { key: 'datasheet', label: 'Datasheet URL' },
  { key: 'description', label: 'Description' },
  { key: 'keywords', label: 'Keywords' },
  { key: 'pinLength', label: 'Pin length (mil)', options: ['auto', '100', '200', '300'] },
  { key: 'stackPowerPins', label: 'Stack power pins that have the same name', checkbox: true },
];

class SymbolSettings extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `
      <dialog>
        <form method="dialog">
          <h2>Symbol settings</h2>
          ${FIELDS.map(fieldHtml).join('')}
          <div class="buttons">
            <button value="cancel">Cancel</button>
            <button value="save" class="primary">Save</button>
          </div>
        </form>
      </dialog>`;
    this.dialog = this.querySelector('dialog');
    this.dialog.addEventListener('close', () => {
      if (this.dialog.returnValue === 'save') this.save();
    });
  }

  open(settings) {
    this.settings = settings;
    for (const field of FIELDS) {
      const input = this.querySelector(`[name="${field.key}"]`);
      if (field.checkbox) input.checked = settings[field.key];
      else input.value = settings[field.key];
    }
    this.dialog.returnValue = '';
    this.dialog.showModal();
  }

  save() {
    for (const field of FIELDS) {
      const input = this.querySelector(`[name="${field.key}"]`);
      this.settings[field.key] = field.checkbox ? input.checked : input.value.trim();
    }
    this.dispatchEvent(new CustomEvent('settings-changed', { bubbles: true }));
  }
}

function fieldHtml(field) {
  if (field.checkbox) {
    return `<label class="checkbox"><input type="checkbox" name="${field.key}"> ${field.label}</label>`;
  }
  if (field.options) {
    const options = field.options.map(option => `<option>${option}</option>`).join('');
    return `<label>${field.label}<select name="${field.key}">${options}</select></label>`;
  }
  return `<label>${field.label}<input name="${field.key}"></label>`;
}

customElements.define('symbol-settings', SymbolSettings);

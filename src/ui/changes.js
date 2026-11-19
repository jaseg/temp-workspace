// Change list and inspector panels of <kicad-diff>.

const KIND_LABELS = { electrical: 'Electrical', metadata: 'Values & properties', layout: 'Layout' };

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== false) e.setAttribute(k, v === true ? '' : v);
  }
  e.append(...children.filter(c => c !== null && c !== undefined));
  return e;
}

/**
 * Change list with kind filters, previous/next navigation and visited marking.
 * `onSelect(change)` is called when a change is selected; `onFilter()` when filters change.
 */
export function createChangeList(container, { onSelect, onFilter }) {
  const state = { changes: [], filters: { electrical: true, metadata: true, layout: true, minor: true }, visited: new Set(), selected: null };
  const header = el('h3');
  const nav = el('div', { class: 'nav' },
    el('button', { class: 'btn', title: 'Previous change (p)', onclick: () => step(-1) }, '↑ Prev'),
    el('button', { class: 'btn', title: 'Next change (n)', onclick: () => step(1) }, 'Next ↓'));
  const filters = el('div', { class: 'filters' });
  const list = el('ol', { class: 'change-list' });
  container.replaceChildren(header, nav, filters, list);

  const visible = () => state.changes.filter(c => state.filters[c.kind] && (state.filters.minor || !c.minor));

  function renderFilters() {
    const count = pred => state.changes.filter(pred).length;
    filters.replaceChildren(...[...Object.keys(KIND_LABELS), 'minor'].map(k => {
      const n = k === 'minor' ? count(c => c.minor) : count(c => c.kind === k);
      const box = el('input', { type: 'checkbox', checked: state.filters[k], onchange: e => {
        state.filters[k] = e.target.checked;
        render();
        onFilter?.();
      } });
      return el('label', { class: `filter ${k}` }, box, el('span', { class: `dot ${k}` }), `${k === 'minor' ? 'Minor' : KIND_LABELS[k]} (${n})`);
    }));
  }

  function render() {
    const shown = visible();
    header.textContent = state.changes.length ? `Changes (${shown.length} of ${state.changes.length})` : 'No changes';
    list.replaceChildren(...shown.map(c => el('li', {
      class: ['change', c.kind, c.minor && 'minor', state.visited.has(c.id) && 'visited', state.selected === c.id && 'selected'].filter(Boolean).join(' '),
      'data-id': c.id,
      title: c.details.join('\n') || undefined,
      onclick: () => select(c.id),
    }, el('span', { class: `dot ${c.kind}` }), el('span', { class: 'text' }, c.summary))));
  }

  function select(id, { notify = true } = {}) {
    state.selected = id;
    if (id !== null) state.visited.add(id);
    render();
    list.querySelector('.selected')?.scrollIntoView({ block: 'nearest' });
    if (notify) onSelect?.(state.changes.find(c => c.id === id) ?? null);
  }

  function step(dir) {
    const shown = visible();
    if (!shown.length) return;
    const i = shown.findIndex(c => c.id === state.selected);
    const next = i < 0 ? (dir > 0 ? 0 : shown.length - 1) : (i + dir + shown.length) % shown.length;
    select(shown[next].id);
  }

  return {
    state,
    visible,
    select,
    step,
    setChanges(changes) {
      state.changes = changes;
      state.selected = null;
      state.visited.clear();
      renderFilters();
      render();
    },
  };
}

/** Inspector: a concise description of the selected change, or of a clicked element. */
export function renderInspector(container, { change, item, related = [] }) {
  const parts = [];
  if (change) {
    parts.push(el('div', { class: 'badges' },
      el('span', { class: `badge ${change.kind}` }, KIND_LABELS[change.kind]),
      change.minor ? el('span', { class: 'badge minor' }, 'minor') : null,
      el('span', { class: 'badge op' }, change.op)));
    parts.push(el('p', { class: 'summary' }, change.summary));
    if (change.details.length) parts.push(el('ul', {}, ...change.details.map(d => el('li', {}, d))));
    if (change.net) parts.push(el('p', { class: 'muted' }, `Net: ${change.net}`));
  } else if (item) {
    const name = item.ref ? `${item.ref}${item.pin ? ` pin ${item.pin}${item.pinName && item.pinName !== '~' ? ` (${item.pinName})` : ''}` : item.pad ? ` pad ${item.pad}` : item.field ? ` ${item.field}` : ''}` : item.name ?? item.text ?? item.kind;
    parts.push(el('p', { class: 'summary' }, `${name}`));
    const facts = [['Type', item.kind], ['Value', item.value], ['Symbol', item.libId], ['Net', item.net], ['Layer', item.layer]].filter(([, v]) => v);
    parts.push(el('dl', {}, ...facts.flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, String(v))])));
    parts.push(el('p', { class: 'muted' }, related.length ? `${related.length} change${related.length > 1 ? 's' : ''} involve this element:` : 'Unchanged.'));
    if (related.length) parts.push(el('ul', {}, ...related.map(c => el('li', {}, c.summary))));
  } else {
    parts.push(el('p', { class: 'muted' }, 'Select a change, or click an element.'));
  }
  container.replaceChildren(el('h3', {}, 'Details'), ...parts);
}

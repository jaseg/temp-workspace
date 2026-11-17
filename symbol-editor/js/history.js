// Undo and redo, by keeping copies of the whole state as JSON text.
// Typing in a cell changes the state on every key press; changes made while
// typing less than a second apart are merged into one undo step.

const LIMIT = 200;
const MERGE_WINDOW_MS = 1000;

export class History {
  constructor(state) {
    this.undoStack = [JSON.stringify(state)]; // the last entry is the current state
    this.redoStack = [];
    this.lastTyping = 0;
  }

  record(state, typing = false) {
    const snapshot = JSON.stringify(state);
    if (snapshot === this.undoStack.at(-1)) return;
    const now = Date.now();
    const merge = typing && now - this.lastTyping < MERGE_WINDOW_MS && this.undoStack.length > 1;
    if (merge) this.undoStack.pop();
    this.lastTyping = typing ? now : 0;
    this.undoStack.push(snapshot);
    if (this.undoStack.length > LIMIT) this.undoStack.shift();
    this.redoStack = [];
  }

  // Both return the state to show, or null if there is nothing to undo/redo.
  undo() {
    if (this.undoStack.length < 2) return null;
    this.redoStack.push(this.undoStack.pop());
    return JSON.parse(this.undoStack.at(-1));
  }

  redo() {
    if (this.redoStack.length === 0) return null;
    this.undoStack.push(this.redoStack.pop());
    return JSON.parse(this.undoStack.at(-1));
  }
}

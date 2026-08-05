// Runs editor.js against a stub DOM and exercises it.
//
// This exists because a syntax check is not enough. An edit once deleted
// half the file's functions and the result still PARSED cleanly - missing
// definitions are a runtime error, not a parse error - so the editor
// shipped broken while the check said it was fine.
//
// The stub keeps real sibling links, so block editing can be tested for
// what it actually does: splitting, merging, escaping a code block, and
// removing a divider.
//
//   node tests/editor_harness.mjs

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import assert from "node:assert";

const root = path.dirname(new URL(import.meta.url).pathname);
const source = fs.readFileSync(
  path.join(root, "..", "bootpages", "static", "editor.js"), "utf8");

// ------------------------------------------------------------ stub DOM

function element(tag = "div", id = "") {
  const node = {
    tag, id,
    children: [],
    parentElement: null,
    dataset: {},
    style: {},
    classList: {add() {}, remove() {}},
    className: "",
    innerHTML: "",
    textContent: "",
    value: "",
    hidden: true,
    disabled: false,
    placeholder: "",
    onclick: null,
    selectionStart: 0,
    selectionEnd: 0,
    scrollHeight: 20,

    get firstElementChild() { return this.children[0] || null; },

    get previousElementSibling() {
      if (!this.parentElement) return null;
      const at = this.parentElement.children.indexOf(this);
      return at > 0 ? this.parentElement.children[at - 1] : null;
    },

    get nextElementSibling() {
      if (!this.parentElement) return null;
      const at = this.parentElement.children.indexOf(this);
      return this.parentElement.children[at + 1] || null;
    },

    get nextSibling() { return this.nextElementSibling; },

    appendChild(child) {
      child.parentElement = this;
      this.children.push(child);
      return child;
    },

    insertBefore(child, ref) {
      child.parentElement = this;
      const at = this.children.indexOf(ref);
      if (at < 0) this.children.push(child);
      else this.children.splice(at, 0, child);
      return child;
    },

    remove() {
      if (!this.parentElement) return;
      const at = this.parentElement.children.indexOf(this);
      if (at >= 0) this.parentElement.children.splice(at, 1);
      this.parentElement = null;
    },

    closest(selector) {
      const want = selector.replace(/^[.#]/, "");
      let at = this;
      while (at) {
        if (at.className === want || at.id === want) return at;
        at = at.parentElement;
      }
      return null;
    },

    querySelector(selector) {
      if (selector === "textarea") {
        return this.children.find((c) => c.tag === "textarea") || null;
      }
      return element();
    },

    querySelectorAll: () => [],
    focus() { context.focused = this; },
    setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b; },
    addEventListener() {},
    getBoundingClientRect: () => ({top: 0, left: 0}),
  };

  return node;
}

const registry = new Map();

const document = {
  getElementById(id) {
    if (!registry.has(id)) registry.set(id, element("div", id));
    return registry.get(id);
  },
  createElement: (tag) => element(tag),
  addEventListener() {},
  title: "",
};

const store = new Map();

const context = {
  document, console, assert,
  URLSearchParams, JSON, Math, Number, String, Object, Array, Error, Promise,
  RegExp,
  focused: null,
  localStorage: {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
  },
  navigator: {},
  history: {replaceState() {}},
  location: {search: "", href: "/"},
  window: {scrollY: 0, scrollX: 0, open() {}},
  requestAnimationFrame: (fn) => fn(),
  setTimeout,
  fetch: async (url) => ({
    json: async () => (url.endsWith("/getInstanceInfo")
      ? {ok: true, result: {
          name: "Harness instance", description: "Testing.",
          mode: "invited", contact: "", pages_url: "http://127.0.0.1:8081"}}
      : {ok: false, error: "METHOD_NOT_FOUND"}),
  }),
};

context.globalThis = context;
vm.createContext(context);

try {
  vm.runInContext(source, context, {filename: "editor.js"});
} catch (problem) {
  console.error("editor.js threw while loading:", problem.message);
  process.exit(1);
}

await new Promise((resolve) => setTimeout(resolve, 50));

// ------------------------------------------------------- first-run card

const card = document.getElementById("card");

assert.equal(document.title, "Harness instance");
assert.equal(document.getElementById("veil").hidden, false,
  "with no stored accounts the first-run card should show");
assert.ok(card.innerHTML.includes("Enter invite code"),
  "invited mode should offer the invite path");
assert.ok(card.innerHTML.includes("I have a token"),
  "every mode should offer the paste-a-token path");
assert.equal(document.getElementById("publish").disabled, true,
  "publishing should be impossible without an account");

// ----------------------------------------------------------- block edits

const blocks = document.getElementById("blocks");
const {makeBlock, onKey} = context;

function reset() {
  blocks.children.length = 0;
}

function press(block, key, extra = {}) {
  const area = block.querySelector("textarea");
  const event = {key, shiftKey: false, metaKey: false, ctrlKey: false,
                 preventDefault() { this.defaulted = true; }, ...extra};
  onKey(event, block, area);
  return event;
}

function atEnd(block) {
  const area = block.querySelector("textarea");
  area.setSelectionRange(area.value.length, area.value.length);
  return block;
}

// A code block written last used to be a trap: Enter inserts a newline by
// design, so there was no way to reach a new block.
reset();
let code = makeBlock("pre", "print('hi')\n");
atEnd(code);
press(code, "Enter");
assert.equal(blocks.children.length, 2,
  "Enter on a blank last line of a code block should leave it");
assert.equal(code.querySelector("textarea").value, "print('hi')",
  "the trailing newline should not survive into the published page");

// And the modifier works from anywhere, mid-line included.
reset();
code = makeBlock("pre", "print('hi')");
code.querySelector("textarea").setSelectionRange(3, 3);
press(code, "Enter", {ctrlKey: true});
assert.equal(blocks.children.length, 2,
  "ctrl+Enter should always make a new block");

// Down at the end of the last block is the general escape, whatever the
// block happens to be.
reset();
const table = atEnd(makeBlock("table", "a\tb"));
press(table, "ArrowDown");
assert.equal(blocks.children.length, 2,
  "down at the end of the last block should make a new one");

// Enter mid-sentence should divide the sentence.
reset();
const para = makeBlock("p", "one two");
para.querySelector("textarea").setSelectionRange(3, 3);
press(para, "Enter");
assert.equal(para.querySelector("textarea").value, "one");
assert.equal(blocks.children[1].querySelector("textarea").value, " two",
  "the text after the cursor should move to the new block");

// Backspace at the start of a block should merge, not destroy.
reset();
makeBlock("p", "first");
const second = makeBlock("p", "second");
second.querySelector("textarea").setSelectionRange(0, 0);
press(second, "Backspace");
assert.equal(blocks.children.length, 1);
assert.equal(blocks.children[0].querySelector("textarea").value, "firstsecond",
  "merging should keep both halves");

// A divider used to be undeletable: display:none meant its textarea could
// never be focused, and Backspace inside a textarea was the only way to
// remove any block.
reset();
makeBlock("p", "before");
const rule = makeBlock("hr");
press(rule, "Backspace");
assert.equal(blocks.children.length, 1,
  "a divider must be removable");
assert.equal(blocks.children[0].querySelector("textarea").value, "before");

// And a divider is passed over when merging backwards, rather than
// swallowing the text.
reset();
makeBlock("p", "before");
makeBlock("hr");
const after = makeBlock("p", "after");
after.querySelector("textarea").setSelectionRange(0, 0);
press(after, "Backspace");
assert.equal(blocks.children.length, 2,
  "backspacing into a divider should remove the divider");

// Choosing "Divider" should leave the cursor past it. A divider added as
// the last block otherwise has nothing underneath it to click.
reset();
const last = makeBlock("p", "");
context.retype(last, "hr");
assert.equal(blocks.children.length, 2,
  "making a divider as the last block should open one below it");
assert.equal(blocks.children[1].dataset.type, "p");
assert.equal(context.focused, blocks.children[1].querySelector("textarea"),
  "the cursor should end up below the divider");

// Converting a block that already had words must not throw them away. The
// text would otherwise sit in a textarea nobody can see and never reach
// the published page.
reset();
const written = makeBlock("p", "some words");
context.retype(written, "hr");
assert.equal(written.querySelector("textarea").value, "",
  "the divider itself holds no text");
assert.equal(blocks.children[1].querySelector("textarea").value, "some words",
  "the words should survive as the block below");

// With something already following, reuse it rather than piling up empty
// paragraphs.
reset();
const middle = makeBlock("p", "");
makeBlock("p", "already here");
context.retype(middle, "hr");
assert.equal(blocks.children.length, 2,
  "an existing block below should be reused, not duplicated");

console.log("editor.js runs, and block editing behaves:");
console.log("  code block has an exit · ctrl+Enter works · down makes a block");
console.log("  Enter splits · Backspace merges · dividers delete");
console.log("  dividers move the cursor past them and keep any words");

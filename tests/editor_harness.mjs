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
    _innerHTML: "",
    textContent: "",

    // A real setter, because editor.js clears the block list with
    // `innerHTML = ""` and a plain property let stale blocks survive it -
    // which made a round-trip test see nodes the page never had.
    get innerHTML() { return this._innerHTML; },
    set innerHTML(value) {
      this._innerHTML = value;
      if (value === "") {
        for (const kid of this.children) kid.parentElement = null;
        this.children = [];
      }
    },

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
    // Real listeners, because a stub that accepts a handler and throws it
    // away reports success for code that never runs. The same failure the
    // innerHTML property had: a write accepted and quietly ignored.
    _on: {},
    addEventListener(type, fn) {
      (this._on[type] || (this._on[type] = [])).push(fn);
    },
    dispatchEvent(type, event = {}) {
      for (const fn of this._on[type] || []) fn(event);
    },

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

// ------------------------------------------------------------ round trip
//
// The bug this exists for: fromNodes read tag and text, toNodes wrote tag
// and text, and everything else was silently discarded. Opening a page
// that carried `require-role: finance` and pressing save republished it
// with the gate removed - failing OPEN, with no error to notice.

const original = [
  {tag: "p", attrs: {id: "intro"}, children: ["Opening words."]},
  {tag: "section", attrs: {"require-role": "finance", source: "https://x/y"},
   children: [{tag: "p", attrs: {}, children: ["Fallback prose."]}]},
  {tag: "gallery", attrs: {"prefer-layout": "grid, list"}, children: []},
  {tag: "p", attrs: {}, children: ["Closing words."]},
];

context.fromNodes(original);
const returned = context.toNodes();

assert.equal(returned.length, original.length,
  "a round trip must not add or drop nodes");

assert.equal(returned[0].attrs && returned[0].attrs.id, "intro",
  "an id must survive a round trip, or nothing published here is watchable");

assert.equal(returned[1].tag, "section",
  "a node the editor cannot draw must keep its tag");
assert.equal(returned[1].attrs["require-role"], "finance",
  "require- MUST survive: dropping it un-gates the section for everyone");
assert.equal(returned[1].children[0].children[0], "Fallback prose.",
  "its children must survive too, not be flattened into text");

assert.equal(returned[2].attrs["prefer-layout"], "grid, list",
  "an unknown tag's attributes must survive");

// Compared the way the store compares: normalise() fills in an omitted
// `attrs` on write, so a missing empty object is not a difference. What
// must not differ is anything that would change the canonical bytes.
const fill = (ns) => ns.map((n) => (typeof n === "string" ? n : {
  tag: n.tag, attrs: n.attrs || {}, children: fill(n.children || []),
}));

assert.deepEqual(fill(returned), fill(original),
  "a page that is opened and saved unchanged must come back identical");

// Editing the text of an ordinary block must not disturb what it carries.
context.fromNodes(original);
document.getElementById("blocks").children[0]
  .querySelector("textarea").value = "Rewritten.";
const edited = context.toNodes();

assert.equal(edited[0].children[0], "Rewritten.");
assert.equal(edited[0].attrs.id, "intro",
  "editing text must not drop the block's id");
assert.deepEqual(fill([edited[1]]), fill([original[1]]),
  "editing one block must not disturb another");

console.log("  round trip keeps attributes, ids, and nodes it cannot draw");

// ------------------------------------------------------------------ ids
//
// An id is never generated. It is suggested, and only written when the
// author leaves the field - because a subscription is a promise from the
// author, and a generated id is a promise nobody made.

document.getElementById("blocks").innerHTML = "";

const idBlockA = makeBlock("p", "Quarterly sales figures");
const idTag = idBlockA.children.find((k) => k.className === "idtag");
const idInput = idBlockA.children.find((k) => k.className === "idinput");

assert.ok(idTag && idInput, "every editable block offers an id control");
assert.equal(idTag.textContent, "#", "a block with no id shows a bare hash");
assert.equal(idInput.hidden, true, "the field stays out of the way until asked");
assert.equal(context.toNodes()[0].attrs, undefined,
  "freestyle prose carries no id, which is the correct outcome");

idTag.dispatchEvent("click", {preventDefault() {}});

assert.equal(idInput.hidden, false, "clicking reveals the field");
assert.equal(idInput.value, "quarterly-sales-figures",
  "the suggestion is slugged from the block's own words");
assert.equal(context.toNodes()[0].attrs, undefined,
  "a suggestion is not an id until the author settles on it");

idInput.dispatchEvent("blur");

assert.equal(context.toNodes()[0].attrs.id, "quarterly-sales-figures",
  "settling writes the id");
assert.equal(idTag.textContent, "#quarterly-sales-figures",
  "and the block shows the address it now has");

// Unique within the page, because the store refuses duplicates - and
// refuses them so a subscription cannot resolve to two nodes.
const idBlockB = makeBlock("p", "Quarterly sales figures");
idBlockB.children.find((k) => k.className === "idtag")
  .dispatchEvent("click", {preventDefault() {}});

assert.equal(idBlockB.children.find((k) => k.className === "idinput").value,
  "quarterly-sales-figures-2",
  "a colliding suggestion is de-duplicated, as page paths are");

// Anything the pattern would reject is cleaned rather than refused.
const idBlockC = makeBlock("p", "x");
const thirdInput = idBlockC.children.find((k) => k.className === "idinput");
thirdInput.value = "Not A Valid Id!!";
thirdInput.dispatchEvent("blur");

assert.equal(context.toNodes()[2].attrs.id, "not-a-valid-id",
  "an id is slugged to what the store will accept");

// Clearing it removes the address rather than leaving an empty one.
thirdInput.value = "";
thirdInput.dispatchEvent("blur");

assert.equal(context.toNodes()[2].attrs, undefined,
  "clearing the field removes the id");

console.log("  ids are suggested, de-duplicated, and never invented");

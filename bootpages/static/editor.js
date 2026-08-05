// The block vocabulary. Only core tags for now - this renderer implements
// no modules, so everything here maps straight onto something Telegraph
// would also accept. When capability pages arrive, a site's declared
// modules get appended to this list at runtime.
const TYPES = [
  {type: "p",          label: "Text",       hint: "plain paragraph"},
  {type: "h3",         label: "Heading"},
  {type: "h4",         label: "Subheading"},
  {type: "blockquote", label: "Quote"},
  {type: "pre",        label: "Code"},
  {type: "li",         label: "List item"},
  {type: "img",        label: "Image",      hint: "paste a URL"},
  {type: "table",      label: "Table",      hint: "paste from a spreadsheet"},
  {type: "hr",         label: "Divider"},
];

const PLACEHOLDER = {
  p: "Write something…",
  h3: "Heading",
  h4: "Subheading",
  blockquote: "Quote",
  pre: "Code",
  li: "List item",
  img: "https://example.org/photo.jpg",
  table: "Paste tab-separated rows, or type them with tabs",
  hr: "",
};

const $ = (id) => document.getElementById(id);

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"]/g, (c) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
}

// ------------------------------------------------------------- accounts
//
// The browser holds a list of tokens. They have NO server-side association
// with each other - the store cannot tell that two of them are yours, and
// there is no endpoint that would let it. This is a privacy property, not
// just a convenience, and it rests on one rule:
//
//   ONE TOKEN PER REQUEST, EVER.
//
// Never send two together, never build a call that accepts several. The
// moment the client correlates them the property is gone retroactively,
// for every account already created.

const REMEMBERED = "bootpages.accounts";

const state = {
  instance: null,   // what getInstanceInfo said
  accounts: [],     // {token, short_name, author_name, remembered}
  current: 0,
  path: null,       // the page being edited, if any
};

function loadAccounts() {
  try {
    const saved = JSON.parse(localStorage.getItem(REMEMBERED) || "[]");
    state.accounts = saved.map((a) => ({...a, remembered: true}));
  } catch (problem) {
    state.accounts = [];
  }
}

// Only remembered accounts are written back. An account the author chose
// not to remember lives in memory and disappears when the tab does.
function saveAccounts() {
  const keep = state.accounts
    .filter((a) => a.remembered)
    .map(({token, short_name, author_name}) => ({token, short_name, author_name}));

  localStorage.setItem(REMEMBERED, JSON.stringify(keep));
}

function account() {
  return state.accounts[state.current] || null;
}

function addAccount(entry, remembered) {
  state.accounts.push({...entry, remembered});
  state.current = state.accounts.length - 1;
  saveAccounts();
  paintBar();
}

// ------------------------------------------------------------------- api

async function call(method, params) {
  const response = await fetch("/" + method, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(params),
  });
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error);
  return payload.result;
}

const ERRORS = {
  ACCOUNT_CREATION_CLOSED: "This instance does not create accounts. Ask its operator for a token.",
  ACCESS_TOKEN_INVALID: "That token is not valid on this instance.",
  INVITE_REQUIRED: "An invite code is needed here.",
  INVITE_INVALID: "That invite code is not recognised.",
  INVITE_ALREADY_USED: "That invite code has already been used.",
  INVITE_EXPIRED: "That invite code has expired.",
  SHORT_NAME_REQUIRED: "A short name is needed.",
  PAGE_NOT_FOUND: "There is no page at that address.",
  PAGE_ACCESS_DENIED: "That page belongs to another account.",
};

const explain = (problem) => ERRORS[problem.message] || problem.message;

// ------------------------------------------------------------------ bar

function paintBar() {
  const who = account();
  $("who").textContent = who ? who.short_name + " ▾" : "no account";
  $("pages").disabled = !who;
  $("publish").disabled = !who;
}

// ----------------------------------------------------------------- cards

function card(html) {
  $("card").innerHTML = html;
  $("veil").hidden = false;
  const first = $("card").querySelector("input, button");
  if (first) first.focus();
}

const closeCard = () => { $("veil").hidden = true; };

// The first thing anyone sees. What it offers is decided by the instance,
// not by this file - an instance can be open, invited or admin-minted, and
// the buttons are a function of which.
function welcome() {
  const {name, description, mode, contact} = state.instance;

  const choices = {
    open:    '<button id="go-create">Start writing</button>',
    invited: '<button id="go-invite">Enter invite code</button>',
    admin:   '',
  }[mode] || '';

  const note = mode === "admin"
    ? `<p class="plain">Accounts here are issued by the operator.${
        contact ? " " + escapeHtml(contact) : ""}</p>`
    : "";

  card(`
    <h2>${escapeHtml(name)}</h2>
    <p>${escapeHtml(description)}</p>
    ${note}
    <div class="row">
      ${choices}
      <button id="go-token" class="quiet">I have a token</button>
    </div>
  `);

  const create = $("go-create");
  const invite = $("go-invite");
  if (create) create.onclick = () => createForm(null);
  if (invite) invite.onclick = () => inviteForm();
  $("go-token").onclick = () => tokenForm();
}

function inviteForm(error) {
  card(`
    <h2>Invite code</h2>
    <p>An invite is a one-time right to create an account. It is not a
       credential to one, and it stops working once used.</p>
    ${error ? `<p class="warn">${escapeHtml(error)}</p>` : ""}
    <label><span>Code</span><input type="text" id="code" autocomplete="off"></label>
    <div class="row">
      <button id="ok">Continue</button>
      <button id="back" class="quiet">Back</button>
    </div>
  `);

  $("ok").onclick = () => {
    const code = $("code").value.trim();
    if (code) createForm(code);
  };
  $("back").onclick = welcome;
}

function createForm(invite, error) {
  card(`
    <h2>Your account</h2>
    <p>A short name is how you tell your own accounts apart. It is private
       and never appears on a published page. The byline is what readers
       see.</p>
    ${error ? `<p class="warn">${escapeHtml(error)}</p>` : ""}
    <label><span>Short name <small>private</small></span>
      <input type="text" id="short" autocomplete="off"></label>
    <label><span>Byline <small>public, optional</small></span>
      <input type="text" id="author" autocomplete="off"></label>
    <div class="row">
      <button id="ok">Create</button>
      <button id="back" class="quiet">Back</button>
    </div>
  `);

  $("ok").onclick = async () => {
    const short_name = $("short").value.trim();
    if (!short_name) return;

    try {
      const created = await call("createAccount", {
        short_name,
        author_name: $("author").value.trim(),
        ...(invite ? {invite} : {}),
      });
      showToken(created);
    } catch (problem) {
      if (invite) inviteForm(explain(problem));
      else createForm(invite, explain(problem));
    }
  };
  $("back").onclick = welcome;
}

// The token is shown once, and the author has to say they have it. There
// is no password to reset and no address to recover to - an account whose
// token is lost is orphaned permanently, and an earlier version of this
// editor minted one silently into storage where nobody ever saw it.
function showToken(created) {
  card(`
    <h2>Save this token</h2>
    <p class="warn">This is the entire account. There is no password to
       reset and no way to recover it. Lose it and the pages are orphaned
       permanently.</p>
    <div class="token">${escapeHtml(created.access_token)}</div>
    <div class="check">
      <input type="checkbox" id="remember" checked>
      <span>Remember this account in this browser. Uncheck on a machine
        that is not yours - it will then last only until you close the
        tab.</span>
    </div>
    <div class="row">
      <button id="ok">I have saved it</button>
      <button id="copy" class="quiet">Copy</button>
    </div>
  `);

  $("copy").onclick = () => {
    if (navigator.clipboard) navigator.clipboard.writeText(created.access_token);
  };
  $("ok").onclick = () => {
    addAccount({
      token: created.access_token,
      short_name: created.short_name,
      author_name: created.author_name || "",
    }, $("remember").checked);
    closeCard();
    ready();
  };
}

function tokenForm(error) {
  card(`
    <h2>Use an existing token</h2>
    <p>Paste the token you were given, or one you saved from another
       browser.</p>
    ${error ? `<p class="warn">${escapeHtml(error)}</p>` : ""}
    <label><span>Token</span><input type="text" id="tok" autocomplete="off"></label>
    <div class="check">
      <input type="checkbox" id="remember" checked>
      <span>Remember this account in this browser.</span>
    </div>
    <div class="row">
      <button id="ok">Continue</button>
      <button id="back" class="quiet">Back</button>
    </div>
  `);

  $("ok").onclick = async () => {
    const token = $("tok").value.trim();
    if (!token) return;

    try {
      // Checked against the server rather than by shape, so a typo is
      // caught here instead of at the first publish.
      const info = await call("getAccountInfo", {access_token: token});
      addAccount({
        token,
        short_name: info.short_name,
        author_name: info.author_name || "",
      }, $("remember").checked);
      closeCard();
      ready();
    } catch (problem) {
      tokenForm(explain(problem));
    }
  };
  $("back").onclick = () => (state.accounts.length ? closeCard() : welcome());
}

// ---------------------------------------------------------------- sheets

function sheet(html) {
  $("sheet").innerHTML = `<div class="inner">${html}</div>`;
  $("sheet").hidden = false;
}

const closeSheet = () => { $("sheet").hidden = true; };

async function pagesSheet() {
  const who = account();
  if (!who) return;

  sheet("<h3>Pages</h3><p>Loading…</p>");

  try {
    // One token. Never a list of them - see the note above the account
    // shelf.
    const listing = await call("getPageList", {access_token: who.token, limit: 50});

    const rows = listing.pages.map((page) => `
      <div class="item">
        <span class="grow">
          <b>${escapeHtml(page.title)}</b>
          <small>${escapeHtml(page.url)} · revision ${escapeHtml(page.revision)} ·
            ${escapeHtml(page.views)} view${page.views === 1 ? "" : "s"}</small>
        </span>
        <button data-edit="${escapeHtml(page.path)}">Edit</button>
        <button data-open="${escapeHtml(page.url)}">Open</button>
      </div>`).join("");

    sheet(`<h3>Pages by ${escapeHtml(who.short_name)}
             (${escapeHtml(listing.total_count)})</h3>
           ${rows || "<p>Nothing published yet.</p>"}`);

    $("sheet").querySelectorAll("[data-edit]").forEach((button) => {
      button.onclick = () => { closeSheet(); load(button.dataset.edit); };
    });
    $("sheet").querySelectorAll("[data-open]").forEach((button) => {
      button.onclick = () => window.open(button.dataset.open, "_blank");
    });

  } catch (problem) {
    sheet(`<h3>Pages</h3><p>${escapeHtml(explain(problem))}</p>`);
  }
}

function accountsSheet() {
  const rows = state.accounts.map((entry, index) => `
    <div class="item${index === state.current ? " current" : ""}">
      <span class="grow">
        <b>${escapeHtml(entry.short_name)}</b>
        <small>${escapeHtml(entry.author_name || "no byline")}${
          entry.remembered ? "" : " · this session only"}</small>
      </span>
      ${index === state.current ? "" : `<button data-use="${index}">Use</button>`}
      <button data-reveal="${index}">Token</button>
      <button data-forget="${index}">Forget</button>
    </div>`).join("");

  sheet(`<h3>Accounts</h3>
         <p>These have no connection to each other. This browser is simply
            where they are listed - the store cannot tell they are yours.</p>
         ${rows}
         <div class="item">
           <span class="grow"></span>
           <button id="add-token">Add a token</button>
           ${state.instance.mode === "open"
              ? '<button id="add-new">New account</button>' : ""}
           ${state.instance.mode === "invited"
              ? '<button id="add-invite">Use an invite</button>' : ""}
         </div>`);

  const bind = (attr, fn) =>
    $("sheet").querySelectorAll(`[data-${attr}]`).forEach((button) => {
      button.onclick = () => fn(Number(button.dataset[attr]));
    });

  bind("use", (index) => { state.current = index; paintBar(); accountsSheet(); });

  bind("reveal", (index) => {
    const entry = state.accounts[index];
    card(`<h2>${escapeHtml(entry.short_name)}</h2>
          <p class="warn">Anyone with this string is this account.</p>
          <div class="token">${escapeHtml(entry.token)}</div>
          <div class="row"><button id="ok">Close</button></div>`);
    $("ok").onclick = closeCard;
  });

  bind("forget", (index) => {
    state.accounts.splice(index, 1);
    state.current = 0;
    saveAccounts();
    paintBar();
    if (state.accounts.length) {
      accountsSheet();
    } else {
      closeSheet();
      welcome();
    }
  });

  const add = $("add-token");
  if (add) add.onclick = () => { closeSheet(); tokenForm(); };
  const fresh = $("add-new");
  if (fresh) fresh.onclick = () => { closeSheet(); createForm(null); };
  const invited = $("add-invite");
  if (invited) invited.onclick = () => { closeSheet(); inviteForm(); };
}

// ---------------------------------------------------------------- fields

function grow(area) {
  // A divider's textarea is positioned over the rule rather than sized to
  // its content, so leave its height alone.
  if (area.parentElement && area.parentElement.dataset.type === "hr") return;

  area.style.height = "auto";
  area.style.height = area.scrollHeight + "px";
}

function field(parent, placeholder) {
  const area = document.createElement("textarea");
  area.rows = 1;
  area.placeholder = placeholder;
  area.addEventListener("input", () => grow(area));
  parent.appendChild(area);
  return area;
}

const titleField = field($("title"), "Title");
const bylineField = field($("byline"), "Your name");

// Both are textareas so they can wrap, which means Enter would otherwise
// put a line break inside a title. It should move into the document.
for (const header of [titleField, bylineField]) {
  header.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      focusBlock($("blocks").firstElementChild, false);
    }
  });
}

// ---------------------------------------------------------------- blocks

function makeBlock(type = "p", text = "", at = null) {
  const block = document.createElement("div");
  block.className = "block";
  block.dataset.type = type;

  const plus = document.createElement("button");
  plus.className = "plus";
  plus.textContent = "+";
  plus.tabIndex = -1;
  plus.addEventListener("click", (event) => {
    event.preventDefault();
    openMenu(block);
  });
  block.appendChild(plus);

  const area = field(block, PLACEHOLDER[type] || "");
  area.value = text;

  area.addEventListener("keydown", (event) => onKey(event, block, area));

  if (at && at.nextSibling) {
    $("blocks").insertBefore(block, at.nextSibling);
  } else {
    $("blocks").appendChild(block);
  }

  requestAnimationFrame(() => grow(area));
  return block;
}

function focusBlock(block, atEnd) {
  if (!block) return;

  const area = block.querySelector("textarea");
  const pos = atEnd ? area.value.length : 0;

  area.focus();
  area.setSelectionRange(pos, pos);
}

function newBlockAfter(block, type = "p", text = "") {
  const next = makeBlock(type, text, block);
  focusBlock(next, false);
  return next;
}

function onKey(event, block, area) {
  const type = block.dataset.type;
  const start = area.selectionStart;
  const atStart = start === 0 && area.selectionEnd === 0;
  const atEnd = start === area.value.length && area.selectionEnd === start;

  // Code and tables treat a newline as content, so Enter cannot mean "next
  // block" there.
  const multiline = type === "pre" || type === "table";

  // The escape hatch that works from anywhere, including inside code.
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    return newBlockAfter(block);
  }

  if (event.key === "Enter" && !event.shiftKey) {
    if (multiline) {
      // Enter on an already-blank last line means "done" - the convention
      // every Markdown-ish editor uses. Without it, a code block written
      // at the end of a page is a trap with no way out.
      if (atEnd && area.value.endsWith("\n")) {
        event.preventDefault();
        area.value = area.value.replace(/\n+$/, "");
        grow(area);
        return newBlockAfter(block);
      }
      return;                       // otherwise the newline is content
    }

    event.preventDefault();

    // Split at the cursor rather than always appending an empty block.
    // Pressing Enter mid-sentence should divide the sentence, not strand
    // the second half.
    const after = area.value.slice(start);
    area.value = area.value.slice(0, start);
    grow(area);

    return newBlockAfter(block, type === "li" ? "li" : "p", after);
  }

  if (event.key === "Backspace" && atStart) {
    const previous = block.previousElementSibling;

    if (!previous) return;
    event.preventDefault();

    if (area.value === "") {
      block.remove();
      return focusBlock(previous, true);
    }

    // A divider holds no text to merge into, so joining backwards past one
    // removes it instead.
    if (previous.dataset.type === "hr") {
      previous.remove();
      return;
    }

    // Merging keeps the words. Deleting the block under them would mean
    // retyping a paragraph because the cursor was one character too far
    // left.
    const target = previous.querySelector("textarea");
    const at = target.value.length;

    target.value += area.value;
    block.remove();
    grow(target);
    target.focus();
    target.setSelectionRange(at, at);

    return;
  }

  // Arrow navigation, and the general answer to "this block type has no
  // exit": down at the end of the last block makes a new one, whatever
  // that block happens to be.
  if (event.key === "ArrowDown" && atEnd) {
    event.preventDefault();
    const next = block.nextElementSibling;

    return next ? focusBlock(next, false) : newBlockAfter(block);
  }

  if (event.key === "ArrowUp" && atStart) {
    const previous = block.previousElementSibling;

    if (previous) {
      event.preventDefault();
      focusBlock(previous, true);
    }
  }
}

function retype(block, type) {
  const area = block.querySelector("textarea");
  const carried = area.value;

  block.dataset.type = type;
  area.placeholder = PLACEHOLDER[type] || "";

  if (type !== "hr") {
    grow(area);
    area.focus();
    return;
  }

  // A divider is not somewhere you type, so making one should leave the
  // cursor past it. Without this, a divider added as the last block has
  // nothing underneath it to click and the page cannot be continued.
  area.value = "";
  grow(area);

  // Converting a block that already had words would otherwise throw them
  // away silently - the text stays in a textarea nobody can see and never
  // reaches the published page.
  if (carried.trim()) return newBlockAfter(block, "p", carried);

  const next = block.nextElementSibling;

  return next ? focusBlock(next, false) : newBlockAfter(block);
}

// ------------------------------------------------------------------ menu

function openMenu(block) {
  const menu = $("menu");
  menu.innerHTML = "";

  for (const item of TYPES) {
    // Built with DOM methods rather than innerHTML on purpose. These
    // labels come from a hardcoded list today, but this is exactly where
    // a site's declared modules get appended once capability pages exist -
    // and at that point they are text from another server. Whoever adds
    // that should not also have to notice this.
    const button = document.createElement("button");
    button.textContent = item.label;

    if (item.hint) {
      const hint = document.createElement("small");
      hint.textContent = item.hint;
      button.appendChild(hint);
    }

    button.addEventListener("click", () => {
      retype(block, item.type);
      menu.hidden = true;
    });
    menu.appendChild(button);
  }

  const box = block.getBoundingClientRect();
  menu.hidden = false;
  menu.style.top = (window.scrollY + box.top) + "px";
  menu.style.left = (window.scrollX + box.left - 16) + "px";
}

// ------------------------------------------------------------ conversion

// Blocks to a node list. Consecutive list items become one ul, and a table
// becomes nested lists - rows of cells - because the core tag set has no
// table and nested bullets are what a site without one should show.
function toNodes() {
  const nodes = [];
  let list = null;

  for (const block of $("blocks").children) {
    const type = block.dataset.type;
    const text = block.querySelector("textarea").value;

    if (type !== "li") list = null;
    if (type !== "hr" && !text.trim()) continue;

    if (type === "li") {
      if (!list) { list = {tag: "ul", children: []}; nodes.push(list); }
      list.children.push({tag: "li", children: [text]});
    } else if (type === "hr") {
      nodes.push({tag: "hr", children: []});
    } else if (type === "img") {
      nodes.push({tag: "figure", children: [{tag: "img", attrs: {src: text.trim()}}]});
    } else if (type === "table") {
      const rows = text.split("\n").filter((line) => line.trim());
      if (!rows.length) continue;
      nodes.push({tag: "table", children: [{tag: "ul", children: rows.map((row) => ({
        tag: "li",
        children: [{tag: "ul", children: splitRow(row).map((cell) => ({
          tag: "li", children: [cell],
        }))}],
      }))}]});
    } else {
      nodes.push({tag: type, children: [text]});
    }
  }

  return nodes;
}

// Tabs first, because that is what a spreadsheet puts on the clipboard.
// Pipes second, for anyone who already writes Markdown tables.
function splitRow(row) {
  if (row.includes("\t")) return row.split("\t").map((c) => c.trim());
  if (row.includes("|")) {
    const cells = row.split("|").map((c) => c.trim());
    if (cells[0] === "") cells.shift();
    if (cells[cells.length - 1] === "") cells.pop();
    return cells;
  }
  return [row.trim()];
}

// The reverse, for editing a page that already exists.
function fromNodes(nodes) {
  $("blocks").innerHTML = "";

  for (const node of nodes) {
    if (typeof node === "string") { makeBlock("p", node); continue; }

    const kids = node.children || [];

    if (node.tag === "ul") {
      for (const item of kids) makeBlock("li", textOf(item));
    } else if (node.tag === "figure") {
      const img = kids.find((k) => k && k.tag === "img");
      makeBlock("img", img && img.attrs ? img.attrs.src : "");
    } else if (node.tag === "hr") {
      makeBlock("hr");
    } else if (node.tag === "table") {
      makeBlock("table", tableText(node));
    } else {
      makeBlock(node.tag, textOf(node));
    }
  }

  if (!$("blocks").children.length) makeBlock("p");
}

function textOf(node) {
  if (typeof node === "string") return node;
  return (node.children || []).map(textOf).join("");
}

function tableText(node) {
  const outer = (node.children || [])[0];
  const rows = outer && outer.children ? outer.children : [];
  return rows.map((row) => {
    const inner = (row.children || [])[0];
    const cells = inner && inner.children ? inner.children : [];
    return cells.map(textOf).join("\t");
  }).join("\n");
}

// -------------------------------------------------------------- publish

async function publish() {
  const who = account();
  if (!who) return welcome();

  const status = $("status");
  status.textContent = "publishing…";

  try {
    const params = {
      access_token: who.token,          // one token, never a list
      title: titleField.value || "Untitled",
      author_name: bylineField.value || who.author_name || "",
      content: JSON.stringify(toNodes()),
    };

    const page = state.path
      ? await call("editPage", {...params, path: state.path})
      : await call("createPage", params);

    state.path = page.path;
    history.replaceState(null, "", "/?edit=" + page.path);

    // The link points at the pages origin, which the server decides - the
    // editor never guesses where a page lives.
    status.innerHTML =
      `<a href="${escapeHtml(page.url)}" target="_blank">${escapeHtml(page.path)}</a>` +
      ` · revision ${escapeHtml(page.revision)} · ${escapeHtml(page.digest.slice(0, 18))}…`;

  } catch (problem) {
    status.textContent = explain(problem);
  }
}

async function load(path) {
  const page = await call("getPage", {path, return_content: "true"});

  state.path = page.path;
  titleField.value = page.title;
  bylineField.value = page.author_name || "";
  grow(titleField);
  grow(bylineField);
  fromNodes(page.content || []);

  history.replaceState(null, "", "/?edit=" + page.path);
  $("status").innerHTML =
    `<a href="${escapeHtml(page.url)}" target="_blank">${escapeHtml(page.path)}</a>` +
    ` · revision ${escapeHtml(page.revision)}`;
}

// ---------------------------------------------------------------- events

$("publish").onclick = publish;
$("new").onclick = () => { location.href = "/"; };
$("pages").onclick = () => ($("sheet").hidden ? pagesSheet() : closeSheet());
$("who").onclick = () => ($("sheet").hidden ? accountsSheet() : closeSheet());

// A click anywhere else closes whatever is open. The veil is deliberately
// not dismissable this way - the first-run card has nothing behind it yet.
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    $("menu").hidden = true;
    closeSheet();
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest("#menu") && !event.target.closest(".plus")) {
    $("menu").hidden = true;
  }
  if (!event.target.closest("#sheet") && !event.target.closest("#bar")) {
    closeSheet();
  }
});

// ------------------------------------------------------------------ boot

function ready() {
  paintBar();

  const editing = new URLSearchParams(location.search).get("edit");

  if (editing && !state.path) {
    load(editing).catch((problem) => {
      $("status").textContent = explain(problem);
      if (!$("blocks").children.length) makeBlock("p");
    });
  } else if (!$("blocks").children.length) {
    makeBlock("p");
    titleField.focus();
  }
}

async function boot() {
  try {
    // Asked before anything is drawn. The instance decides what the first
    // screen offers - this file does not know whether accounts can be
    // created here until it is told.
    state.instance = await call("getInstanceInfo", {});
  } catch (problem) {
    state.instance = {name: "Bootpages", description: "", mode: "admin", contact: ""};
  }

  document.title = state.instance.name;

  loadAccounts();
  paintBar();

  if (state.accounts.length) {
    ready();
  } else {
    welcome();
  }
}

boot();

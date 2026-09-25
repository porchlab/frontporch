"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[ch]);
const icon = name => `<svg class="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PORTAL.icons[name] || PORTAL.icons.home}</svg>`;
const avatar = (name, color = "blue", size = "") => `<span class="avatar ${esc(color)} ${size}">${esc(String(name).slice(0, 1).toUpperCase())}</span>`;
const button = (label, action, id = "", kind = "secondary") => `<button type="button" class="${/text-button|card-action/.test(kind) ? kind : `button ${kind}`}" data-action="${action}" data-id="${esc(id)}">${label}</button>`;
const link = (label, route, kind = "text-button blue-text") => `<a class="${kind}" href="#family/${esc(route)}">${label}</a>`;
const phonebookLink = (phone, kind = "button secondary") => `<a class="${kind}" href="phonebook.html?phone=${encodeURIComponent(phone.id)}">Print phonebook</a>`;
const brand = () => `<a class="brand" href="#welcome"><span class="brand-mark">${icon("home")}</span>FrontPorch<span class="brand-period">.</span></a>`;
const note = text => `<div class="demo-notice">${text}</div>`;
const empty = (title, text, action = "") => `<div class="empty-state"><h3>${title}</h3><p>${text}</p>${action}</div>`;
const heading = (title, subtitle, action = "", eyebrow = "YOUR FAMILY’S FRONT PORCH") => `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${subtitle}</p></div>${action}</div>`;
const formErrorMarkup = '<p class="form-error" role="alert" hidden></p>';
let state;
try { state = Demo.load(window.sessionStorage); } catch { state = Demo.seed(); }
let section = "overview", detailId = "", inviteTab = "incoming", directoryQuery = "";
let confirmAction = null, dialogReturnFocus = null, toastTimer;
let inviteDraft = null;
const currentParent = () => Demo.actor(state) || state.guardians.find(g => g.primary);
const familyName = familyId => Demo.family(state, familyId)?.name || "Family";
const names = ids => ids.map(key => Demo.findChild(state, key)?.name).filter(Boolean).join(", ");
const peerNames = invitation => invitation.peerIds.map(key => Demo.family(state, invitation.familyId)?.children.find(c => c.id === key)?.name).filter(Boolean).join(", ");
const pendingCount = () => state.invitations.filter(i => i.direction === "incoming" && i.status === "pending").length;

function persist(message) {
  if (message) state.activity.unshift({text:message, time:"Just now"});
  state.activity = state.activity.slice(0, 30);
  try { Demo.save(window.sessionStorage, state); }
  catch { toast("Browser storage is unavailable. Changes last until this page is refreshed."); }
}
function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").classList.add("visible");
  toastTimer = setTimeout(() => $("#toast").classList.remove("visible"), 4500);
}
function go(route = "overview") {
  const hash = ["welcome", "signup", "login"].includes(route) ? `#${route}` : `#family/${route}`;
  closeDialog();
  if (location.hash === hash) render(); else location.hash = hash;
}
function finish(message, route) {
  persist(message); closeDialog();
  if (route) go(route); else render();
  toast(message);
}
function showError(form, message) {
  const error = $(".form-error", form);
  error.hidden = false; error.textContent = message; error.scrollIntoView({block:"nearest"});
}
function openDialog(title, content, {form = "", id = "", submit = "Save", extra = ""} = {}) {
  const dialog = $("#dialog");
  if (!dialog.open) dialogReturnFocus = document.activeElement;
  else dialog.close();
  dialog.innerHTML = `<div class="dialog-heading"><h2 id="dialog-title">${title}</h2><button type="button" class="icon-button" data-action="close" aria-label="Close dialog">${icon("close")}</button></div>${form ? `<form data-form="${form}" data-id="${esc(id)}" ${extra}>` : ""}<div class="dialog-body">${content}${formErrorMarkup}</div>${form ? `<div class="dialog-footer">${button("Cancel", "close")}<button class="button">${submit}</button></div></form>` : ""}`;
  dialog.showModal();
}
function closeDialog() {
  const dialog = $("#dialog");
  if (dialog.open) { dialog.close(); if (dialogReturnFocus?.isConnected) dialogReturnFocus.focus(); }
}
function confirm(title, text, callback) {
  confirmAction = callback;
  openDialog(title, `<p class="dialog-intro">${text}</p><div class="confirm-actions">${button("Keep as is", "close")}${button("Confirm", "confirm", "", "danger")}</div>`);
}

// Field labels, types, limits, defaults, help and choices come from Django forms.
function field(formName, name, values = {}, {options, readonly = false} = {}) {
  const spec = PORTAL.forms[formName].find(f => f.name === name);
  if (!spec) throw new Error(`Unknown exported field: ${formName}.${name}`);
  const value = values[name] ?? spec.initial ?? "";
  const fieldId = `field-${formName}-${name}`;
  const attrs = `id="${fieldId}" name="${name}"${spec.required && spec.type !== "checkbox" && spec.type !== "members" ? " required" : ""}${spec.max_length ? ` maxlength="${spec.max_length}"` : ""}${spec.min_length ? ` minlength="${spec.min_length}"` : ""}${readonly ? " readonly" : ""}${spec.help ? ` aria-describedby="${fieldId}-help"` : ""}`;
  const help = spec.help ? `<div class="form-note" id="${fieldId}-help">${spec.help}</div>` : "";
  if (spec.type === "members") {
    const selected = Array.isArray(value) ? value : [];
    return `<fieldset><legend>${esc(spec.label)}</legend><div class="checkbox-list">${(options || []).map(o => `<label class="check-row"><input type="checkbox" name="${name}" value="${esc(o.id)}" ${selected.includes(o.id) ? "checked" : ""}>${esc(o.name)}</label>`).join("") || '<p class="form-note">Add a child first.</p>'}</div>${help}</fieldset>`;
  }
  let input;
  if (spec.type === "textarea") input = `<textarea ${attrs} rows="3">${esc(value)}</textarea>`;
  else if (spec.type === "select") input = `<select ${attrs}>${(options || spec.choices || []).map(([key, label]) => `<option value="${esc(key)}" ${String(key) === String(value) ? "selected" : ""}>${esc(label)}</option>`).join("")}</select>`;
  else if (spec.type === "checkbox") input = `<input ${attrs} type="checkbox" ${value ? "checked" : ""}>`;
  else input = `<input ${attrs} type="${spec.type}" value="${spec.type === "password" ? "" : esc(value)}"${spec.type === "password" ? ' autocomplete="new-password"' : ""}>`;
  return `<div class="field"><label for="${fieldId}">${esc(spec.label)}</label>${input}${help}</div>`;
}
function fields(name, values = {}, omit = []) { return PORTAL.forms[name].filter(f => !omit.includes(f.name)).map(f => field(name, f.name, values)).join(""); }
function formValues(formName, data) {
  const values = {};
  for (const spec of PORTAL.forms[formName]) {
    values[spec.name] = spec.type === "checkbox" ? data.has(spec.name) : String(data.get(spec.name) || "").trim();
    if (spec.type !== "checkbox" && spec.type !== "members") {
      Demo.assert(!spec.required || values[spec.name], `Enter ${spec.label.toLowerCase()}.`);
      Demo.assert(!spec.max_length || values[spec.name].length <= spec.max_length, `${spec.label} is too long.`);
    }
  }
  return values;
}
function validateDemoPassword(values) {
  Demo.assert(values.password1 === values.password2, "The two password fields didn’t match.");
  Demo.assert(values.password1.length >= 8, "Use at least 8 characters for this demo password.");
}

function publicPage() {
  const route = location.hash.slice(1);
  let content = PORTAL.welcome.replaceAll('href="/register/"', 'href="#signup"');
  if (route === "signup" || route === "login") {
    const signup = route === "signup";
    content = `<section class="form-panel panel auth-panel"><div class="eyebrow">${signup ? "MAKE YOURSELF AT HOME" : "WELCOME HOME"}</div><h1>${signup ? "A front porch for your family." : "Welcome back."}</h1><p class="dialog-intro">${signup ? "Children don’t need accounts. You manage their phones and the people they can call." : "Your family’s little corner is right here."}</p>${note("Use fictional details and a made-up password. This demo creates no accounts and never stores passwords.")}<form data-form="${route}">${fields(route, signup ? {} : {login:currentParent().email})}${signup ? '<aside class="info-strip listing-preview"><div><strong>Listing preview</strong><p><span data-preview-family>Your family</span> · <span data-preview-guardian>Your guardian name</span></p><p class="form-note">Shown only if you choose to be listed. Email, phone numbers, and children stay private.</p></div></aside>' : ""}${formErrorMarkup}<button class="button full-width">${signup ? "Create family account" : "Log in"}</button></form><p class="auth-footnote">${signup ? 'Already have an account? <a href="#login">Log in</a>' : 'New here? <a href="#signup">Set up your family</a>'}</p></section>`;
  }
  return `<header class="landing-header">${brand()}<nav aria-label="Welcome"><a href="#how-it-works">How it works</a><a href="#login">Log in</a><a class="button small" href="#signup">Set up your family ${icon("arrow")}</a></nav></header><main id="main" class="public-main" tabindex="-1">${content}</main><footer class="landing-footer"><span>FrontPorch. A phone is a place.</span><span>Emergency calling is not available. Keep another phone for emergencies.</span></footer>`;
}
const NAV = [["overview", "home", "Overview"], ["children", "users", "Children & phones"], ["circle", "leaf", "Family connections"], ["directory", "search", "Family directory"], ["invites", "mail", "Invitations"], ["contacts", "book", "External contacts"], ["settings", "settings", "Family settings"]];
function familyPage() {
  const parent = currentParent();
  const current = ["child", "shortcuts"].includes(section) ? "children" : section;
  const page = ({overview, children:childrenPage, child:childPage, shortcuts:shortcutsPage, circle:connectionsPage, directory:directoryPage, invites:invitationsPage, contacts:contactsPage, settings:settingsPage})[section] || overview;
  return `<div class="app-shell"><aside class="sidebar">${brand()}<div class="family-switch">${avatar(state.family)}<div><strong>${esc(state.family)} family</strong><span>Your private space</span></div></div><div class="nav-label">YOUR FRONT PORCH</div><nav aria-label="Family navigation">${NAV.map(([key, symbol, label]) => `<a class="nav-item ${current === key ? "active" : ""}" href="#family/${key}" ${current === key ? 'aria-current="page"' : ""}>${icon(symbol)}<span>${label}</span></a>`).join("")}</nav><div class="sidebar-bottom"><div class="profile">${avatar(parent.name, "yellow", "small-avatar")}<div><strong>${esc(parent.name)}</strong><span>${parent.primary ? "Primary guardian" : "Guardian"}</span></div></div></div></aside><div class="workspace"><header class="app-topbar"><span>My FrontPorch / ${NAV.find(n => n[0] === current)?.[2]}</span><div class="topbar-right"><span class="privacy-label">${icon("lock")} Only your family</span><a class="icon-button notification-button" href="#family/invites" aria-label="Invitations (${pendingCount()} waiting)">${icon("mail")}${pendingCount() ? '<span class="notification-dot"></span>' : ""}</a>${button("Log out", "logout", "", "text-button")}</div></header><main id="main" class="family-main" tabindex="-1">${page()}</main><footer class="app-footer"><span>${icon("shield")} Private by design. Connected by choice.</span><span>Emergency calling is not available.</span></footer></div></div>`;
}
function render() {
  const parts = location.hash.split("/");
  section = parts[1] || "overview"; detailId = parts[2] || "";
  $("#emergency-notice").hidden = currentParent().emergencyNoticeDismissed;
  $("#app").innerHTML = location.hash.startsWith("#family/") ? familyPage() : publicPage();
  document.title = location.hash.startsWith("#family/") ? `${state.family} family · FrontPorch demo` : "FrontPorch · Explore the demo";
}
function route() {
  closeDialog(); render();
  if (location.hash === "#how-it-works") $("#how-it-works")?.scrollIntoView();
  else window.scrollTo(0, 0);
}
function childCard(child) {
  const pairs = state.connections.filter(c => c.childId === child.id).length;
  return `<article class="child-card"><div class="child-card-heading">${avatar(child.name, child.color)}<div><h3>${esc(child.name)}</h3><span>A place to call their own</span></div><button class="icon-button" data-action="child" data-id="${esc(child.id)}" aria-label="Edit ${esc(child.name)}">${icon("edit")}</button></div><div class="child-meta">${child.devices.map(phone => `<div class="phone-status"><span>${icon("phone")} ${esc(phone.name)} · <b>${phone.extension}</b></span><span class="pill ${phone.active ? "green" : "amber"}">${phone.active ? "Enabled" : "Setup pending"}</span></div>${link(`${icon("phone")} Dial shortcuts <span>${phone.shortcuts.length} set ${icon("chevron")}</span>`, `shortcuts/${phone.id}`, "shortcut-card-link")}${phonebookLink(phone, "shortcut-card-link")}`).join("") || `<div class="phone-status">${icon("phone")} No phone registered yet</div>`}<span>${icon("users")} ${pairs} connection${pairs === 1 ? "" : "s"} · ${state.contacts.length} external contacts</span><span>${icon("clock")} ${child.quietHours.length} quiet hours schedule${child.quietHours.length === 1 ? "" : "s"}</span></div>${link(`Manage phone & permissions ${icon("arrow")}`, `child/${child.id}`, "card-action")}</article>`;
}
function setupChecklist() {
  if (state.setupDismissed) return "";
  const phoneDone = state.children.length > 0 && state.children.every(c => c.devices.some(p => p.active));
  const circleDone = state.connections.length > 0;
  return `<section class="setup-banner" aria-label="Family setup checklist"><div class="setup-banner-intro"><span class="setup-icon">${icon("home")}</span><div class="setup-copy"><h2>A few little steps. A lot of connection.</h2><p>Let’s get your family ready for their first hello.</p></div><div class="setup-controls"><span class="setup-count">${1 + Number(phoneDone) + Number(circleDone)} of 3 complete</span>${button("Dismiss setup", "dismiss-setup", "", "text-button")}</div></div><div class="setup-steps">${[[true, "settings", "Make it your family", `${esc(state.family)} family is set up`], [phoneDone, "children", "Add their phones", phoneDone ? "A phone for every child" : "Give each child a place to call"], [circleDone, "circle", "Build your circle", circleDone ? "Your first connection is here" : "Invite a family you know"]].map(([done, route, title, copy], n) => `<a href="#family/${route}"><span class="step-number ${done ? "done" : ""}">${done ? icon("check") : n + 1}</span><span>${title}<strong>${copy}</strong></span></a>`).join("")}</div></section>`;
}
function pairLabel(pair) {
  const family = Demo.family(state, pair.familyId);
  return `${esc(Demo.findChild(state, pair.childId)?.name)} ↔ ${esc(family?.children.find(c => c.id === pair.peerId)?.name)}`;
}
function overview() {
  const incoming = state.invitations.filter(i => i.direction === "incoming" && i.status === "pending");
  return `${heading(`The ${esc(state.family)} family`, "A little independence for them. Peace of mind for you.", button("Add a child", "child", "", ""), `WELCOME HOME, ${esc(currentParent().name.toUpperCase())}`)}${setupChecklist()}<div class="dashboard-grid"><div class="dashboard-primary"><section><div class="section-heading"><h2>Children & phones <span class="heading-count">${state.children.length}</span></h2>${link("View all", "children")}</div><div class="children-grid">${state.children.map(childCard).join("") || empty("Their first hello starts here.", "Add a child, then reserve their phone.", button("Add your first child", "child", "", ""))}</div></section><section class="connections-preview"><div class="section-heading"><h2>Your family connections</h2>${link("Manage", "circle")}</div><div class="panel compact">${state.connections.map(pair => `<div class="family-row">${avatar("Friends", "lavender")}<div class="family-row-copy"><h3>${pairLabel(pair)}</h3><p>${esc(state.family)} · ${esc(familyName(pair.familyId))}</p></div><span class="pill green">Calls both ways</span></div>`).join("") || empty("Good company starts with an invitation.", "Connect with a family you already know.", link("Browse the directory", "directory", "button"))}</div></section><section class="activity-section"><div class="section-heading"><h2>Around your front porch</h2><span class="muted">Recent changes</span></div>${state.activity.slice(0, 6).map(a => `<div class="activity-row"><span class="activity-icon">${icon("check")}</span><p>${esc(a.text)}</p><time>${esc(a.time)}</time></div>`).join("")}</section></div><aside class="dashboard-secondary"><section class="inbox-panel"><div class="section-heading"><h2>A little hello</h2><span class="nav-count">${incoming.length}</span></div>${incoming.map(i => `<div class="invite-peek"><h3>The ${esc(familyName(i.familyId))} family</h3><p>${esc(peerNames(i))} would like to connect.</p>${button("Review invitation", "review-invite", i.id, "full-width")}</div>`).join("") || '<p class="small-empty">You’re all caught up.</p>'}${link("All invitations", "invites")}</section><section class="trust-note"><div class="note-symbol">${icon("shield")}</div><h3>Their freedom.<br>Your boundaries.</h3><p>Only approved people can reach your family. Every new connection starts with a parent’s say-so.</p>${link("See your family’s connections", "circle")}</section></aside></div>`;
}
function childrenPage() {
  return `${heading("Their people. Their phones.", "Give each child a place to call their own.", button("Add a child", "child", "", ""))}<div class="info-strip"><p>New children share your family’s saved external contacts. Connections with other FrontPorch families need approval for each child.</p></div><div class="children-grid expanded">${state.children.map(childCard).join("") || empty("A place for each child.", "Start with a first name. You can add their phone next.", button("Add a child", "child"))}</div><p class="section-footnote">Your installer configures and activates reserved phones.</p>`;
}
function childPage() {
  const child = Demo.findChild(state, detailId);
  if (!child) return empty("Child not found.", "Choose a child from Children & phones.", link("Children & phones", "children", "button"));
  return `${heading(`${esc(child.name)}’s place to call.`, "Phones, quiet hours, and the people in their circle.", button("Edit child", "child", child.id))}<div class="settings-grid"><section class="panel"><h2>Their phones</h2>${child.devices.map(phone => `<div class="device-row"><h3>${esc(phone.name)}</h3><p>Extension ${phone.extension} · ${phone.active ? "Enabled" : "Setup pending · your installer activates this phone"}</p><div class="inline-actions">${link("Dial shortcuts", `shortcuts/${phone.id}`, "button secondary")}${phonebookLink(phone)}${button("Rename phone", "rename-phone", phone.id, "text-button blue-text")}</div></div>`).join("") || '<p class="small-empty">No phone registered yet.</p>'}${button("Add a phone", "phone", child.id, "spaced")}<p class="form-note spaced">Your installer connects and tests the physical phone. Enabled does not mean the phone is currently online.</p></section><section class="panel"><div class="section-heading"><h2>Quiet hours</h2>${button("Add quiet hours", "quiet", child.id, "text-button blue-text")}</div><p class="form-note">All times use ${Demo.TIME_ZONE}, the demo phone system’s time zone. Each interval must end on the same day.</p>${child.quietHours.map(period => `<div class="device-row"><h3>${esc(period.label)} ${period.is_active ? "" : '<span class="pill neutral">Paused</span>'}</h3><p>${esc(PORTAL.forms.quiet.find(f => f.name === "day_group").choices.find(([key]) => key === period.day_group)?.[1])} · ${esc(period.start_time)}–${esc(period.end_time)}</p><div class="inline-actions"><button class="text-button blue-text" data-action="edit-quiet" data-id="${esc(child.id)}" data-period="${esc(period.id)}">Edit</button>${period.is_active ? `<button class="text-button" data-action="pause-quiet" data-id="${esc(child.id)}" data-period="${esc(period.id)}">Pause</button>` : ""}</div></div>`).join("") || '<p class="small-empty">No quiet hours set.</p>'}</section></div><p class="section-footnote">${link("Manage family connections", "circle")} · ${link("Manage external contacts", "contacts")}</p>`;
}
function shortcutsPage() {
  const source = Demo.findDevice(state, detailId);
  if (!source) return empty("Phone not found.", "Choose a phone from Children & phones.");
  const targets = Demo.destinations(state, source.phone.id);
  return `${heading(`Dial shortcuts · ${esc(source.phone.name)}`, "A familiar voice, one digit away.", `<div class="inline-actions">${phonebookLink(source.phone)}${link("Back to child", `child/${source.child.id}`, "button secondary")}</div>`)}<div class="info-strip"><p>Shortcuts never add calling permission. Only approved destinations can be assigned.</p></div><div class="dial-grid">${PORTAL.forms.shortcut.find(f => f.name === "digits").choices.map(([digit]) => {
    const shortcut = source.phone.shortcuts.find(s => s.digits === digit);
    const target = shortcut && targets.find(t => t.key === shortcut.target);
    return `<article class="dial-slot"><span class="dial-digit">${digit}</span><h2>${shortcut ? esc(shortcut.label || target?.name || shortcut.targetName || "Saved destination") : "Not assigned"}</h2>${shortcut ? `<p>${target ? esc(`${target.name} · ${target.detail}`) : "Destination unavailable"}</p><span class="pill ${target && shortcut.active ? "green" : "neutral"}">${!target ? "Unavailable" : shortcut.active ? "Enabled" : "Paused"}</span>` : ""}<div class="inline-actions"><button class="text-button blue-text" data-action="edit-shortcut" data-id="${esc(source.phone.id)}" data-digit="${digit}">${shortcut ? "Edit" : "Assign"}</button>${shortcut ? `<button class="text-button" data-action="toggle-shortcut" data-id="${esc(source.phone.id)}" data-shortcut="${esc(shortcut.id)}">${shortcut.active ? "Pause" : "Enable"}</button><button class="text-button danger-text" data-action="remove-shortcut" data-id="${esc(source.phone.id)}" data-shortcut="${esc(shortcut.id)}">Remove</button>` : ""}</div></article>`;
  }).join("")}</div>`;
}
function connectionsPage() {
  return `${heading("A circle you choose.", "Build connections with families you already know.", link("Connect a family", "directory", "button"))}<div class="info-strip"><p>One invitation, one acceptance. Only the selected children can call each other both ways. Other children and parent/shared phones are not included.</p></div><div class="connection-grid">${state.connections.map(pair => `<article class="connection-card"><div class="person-line">${avatar("Friends", "lavender")}<div><h2>${pairLabel(pair)}</h2><span>${esc(state.family)} · ${esc(familyName(pair.familyId))}</span></div></div><div class="direction-block"><div class="permission-line"><span>Child-to-child connection</span><span class="pill green">Calls both ways</span></div>${button("Remove connection", "remove-connection", pair.id, "text-button danger-text")}</div></article>`).join("") || empty("Start with someone you know.", "Explore listed families, or use a code shared by a parent.", link("Browse the directory", "directory", "button"))}</div><section class="connections-preview"><div class="section-heading"><h2>Group calls</h2>${button("Add a group", "group")}</div><p class="form-note">Groups need explicit membership approval. Your installer enables a group’s dial extension.</p><div class="connection-grid spaced">${state.groups.map(group => `<article class="panel"><h3>${esc(group.name)}</h3><p>${esc(names(group.members))}</p><p>${group.is_active && group.enabled ? `Extension ${group.extension}` : "Calling not enabled"}</p>${button("Manage group", "group", group.id, "text-button blue-text")}</article>`).join("") || '<p class="small-empty">No group calls set up yet.</p>'}</div></section>`;
}
function directoryStatus(familyId) {
  const pending = state.invitations.find(i => i.familyId === familyId && i.status === "pending");
  if (pending) return pending.direction === "incoming" ? "Invitation received" : "Invitation sent";
  return state.connections.some(c => c.familyId === familyId) ? "Connected" : "";
}
function directoryResults() {
  return Demo.listedFamilies(state, directoryQuery).map(family => {
    const status = family.id === "own" ? "Your family" : directoryStatus(family.id);
    return `<article class="directory-card"><div class="directory-card-top">${avatar(family.name)}${status ? `<span class="pill blue">${status}</span>` : ""}</div><h2>The ${esc(family.name)} family</h2><div class="directory-guardians">${icon("users")}<div>${esc(family.guardians.join(", ") || "Guardian names private")}</div></div>${status.startsWith("Invitation") ? button(status === "Invitation received" ? "Review invitation" : "View invitation", "pending-family", family.id, "card-action") : family.id === "own" ? "" : button("Request a connection", "invite", family.id, "card-action")}</article>`;
  }).join("") || empty("No familiar names yet.", "Try another name or use a code shared by a parent.");
}
function directoryPage() {
  return `${heading("Find a familiar family.", "Explore families who have chosen to be listed in your private network.", button("Use an invite code", "invite-code"))}<div class="directory-welcome"><span class="directory-welcome-icon">${icon("users")}</span><div><h2>Good company starts with a hello.</h2><p>Only family names and opted-in guardian names appear here. An invitation still needs approval before children can call.</p></div></div><div class="directory-visibility-summary"><p>Your family is <strong>${state.directoryListed ? "listed" : "unlisted"}</strong>. You choose when to be found.</p>${link("Manage visibility", "settings")}</div><form class="directory-toolbar" data-form="directory-search"><label class="directory-search">${icon("search")}<span class="sr-only">Search family or guardian names</span><input name="q" id="directory-search" type="search" maxlength="200" value="${esc(directoryQuery)}" placeholder="Search family or guardian names"></label><button class="button secondary">Search</button><span class="directory-count" id="directory-count" role="status">${Demo.listedFamilies(state, directoryQuery).length} families</span></form><div class="directory-grid" id="directory-results">${directoryResults()}</div>`;
}
function invitationsPage() {
  const items = state.invitations.filter(i => inviteTab === "history" ? i.status !== "pending" : i.direction === inviteTab && i.status === "pending");
  return `${heading("A hello worth opening.", "Review who wants to connect, and keep track of your invitations.", link("Connect a family", "directory", "button"))}<div class="tab-list" role="tablist" aria-label="Invitation type">${[["incoming", "Received"], ["outgoing", "Sent"], ["history", "History"]].map(([key, name]) => `<button role="tab" id="tab-${key}" aria-controls="invitation-panel" aria-selected="${inviteTab === key}" tabindex="${inviteTab === key ? "0" : "-1"}" class="${inviteTab === key ? "selected" : ""}" data-action="invite-tab" data-id="${key}">${name}</button>`).join("")}</div><div class="invite-list" id="invitation-panel" role="tabpanel" aria-labelledby="tab-${inviteTab}">${items.map(invitation => `<article class="invite-card"><div class="invite-card-top"><div class="person-line">${avatar(familyName(invitation.familyId), "lavender")}<div><h2>The ${esc(familyName(invitation.familyId))} family</h2><span>${esc(invitation.date)}</span></div></div><span class="pill ${invitation.status === "accepted" ? "green" : invitation.status === "pending" ? "amber" : "neutral"}">${esc(invitation.status === "pending" ? invitation.direction === "incoming" ? "Needs your approval" : "Waiting for their approval" : invitation.status)}</span></div><p>${invitation.direction === "incoming" ? `Their children: <strong>${esc(peerNames(invitation))}</strong>` : `Your children: <strong>${esc(names(invitation.childIds))}</strong>`}${invitation.status === "accepted" ? `<br>Connected: ${esc(names(invitation.childIds))} ↔ ${esc(peerNames(invitation))}` : ""}</p>${invitation.message ? `<blockquote>${esc(invitation.message)}</blockquote>` : ""}<div class="invite-card-bottom"><span>${icon("shield")} ${invitation.status === "pending" ? "Calling stays off until both families approve." : "Manage current permissions in Family connections."}</span>${invitation.status === "pending" ? `<div>${invitation.direction === "incoming" ? button("Decline", "decline-invite", invitation.id) + button("Review invitation", "review-invite", invitation.id, "") : button("Cancel invitation", "cancel-invite", invitation.id)}</div>` : ""}</div>${invitation.direction === "outgoing" && invitation.status === "pending" ? `<div class="demo-control-row">${button("Demo: preview receiving parent", "preview-receiver", invitation.id, "text-button blue-text")}</div>` : ""}</article>`).join("") || empty("You’re all caught up.", "Your invitations will appear here.")}</div>`;
}
function contactsPage() {
  return `${heading("Familiar voices, near and far.", "A private address book for the people outside FrontPorch.", button("Add a contact", "contact", "", ""))}<section class="family-contacts-banner"><span class="icon-tile">${icon("users")}</span><div><h2>Familiar voices for the whole family.</h2><p>Saving a contact approves calls both ways for all current and future children in your family.</p></div></section>${state.contacts.length ? `<div class="contacts-table-wrap"><table class="contacts-table"><thead><tr><th>Contact</th><th>Dial extension</th><th>Calling access</th><th><span class="sr-only">Manage</span></th></tr></thead><tbody>${state.contacts.map(contact => `<tr><th scope="row"><div class="person-line">${avatar(contact.name, "peach", "small-avatar")}<div><strong>${esc(contact.name)}</strong><span>${esc(contact.phone)}</span></div></div></th><td>${contact.extension}</td><td><span class="pill green">All children</span></td><td>${button("Edit", "contact", contact.id, "text-button blue-text")}</td></tr>`).join("")}</tbody></table></div>` : empty("Keep a familiar voice close.", "Add a trusted person’s phone number.", button("Add a contact", "contact"))}<p class="section-footnote">Contact names are private to your family. Removing a contact revokes this family approval for all children.</p>`;
}
function settingsPage() {
  const parent = currentParent();
  const profile = {display_name:parent.name, phone:parent.phone, call_destination:parent.callDestination, directory_visible:parent.directoryVisible};
  return `${heading("Make yourself at home.", "Your family details and the parents who keep things running.")}<div class="settings-grid"><section class="panel settings-panel"><h2>Your family</h2><form data-form="family">${fields("family", {name:state.family, directory_listed:state.directoryListed})}${formErrorMarkup}<p class="form-note">Listing shows only your family name and guardian names that each guardian chooses to share. Hiding your family preserves existing connections.</p><button class="button">Save family details</button></form>${button("Show setup checklist", "show-setup", "", "text-button blue-text spaced")}</section><section class="panel settings-panel"><h2>Your guardian profile</h2><p class="form-note">Your calling extension is <strong>${esc(parent.extension)}</strong>.</p><form data-form="profile">${fields("profile", profile)}${formErrorMarkup}<button class="button">Save your profile</button></form></section>${guardiansPanel()}<section class="panel settings-panel"><h2>A hello by invitation.</h2><p class="dialog-intro">Share this code privately with another parent to help them find your family, even when you’re unlisted. It never grants calling permission.</p><code class="family-code" id="family-code">${esc(state.inviteCode)}</code>${button(`${icon("copy")} Copy code`, "copy-code")}<p class="copy-status" role="status"></p>${button("Replace code", "rotate-code", "", "text-button blue-text")}${note("This fictional code belongs to this tab. It cannot connect visitors on other browsers.")}</section><section class="safety-panel"><span class="icon-tile">${icon("info")}</span><div><h3>Keep another phone for emergencies.</h3><p>FrontPorch does not support emergency calls. Your family needs another way to reach emergency services.</p>${parent.emergencyNoticeDismissed ? button("Show 911 notice", "show-emergency", "", "text-button") : ""}</div></section></div>`;
}
function guardiansPanel() {
  const primary = currentParent().primary;
  return `<section class="panel settings-panel"><h2>Parents & guardians</h2>${state.guardians.map(member => `<div class="device-row"><div class="person-line">${avatar(member.name, "yellow", "small-avatar")}<div><strong>${esc(member.name)}</strong><span>${esc(member.email)}</span></div><span class="pill neutral">${member.primary ? "Primary guardian" : member.active ? "Guardian" : "No portal access"}</span></div>${primary && member.active && !member.primary ? button("Remove guardian access", "remove-guardian", member.id, "text-button danger-text spaced") : ""}</div>`).join("")}${primary ? button("Invite a guardian", "invite-guardian", "", "secondary spaced") : '<p class="form-note">The primary guardian manages membership invitations.</p>'}${primary ? state.guardianInvites.filter(i => i.status === "pending").map(invitation => `<div class="device-row"><h3>${esc(invitation.name)}</h3><p>${esc(invitation.email)} · ${Demo.inviteStatus(invitation) === "pending" ? "Pending until" : "Expired"} ${new Date(invitation.expiresAt).toLocaleDateString("en-US", {month:"short", day:"numeric"})}</p><div class="inline-actions">${button("Resend invitation", "resend-guardian", invitation.id, "text-button blue-text")}${button("Cancel invitation", "cancel-guardian", invitation.id, "text-button")}</div>${Demo.inviteStatus(invitation) === "pending" ? `<div class="demo-control-row">${button("Demo: preview recipient", "preview-guardian", invitation.id, "text-button blue-text")}</div>` : ""}</div>`).join("") : ""}</section>`;
}
function childDialog(childId) {
  const child = Demo.findChild(state, childId);
  openDialog(child ? `Edit ${esc(child.name)}` : "Add a child", `<p class="dialog-intro">Children don’t need accounts. You manage their phones and the people they can call.</p>${fields("child", child || {})}`, {form:"child", id:childId});
}
function phoneDialog(childId, deviceId = "") {
  const source = deviceId && Demo.findDevice(state, deviceId);
  const child = source ? source.child : Demo.findChild(state, childId);
  if (!child) return;
  openDialog(source ? "A familiar name for their phone." : `A phone for ${esc(child.name)}`, `<p class="dialog-intro">${source ? "Your installer manages activation and connection details." : "We’ll reserve an extension automatically. Your installer configures the physical phone and activates calling."}</p>${fields("phone", {friendly_name:source ? source.phone.name : `${child.name}’s phone`})}`, {form:source ? "rename-phone" : "phone", id:source ? deviceId : childId, submit:source ? "Save" : "Reserve phone"});
}
function quietDialog(childId, periodId = "") {
  const child = Demo.findChild(state, childId);
  if (!child) return;
  const period = child.quietHours.find(p => p.id === periodId);
  openDialog(`${period ? "Edit" : "Add"} quiet hours for ${esc(child.name)}`, `<p class="form-note">Times use ${Demo.TIME_ZONE}, the demo phone system’s time zone. End time must be later on the same day.</p>${fields("quiet", period || {})}`, {form:"quiet", id:childId, extra:`data-period="${esc(periodId)}"`});
}
function shortcutDialog(deviceId, digit) {
  const source = Demo.findDevice(state, deviceId);
  if (!source) return;
  const shortcut = source.phone.shortcuts.find(s => s.digits === digit);
  const options = [["", "Choose an approved destination"], ...Demo.destinations(state, deviceId).map(t => [t.key, `${t.name} · ${t.detail}`])];
  openDialog(`Dial shortcut · ${esc(source.phone.name)}`, `<p class="dialog-intro">Choose an already approved destination. Shortcuts never add calling permission; quiet hours still apply.</p>${field("shortcut", "digits", {digits:digit})}${field("shortcut", "target", {target:shortcut?.target || ""}, {options})}${field("shortcut", "label", {label:shortcut?.label || ""})}${field("shortcut", "is_active", {is_active:shortcut ? shortcut.active : true})}`, {form:"shortcut", id:deviceId, extra:`data-shortcut="${esc(shortcut?.id || "")}"`, submit:"Save shortcut"});
}
function connectionDialog(familyId, code = "") {
  const target = Demo.family(state, familyId);
  if (!target || (!target.listed && target.code !== code)) return;
  if (!state.children.length) { openDialog("Add a child first.", `<p class="dialog-intro">Add a child before sending a connection invitation.</p>${button("Add a child", "child")}`); return; }
  inviteDraft = {familyId, code};
  openDialog(`Say hello to the ${esc(target.name)} family.`, `<p class="dialog-intro">Select your children. The receiving parent chooses which of their children to connect with them. One acceptance enables calls both ways for those selected child pairs.</p>${field("invitation", "children", {}, {options:state.children})}${field("invitation", "message")}`, {form:"invitation", submit:"Send invitation"});
}
function reviewInvitation(invitationId, preview = false) {
  const invitation = state.invitations.find(i => i.id === invitationId && i.status === "pending");
  if (!invitation || (preview ? invitation.direction !== "outgoing" : invitation.direction !== "incoming")) return;
  const target = Demo.family(state, invitation.familyId);
  const choices = preview ? target.children : state.children;
  openDialog(preview ? `Receiving parent · ${esc(target.name)} family` : `A hello from the ${esc(target.name)} family.`, `${preview ? note("Demo recipient preview: choose the other family’s children. Only this tab changes; no invitation is delivered.") : ""}<p class="dialog-intro">${preview ? "Invited children: " + esc(names(invitation.childIds)) : "Their children: " + esc(peerNames(invitation))}. Only the selected child pairs can call each other both ways.</p>${invitation.message ? `<blockquote>${esc(invitation.message)}</blockquote>` : ""}${field("accept", "children", {children:choices.map(c => c.id)}, {options:choices})}`, {form:"accept", id:invitation.id, submit:"Accept invitation"});
}
function contactDialog(contactId) {
  const contact = state.contacts.find(c => c.id === contactId);
  openDialog(contact ? "Edit family contact" : "Add a family contact", `<p class="dialog-intro">Saving approves calls both ways for every current and future child in your family. The name stays private.</p>${fields("contact", contact ? {label:contact.name, phone_number:contact.phone, notes:contact.notes} : {})}${contact ? button("Remove contact", "remove-contact", contact.id, "text-button danger-text") : ""}`, {form:"contact", id:contactId});
}
function guardianDialog() {
  Demo.primaryOnly(state);
  openDialog("Invite a guardian", `<p class="dialog-intro">Invite a guardian to manage your existing family. Access begins when they accept.</p>${fields("guardian")}${note("Use a fictional email. No email is sent; a recipient preview will appear in Family settings.")}`, {form:"guardian", submit:"Send invitation"});
}
function guardianJoin(invitationId, login = false) {
  const invitation = state.guardianInvites.find(i => i.id === invitationId);
  if (!invitation || Demo.inviteStatus(invitation) !== "pending") { openDialog("This invitation is no longer available.", '<p>Ask the primary guardian for a new invitation.</p>'); return; }
  const outsideAccount = state.network.some(f => f.guardians.some(g => Demo.same(g.email, invitation.email)));
  const existing = outsideAccount || state.guardians.some(g => Demo.same(g.email, invitation.email));
  openDialog(`Join the ${esc(state.family)} family.`, `${note("Demo recipient preview. Use a made-up password. No email or authentication occurs, and passwords are discarded.")}<p class="dialog-intro">${esc(state.guardians.find(g => g.primary).name)} invited ${esc(invitation.name)} (${esc(invitation.email)}) to join as a guardian.</p>${existing || login ? `${field("login", "login", {login:invitation.email})}${field("login", "password")}` : `${button("I already have an account", "guardian-login", invitation.id)}<h3 class="spaced">Create your guardian account</h3><p class="form-note">Your email is fixed to ${esc(invitation.email)}.</p>${fields("join")}`}`, {form:"join", id:invitationId, extra:`data-mode="${existing || login ? "login" : "create"}"`, submit:"Accept invitation and join family"});
}
function groupDialog(groupId) {
  const group = state.groups.find(g => g.id === groupId);
  openDialog(group ? "Edit Conference Group" : "Add Conference Group", `${field("group", "name", group || {})}${field("group", "members", group || {}, {options:state.children})}${field("group", "is_active", group || {})}${field("group", "notes", group || {})}<p class="form-note">Choose at least two children. Your installer enables the group’s dial extension.</p>`, {form:"group", id:groupId});
}
function demoTools() {
  openDialog("Your demo sandbox", `${note("These controls simulate actions performed by another guardian or installer. All changes stay in this tab.")}<form data-form="demo-actor"><label class="field"><span>Explore as guardian</span><select name="guardian">${state.guardians.filter(g => g.active).map(g => `<option value="${esc(g.id)}" ${g.id === currentParent().id ? "selected" : ""}>${esc(g.name)} · ${g.primary ? "Primary guardian" : "Guardian"}</option>`).join("")}</select></label><button class="button secondary">Switch guardian</button>${formErrorMarkup}</form><h3 class="spaced">Installer preview</h3><p class="form-note">Enabled means configured, not observed online. Real parents reserve phones; their installer activates them.</p>${state.children.flatMap(c => c.devices.map(phone => `<div class="device-row"><h3>${esc(c.name)} · ${esc(phone.name)}</h3><p>Extension ${phone.extension} · ${phone.active ? "Enabled" : "Setup pending"}</p>${button(phone.active ? "Demo: disable phone" : "Demo: activate phone", "demo-activate", phone.id, "text-button blue-text")}</div>`)).join("") || '<p class="small-empty">Reserve a phone to try installer activation.</p>'}${state.groups.map(group => `<div class="device-row"><h3>${esc(group.name)}</h3>${button(group.enabled ? "Demo: disable group calling" : "Demo: enable group calling", "demo-group", group.id, "text-button blue-text")}</div>`).join("")}<p class="form-note spaced">Try a fictional unlisted family with code <strong>PINE-7K2M</strong>. Review sent connection invitations to preview the receiving parent.</p>`);
}
document.addEventListener("click", async event => {
  if (event.target.closest(".skip-link")) { event.preventDefault(); $("#main").focus(); $("#main").scrollIntoView(); return; }
  const element = event.target.closest("[data-action]");
  if (!element) return;
  event.preventDefault();
  const {action, id = "", period, digit, shortcut:shortcutId} = element.dataset;
  try {
    switch (action) {
      case "landing": case "logout": go("welcome"); break;
      case "demo": go("overview"); break;
      case "signup": go("signup"); break;
      case "close": closeDialog(); break;
      case "confirm": { const callback = confirmAction; confirmAction = null; if (callback) callback(); break; }
      case "reset": confirm("Start fresh with the Maple family?", "This resets this tab’s demo changes and restores the sample children, connections, and invitations.", () => { state = Demo.seed(); inviteTab = "incoming"; directoryQuery = ""; inviteDraft = null; finish("The sample family is ready to explore again.", "overview"); }); break;
      case "demo-tools": demoTools(); break;
      case "dismiss-setup": state.setupDismissed = true; finish("Setup dismissed. Reopen it in Family settings."); break;
      case "show-setup": state.setupDismissed = false; finish("Setup checklist restored.", "overview"); break;
      case "dismiss-emergency-notice": currentParent().emergencyNoticeDismissed = true; finish("911 notice dismissed."); break;
      case "show-emergency": currentParent().emergencyNoticeDismissed = false; finish("911 notice restored."); break;
      case "child": childDialog(id); break;
      case "phone": phoneDialog(id); break;
      case "rename-phone": phoneDialog("", id); break;
      case "quiet": quietDialog(id); break;
      case "edit-quiet": quietDialog(id, period); break;
      case "pause-quiet": {
        const schedule = Demo.findChild(state, id)?.quietHours.find(p => p.id === period);
        if (schedule) { schedule.is_active = false; finish("Quiet hours paused."); }
        break;
      }
      case "demo-activate": {
        const source = Demo.findDevice(state, id);
        if (source) { source.phone.active = !source.phone.active; finish(`Demo installer ${source.phone.active ? "enabled" : "disabled"} ${source.phone.name}.`); demoTools(); }
        break;
      }
      case "demo-group": {
        const group = state.groups.find(g => g.id === id);
        if (group) {
          if (!group.extension) group.extension = Demo.nextExtension(state);
          group.enabled = !group.enabled; finish(`Demo installer ${group.enabled ? "enabled" : "disabled"} group calling.`); demoTools();
        }
        break;
      }
      case "edit-shortcut": shortcutDialog(id, digit); break;
      case "toggle-shortcut": {
        const item = Demo.findDevice(state, id)?.phone.shortcuts.find(s => s.id === shortcutId);
        if (item) {
          Demo.assert(item.active || Demo.destinations(state, id).some(t => t.key === item.target), "Choose an approved destination before enabling this shortcut.");
          item.active = !item.active; finish(item.active ? "Shortcut enabled." : "Shortcut paused.");
        }
        break;
      }
      case "remove-shortcut": confirm("Remove this shortcut?", "This frees the key on this phone. Calling permissions stay the same.", () => {
        const source = Demo.findDevice(state, id);
        if (source) { source.phone.shortcuts = source.phone.shortcuts.filter(s => s.id !== shortcutId); finish("Shortcut removed."); }
      }); break;
      case "invite": connectionDialog(id); break;
      case "invite-code": openDialog("Find a family by code", `${fields("code")}${note("Try WILLOW-3R7J, or PINE-7K2M for a fictional unlisted family.")}`, {form:"code", submit:"Find family"}); break;
      case "pending-family": inviteTab = state.invitations.find(i => i.familyId === id && i.status === "pending")?.direction || "incoming"; go("invites"); break;
      case "invite-tab": inviteTab = id; render(); $(`#tab-${id}`).focus(); break;
      case "review-invite": reviewInvitation(id); break;
      case "preview-receiver": reviewInvitation(id, true); break;
      case "decline-invite": case "cancel-invite": confirm(action === "decline-invite" ? "Decline this invitation?" : "Cancel this invitation?", "This request will not connect any children. It will move to History.", () => {
        const invitation = state.invitations.find(i => i.id === id && i.status === "pending");
        if (invitation) { invitation.status = action === "decline-invite" ? "declined" : "cancelled"; finish(`Invitation ${invitation.status}.`); }
      }); break;
      case "remove-connection": confirm("Remove this connection?", "Stop calls between these children in both directions?", () => {
        state.connections = state.connections.filter(pair => pair.id !== id); finish("Calling between these children is now off in both directions.");
      }); break;
      case "contact": contactDialog(id); break;
      case "remove-contact": confirm("Remove this contact?", "Calling approval is removed for all children. Saved shortcuts to this number become unavailable.", () => {
        state.contacts = state.contacts.filter(c => c.id !== id); finish("Contact removed for all children.");
      }); break;
      case "invite-guardian": guardianDialog(); break;
      case "preview-guardian": guardianJoin(id); break;
      case "guardian-login": guardianJoin(id, true); break;
      case "resend-guardian": Demo.resendGuardian(state, id); finish("A replacement invitation is ready in this demo. The previous invitation no longer works."); break;
      case "cancel-guardian": Demo.primaryOnly(state); confirm("Cancel this guardian invitation?", "The recipient can no longer join using this invitation.", () => {
        Demo.primaryOnly(state);
        const invitation = state.guardianInvites.find(i => i.id === id && i.status === "pending");
        if (invitation) { invitation.status = "cancelled"; finish("Guardian invitation cancelled."); }
      }); break;
      case "remove-guardian": Demo.primaryOnly(state); confirm("Remove guardian access?", "This guardian loses family access. Existing calling approvals stay in place.", () => { Demo.removeGuardian(state, id); finish("Guardian access removed."); }); break;
      case "rotate-code": confirm("Replace your family code?", "The previous code will stop working.", () => { state.inviteCode = `FP-${Demo.id().replaceAll("-", "").slice(0, 24)}`; finish("Family code replaced."); }); break;
      case "copy-code": {
        const status = $(".copy-status");
        try { await navigator.clipboard.writeText(state.inviteCode); status.textContent = "Demo code copied. It works only within this tab’s fictional world."; }
        catch { const range = document.createRange(); range.selectNodeContents($("#family-code")); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); status.textContent = "Code selected. Use your device’s copy command."; }
        break;
      }
      case "group": groupDialog(id); break;
    }
  } catch (error) {
    const errorElement = $("#dialog[open] .form-error");
    if (errorElement) { errorElement.hidden = false; errorElement.textContent = error.message; }
    else toast(error.message);
  }
});

document.addEventListener("submit", event => {
  const form = event.target.closest("[data-form]");
  if (!form) return;
  event.preventDefault();
  const data = new FormData(form), {form:kind, id = ""} = form.dataset;
  try {
    switch (kind) {
      case "login": form.reset(); finish("You’re exploring your browser’s demo family.", "overview"); break;
      case "signup": {
        const values = formValues("signup", data);
        validateDemoPassword(values);
        const phone = Demo.normalizePhone(values.phone);
        Demo.assert(!state.network.some(f => Demo.same(f.name, values.family_name)), "A family with this name already exists.");
        Demo.assert(!state.network.some(f => f.guardians.some(g => Demo.same(g.email, values.email))), "An account already uses this email.");
        state = Demo.seed();
        state.family = values.family_name; state.directoryListed = values.directory_listed;
        state.inviteCode = `FP-${Demo.id().replaceAll("-", "").slice(0, 24)}`;
        Object.assign(state.guardians[0], {name:values.display_name, email:values.email.toLowerCase(), phone, directoryVisible:values.directory_listed});
        state.children = []; state.connections = []; state.invitations = []; state.contacts = []; state.contactExtensions = {}; state.groups = []; state.activity = [];
        form.reset(); finish("Your family is set up. Add your first child next.", "overview"); break;
      }
      case "child": {
        const child = Demo.saveChild(state, id, formValues("child", data));
        finish(`${child.name}’s child card saved.`, "children"); break;
      }
      case "phone": {
        const phone = Demo.reservePhone(state, id, formValues("phone", data).friendly_name);
        finish(`Extension ${phone.extension} reserved. Your installer will configure and activate this phone.`, `child/${id}`); break;
      }
      case "rename-phone": {
        const source = Demo.findDevice(state, id);
        Demo.assert(source, "This phone is no longer available.");
        source.phone.name = formValues("phone", data).friendly_name;
        finish("Phone name updated.", `child/${source.child.id}`); break;
      }
      case "quiet": Demo.saveQuiet(state, id, form.dataset.period, formValues("quiet", data)); finish("Quiet hours saved.", `child/${id}`); break;
      case "shortcut": {
        const values = formValues("shortcut", data);
        Demo.saveShortcut(state, id, form.dataset.shortcut, {digits:values.digits, target:values.target, label:values.label, active:values.is_active});
        finish("Dial shortcut saved.", `shortcuts/${id}`); break;
      }
      case "directory-search": directoryQuery = String(data.get("q") || "").trim(); render(); break;
      case "code": {
        const {code} = formValues("code", data);
        Demo.assert(code !== state.inviteCode, "That is your own family’s code. Ask the other parent for theirs.");
        const target = state.network.find(f => f.code === code);
        Demo.assert(target, "We couldn’t find that invite code. Check it with the parent who shared it.");
        connectionDialog(target.id, code); break;
      }
      case "invitation": {
        Demo.assert(inviteDraft, "Choose a listed family or enter a valid code first.");
        const {message} = formValues("invitation", data);
        Demo.sendInvitation(state, inviteDraft.familyId, data.getAll("children"), message, inviteDraft.code);
        inviteDraft = null; inviteTab = "outgoing";
        finish("Invitation saved in this demo. Calling stays off until the other family accepts.", "invites"); break;
      }
      case "accept": Demo.acceptInvitation(state, id, data.getAll("children")); finish("The selected children can now call each other both ways.", "circle"); break;
      case "contact": {
        const contact = Demo.saveContact(state, id, formValues("contact", data));
        finish(`${contact.name} is approved for calls both ways with all your children.`, "contacts"); break;
      }
      case "family": {
        const values = formValues("family", data);
        Demo.assert(!state.network.some(f => Demo.same(f.name, values.name)), "A family with this name already exists.");
        state.family = values.name; state.directoryListed = values.directory_listed;
        finish("Family details saved."); break;
      }
      case "profile": Demo.saveProfile(state, formValues("profile", data)); finish("Guardian profile saved."); break;
      case "guardian": {
        const values = formValues("guardian", data);
        Demo.inviteGuardian(state, values.display_name, values.email);
        finish("Guardian invitation created in this demo. Use the recipient preview in Family settings.", "settings"); break;
      }
      case "join": {
        const invitation = state.guardianInvites.find(i => i.id === id);
        if (form.dataset.mode === "create") validateDemoPassword(formValues("join", data));
        const email = form.dataset.mode === "login" ? String(data.get("login") || "") : invitation?.email;
        const member = Demo.joinGuardian(state, id, email);
        form.reset(); finish(`${member.name} joined as a guardian. You’re back in the sender’s view.`, "settings"); break;
      }
      case "group": {
        const group = Demo.saveGroup(state, id, formValues("group", data), data.getAll("members"));
        finish(`${group.name} saved.`, "circle"); break;
      }
      case "demo-actor": {
        const parent = state.guardians.find(g => g.id === data.get("guardian") && g.active);
        Demo.assert(parent, "Choose an active guardian.");
        state.currentGuardianId = parent.id; finish(`Demo: exploring as ${parent.name}.`, "settings"); break;
      }
    }
  } catch (error) { showError(form, error.message); }
});

document.addEventListener("input", event => {
  const input = event.target;
  if (input.id === "directory-search") {
    directoryQuery = input.value;
    $("#directory-results").innerHTML = directoryResults();
    $("#directory-count").textContent = `${Demo.listedFamilies(state, directoryQuery).length} families`;
  }
  if (input.closest('[data-form="signup"]')) {
    if (input.name === "family_name") $("[data-preview-family]").textContent = input.value.trim() || "Your family";
    if (input.name === "display_name") $("[data-preview-guardian]").textContent = input.value.trim() || "Your guardian name";
  }
});
document.addEventListener("keydown", event => {
  if (!event.target.matches('[role="tab"]') || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const options = ["incoming", "outgoing", "history"];
  inviteTab = event.key === "Home" ? "incoming" : event.key === "End" ? "history" : options[(options.indexOf(inviteTab) + (event.key === "ArrowRight" ? 1 : 2)) % 3];
  render(); $(`#tab-${inviteTab}`).focus();
});
window.addEventListener("hashchange", route);
route();

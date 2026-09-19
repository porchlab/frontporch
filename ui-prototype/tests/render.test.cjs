const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {runtime, root} = require('./harness.cjs');

function ui() {
  const {context} = runtime();
  const listeners = {}, nodes = new Map();
  const node = () => ({hidden:false, innerHTML:'', textContent:'', classList:{add() {}, remove() {}}, focus() {}, scrollIntoView() {}, close() {}, showModal() {}});
  Object.assign(context, {
    document:{addEventListener(name, handler) { listeners[name] = handler; }, querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, node()); return nodes.get(selector); }},
    window:{sessionStorage:{getItem() {return null;}, setItem() {}}, addEventListener() {}, scrollTo() {}},
    location:{hash:'#family/overview'}, setTimeout() {}, clearTimeout() {},
    FormData:class {
      constructor(form) { this.values = form.values; }
      get(key) { return this.values[key] ?? null; }
      has(key) { return Object.hasOwn(this.values, key); }
      getAll(key) { return [].concat(this.values[key] || []); }
    },
  });
  for (const file of ['portal-contract.js', 'app.js']) vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
  return {context, nodes, listeners, run:script => vm.runInContext(script, context)};
}

test('all workspace renderers work with populated and empty households', () => {
  const {run} = ui();
  for (const page of ['overview', 'childrenPage', 'connectionsPage', 'directoryPage', 'invitationsPage', 'contactsPage', 'settingsPage']) {
    assert.match(run(`${page}()`), /<h1>/);
  }
  run('state.children = []; state.connections = []; state.invitations = []; state.contacts = []; state.groups = [];');
  for (const page of ['overview', 'childrenPage', 'connectionsPage', 'directoryPage', 'invitationsPage', 'contactsPage', 'settingsPage']) {
    assert.match(run(`${page}()`), /<h1>/);
  }
});
test('family, child, contact and guardian values are escaped wherever rendered', () => {
  const {run} = ui();
  run(`state.family = '<img src=x onerror=alert(1)>'; state.children[0].name = state.family; state.contacts[0].name = state.family; state.guardians[0].name = state.family;`);
  for (const page of ['overview', 'childrenPage', 'connectionsPage', 'contactsPage', 'settingsPage']) {
    const html = run(`${page}()`);
    assert(!html.includes('<img src=x'));
    assert(html.includes('&lt;img src=x'));
  }
});
test('phone setup never renders an editable extension or activation checkbox', () => {
  const {run, nodes} = ui();
  run(`phoneDialog('casey')`);
  const html = nodes.get('#dialog').innerHTML;
  assert(html.includes('name="friendly_name"'));
  assert(!html.includes('name="extension"'));
  assert(!html.includes('name="is_active"'));
  assert(html.includes('Reserve phone'));
});
test('signup creates an empty independent family and discards both passwords', () => {
  const {run, listeners, context} = ui();
  let saved;
  context.window.sessionStorage.setItem = (key, value) => { saved = value; };
  const form = {dataset:{form:'signup'}, closest() {return this;}, reset() {}, values:{
    family_name:'Juniper', display_name:'Rowan', email:'rowan@example.com',
    password1:'do-not-store-this-password', password2:'do-not-store-this-password',
    phone:'', directory_listed:'on',
  }};
  listeners.submit({target:form, preventDefault() {}});
  assert.equal(run('state.family'), 'Juniper');
  assert.equal(run('state.children.length'), 0);
  assert.equal(run('state.connections.length'), 0);
  assert.equal(run('state.guardians[0].directoryVisible'), true);
  assert(saved);
  assert(!saved.includes('do-not-store-this-password'));
  assert(!saved.includes('password'));
});

const test = require('node:test');
const assert = require('node:assert/strict');
const {ui} = require('./harness.cjs');

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
test('phonebook links appear on child cards, child details and shortcut pages', () => {
  const {run} = ui();
  assert.match(run('childrenPage()'), /phonebook.html\?phone=casey-phone/);
  assert.match(run('detailId="casey"; childPage()'), /phonebook.html\?phone=casey-phone/);
  assert.match(run('detailId="casey-phone"; shortcutsPage()'), /phonebook.html\?phone=casey-phone/);
});
test('phonebooks escape all family values, keep the final row with the footer and handle unavailable sources', () => {
  const {run, context, nodes} = ui({phonebook:true});
  assert.equal(context.document.body.className, 'monochrome');
  assert.match(nodes.get('#main').innerHTML, /Fictional data/);
  assert.match(nodes.get('#main').innerHTML, /phonebook-ending/);
  const html = run(`(() => {
    const data=Demo.seed(), value='<img src=x onerror=alert(1)>';
    data.family=value; data.children[0].name=value; data.children[0].devices[0].name=value;
    data.contacts[0].name=value; data.children[0].devices[0].shortcuts[0].label=value;
    return phonebookCard(data, 'casey-phone');
  })()`);
  assert(!html.includes('<img src=x')); assert(html.includes('&lt;img src=x'));
  assert(!html.includes('+1202555'));
  assert.match(run(`phonebookCard(Demo.seed(), 'river-phone-0')`), /Phone not found/);
  assert.match(run(`(() => { const data=Demo.seed(); data.children[0].devices[0].active=false; return phonebookCard(data, 'casey-phone'); })()`), /not enabled yet/);
  assert.match(run(`(() => { const data=Demo.seed(); data.contacts=[]; data.connections=[]; return phonebookCard(data, 'casey-phone'); })()`), /No calls available yet/);
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

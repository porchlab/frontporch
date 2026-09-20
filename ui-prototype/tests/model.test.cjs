const test = require('node:test');
const assert = require('node:assert/strict');
const {runtime} = require('./harness.cjs');
const {Demo} = runtime();
const memory = () => ({value:null, getItem() { return this.value; }, setItem(key, value) { this.value = value; }});

test('phonebooks list every permitted extension, with shortcuts scoped to the selected phone', () => {
  const data = Demo.seed();
  const second = Demo.reservePhone(data, 'casey', 'Desk'); second.active = true;
  const entries = Demo.phonebook(data, 'casey-phone');
  assert.deepEqual(Array.from(entries, e => e.extension).sort(), ['6100', '6101', '7000', second.extension].sort());
  assert.equal(entries.find(e => e.extension === '7000').name, 'Alex');
  assert.equal(entries.find(e => e.extension === '7000').shortcuts[0].digits, '2');
  assert(entries.some(e => e.name === 'Grandma June' && e.shortcuts.length === 0));
  assert(Demo.phonebook(data, second.id).every(e => e.shortcuts.length === 0));
  assert(!JSON.stringify(entries).includes('+1202555'));
  assert.equal(Demo.phonebook(data, 'river-phone-0').length, 0);
});
test('phonebooks deduplicate shared extensions and omit shortcuts pointing at an inactive shared phone', () => {
  const data = Demo.seed(), peer = data.network[0].children[0];
  peer.devices.push({...peer.devices[0], id:'alex-second', name:'Alex desk'});
  Demo.saveShortcut(data, 'casey-phone', '', {digits:'3', target:'device:alex-second', label:'Buddy', active:true});
  let entries = Demo.phonebook(data, 'casey-phone');
  assert.equal(entries.filter(e => e.extension === '7000').length, 1);
  assert.deepEqual(Array.from(entries.find(e => e.extension === '7000').shortcuts, s => s.digits), ['2', '3']);
  peer.devices[0].active = false;
  entries = Demo.phonebook(data, 'casey-phone');
  assert.deepEqual(Array.from(entries.find(e => e.extension === '7000').shortcuts, s => s.digits), ['3']);
});
test('phonebooks recheck revoked connections, removed contacts, paused shortcuts and inactive phones', () => {
  const data = Demo.seed(), source = Demo.findDevice(data, 'casey-phone').phone;
  Demo.saveShortcut(data, source.id, '', {digits:'1', target:'contact:+12025550142', label:'Grandma', active:true});
  source.shortcuts[0].active = false;
  assert.equal(Demo.phonebook(data, source.id).find(e => e.extension === '7000').shortcuts.length, 0);
  source.shortcuts[0].active = true;
  data.connections = []; data.contacts = [];
  assert.equal(Demo.phonebook(data, source.id).length, 0);
  assert.equal(source.shortcuts.length, 2);
  Demo.acceptInvitation(data, 'cedar-invite', ['jordan']);
  assert.equal(Demo.phonebook(data, source.id).length, 0);
  data.contacts.push({name:'Grandma', phone:'+12025550142', extension:'6100'});
  source.active = false;
  assert.equal(Demo.phonebook(data, source.id).length, 0);
});
test('phonebooks include enabled member groups and parent phone shortcuts without inventing an extension', () => {
  const data = Demo.seed(); data.guardians[0].phone = '+12025550199';
  assert(!Demo.phonebook(data, 'casey-phone').some(e => e.extension === ''));
  Demo.saveShortcut(data, 'casey-phone', '', {digits:'1', target:'parent:primary', label:'Mom', active:true});
  const parent = Demo.phonebook(data, 'casey-phone').find(e => e.extension === '');
  assert.equal(parent.name, 'Morgan'); assert.equal(parent.shortcuts[0].digits, '1');
  const group = Demo.saveGroup(data, '', {name:'Home', is_active:true}, ['casey', 'jordan']);
  group.extension = Demo.nextExtension(data); group.enabled = true;
  assert(Demo.phonebook(data, 'casey-phone').some(e => e.extension === group.extension));
  Demo.saveShortcut(data, 'casey-phone', '', {digits:'3', target:`group:${group.id}`, active:true});
  group.enabled = false;
  assert(!Demo.phonebook(data, 'casey-phone').some(e => e.extension === group.extension));
  group.enabled = true; group.members = ['jordan', 'other-child'];
  assert(!Demo.phonebook(data, 'casey-phone').some(e => e.extension === group.extension));
  data.guardians[0].phone = '';
  assert(!Demo.phonebook(data, 'casey-phone').some(e => e.extension === ''));
});

// These assertions describe product outcomes, including denial and revocation.
test('each browser store has independent progress and a fresh reset', () => {
  const one = memory(), two = memory(), data = Demo.load(one);
  data.family = 'Juniper'; Demo.save(one, data);
  assert.equal(Demo.load(one).family, 'Juniper');
  assert.equal(Demo.load(two).family, 'Maple');
  Demo.save(one, Demo.seed()); assert.equal(Demo.load(one).family, 'Maple');
  one.value = '{broken'; assert.equal(Demo.load(one).family, 'Maple');
});
test('reserving multiple phones never enables calling and avoids all extension owners', () => {
  const data = Demo.seed(), first = Demo.reservePhone(data, 'casey', 'Desk'), second = Demo.reservePhone(data, 'casey', 'Kitchen');
  assert.equal(first.active, false); assert.equal(second.active, false);
  assert.notEqual(first.extension, second.extension);
  assert.equal(Demo.findChild(data, 'casey').devices.length, 3);
  assert(!Demo.destinations(data, 'casey-phone').some(t => t.key === `device:${first.id}`));
  first.active = true;
  assert(Demo.destinations(data, 'casey-phone').some(t => t.key === `device:${first.id}`));
  const contact = Demo.saveContact(data, '', {label:'Friend', phone_number:'202-555-0199', notes:''});
  assert.notEqual(contact.extension, first.extension);
});
test('shortcut keys are per phone and never grant a connection', () => {
  const data = Demo.seed(), other = Demo.reservePhone(data, 'casey', 'Desk');
  Demo.saveShortcut(data, 'casey-phone', '', {digits:'1', target:'contact:+12025550142', label:'Grandma', active:true});
  Demo.saveShortcut(data, other.id, '', {digits:'1', target:'contact:+12025550163', label:'Drew', active:true});
  assert.throws(() => Demo.saveShortcut(data, other.id, '', {digits:'1', target:'contact:+12025550142'}), /already assigned/);
  assert.throws(() => Demo.saveShortcut(data, other.id, '', {digits:'0', target:'contact:+12025550142'}), /1 to 9/);
  assert.throws(() => Demo.saveShortcut(data, other.id, '', {digits:'3', target:'device:river-phone-1'}), /approved destination/);
  assert(!Demo.destinations(data, 'casey-phone').some(t => t.key === 'device:casey-phone'));
});
test('acceptance creates only the selected Cartesian child pairs', () => {
  const data = Demo.seed(); Demo.acceptInvitation(data, 'cedar-invite', ['casey']);
  const pairs = data.connections.filter(c => c.familyId === 'cedar');
  assert.equal(pairs.length, 2); assert(pairs.every(c => c.childId === 'casey'));
  const later = Demo.saveChild(data, '', {name:'Blair', color:'green', notes:''});
  assert(!data.connections.some(c => c.childId === later.id || c.childId === 'jordan'));
  assert.throws(() => Demo.acceptInvitation(data, 'cedar-invite', ['jordan']), /already been answered/);
});
test('outgoing recipient preview excludes unchecked children and supports a later request', () => {
  const data = Demo.seed(); Demo.acceptInvitation(data, 'ash-invite', ['ash-0']);
  assert.equal(data.connections.filter(c => c.familyId === 'ash').length, 1);
  assert(!data.connections.some(c => c.peerId === 'ash-1'));
  const again = Demo.sendInvitation(data, 'ash', ['casey'], 'Another connection');
  Demo.acceptInvitation(data, again.id, ['ash-1']);
  assert.equal(data.connections.filter(c => c.familyId === 'ash').length, 2);
});
test('pending invitations in either direction prevent duplicates without granting permissions', () => {
  const data = Demo.seed();
  assert.throws(() => Demo.sendInvitation(data, 'ash', ['jordan'], ''), /pending invitation/);
  assert.throws(() => Demo.sendInvitation(data, 'cedar', ['jordan'], ''), /pending invitation/);
  assert.equal(data.connections.length, 1);
  assert.throws(() => Demo.sendInvitation(data, 'willow', [], ''), /at least one/);
  assert.throws(() => Demo.acceptInvitation(data, 'cedar-invite', []), /at least one/);
});
test('removing a pair withdraws shortcut eligibility without removing other pairs', () => {
  const data = Demo.seed(); Demo.acceptInvitation(data, 'cedar-invite', ['casey']);
  data.connections = data.connections.filter(c => c.id !== 'casey-alex-pair');
  assert(!Demo.destinations(data, 'casey-phone').some(t => t.key === 'device:river-phone-0'));
  assert.equal(Demo.findDevice(data, 'casey-phone').phone.shortcuts.length, 1);
  assert(Demo.destinations(data, 'casey-phone').some(t => t.key === 'device:cedar-phone-0'));
});
test('contact access follows the number, includes future children, and is revoked on removal', () => {
  const data = Demo.seed();
  const later = Demo.saveChild(data, '', {name:'Blair', color:'green', notes:''});
  const phone = Demo.reservePhone(data, later.id, 'Desk');
  assert(Demo.destinations(data, phone.id).some(t => t.key === 'contact:+12025550142'));
  assert.throws(() => Demo.saveContact(data, '', {label:'Duplicate', phone_number:'(202) 555-0142'}), /already saved/);
  Demo.saveContact(data, 'grandma', {label:'Grandma', phone_number:'202-555-0199', notes:''});
  assert(!Demo.destinations(data, phone.id).some(t => t.key === 'contact:+12025550142'));
  const restored = Demo.saveContact(data, '', {label:'June', phone_number:'202-555-0142', notes:''});
  assert.equal(restored.extension, '6100');
  data.contacts = data.contacts.filter(c => c.id !== restored.id);
  assert(!Demo.destinations(data, phone.id).some(t => t.key === 'contact:+12025550142'));
});
test('directory hides unlisted families and individually hidden guardians before searching', () => {
  const data = Demo.seed();
  assert.equal(Demo.listedFamilies(data, 'Pine').length, 0);
  assert.equal(Demo.listedFamilies(data, 'Private River guardian').length, 0);
  data.directoryListed = true;
  assert.equal(Demo.listedFamilies(data, 'Morgan').length, 0);
  Demo.saveProfile(data, {display_name:'Morgan', phone:'', directory_visible:true});
  assert.equal(Demo.listedFamilies(data, 'Morgan').length, 1);
  data.directoryListed = false;
  assert.equal(Demo.listedFamilies(data, 'Morgan').length, 0);
  assert.equal(data.connections.length, 1);
});
test('code discovery does not grant calling and must be revalidated when sending', () => {
  const data = Demo.seed();
  assert.throws(() => Demo.sendInvitation(data, 'pine', ['casey'], ''), /valid invite code/);
  const target = Demo.family(data, 'pine'); const code = target.code;
  target.code = 'REPLACED';
  assert.throws(() => Demo.sendInvitation(data, 'pine', ['casey'], '', code), /valid invite code/);
  Demo.sendInvitation(data, 'pine', ['casey'], '', target.code);
  assert(!data.connections.some(c => c.familyId === 'pine'));
});
test('quiet hours support several schedules and same-day validation while paused', () => {
  const data = Demo.seed();
  Demo.saveQuiet(data, 'casey', '', {label:'Bedtime', start_time:'20:00', end_time:'23:59', day_group:'every_day', is_active:true});
  assert.equal(Demo.findChild(data, 'casey').quietHours.length, 2);
  assert.throws(() => Demo.saveQuiet(data, 'casey', '', {start_time:'20:00', end_time:'07:00', is_active:false}), /same day/);
});
test('guardian membership is primary-only, email-bound, expiring and single-use', () => {
  const data = Demo.seed(), invitation = Demo.inviteGuardian(data, 'Drew', 'drew@example.com');
  assert.throws(() => Demo.joinGuardian(data, invitation.id, 'different@example.com'), /matches/);
  const member = Demo.joinGuardian(data, invitation.id, invitation.email);
  assert.equal(member.directoryVisible, false);
  assert.throws(() => Demo.joinGuardian(data, invitation.id, invitation.email), /no longer available/);
  data.currentGuardianId = member.id;
  assert.throws(() => Demo.inviteGuardian(data, 'Pat', 'pat@example.com'), /primary guardian/);
  data.currentGuardianId = 'primary';
  const expired = Demo.inviteGuardian(data, 'Pat', 'pat@example.com'); expired.expiresAt = Date.now() - 1;
  assert.throws(() => Demo.joinGuardian(data, expired.id, expired.email), /no longer available/);
});
test('resend and cancel invalidate old previews; removal preserves approvals and rejoin identity', () => {
  const data = Demo.seed(), old = Demo.inviteGuardian(data, 'Drew', 'drew@example.com');
  const replacement = Demo.resendGuardian(data, old.id);
  assert.throws(() => Demo.joinGuardian(data, old.id, old.email), /no longer available/);
  const member = Demo.joinGuardian(data, replacement.id, replacement.email);
  Demo.removeGuardian(data, member.id);
  assert.equal(data.connections.length, 1); assert.equal(member.active, false);
  const rejoin = Demo.inviteGuardian(data, 'Drew', 'drew@example.com');
  assert.equal(Demo.joinGuardian(data, rejoin.id, rejoin.email).id, member.id);
  assert.throws(() => Demo.removeGuardian(data, 'primary'), /cannot be removed/);
  const cancelled = Demo.inviteGuardian(data, 'Pat', 'pat@example.com'); cancelled.status = 'cancelled';
  assert.throws(() => Demo.joinGuardian(data, cancelled.id, cancelled.email), /no longer available/);
});
test('existing-account preview never moves another household into this one', () => {
  const data = Demo.seed();
  assert.throws(() => Demo.inviteGuardian(data, 'Taylor', 'taylor@river.example.com'), /family account/);
  const invitation = Demo.inviteGuardian(data, 'Taylor', 'taylor@example.com');
  // The recipient joined another household after the invitation was issued.
  data.network[0].guardians.push({email:'taylor@example.com', name:'Taylor', visible:false});
  assert.throws(() => Demo.joinGuardian(data, invitation.id, invitation.email), /another family/);
  assert.equal(data.guardians.length, 1);
});
test('group shortcuts require installer activation and explicit membership', () => {
  const data = Demo.seed();
  assert.throws(() => Demo.saveGroup(data, '', {name:'Home'}, ['casey']), /at least two/);
  const group = Demo.saveGroup(data, '', {name:'Home', is_active:true}, ['casey', 'jordan']);
  assert(!Demo.destinations(data, 'casey-phone').some(t => t.key === `group:${group.id}`));
  group.extension = Demo.nextExtension(data); group.enabled = true;
  assert(Demo.destinations(data, 'casey-phone').some(t => t.key === `group:${group.id}`));
  group.is_active = false;
  assert(!Demo.destinations(data, 'casey-phone').some(t => t.key === `group:${group.id}`));
});
test('legacy session keeps identity, permissions, phones, schedules, contacts and shortcut keys', () => {
  const old = {family:'Maple', parent:'Morgan', email:'morgan@example.com', directoryListed:true, setupDismissed:true,
    children:[{id:'casey', name:'Casey', color:'yellow', phone:'Desk', extension:'4754', phoneStatus:'pending', quiet:true, start:'16:00', end:'17:00', days:'Weekdays', shortcuts:[{id:'key', digits:'1', target:'["family","river","Alex"]', label:'Alex', active:true}]}],
    families:[{id:'river', name:'River', peers:['Alex'], connections:[{childId:'casey', peer:'Alex', status:'approved'}]}],
    contacts:[{id:'grandma', name:'Grandma', phone:'+12025550142', extension:'6100'}], invites:[], guardians:[], activity:[]};
  const store = memory(); store.value = JSON.stringify({version:6, data:old});
  const data = Demo.load(store);
  assert.equal(data.children[0].devices[0].active, false);
  assert.equal(data.children[0].quietHours[0].day_group, 'weekdays');
  assert.equal(data.children[0].devices[0].shortcuts[0].target, 'device:river-phone-0');
  assert.equal(data.connections.length, 1);
  assert.equal(data.contacts[0].extension, '6100');
  assert.equal(data.guardians[0].directoryVisible, true);
  Demo.save(store, data); assert.equal(JSON.parse(store.value).version, Demo.VERSION);
});
test('old one-way states return to review without inventing new permissions', () => {
  const data = Demo.migrateLegacy({family:'Maple', parent:'Morgan', children:[{id:'casey', name:'Casey'}], families:[{id:'river', name:'River', incoming:['Alex'], outgoing:[]}], contacts:[], invites:[]});
  assert.equal(data.connections.length, 0);
  assert.equal(data.invitations[0].status, 'pending');
});

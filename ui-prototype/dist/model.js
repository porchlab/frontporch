"use strict";

// Fictional, tab-local state. Django remains the authority for real permissions.
const Demo = (() => {
  const VERSION = 7;
  const STORAGE_KEY = "frontporch-design-v1";
  const TIME_ZONE = "America/New_York";
  const id = () => globalThis.crypto.randomUUID();
  const same = (a, b) => String(a).trim().toLowerCase() === String(b).trim().toLowerCase();
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const clone = value => JSON.parse(JSON.stringify(value));
  const device = (key, name, extension, active = true) => ({id:key, name, extension, active, shortcuts:[]});
  const child = (key, name, color = "yellow", devices = []) => ({id:key, name, color, notes:"", devices, quietHours:[]});
  const guardian = (key, name, email, primary = false) => ({id:key, name, email, primary, active:true, phone:"", directoryVisible:false, emergencyNoticeDismissed:false});

  function network() {
    return [
      ["river", "River", "Taylor", "Alex", "Jamie", true, "RIVER-4B8N"],
      ["cedar", "Cedar", "Sam", "Robin", "Wren", true, "CEDAR-8D2P"],
      ["ash", "Ash", "Avery", "Finley", "Quinn", true, "ASH-6G1V"],
      ["willow", "Willow", "Rowan", "Sky", "Remy", true, "WILLOW-3R7J"],
      ["birch", "Birch", "Sophie", "Blair", "Sage", true, "BIRCH-5C9H"],
      ["elm", "Elm", "Nora", "Ellis", "Noel", true, "ELM-2F6B"],
      ["pine", "Pine", "Hazel", "Arden", "Reese", false, "PINE-7K2M"],
    ].map(([key, name, parent, first, second, listed, code], index) => ({
      id:key, name, listed, code,
      guardians:[{name:parent, email:`${parent.toLowerCase()}@${key}.example.com`, visible:true},
        {name:`Private ${name} guardian`, email:`private@${key}.example.com`, visible:false}],
      children:[first, second].map((name, n) => child(`${key}-${n}`, name, "lavender", [
        device(`${key}-phone-${n}`, `${name}’s phone`, String(7000 + index * 10 + n)),
      ])),
    }));
  }

  function seed() {
    const primary = guardian("primary", "Morgan", "morgan@example.com", true);
    const casey = child("casey", "Casey", "yellow", [device("casey-phone", "Bedroom phone", "4754")]);
    casey.devices[0].shortcuts.push({id:"casey-alex", digits:"2", target:"device:river-phone-0", label:"Alex", active:true, targetName:"Alex’s phone"});
    casey.quietHours.push({id:"homework", label:"Homework", day_group:"weekdays", start_time:"16:00", end_time:"17:00", is_active:true, notes:""});
    return {
      family:"Maple", setupDismissed:false, directoryListed:false, inviteCode:"MAPLE-9Q4T",
      guardians:[primary], currentGuardianId:primary.id, guardianInvites:[],
      children:[casey, child("jordan", "Jordan", "blue")], network:network(),
      connections:[{id:"casey-alex-pair", childId:"casey", familyId:"river", peerId:"river-0"}],
      invitations:[
        {id:"cedar-invite", familyId:"cedar", peerIds:["cedar-0", "cedar-1"], childIds:[], direction:"incoming", status:"pending", message:"Robin and Wren would love to call after school.", date:"Today"},
        {id:"ash-invite", familyId:"ash", childIds:["casey"], peerIds:[], direction:"outgoing", status:"pending", message:"Let’s stay in touch!", date:"Yesterday"},
      ],
      contacts:[{id:"grandma", name:"Grandma June", phone:"+12025550142", notes:"Grandparent", extension:"6100"},
        {id:"drew", name:"Drew’s mobile", phone:"+12025550163", notes:"", extension:"6101"}],
      contactExtensions:{"+12025550142":"6100", "+12025550163":"6101"}, groups:[],
      activity:[{text:"You approved Casey’s connection with Alex.", time:"Yesterday"}],
    };
  }

  function actor(data) { return data.guardians.find(g => g.id === data.currentGuardianId && g.active); }
  function primaryOnly(data) { assert(actor(data)?.primary, "The primary guardian manages family membership."); }
  function findChild(data, childId) { return data.children.find(c => c.id === childId); }
  function findDevice(data, deviceId) {
    for (const child of data.children) {
      const phone = child.devices.find(p => p.id === deviceId);
      if (phone) return {child, phone};
    }
    return null;
  }
  function family(data, familyId) { return data.network.find(f => f.id === familyId); }
  function selectedChildren(data, ids) {
    const selected = [...new Set(ids)].filter(key => findChild(data, key));
    assert(selected.length, "Choose at least one child.");
    return selected;
  }
  function nextExtension(data) {
    const used = new Set([
      ...data.children.flatMap(c => c.devices.map(p => p.extension)),
      ...data.network.flatMap(f => f.children.flatMap(c => c.devices.map(p => p.extension))),
      ...Object.values(data.contactExtensions), ...data.groups.map(g => g.extension),
    ]);
    for (let n = 5200; n <= 9999; n++) if (!used.has(String(n))) return String(n);
    throw new Error("No free extensions are available in this demo.");
  }
  function reservePhone(data, childId, name) {
    const owner = findChild(data, childId);
    assert(owner && name.trim(), "Choose a child and enter a phone name.");
    const phone = device(id(), name.trim(), nextExtension(data), false);
    owner.devices.push(phone);
    return phone;
  }
  function saveChild(data, childId, values) {
    assert(!data.children.some(c => c.id !== childId && same(c.name, values.name)), "A child with this name already belongs to your family.");
    let item = findChild(data, childId);
    if (!item) { item = child(id(), values.name); data.children.push(item); }
    Object.assign(item, {name:values.name, color:values.color || "yellow", notes:values.notes});
    return item;
  }
  function saveQuiet(data, childId, periodId, values) {
    const owner = findChild(data, childId);
    assert(owner, "Choose a child first.");
    assert(/^\d{2}:\d{2}$/.test(values.start_time) && /^\d{2}:\d{2}$/.test(values.end_time)
      && values.end_time > values.start_time, "End time must be later on the same day.");
    let period = owner.quietHours.find(p => p.id === periodId);
    if (!period) { period = {id:id()}; owner.quietHours.push(period); }
    Object.assign(period, values);
    return period;
  }
  function listedFamilies(data, query = "") {
    const result = data.network.filter(f => f.listed).map(f => ({id:f.id, name:f.name, guardians:f.guardians.filter(g => g.visible).map(g => g.name)}));
    if (data.directoryListed) result.push({id:"own", name:data.family, guardians:data.guardians.filter(g => g.active && g.directoryVisible).map(g => g.name)});
    return result.filter(f => `${f.name} ${f.guardians.join(" ")}`.toLowerCase().includes(query.trim().toLowerCase())).sort((a, b) => a.name.localeCompare(b.name));
  }
  function sendInvitation(data, familyId, childIds, message, code = "") {
    const target = family(data, familyId);
    assert(target && (target.listed || target.code === code), "Choose a listed family or enter a valid invite code first.");
    assert(!data.invitations.some(i => i.familyId === familyId && i.status === "pending"), "There is already a pending invitation between your families. Review it in Invitations.");
    const invitation = {id:id(), familyId, childIds:selectedChildren(data, childIds), peerIds:[], message, direction:"outgoing", status:"pending", date:"Just now"};
    data.invitations.unshift(invitation);
    return invitation;
  }
  function acceptInvitation(data, invitationId, chosen) {
    const invitation = data.invitations.find(i => i.id === invitationId);
    assert(invitation?.status === "pending", "This invitation has already been answered.");
    const target = family(data, invitation.familyId);
    assert(target, "This family is no longer available.");
    const local = invitation.direction === "incoming" ? selectedChildren(data, chosen) : selectedChildren(data, invitation.childIds);
    const remote = [...new Set(invitation.direction === "incoming" ? invitation.peerIds : chosen)].filter(key => target.children.some(c => c.id === key));
    assert(remote.length, "Choose at least one child from the receiving family.");
    for (const childId of local) for (const peerId of remote) {
      if (!data.connections.some(c => c.childId === childId && c.familyId === target.id && c.peerId === peerId))
        data.connections.push({id:id(), childId, familyId:target.id, peerId});
    }
    invitation.childIds = local;
    invitation.peerIds = remote;
    invitation.status = "accepted";
    return invitation;
  }
  function destinations(data, deviceId) {
    const source = findDevice(data, deviceId);
    if (!source) return [];
    const result = [];
    const addPhone = (phone, group, detail) => {
      if (phone.active && phone.id !== deviceId) result.push({key:`device:${phone.id}`, name:phone.name, group, detail});
    };
    for (const child of data.children) for (const phone of child.devices) addPhone(phone, "Your family’s phones", child.name);
    for (const pair of data.connections.filter(c => c.childId === source.child.id)) {
      const peerFamily = family(data, pair.familyId);
      const peer = peerFamily?.children.find(c => c.id === pair.peerId);
      for (const phone of peer?.devices || []) addPhone(phone, "Approved child connections", `${peer.name} · ${peerFamily.name}`);
    }
    for (const contact of data.contacts) result.push({key:`contact:${contact.phone}`, name:contact.name, detail:`Extension ${contact.extension}`, group:"Family contacts"});
    for (const parent of data.guardians.filter(g => g.phone)) result.push({key:`parent:${parent.id}`, name:parent.name, detail:"Phone", group:"Your family’s phones"});
    for (const group of data.groups.filter(g => g.is_active && g.enabled && g.extension && g.members.length >= 2 && g.members.includes(source.child.id)))
      result.push({key:`group:${group.id}`, name:group.name, detail:`Extension ${group.extension}`, group:"Group calls"});
    return result;
  }
  function saveShortcut(data, deviceId, shortcutId, values) {
    const source = findDevice(data, deviceId);
    assert(source, "Choose a phone first.");
    const existing = source.phone.shortcuts.find(s => s.id === shortcutId);
    assert(!shortcutId || existing, "This shortcut has been removed.");
    assert(/^[1-9]$/.test(values.digits), "Choose a single digit from 1 to 9.");
    assert(!source.phone.shortcuts.some(s => s.id !== shortcutId && s.digits === values.digits), "This key is already assigned on this phone.");
    const target = destinations(data, deviceId).find(t => t.key === values.target);
    assert(target, "Choose an already approved destination. You can pause or remove unavailable shortcuts.");
    const shortcut = {...values, id:existing?.id || id(), targetName:target.name};
    source.phone.shortcuts = [...source.phone.shortcuts.filter(s => s.id !== shortcutId), shortcut];
    return shortcut;
  }
  function normalizePhone(value) {
    if (!String(value).trim()) return "";
    let number = String(value).replace(/[\s().-]/g, "");
    if (/^\d{10}$/.test(number)) number = "+1" + number;
    else if (/^1\d{10}$/.test(number)) number = "+" + number;
    assert(/^\+[1-9]\d{7,14}$/.test(number), "Enter a phone number with country code, such as +1 202 555 0142.");
    return number;
  }
  function saveContact(data, contactId, values) {
    const phone = normalizePhone(values.phone_number);
    assert(phone, "Enter a phone number.");
    assert(!data.contacts.some(c => c.id !== contactId && c.phone === phone), "This number is already saved in your family contacts.");
    if (!data.contactExtensions[phone]) data.contactExtensions[phone] = nextExtension(data);
    let contact = data.contacts.find(c => c.id === contactId);
    assert(!contactId || contact, "This contact has been removed.");
    if (!contact) { contact = {id:id()}; data.contacts.push(contact); }
    Object.assign(contact, {name:values.label, phone, extension:data.contactExtensions[phone], notes:values.notes});
    return contact;
  }
  function inviteStatus(invitation, now = Date.now()) {
    return invitation.status === "pending" && invitation.expiresAt <= now ? "expired" : invitation.status;
  }
  function inviteGuardian(data, name, email) {
    primaryOnly(data);
    email = email.trim().toLowerCase();
    assert(!data.network.some(f => f.guardians.some(g => same(g.email, email))), "This email already belongs to a family account.");
    assert(!data.guardians.some(g => g.active && same(g.email, email)), "This email already belongs to a guardian in your family.");
    assert(!data.guardians.some(g => g.active && same(g.name, name)), "A guardian with this name already belongs to your family.");
    assert(!data.guardianInvites.some(i => same(i.email, email) && i.status === "pending"), "There is already an invitation for this email. Resend or cancel it in Family settings.");
    const invitation = {id:id(), name, email, status:"pending", expiresAt:Date.now() + 7 * 86400000};
    data.guardianInvites.unshift(invitation);
    return invitation;
  }
  function resendGuardian(data, invitationId) {
    primaryOnly(data);
    const previous = data.guardianInvites.find(i => i.id === invitationId);
    assert(previous?.status === "pending", "This invitation is no longer available.");
    previous.status = "replaced";
    try { return inviteGuardian(data, previous.name, previous.email); }
    catch (error) { previous.status = "pending"; throw error; }
  }
  function joinGuardian(data, invitationId, email) {
    const invitation = data.guardianInvites.find(i => i.id === invitationId);
    assert(invitation && inviteStatus(invitation) === "pending", "This invitation is no longer available.");
    assert(same(invitation.email, email), "Sign in with the account whose email matches this invitation.");
    assert(!data.network.some(f => f.guardians.some(g => same(g.email, email))), "This account already belongs to another family. It cannot be moved by this invitation.");
    let member = data.guardians.find(g => same(g.email, email));
    assert(!member?.active, "This account already has guardian access.");
    assert(!data.guardians.some(g => g.id !== member?.id && same(g.name, invitation.name)), "A guardian with this name already belongs to your family.");
    if (!member) { member = guardian(id(), invitation.name, invitation.email); data.guardians.push(member); }
    member.active = true;
    invitation.status = "accepted";
    return member;
  }
  function removeGuardian(data, memberId) {
    primaryOnly(data);
    const member = data.guardians.find(g => g.id === memberId);
    assert(member && !member.primary, "The primary guardian cannot be removed.");
    member.active = false;
  }
  function saveProfile(data, values) {
    const parent = actor(data);
    assert(parent, "Choose an active guardian.");
    assert(!data.guardians.some(g => g.id !== parent.id && same(g.name, values.display_name)), "A guardian with this name already belongs to your family.");
    Object.assign(parent, {name:values.display_name, phone:normalizePhone(values.phone), directoryVisible:values.directory_visible});
  }
  function saveGroup(data, groupId, values, members) {
    members = selectedChildren(data, members);
    assert(members.length >= 2, "Choose at least two children.");
    let group = data.groups.find(g => g.id === groupId);
    if (!group) { group = {id:id(), enabled:false, extension:""}; data.groups.push(group); }
    Object.assign(group, values, {members});
    return group;
  }

  // Upgrade versions 1–6 without losing household edits or shortcut identity.
  function migrateLegacy(old) {
    const data = seed();
    data.family = old.family || "Maple";
    data.setupDismissed = !!old.setupDismissed;
    data.directoryListed = !!old.directoryListed;
    data.inviteCode = old.inviteCode || data.inviteCode;
    Object.assign(data.guardians[0], {name:old.parent || "Morgan", email:old.email || "morgan@example.com", directoryVisible:!!old.directoryListed, emergencyNoticeDismissed:!!old.emergencyNoticeDismissed});
    data.guardians.push(...(old.guardians || []).map(g => ({...guardian(g.id, g.name, g.email), directoryVisible:false})));
    data.guardianInvites = clone(old.guardianInvites || []);
    data.children = (old.children || []).map(c => {
      const converted = child(c.id, c.name, c.color, c.extension ? [device(`${c.id}-phone`, c.phone || `${c.name}’s phone`, c.extension, c.phoneStatus === "ready")] : []);
      if (c.quiet) converted.quietHours.push({id:`${c.id}-quiet`, label:"Quiet hours", day_group:({Weekdays:"weekdays", Weekends:"weekends", "Every day":"every_day"})[c.days] || "weekdays", start_time:c.start, end_time:c.end, is_active:true, notes:""});
      return converted;
    });
    data.connections = [];
    data.invitations = [];
    const ensureFamily = (name, guardianName = "Family guardian") => {
      let match = data.network.find(f => same(f.name, name));
      if (!match) {
        match = {id:id(), name, listed:false, code:`DEMO-${id().slice(0,8)}`, guardians:[{name:guardianName, visible:false}], children:[]};
        data.network.push(match);
      }
      return match;
    };
    const ensurePeer = (peerFamily, name) => {
      let match = peerFamily.children.find(c => c.name === name);
      if (!match) { match = child(id(), name, "lavender", [device(id(), `${name}’s phone`, nextExtension(data))]); peerFamily.children.push(match); }
      return match;
    };
    for (const f of old.families || []) {
      const peerFamily = ensureFamily(f.name, f.guardian);
      const peers = f.peers || f.incoming || [];
      for (const peer of peers) ensurePeer(peerFamily, peer);
      const connections = f.connections || (f.outgoing || []).flatMap(c => peers.map(peer => ({childId:c.childId, peer, status:c.status})));
      for (const c of connections.filter(c => c.status === "approved" && findChild(data, c.childId)))
        data.connections.push({id:id(), childId:c.childId, familyId:peerFamily.id, peerId:ensurePeer(peerFamily, c.peer).id});
      for (const peer of peers.filter(peer => !connections.some(c => c.peer === peer && c.status === "approved"))) {
        if (!(old.invites || []).some(i => same(i.family, f.name) && i.child === peer && i.status === "pending"))
          data.invitations.push({id:id(), familyId:peerFamily.id, peerIds:[ensurePeer(peerFamily, peer).id], childIds:[], status:"pending", direction:"incoming", message:"Review this connection to enable calls both ways.", date:"Today"});
      }
    }
    for (const i of old.invites || []) {
      const target = ensureFamily(i.family, i.guardian);
      data.invitations.push({id:i.id, familyId:target.id, direction:i.direction, status:i.status, message:i.message || "", date:i.date || "Earlier", childIds:i.acceptedChildIds || i.childIds || [], peerIds:(i.child ? [i.child] : i.peers || []).map(name => ensurePeer(target, name).id)});
    }
    data.contactExtensions = {...old.contactExtensions};
    data.contacts = (old.contacts || []).map(c => {
      if (!data.contactExtensions[c.phone]) data.contactExtensions[c.phone] = c.extension || nextExtension(data);
      return {id:c.id, name:c.name, phone:c.phone, notes:c.notes || c.relation || "", extension:data.contactExtensions[c.phone]};
    });
    for (const c of old.children || []) {
      const phone = findChild(data, c.id)?.devices[0];
      if (!phone) continue;
      phone.shortcuts = (c.shortcuts || []).map(s => {
        let target = `unavailable:${s.id}`;
        try {
          const [kind, key, peerName] = JSON.parse(s.target);
          if (kind === "contact") target = `contact:${old.contacts.find(c => c.id === key)?.phone || key}`;
          if (kind === "home") target = `device:${key}-phone`;
          if (kind === "family") {
            const oldFamily = old.families.find(f => f.id === key);
            const peer = data.network.find(f => same(f.name, oldFamily?.name || ""))?.children.find(c => c.name === peerName);
            if (peer) target = `device:${peer.devices[0].id}`;
          }
        } catch { /* Keep stale assignments visible and unavailable. */ }
        return {...s, target};
      });
    }
    data.activity = clone(old.activity || []);
    return data;
  }
  function load(storage) {
    try {
      const saved = JSON.parse(storage.getItem(STORAGE_KEY));
      if (saved?.version === VERSION && Array.isArray(saved.data?.network)
          && Array.isArray(saved.data?.children) && saved.data?.guardians?.some(g => g.primary)) return saved.data;
      if ([1,2,3,4,5,6].includes(saved?.version) && Array.isArray(saved.data?.children)) return migrateLegacy(saved.data);
    } catch { /* Storage may be unavailable; a fresh in-memory demo still works. */ }
    return seed();
  }
  function save(storage, data) { storage.setItem(STORAGE_KEY, JSON.stringify({version:VERSION, data})); }
  return {VERSION, STORAGE_KEY, TIME_ZONE, id, same, assert, seed, actor, primaryOnly, findChild, findDevice, family, nextExtension,
    reservePhone, saveChild, saveQuiet, listedFamilies, sendInvitation, acceptInvitation, destinations, saveShortcut,
    normalizePhone, saveContact, inviteStatus, inviteGuardian, resendGuardian, joinGuardian, removeGuardian, saveProfile,
    saveGroup, migrateLegacy, load, save};
})();

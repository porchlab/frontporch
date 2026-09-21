// Cross-runtime fixture: Python feeds expected outcomes from real Django models.
const fs = require('node:fs');
const {runtime} = require('./harness.cjs');
const {Demo} = runtime();
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const data = input.data;
Demo.acceptInvitation(data, 'incoming', input.selected);
const sourceId = input.source;
const snapshot = () => ({
  pairs:data.connections.map(c => `${c.childId}:${c.peerId}`).sort(),
  targets:Demo.destinations(data, sourceId).map(t => t.name).sort(),
  phonebook:Demo.phonebook(data, sourceId).map(e => ({extension:e.extension, shortcuts:e.shortcuts.map(s => s.digits)}))
    .sort((a, b) => a.extension.localeCompare(b.extension)),
});
const result = [snapshot()];
data.connections = data.connections.filter(c => c.peerId !== input.revokedPeer);
result.push(snapshot());
data.contacts = [];
result.push(snapshot());
data.guardians[0].callDestination = "disabled";
result.push(snapshot());
process.stdout.write(JSON.stringify(result));

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {parseHTML} = require('linkedom');
const {root, ui} = require('./harness.cjs');
const {render, insidePages} = require('./phonebook-pdf-harness.cjs');

function demoCard(changes = '', options = {}) {
  const {run} = ui({phonebook:true});
  const {document} = parseHTML(fs.readFileSync(path.join(root,'phonebook.html'),'utf8'));
  document.querySelector('#main').innerHTML = run(`(() => {
    const data=Demo.seed(); ${changes}
    return phonebookCard(data, 'casey-phone');
  })()`);
  const result = render(document.toString(), options);
  insidePages(result.doc, result.drawn);
  return result;
}

test('demo HTML passes escaped names, final rows, multiple shortcuts and shortcut-only contacts to the PDF', () => {
  for (const color of [false,true]) {
    const {data,drawn}=demoCard(`
      data.children[0].name='Casey & "C"';
      data.children[0].devices[0].name='Bedroom <north>';
      data.contacts[0].name='Grandma <June> & Élodie';
      data.guardians[0].phone='+12025550199';
      Demo.saveShortcut(data,'casey-phone','',{digits:'3',target:'device:river-phone-0',label:'Best & <buddy>',active:true});
      Demo.saveShortcut(data,'casey-phone','',{digits:'4',target:'parent:primary',label:'Call home',active:true});
    `,{color});
    assert.equal(data.title,'Casey & "C"’s phonebook.');
    assert.equal(data.identity,'Bedroom <north> · My extension 4754');
    assert.deepEqual(JSON.parse(JSON.stringify(data.entries)),[
      {name:'Alex',description:'River family',extension:'7000',shortcuts:[{digits:'2',label:''},{digits:'3',label:'Best & <buddy>'}]},
      {name:'Drew’s mobile',description:'Family contact',extension:'6101',shortcuts:[]},
      {name:'Grandma <June> & Élodie',description:'Family contact',extension:'6100',shortcuts:[]},
      {name:'Morgan',description:'Parent phone · shortcut only',extension:'Use shortcut',shortcuts:[{digits:'4',label:'Call home'}]},
    ]);
    assert.equal(data.guide[0],'Pick up the phone. Dial an extension or use a shortcut.');
    assert.match(data.reminders[0],/Quiet hours still apply/);
    assert.equal(data.reminders[1],'FrontPorch cannot call 911. Use another phone for emergencies.');
    assert.match(data.metadata[0],/^Made .*Reprint when your circle changes\.$/);
    assert.equal(data.metadata[1],'FrontPorch demo · Fictional data.');
    for(const entry of data.entries) assert(drawn.some(item=>item.value===entry.name));
    assert(!JSON.stringify(data).includes('+1202555'));
  }
});
test('demo empty and inactive HTML retain their notices and footer without inventing entries', () => {
  const empty=demoCard('data.connections=[]; data.contacts=[];').data;
  assert.equal(empty.entries.length,0);
  assert.equal(empty.empty,'No calls available yet. Check your connections and contacts, then print a new card.');
  assert.equal(empty.reminders.length,2); assert.equal(empty.metadata.length,2);
  const inactive=demoCard('data.children[0].devices[0].active=false;').data;
  assert.equal(inactive.entries.length,0); assert.equal(inactive.empty,'');
  assert.equal(inactive.guide[0],'This phone is not enabled yet. Activate it through Demo tools, then print a new card.');
  assert.equal(inactive.reminders.length,2); assert.equal(inactive.metadata.length,2);
});

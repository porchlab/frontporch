const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {root} = require('./harness.cjs');
const {jsPDF} = require(path.join(root, 'vendor/jspdf.umd.min.js'));

function render(data, options) {
  const drawn = [];
  const context = vm.createContext({jspdf:{jsPDF:function(...args) {
    const doc = new jsPDF(...args), text = doc.text.bind(doc);
    doc.text = (value, x, y, ...rest) => {
      drawn.push({value, x, y, page:doc.getNumberOfPages(), size:doc.getFontSize(), width:doc.getTextWidth(String(value))});
      return text(value, x, y, ...rest);
    };
    return doc;
  }}});
  for (const file of ['phonebook-fonts.js', 'phonebook-pdf.js']) vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
  const doc = vm.runInContext('PhonebookPDF', context).create(data, options);
  return {doc, drawn};
}
const sample = () => ({
  title:'Casey’s phonebook.', identity:'Bedroom phone · My extension 4754',
  guide:['Pick up the phone. Dial an extension or use a shortcut.'],
  entries:[
    {name:'Alex', description:'River family', extension:'7000', shortcuts:[{digits:'2', label:''}]},
    {name:'Grandma June', description:'Family contact', extension:'6100', shortcuts:[{digits:'1', label:'Grandma'}]},
    {name:'Élodie', description:'Parent phone · shortcut only', extension:'Use shortcut', shortcuts:[{digits:'5', label:''}]},
  ],
  empty:'', reminders:['Quiet hours still apply. If a call doesn’t connect, ask a grown-up.', 'FrontPorch cannot call 911. Use another phone for emergencies.'],
  metadata:['Made Sep 20, 2026 · Reprint when your circle changes.', 'FrontPorch demo · Fictional data.'],
});
function insidePages(doc, drawn) {
  const pageWidth=doc.internal.pageSize.getWidth(), pageHeight=doc.internal.pageSize.getHeight();
  for (const {value, x, y, width} of drawn) {
    assert(x >= 36 && x + width <= pageWidth - 36, `Text outside horizontal margins: ${value}`);
    assert(y >= 36 && y <= pageHeight - 36, `Text outside vertical margins: ${value}`);
  }
}
test('direct PDFs embed fonts and preserve approved names, extensions and shortcuts on Letter and A4', () => {
  for (const paper of ['letter', 'a4']) for (const color of [false, true]) {
    const {doc, drawn} = render(sample(), {paper, color});
    assert.equal(doc.getNumberOfPages(), 1);
    assert(Math.abs(doc.internal.pageSize.getWidth() - (paper === 'letter' ? 612 : 595.28)) < .02);
    assert(Math.abs(doc.internal.pageSize.getHeight() - (paper === 'letter' ? 792 : 841.89)) < .02);
    for (const expected of ['Alex', '7000', '2', 'Grandma June', '6100', '1', 'Grandma', 'Élodie', 'Use shortcut', '5']) {
      assert(drawn.some(item => item.value === expected), `Missing ${expected}`);
    }
    const pdf = doc.output();
    assert(pdf.startsWith('%PDF-'));
    assert(pdf.includes('/FontFile2'));
    assert(pdf.includes('/ToUnicode'));
    assert(pdf.includes('%%EOF'));
    assert(!pdf.includes('/JavaScript'));
    insidePages(doc, drawn);
  }
});
test('long lists repeat identity, headings and reminders without missing or splitting normal rows', () => {
  const data = sample();
  data.entries=Array.from({length:75}, (_, i) => ({name:`Friend ${i}`, description:'Fictional family', extension:String(7000+i), shortcuts:[]}));
  for (const paper of ['letter','a4']) {
    const {doc, drawn}=render(data,{paper});
    assert(doc.getNumberOfPages() > 3);
    for (let i=0; i<75; i++) {
      const name=drawn.filter(item=>item.value===`Friend ${i}`), extension=drawn.filter(item=>item.value===String(7000+i));
      assert.equal(name.length,1); assert.equal(extension.length,1); assert.equal(name[0].page,extension[0].page);
    }
    for(let page=1;page<=doc.getNumberOfPages();page++) {
      const values=drawn.filter(item=>item.page===page).map(item=>item.value);
      assert(values.includes(data.identity)); assert(values.includes('WHO TO CALL')); assert(values.includes(data.reminders[1]));
    }
    insidePages(doc,drawn);
  }
});
test('an oversized row retains every long shortcut label across page boundaries', () => {
  const data=sample();
  data.entries=[{name:'A very long fictional contact name '.repeat(3), description:'Fictional family', extension:'6100', shortcuts:Array.from({length:9},(_,i)=>({digits:String(i+1),label:`Label ${i+1} ${'a'.repeat(160)}`}))}];
  const {doc,drawn}=render(data,{color:true});
  assert(doc.getNumberOfPages()>1);
  for(let i=1;i<=9;i++) assert(drawn.some(item=>item.value===String(i)));
  const labels=drawn.filter(item=>item.size===8 && (/^Label \d/.test(item.value) || /^a+$/.test(item.value)))
    .map(item=>item.value).join('').replace(/Label \d /g,'');
  assert.equal(labels, 'a'.repeat(9*160));
  insidePages(doc,drawn);
});
test('inactive, empty and landline calling instructions are carried into the PDF', () => {
  for (const guide of [
    ['This phone is not enabled yet. Print a new card after your installer activates it.'],
    ['First, call FrontPorch: +1 202-555-0199', 'Your call connects directly to Alex. No extension or shortcut is needed.'],
  ]) {
    const data=sample();data.entries=[];data.guide=guide;data.empty='No calls available yet.';
    const {doc,drawn}=render(data,{});
    for(const value of guide) assert(drawn.some(item=>item.value===value));
    assert(drawn.some(item=>item.value===data.empty));
    assert(!drawn.some(item=>item.value==='7000'));
    insidePages(doc,drawn);
  }
});

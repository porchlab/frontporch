const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {parseHTML} = require('linkedom');
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
  const api = vm.runInContext('PhonebookPDF', context);
  if (typeof data === 'string') data = api.readCard(parseHTML(data).document.querySelector('.phonebook'));
  const doc = api.create(data, options);
  return {data, doc, drawn};
}
function insidePages(doc, drawn) {
  const pageWidth=doc.internal.pageSize.getWidth(), pageHeight=doc.internal.pageSize.getHeight();
  for (const {value, x, y, width} of drawn) {
    assert(x >= 36 && x + width <= pageWidth - 36, `Text outside horizontal margins: ${value}`);
    assert(y >= 36 && y <= pageHeight - 36, `Text outside vertical margins: ${value}`);
  }
}

module.exports = {render, insidePages};

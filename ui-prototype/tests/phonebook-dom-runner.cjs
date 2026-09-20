// Django passes rendered, fictional card HTML through the production extractor.
const fs = require('node:fs');
const {render, insidePages} = require('./phonebook-pdf-harness.cjs');
const cards = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = cards.map(({html, options}) => {
  const {data, doc, drawn} = render(html, options);
  insidePages(doc, drawn);
  return {data, pages:doc.getNumberOfPages(), text:drawn.map(item => item.value)};
});
process.stdout.write(JSON.stringify(results));

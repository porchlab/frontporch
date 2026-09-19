const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../dist');
function runtime() {
  const context = vm.createContext({crypto, console, Date});
  vm.runInContext(fs.readFileSync(path.join(root, 'model.js'), 'utf8'), context);
  return {Demo:vm.runInContext('Demo', context), context};
}
module.exports = {runtime, root};

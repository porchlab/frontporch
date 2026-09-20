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
function ui({phonebook = false} = {}) {
  const {context} = runtime();
  const listeners = {}, nodes = new Map();
  const node = () => ({hidden:false, innerHTML:'', textContent:'', classList:{add() {}, remove() {}}, setAttribute() {}, addEventListener() {}, focus() {}, scrollIntoView() {}, close() {}, showModal() {}});
  Object.assign(context, {
    document:{body:{}, addEventListener(name, handler) { listeners[name] = handler; }, querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, node()); return nodes.get(selector); }},
    window:{sessionStorage:{getItem() {return null;}, setItem() {}}, addEventListener() {}, scrollTo() {}},
    location:{hash:'#family/overview', search:'?phone=casey-phone', pathname:'/phonebook.html'}, URLSearchParams, setTimeout() {}, clearTimeout() {},
    FormData:class {
      constructor(form) { this.values = form.values; }
      get(key) { return this.values[key] ?? null; }
      has(key) { return Object.hasOwn(this.values, key); }
      getAll(key) { return [].concat(this.values[key] || []); }
    },
  });
  for (const file of ['portal-contract.js', phonebook ? 'phonebook-page.js' : 'app.js']) vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
  return {context, nodes, listeners, run:script => vm.runInContext(script, context)};
}

module.exports = {runtime, root, ui};

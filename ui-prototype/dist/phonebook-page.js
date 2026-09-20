"use strict";

const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[ch]);
const icon = name => `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PORTAL.icons[name]}</svg>`;

function phonebookCard(data, deviceId) {
  const source = Demo.findDevice(data, deviceId);
  if (!source) return '<div class="empty-phonebook"><h1>Phone not found.</h1><p>Choose a phone from Children &amp; phones in this demo tab.</p></div>';
  const {child, phone} = source;
  const entries = Demo.phonebook(data, deviceId);
  const date = new Date().toLocaleDateString("en-US", {month:"short", day:"numeric", year:"numeric", timeZone:Demo.TIME_ZONE});
  const footer = `<footer class="card-footer"><p><strong>A little reminder</strong> Quiet hours still apply. If a call doesn’t connect, ask a grown-up.</p>
    <p>FrontPorch cannot call 911. Use another phone for emergencies.</p>
    <div><span>Made ${esc(date)} · Reprint when your circle changes.</span><span>FrontPorch demo · Fictional data.</span></div></footer>`;
  const row = entry => `<tr><td><strong class="person-name">${esc(entry.name)}</strong><span class="entry-description">${esc(entry.description)}</span></td>
    <td class="extension">${entry.extension ? esc(entry.extension) : '<span class="no-extension">Use shortcut</span>'}</td>
    <td>${entry.shortcuts.map(shortcut => `<span class="shortcut"><b>${esc(shortcut.digits)}</b>${shortcut.label && shortcut.label !== entry.name ? `<span>${esc(shortcut.label)}</span>` : ""}</span>`).join("") || '<span class="no-shortcut" aria-label="No shortcut">—</span>'}</td></tr>`;
  const table = entries.length ? `<table><colgroup><col class="person-column"><col class="extension-column"><col class="shortcut-column"></colgroup>
    <thead><tr class="print-identity"><td colspan="3">${esc(child.name)}’s phonebook · ${esc(phone.name)} · My extension ${esc(phone.extension)}</td></tr>
    <tr><th scope="col">Who to call</th><th scope="col">Extension</th><th scope="col">Shortcut</th></tr></thead>
    <tbody>${entries.slice(0, -1).map(row).join("")}</tbody>
    <tbody class="phonebook-ending">${row(entries[entries.length - 1])}<tr class="footer-row"><td colspan="3">${footer}</td></tr></tbody></table>` : "";
  return `<header class="card-heading"><div class="wordmark">${icon("home")} FrontPorch <span>A little more hello.</span></div>
    <div class="card-title"><div><h1>${esc(child.name)}’s<br>phonebook.</h1><p>${esc(phone.name)} · My extension <strong>${esc(phone.extension)}</strong></p></div>
    <span class="phone-drawing" aria-hidden="true">${icon("phone")}<span>hello!</span></span></div></header>
    <section class="calling-guide" aria-label="How to call">${phone.active
      ? '<p>Pick up the phone. Dial an <strong>extension</strong> or use a <strong>shortcut</strong>.</p>'
      : '<p><strong>This phone is not enabled yet.</strong> Activate it through Demo tools, then print a new card.</p>'}</section>
    ${table || (phone.active ? '<div class="empty-phonebook"><h2>No calls available yet.</h2><p>Check your connections and contacts, then print a new card.</p></div>' : "")}
    ${entries.length ? "" : footer}`;
}

function renderPhonebook() {
  let data;
  try { data = Demo.load(window.sessionStorage); } catch { data = Demo.seed(); }
  const options = new URLSearchParams(location.search);
  const deviceId = options.get("phone");
  const source = Demo.findDevice(data, deviceId);
  const card = document.querySelector("#main");
  card.innerHTML = phonebookCard(data, deviceId);
  card.setAttribute("aria-label", source ? `${source.child.name}’s phonebook` : "Phone not found");
  document.title = source ? `${source.child.name}’s phonebook · FrontPorch demo` : "Phone not found · FrontPorch demo";
  const back = document.querySelector(".back-link");
  back.href = source ? `index.html#family/child/${encodeURIComponent(source.child.id)}` : "index.html#family/children";
  back.textContent = source ? `← Back to ${source.child.name}’s phones` : "← Back to Children & phones";
  document.querySelector("[data-print]").disabled = !source;
  document.querySelector("[data-download-pdf]").disabled = !source;
  document.querySelector("#print-style").value = options.get("style") === "color" ? "color" : "bw";
  document.body.className = options.get("style") === "color" ? "color" : "monochrome";
}

document.querySelector("#print-options").addEventListener("submit", event => {
  event.preventDefault();
  const style = document.querySelector("#print-style").value === "color" ? "color" : "bw";
  const options = new URLSearchParams(location.search);
  options.set("style", style);
  history.replaceState(null, "", `${location.pathname}?${options}`);
  renderPhonebook();
});
// Recheck current tab data after Back/Forward restores a cached preview.
window.addEventListener("pageshow", renderPhonebook);
renderPhonebook();

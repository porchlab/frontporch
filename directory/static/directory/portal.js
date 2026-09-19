"use strict";
document.addEventListener("submit", event => {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});
document.addEventListener("click", async event => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  const source = document.getElementById(button.dataset.copy);
  const status = button.parentElement.querySelector(".copy-status");
  try {
    await navigator.clipboard.writeText(source.textContent.trim());
    status.textContent = "Code copied. Share it privately with another parent.";
  } catch {
    const range = document.createRange(); range.selectNodeContents(source);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    status.textContent = "Code selected. Copy it using your device’s copy command.";
  }
});

// Display-only preview: values are still validated and saved by Django.
document.addEventListener("input", event => {
  const field = event.target;
  const selector = field.name === "family_name" ? "[data-preview-family]" : field.name === "display_name" ? "[data-preview-guardian]" : null;
  if (!selector) return;
  const preview = document.querySelector(selector);
  if (preview) preview.textContent = field.value.trim() || (field.name === "family_name" ? "Your family" : "Your guardian name");
});

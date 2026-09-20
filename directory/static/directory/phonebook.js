"use strict";
const printButton = document.querySelector("[data-print]");
if (printButton) {
  printButton.hidden = false;
  printButton.addEventListener("click", () => window.print());
}

const pdfButton = document.querySelector("[data-download-pdf]");
if (pdfButton && typeof jspdf !== "undefined" && typeof PhonebookPDF !== "undefined") {
  document.querySelector("[data-pdf-controls]").hidden = false;
  pdfButton.addEventListener("click", async () => {
    const status = document.querySelector("[data-pdf-status]");
    pdfButton.disabled = true;
    status.hidden = false;
    status.textContent = "Preparing your PDF…";
    try {
      await document.fonts.ready;
      const card = PhonebookPDF.readCard(document.querySelector(".phonebook"));
      const pdf = PhonebookPDF.create(card, {
        paper:document.querySelector("#pdf-paper").value,
        color:document.querySelector("#print-style").value === "color",
      });
      // A local Blob download also works in Safari; no print dialog or upload.
      await pdf.save("frontporch-phonebook.pdf", {returnPromise:true});
      status.textContent = "PDF downloaded. Open it to print at 100%.";
    } catch (error) {
      status.textContent = "The PDF could not be created. Try again, or use Print preview and turn off browser headers and footers.";
    } finally {
      pdfButton.disabled = false;
    }
  });
}

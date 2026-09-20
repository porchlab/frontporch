"use strict";

// One direct PDF layout for the guardian portal and the offline browser demo.
// Input is only the already-authorized, visible card; never look up destinations.
const PhonebookPDF = (() => {
  const clean = node => (node?.textContent || "").replace(/\s+/g, " ").trim();
  function readCard(card) {
    return {
      title: card.querySelector("h1").innerText.replace(/\s+/g, " ").trim(),
      identity: clean(card.querySelector(".card-title p")),
      guide: [...card.querySelectorAll(".calling-guide p")].map(clean),
      entries: [...card.querySelectorAll("tr")].filter(row => row.querySelector(".person-name")).map(row => ({
        name: clean(row.querySelector(".person-name")),
        description: clean(row.querySelector(".entry-description")),
        extension: clean(row.querySelector(".extension")),
        shortcuts: [...row.querySelectorAll(".shortcut")].map(shortcut => ({
          digits: clean(shortcut.querySelector("b")), label: clean(shortcut.querySelector("span")),
        })),
      })),
      empty: [...card.querySelectorAll(".empty-phonebook > *")].map(clean).join(" "),
      reminders: [...card.querySelectorAll(".card-footer p")].map(clean),
      metadata: [...card.querySelectorAll(".card-footer > div > span")].map(clean),
    };
  }

  function create(data, {paper = "letter", color = false} = {}) {
    const doc = new jspdf.jsPDF({unit:"pt", format:paper === "a4" ? "a4" : "letter", compress:true, putOnlyUsedFonts:true});
    for (const [weight, style] of [["regular", "normal"], ["bold", "bold"]]) {
      doc.addFileToVFS(`${weight}.ttf`, PHONEBOOK_FONTS[weight]);
      doc.addFont(`${weight}.ttf`, "DM Sans", style);
    }
    doc.setProperties({title:data.title, subject:"FrontPorch phonebook", creator:"FrontPorch"});
    const accent = color ? "#203dcc" : "#111111";
    const width = 510, left = (doc.internal.pageSize.getWidth() - width) / 2;
    const x = left + 20, inner = width - 40, top = 36;
    const columns = [x, x + inner * .52, x + inner * .79];
    const widths = [inner * .52 - 12, inner * .27 - 12, inner * .21 - 4];
    const pageBottom = doc.internal.pageSize.getHeight() - 36;
    let y, pageStart, page = 0;

    function font(size = 10, bold = false, ink = "#111111") {
      doc.setFont("DM Sans", bold ? "bold" : "normal");
      doc.setFontSize(size);
      doc.setTextColor(ink);
    }
    function needsFallback(text) {
      const glyphs = doc.getFont().metadata.cmap.unicode.codeMap;
      return [...String(text)].some(char => char !== "\n" && !glyphs[char.codePointAt(0)]);
    }
    function canvasFont(size, bold) {
      const canvas = document.createElement("canvas"), context = canvas.getContext("2d");
      context.font = `${bold ? "bold " : ""}${size}px "DM Sans", sans-serif`;
      return {canvas, context};
    }
    function lines(text, size, bold, available) {
      font(size, bold);
      // DM Sans is a Latin subset. Keep other scripts/emoji visible using the
      // browser's font fallback, embedded as high-resolution text images.
      if (needsFallback(text)) {
        const {context} = canvasFont(size, bold), result = [];
        const graphemes = new Intl.Segmenter(undefined, {granularity:"grapheme"});
        for (const paragraph of String(text).split("\n")) {
          let line = "";
          for (const {segment} of graphemes.segment(paragraph)) {
            if (line && context.measureText(line + segment).width > available) { result.push(line.trim()); line = ""; }
            line += segment;
          }
          result.push(line.trim());
        }
        return result;
      }
      return doc.splitTextToSize(String(text || ""), available);
    }
    function write(text, atX, atY, size = 10, bold = false, ink = "#111111") {
      font(size, bold, ink);
      if (needsFallback(text)) {
        const scale = 3, {canvas, context} = canvasFont(size * scale, bold);
        const face = context.font;
        canvas.width = Math.ceil(context.measureText(String(text)).width) + 6;
        canvas.height = Math.ceil(size * scale * 1.6);
        context.font = face; context.fillStyle = ink;
        context.fillText(String(text), 3, size * scale);
        if (!color) {
          const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
          for (let i = 0; i < pixels.data.length; i += 4) {
            const gray = Math.round(pixels.data[i] * .299 + pixels.data[i + 1] * .587 + pixels.data[i + 2] * .114);
            pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = gray;
          }
          context.putImageData(pixels, 0, 0);
        }
        doc.addImage(canvas.toDataURL("image/png"), "PNG", atX - 1, atY - size, canvas.width / scale, canvas.height / scale);
        return;
      }
      doc.text(String(text), atX, atY);
    }
    function rule(atY, ink = "#bbbbbb") {
      doc.setDrawColor(ink); doc.setLineWidth(.6); doc.line(x, atY, x + inner, atY);
    }
    function paragraph(text, size = 10, bold = false, ink = "#111111", available = inner) {
      for (const line of lines(text, size, bold, available)) {
        write(line, x, y + size, size, bold, ink); y += size * (size >= 18 ? 1.1 : 1.35);
      }
    }
    const footerLines = data.reminders.flatMap(text => lines(text, 8, false, inner));
    const metadataLines = data.metadata.flatMap(text => lines(text, 7, false, inner - 55));
    const footerHeight = 26 + footerLines.length * 11 + metadataLines.length * 10;
    const rowLimit = pageBottom - footerHeight - 16;
    function finishPage() {
      y += 13;
      for (const line of footerLines) { write(line, x, y + 8, 8); y += 11; }
      y += 7; rule(y); y += 9;
      for (const line of metadataLines) { write(line, x, y + 7, 7); y += 10; }
      write(`Page ${page}`, x + inner - 32, y - 3, 7);
      doc.setDrawColor(accent); doc.setLineWidth(.8);
      doc.roundedRect(left, top, width, y + 12 - top, 7, 7);
      if (color) { doc.setDrawColor(accent); doc.setLineWidth(3); doc.line(left + 8, top + 1, left + width - 8, top + 1); }
    }
    function startPage() {
      if (page) doc.addPage();
      page += 1; y = top + 18;
      write("FrontPorch", x, y + 11, 11, true, accent);
      write(page === 1 ? "A little more hello." : "Phonebook continued", x + inner - 98, y + 11, 8);
      y += 30;
      const titleY = y;
      const firstTitle = data.title.replace(/ phonebook\.$/, "\nphonebook.");
      const fullHeadingHeight = lines(firstTitle, 28, true, inner - 80).length * 28 * 1.1
        + lines(data.identity, 10, false, inner).length * 13.5 + 30;
      // Maximum-length names can make the decorative title taller than a page.
      // Use the readable continuation layout in that case, retaining all text.
      const largeTitle = page === 1 && y + fullHeadingHeight + 18 <= rowLimit;
      paragraph(largeTitle ? firstTitle : data.title,
        largeTitle ? 28 : 18, true, accent, largeTitle ? inner - 80 : inner);
      if (largeTitle) {
        // A telephone receiver, drawn as vectors so it stays crisp in print.
        const phoneX = x + inner - 57, phoneY = titleY + 2;
        doc.setDrawColor(color ? "#b74b26" : accent); doc.setLineWidth(1.5);
        const receiver = [
          ["m", 6, 0], ["c", 2, 0, 0, 3, 0, 7], ["c", 0, 23, 14, 37, 30, 37],
          ["c", 34, 37, 37, 35, 37, 31], ["l", 37, 27], ["c", 37, 25, 36, 24, 34, 24],
          ["l", 27, 22], ["c", 25, 21, 24, 22, 23, 23], ["l", 20, 26],
          ["c", 14, 23, 10, 19, 7, 13], ["l", 10, 10], ["c", 11, 9, 11, 8, 11, 6],
          ["l", 10, 3], ["c", 10, 1, 9, 0, 7, 0], ["h"],
        ];
        doc.path(receiver.map(([op, ...coords]) => ({op, c:coords.map((value, i) => value + (i % 2 ? phoneY : phoneX))}))).stroke();
        write("hello!", phoneX + 4, phoneY + 53, 11, true, color ? "#b74b26" : accent);
      }
      y += 8; paragraph(data.identity, 10); y += 12; rule(y, accent); y += 10;
    }
    function tableHeading() {
      rule(y, accent);
      ["WHO TO CALL", "EXTENSION", "SHORTCUT"].forEach((label, i) => write(label, columns[i], y + 16, 8, true));
      y += 25; rule(y, accent);
      pageStart = y;
    }
    function nextTablePage() { finishPage(); startPage(); tableHeading(); }
    function flowingParagraph(text, size = 10) {
      const leading = size * 1.35;
      for (const line of lines(text, size, false, inner)) {
        if (y + leading > rowLimit) { finishPage(); startPage(); }
        write(line, x, y + size, size); y += leading;
      }
      y = Math.min(y + 4, rowLimit);
    }

    // Each cell is a stack of measured lines. Oversized rows can continue across
    // pages without cutting a line, omitting a shortcut, or shrinking the type.
    function cell(text, size, bold, available, ink = "#111111") {
      return lines(text, size, bold, available).map(text => ({text, size, bold, ink, height:size * 1.35}));
    }
    function entryCells(entry) {
      const shortcuts = entry.shortcuts.flatMap(shortcut => {
        const result = [{text:shortcut.digits, size:18, bold:true, ink:accent, height:28, badge:true}];
        if (shortcut.label) result.push(...cell(shortcut.label, 8, false, widths[2]).map(line => ({...line, shortcutDigits:shortcut.digits})));
        result[result.length - 1].height += 5;
        return result;
      });
      return [
        [...cell(entry.name, 13, true, widths[0], color ? "#193b32" : "#111111"), ...cell(entry.description, 8, false, widths[0])],
        cell(entry.extension, /^\d+$/.test(entry.extension) ? 19 : 9, /^\d+$/.test(entry.extension), widths[1]),
        shortcuts.length ? shortcuts : cell("-", 13, false, widths[2]),
      ];
    }
    const height = cells => Math.max(...cells.map(cell => cell.reduce((sum, line) => sum + line.height, 0))) + 16;
    startPage();
    // Calling instructions can contain many dial-in numbers. Paginate them as
    // body text, before introducing the table, and reserve the footer on every
    // page even when the card has no permitted destinations yet.
    for (const text of data.guide) flowingParagraph(text);
    y = Math.min(y + 5, rowLimit);
    if (data.entries.length) {
      const firstCells = entryCells(data.entries[0]);
      const firstLineHeight = Math.max(...firstCells.map(cell => cell[0]?.height || 0));
      if (y + 25 + 16 + firstLineHeight > rowLimit) { finishPage(); startPage(); }
      tableHeading();
    }
    data.entries.forEach((entry, rowIndex) => {
      const cells = entryCells(entry);
      if (y + height(cells) > rowLimit && y > pageStart) nextTablePage();
      while (cells.some(cell => cell.length)) {
        const available = rowLimit - y - 16;
        const chunk = cells.map(cell => {
          let used = 0, count = 0;
          while (count < cell.length && used + cell[count].height <= available) { used += cell[count++].height; }
          return cell.splice(0, count);
        });
        if (!chunk.some(cell => cell.length)) throw new Error("The phonebook heading is too long to fit on a page.");
        const rowHeight = height(chunk);
        if (color && rowIndex % 2) { doc.setFillColor("#f3f7f2"); doc.rect(x, y, inner, rowHeight, "F"); }
        chunk.forEach((cell, col) => {
          let atY = y + 8;
          for (const line of cell) {
            if (line.badge) {
              doc.setFillColor(color ? "#fff1ac" : "#ffffff"); doc.setDrawColor(accent); doc.setLineWidth(.5);
              doc.roundedRect(columns[col], atY - 1, 24, 24, 5, 5, "FD");
            }
            write(line.text, columns[col] + (line.badge ? 4 : 0), atY + line.size, line.size, line.bold, line.ink);
            atY += line.height;
          }
        });
        y += rowHeight; rule(y);
        if (cells.some(cell => cell.length)) {
          nextTablePage();
          // Keep continued labels associated with their person and shortcut.
          if (!cells[0].length) cells[0] = cell(`${entry.name} (continued)`, 13, true, widths[0]);
          if (!cells[1].length) cells[1] = cell(entry.extension, 9, false, widths[1]);
          if (cells[2][0]?.shortcutDigits) cells[2].unshift({text:cells[2][0].shortcutDigits, size:18, bold:true, ink:accent, height:28, badge:true});
        }
      }
    });
    if (!data.entries.length && data.empty) flowingParagraph(data.empty, 12);
    finishPage();
    return doc;
  }
  return {readCard, create};
})();

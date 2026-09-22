// Renders docs/handover/sukoon-owner-manual.html to Sukoon-Owner-Manual.pdf.
//
// The HTML is the editable original; the PDF is what the client is sent. The cover
// is rendered full-bleed without a footer, the body with page numbers, and the two
// are joined with pdfunite (poppler-utils).
//
//   node docs/handover/render-manual.js
//
// Needs: puppeteer-core (already a dev dependency), Google Chrome, pdfunite.

const puppeteer = require("puppeteer-core");
const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const HERE = __dirname;
const SRC = "file://" + path.join(HERE, "sukoon-owner-manual.html");
const OUT = path.join(HERE, "Sukoon-Owner-Manual.pdf");

const CHROME =
  process.env.CHROME_PATH ||
  ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"].find(
    fs.existsSync,
  );

const footer = `
<div style="width:100%;font-family:'Noto Sans',sans-serif;font-size:7.5pt;color:#86868B;
            padding:0 16mm;display:flex;justify-content:space-between;align-items:center;">
  <span>Sukoon &middot; Owner's Manual &middot; Al-Rehman General Store</span>
  <span class="pageNumber" style="font-weight:600;color:#0E6B57;"></span>
</div>`;

(async () => {
  if (!CHROME) throw new Error("No Chrome found. Set CHROME_PATH.");

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "sukoon-manual-"));
  const cover = path.join(tmp, "cover.pdf");
  const body = path.join(tmp, "body.pdf");

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: ["--no-sandbox", "--disable-gpu"],
  });

  try {
    const page = await browser.newPage();
    await page.goto(SRC, { waitUntil: "networkidle0" });

    await page.pdf({
      path: cover,
      format: "A4",
      printBackground: true,
      pageRanges: "1",
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
    });

    await page.pdf({
      path: body,
      format: "A4",
      printBackground: true,
      pageRanges: "2-",
      displayHeaderFooter: true,
      headerTemplate: "<span></span>",
      footerTemplate: footer,
      margin: { top: "18mm", right: "16mm", bottom: "16mm", left: "16mm" },
    });
  } finally {
    await browser.close();
  }

  execFileSync("pdfunite", [cover, body, OUT]);
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log("Wrote " + OUT);
})();

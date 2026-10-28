// Renders docs/handover/upgrade-to-<version>.html to Sukoon-Upgrade-to-<version>.pdf: the one
// sheet an owner already running Sukoon is sent with a new installer. Same toolchain as
// render-manual.js.
//
//   node docs/handover/render-upgrade.js            # the current release
//   node docs/handover/render-upgrade.js 1.1.0      # an earlier sheet

const puppeteer = require("puppeteer-core");
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
const VERSION = process.argv[2] || "1.2.0";
const SRC = "file://" + path.join(HERE, `upgrade-to-${VERSION}.html`);
const OUT = path.join(HERE, `Sukoon-Upgrade-to-${VERSION}.pdf`);
const CHROME =
  process.env.CHROME_PATH ||
  ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"].find(
    fs.existsSync,
  );

const footer = `
<div style="width:100%;font-family:'Noto Sans',sans-serif;font-size:7.5pt;color:#86868B;
            padding:0 16mm;display:flex;justify-content:space-between;align-items:center;">
  <span>Sukoon &middot; Upgrading to ${VERSION} &middot; Al-Rehman General Store</span>
  <span class="pageNumber" style="font-weight:600;color:#0E6B57;"></span>
</div>`;

(async () => {
  if (!CHROME) throw new Error("No Chrome found. Set CHROME_PATH.");
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: ["--no-sandbox", "--disable-gpu"],
  });
  try {
    const page = await browser.newPage();
    await page.goto(SRC, { waitUntil: "networkidle0" });
    await page.pdf({
      path: OUT,
      format: "A4",
      printBackground: true,
      displayHeaderFooter: true,
      headerTemplate: "<span></span>",
      footerTemplate: footer,
      margin: { top: "18mm", right: "16mm", bottom: "16mm", left: "16mm" },
    });
  } finally {
    await browser.close();
  }
  console.log("Wrote " + OUT);
})();

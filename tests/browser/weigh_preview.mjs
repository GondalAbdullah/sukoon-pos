// The weigh box: what the cashier is shown before pressing Set must equal what the cart records
// after it. The preview read `amount * 1000 / unitPrice` (rupees over paisa) and showed ten times
// the weight — the sale was right, the screen wasn't.
import puppeteer from 'puppeteer-core';

const BASE = process.env.BASE;
const SHOTS = process.env.SHOTS;
const browser = await puppeteer.launch({executablePath: '/usr/bin/google-chrome', headless: 'new',
                                        args: ['--no-sandbox']});
const page = await browser.newPage();
await page.setViewport({width: 1366, height: 900});
const fail = m => { console.log('FAIL', m); process.exitCode = 1; };

// sign in
await page.goto(BASE + '/login', {waitUntil: 'networkidle0'});
// the password box appears once a name is chosen, as it does for a cashier
for (const b of await page.$$('button')) {
  if ((await b.evaluate(n => n.textContent)).includes('Owner')) { await b.click(); break; }
}
await new Promise(r => setTimeout(r, 400));
await page.type('input[name=password]', 'owner-pass-check');
await Promise.all([page.waitForNavigation(), page.click('button[type=submit]')]);

// till: add the loose product
await page.goto(BASE + '/till/', {waitUntil: 'networkidle0'});
const label = await page.$('form[action*="terminal"] input[name=label]');
if (label && await label.isVisible()) {
  await label.type('Till 1');
  await Promise.all([page.waitForResponse(r => r.request().method() === 'POST'), label.press('Enter')]);
  await new Promise(r => setTimeout(r, 600));
}
await page.type('#scan-input', 'Atta');
await Promise.all([page.waitForResponse(r => r.request().method() === 'POST'),
                   page.keyboard.press('Enter')]);
await new Promise(r => setTimeout(r, 800));

// by amount: Rs 200 of atta at Rs 480/kg is 0.417 kg
const byAmount = await page.$$('button');
for (const b of byAmount) {
  if ((await b.evaluate(n => n.textContent)).includes('Amount')) { await b.click(); break; }
}
await new Promise(r => setTimeout(r, 300));
const amountBox = await page.$('input[name=amount]');
await amountBox.click();
await amountBox.type('200');
await new Promise(r => setTimeout(r, 300));

const preview = await page.evaluate(() => {
  const pill = [...document.querySelectorAll('span')].find(s => s.textContent.trim().startsWith('≈ 0.') ||
                                                              s.textContent.trim().match(/^≈ \d/));
  return pill ? pill.textContent.trim() : null;
});
console.log('preview shown to the cashier:', preview);
if (preview !== '≈ 0.417 kg') fail(`preview should be "≈ 0.417 kg", got ${preview}`);
await page.screenshot({path: `${SHOTS}/weigh-preview.png`});

// press Set and read what the cart recorded
// the Set button of the *amount* form, not the weight one
const setAmount = await page.$('form:has(input[name=op][value="set_amount"]) button[type=submit]');
if (!setAmount) fail('could not find the Set button for the amount form');
await Promise.all([page.waitForResponse(r => r.request().method() === 'POST'), setAmount.click()]);
await new Promise(r => setTimeout(r, 900));
const cart = await page.evaluate(() => document.body.innerText);
const saved = cart.match(/0\.417 kg/);
const total = cart.match(/Rs 200\b/);
console.log('cart line:', saved ? saved[0] : '(no 0.417 kg found)', '| total:', total ? total[0] : '(no Rs 200)');
if (!saved) fail('the cart should hold 0.417 kg, matching the preview');
if (!total) fail('the line should cost exactly the Rs 200 that was typed');
await page.screenshot({path: `${SHOTS}/weigh-saved.png`});
await browser.close();
console.log(process.exitCode ? 'CHECK FAILED' : 'CHECK PASSED: preview and saved quantity agree');

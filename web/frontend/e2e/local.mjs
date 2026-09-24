import { chromium } from "playwright";
const SHOTS = new URL("./shots", import.meta.url).pathname;
import { mkdirSync } from "node:fs";
mkdirSync(new URL("./shots", import.meta.url).pathname, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await ctx.addInitScript(() => localStorage.setItem("bs.lang", "ru")); // selectors below are Russian
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push(m.type() + ": " + m.text()); });

await page.goto("http://localhost:5173/");
await page.waitForSelector("text=Как играем?");
await page.fill("input[placeholder='имя или ник']", "Тестер");
await page.click("text=Сохранить");
await page.waitForSelector("text=вы — Тестер", { timeout: 10000 });
await page.screenshot({ path: `${SHOTS}/01-home.png` });

await page.click("text=Играть с моделью");
await page.waitForSelector("text=Расстановка");
await page.waitForSelector("button:has-text('К бою'):not([disabled])", { timeout: 30000 });
await page.screenshot({ path: `${SHOTS}/02-placement.png` });

// rotate the first ship (4-decker) by click and drag it to the right
await page.click(".ship--drag >> nth=0", { position: { x: 10, y: 10 } });   // rotate
const ship = page.locator(".ship--drag").first();
const box = await ship.boundingBox();
await page.mouse.move(box.x + 10, box.y + 10);
await page.mouse.down();
await page.mouse.move(box.x + 10 + 40 * 2, box.y + 10, { steps: 5 });     // move
await page.mouse.up();
await page.click("text=Перемешать");
await page.click("button:has-text('К бою')");
await page.waitForSelector("text=Флот соперника");
await page.screenshot({ path: `${SHOTS}/03-battle-start.png` });

// play: shoot the first available cell until the game ends (up to 250 clicks)
let turns = 0;
while (turns < 250) {
  const over = await page.locator(".overlay").count();
  if (over) break;
  const btn = page.locator("button.cell--btn:not([disabled])").first();
  if (await btn.count()) {
    await btn.click({ timeout: 2000 }).catch(() => undefined);
    turns++;
  } else {
    await page.waitForTimeout(300);
  }
}
await page.screenshot({ path: `${SHOTS}/04-battle-end.png` });
const title = await page.locator(".overlay__title").textContent();
const text = await page.locator(".overlay .muted").textContent();
console.log("итог:", title, "|", text, "| нажатий:", turns);
const chips = await page.locator(".chip").allTextContents();
console.log("журнал:", chips.slice(0, 4).join(" / "));

// dark theme
await page.click(".theme-link", { force: true });
await page.waitForTimeout(300);
await page.screenshot({ path: `${SHOTS}/05-dark.png` });
console.log("тема:", await page.evaluate(() => document.documentElement.dataset.theme));

// mobile width
await page.setViewportSize({ width: 375, height: 800 });
await page.waitForTimeout(300);
await page.screenshot({ path: `${SHOTS}/06-mobile.png`, fullPage: true });
const cellW = await page.evaluate(() => document.querySelector(".cell").getBoundingClientRect().width);
console.log("клетка на 375px:", cellW);
console.log("ошибки в консоли:", errors.length ? errors : "нет");
await browser.close();

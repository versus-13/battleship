import { chromium } from "playwright";
const S = new URL("./shots", import.meta.url).pathname;
import { mkdirSync } from "node:fs";
mkdirSync(new URL("./shots", import.meta.url).pathname, { recursive: true });
const browser = await chromium.launch();
const errors = [];
const mk = async (name) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`${name} pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${name} console: ${m.text().slice(0, 200)}`); });
  await page.goto((process.env.BASE ?? "http://localhost:5173") + "/");
  await page.waitForSelector("text=Как играем?");
  await page.fill("input[placeholder='имя или ник']", name);
  await page.click("text=Сохранить");
  await page.waitForSelector(`text=вы — ${name}`);
  return page;
};
const A = await mk("Алиса"), B = await mk("Боб");

// A creates a room
await A.click("text=Позвать друга");
await A.waitForSelector("text=Ждём соперника");
const link = await A.inputValue(".link-row input");
console.log("ссылка:", link);
await A.screenshot({ path: `${S}/10-room-wait.png` });

// B opens the link and accepts
await B.goto(link);
await B.waitForSelector("text=вас зовёт Алиса");
await B.screenshot({ path: `${S}/11-room-join.png` });
await B.click("text=Принять вызов");
await B.waitForSelector("button:has-text('К бою')");
await A.waitForSelector("button:has-text('К бою')");
console.log("оба на расстановке; заголовок A:", await A.locator(".header__sub").textContent());

await A.click("button:has-text('К бою')");
await B.waitForSelector("text=соперник готов", { timeout: 5000 }).catch(() => console.log("(подсказка «соперник готов» не поймана)"));
await B.click("button:has-text('К бою')");
await A.waitForSelector("text=Флот соперника");
await B.waitForSelector("text=Флот соперника");
await A.screenshot({ path: `${S}/12-online-start-A.png` });

const status = async (p) => (await p.locator(".panel .status").textContent()).trim();
console.log("A:", await status(A), "| B:", await status(B));

// reconnect check: B reloads the page mid-game
let turns = 0, reloaded = false;
while (turns < 400) {
  if (await A.locator(".overlay").count() || await B.locator(".overlay").count()) break;
  const sa = await status(A);
  const cur = sa === "Ваш ход" ? A : (await status(B)) === "Ваш ход" ? B : null;
  if (!cur) { await A.waitForTimeout(150); continue; }
  const btn = cur.locator("button.cell--btn:not([disabled])").first();
  if (await btn.count()) { await btn.click({ timeout: 1500 }).catch(() => undefined); turns++; }
  if (turns === 25 && !reloaded) {
    reloaded = true;
    const before = await B.locator(".chip").count();
    await B.reload();
    await B.waitForSelector("text=Флот соперника");
    await B.waitForTimeout(500);
    const hits = await B.locator(".board-col").nth(1).locator(".cell svg").count();
    console.log("реконнект B: пометок на чужом поле после перезагрузки:", hits, "(чипов журнала было", before, ")");
    await B.screenshot({ path: `${S}/13-online-after-reload-B.png` });
  }
  await A.waitForTimeout(60);
}
await A.waitForTimeout(600);
console.log("итог A:", await A.locator(".overlay__title").textContent(), "|", await A.locator(".overlay .muted").textContent());
console.log("итог B:", await B.locator(".overlay__title").textContent(), "|", await B.locator(".overlay .muted").textContent());
await A.screenshot({ path: `${S}/14-online-end-A.png` });
await B.screenshot({ path: `${S}/14-online-end-B.png` });

await A.click(".overlay button:has-text('На главную')");
await A.waitForSelector("text=Лидеры");
await A.waitForTimeout(800);
console.log("лидерборд:", (await A.locator(".leader tbody").textContent().catch(() => "пусто")).slice(0, 120));
await A.screenshot({ path: `${S}/15-home-after.png` });
console.log("ошибки:", errors.length ? errors : "нет");
await browser.close();

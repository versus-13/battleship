import { chromium } from "playwright";
const browser = await chromium.launch();
const errors = [];
const mk = async (name) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`${name} pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${name} console: ${m.text().slice(0, 200)}`); });
  await page.goto("http://localhost:5173/");
  await page.waitForSelector("text=Как играем?");
  return page;
};
const A = await mk("A"), B = await mk("B");
// name moderation in the UI
await A.fill("input[placeholder='имя или ник']", "xyй");
await A.click("text=Сохранить");
await A.waitForSelector("text=такое имя не подходит");
console.log("модерация: отклонено с подсказкой");
await A.fill("input[placeholder='имя или ник']", "Вася");
await A.click("text=Сохранить");
await A.waitForSelector("text=вы — Вася");
// queue
await A.click("text=Найти соперника");
await A.waitForSelector("text=Ищем соперника");
await A.waitForTimeout(2500);
await B.click("text=Найти соперника");
await A.waitForSelector("button:has-text('К бою')", { timeout: 15000 });
await B.waitForSelector("button:has-text('К бою')", { timeout: 15000 });
console.log("очередь: оба на расстановке, A url:", A.url().replace("http://localhost:5173", ""), "| B заголовок:", await B.locator(".header__sub").textContent());
await A.click("button:has-text('К бою')");
await B.click("button:has-text('К бою')");
await A.waitForSelector("text=Флот соперника");
await B.waitForSelector("text=Флот соперника");
// surrender
await B.click(".panel button:has-text('Сдаться')");
await A.waitForSelector(".overlay");
console.log("A после сдачи B:", await A.locator(".overlay__title").textContent(), "|", await A.locator(".overlay .muted").textContent());
console.log("B:", await B.locator(".overlay__title").textContent(), "|", await B.locator(".overlay .muted").textContent());
console.log("ошибки:", errors.length ? errors : "нет");
await browser.close();

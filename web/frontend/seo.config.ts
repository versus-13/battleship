/**
 * Per-language page metadata. vite.config.ts renders it into index.html (en, served at /)
 * and ru/index.html (served at /ru/). Crawlers and link-preview bots do not run JS, so this
 * static head is all they see. `title` must match documentTitle in src/i18n.ts.
 */
export const SITE = "https://hullbreak.com";

export type SeoLang = "en" | "ru";

export interface Seo {
  path: string;
  title: string;
  description: string;
  ogTitle: string;
  ogDescription: string;
  ogImage: string;
  ogImageAlt: string;
  ogLocale: string;
  noscript: string;
}

export const SEO: Record<SeoLang, Seo> = {
  en: {
    path: "/",
    title: "Hullbreak — Play Battleship Online with a Friend",
    description: "Free online Battleship: invite a friend by link or challenge a neural-network AI. No sign-up, no download — the classic 10×10 game in your browser.",
    ogTitle: "Hullbreak — Battleship online with a friend",
    ogDescription: "Invite a friend by link or take on a neural-network AI. Free, no sign-up, right in the browser.",
    ogImage: "/og.png",
    ogImageAlt: "Hullbreak: a Battleship board with a sunk ship and hits marked in red",
    ogLocale: "en_US",
    noscript: "Play the classic 10×10 Battleship with a friend by link or against a neural-network AI. The game needs JavaScript.",
  },
  ru: {
    path: "/ru/",
    title: "Hullbreak — морской бой онлайн с другом",
    description: "Морской бой онлайн бесплатно: позовите друга по ссылке или сыграйте против нейросети. Без регистрации и установки — классические правила, поле 10×10.",
    ogTitle: "Hullbreak — морской бой онлайн с другом",
    ogDescription: "Позовите друга по ссылке или сразитесь с нейросетью. Бесплатно, без регистрации, прямо в браузере.",
    ogImage: "/og-ru.png",
    ogImageAlt: "Hullbreak: поле морского боя с потопленным кораблём и попаданиями",
    ogLocale: "ru_RU",
    noscript: "Классический морской бой 10×10: с другом по ссылке или против нейросети. Для игры нужен JavaScript.",
  },
};

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** Fills the `<!-- seo:head -->` / `<!-- seo:body -->` markers and the html lang of index.html. */
export function renderSeo(html: string, lang: SeoLang): string {
  const m = SEO[lang];
  const other: SeoLang = lang === "en" ? "ru" : "en";
  const url = SITE + m.path;
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "VideoGame",
    name: "Hullbreak",
    alternateName: lang === "en" ? "Battleship online" : "Морской бой онлайн",
    url,
    image: SITE + m.ogImage,
    description: m.description,
    genre: ["Board game", "Strategy"],
    gamePlatform: "Web browser",
    applicationCategory: "Game",
    playMode: ["MultiPlayer", "SinglePlayer"],
    inLanguage: lang,
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  };
  const head = [
    `<title>${esc(m.title)}</title>`,
    `<meta name="description" content="${esc(m.description)}" />`,
    `<link rel="canonical" href="${url}" />`,
    `<link rel="alternate" hreflang="en" href="${SITE}${SEO.en.path}" />`,
    `<link rel="alternate" hreflang="ru" href="${SITE}${SEO.ru.path}" />`,
    `<link rel="alternate" hreflang="x-default" href="${SITE}${SEO.en.path}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:site_name" content="Hullbreak" />`,
    `<meta property="og:title" content="${esc(m.ogTitle)}" />`,
    `<meta property="og:description" content="${esc(m.ogDescription)}" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:image" content="${SITE}${m.ogImage}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta property="og:image:alt" content="${esc(m.ogImageAlt)}" />`,
    `<meta property="og:locale" content="${m.ogLocale}" />`,
    `<meta property="og:locale:alternate" content="${SEO[other].ogLocale}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<script type="application/ld+json">${JSON.stringify(jsonLd).replace(/</g, "\\u003c")}</script>`,
  ].join("\n    ");
  const body = `<noscript><h1>${esc(m.ogTitle)}</h1><p>${esc(m.noscript)}</p></noscript>`;
  return html
    .replace(/<html lang="[^"]*"/, `<html lang="${lang}"`)
    .replace("<!-- seo:head -->", head)
    .replace("<!-- seo:body -->", body);
}

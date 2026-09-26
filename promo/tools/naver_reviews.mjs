// 네이버 플레이스 방문자 리뷰·키워드·사진·기본정보 수집기
// 사용: node naver_reviews.mjs [placeId] [outDir]
// 결과: outDir/naver_home.txt, naver_reviews.json, naver_reviews.txt, naver_photos.json
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import fs from 'fs';
import path from 'path';

const id = process.argv[2] || '13154835';
const outDir = process.argv[3] || path.resolve('../assets/reviews');
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({
  userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  viewport: { width: 414, height: 896 }, locale: 'ko-KR',
});
const page = await ctx.newPage();

async function open(url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(3500);
}

// 1) 홈: 기본 정보 텍스트
await open(`https://m.place.naver.com/hospital/${id}/home`);
fs.writeFileSync(path.join(outDir, 'naver_home.txt'), await page.evaluate(() => document.body.innerText));

// 2) 방문자 리뷰: 더보기를 끝까지 누른다
await open(`https://m.place.naver.com/hospital/${id}/review/visitor`);
for (let i = 0; i < 60; i++) {
  const more = page.locator('a:has-text("더보기"), button:has-text("더보기"), a:has-text("펼쳐보기")');
  const n = await more.count();
  if (!n) break;
  let clicked = false;
  for (let k = 0; k < n; k++) {
    try { await more.nth(k).click({ timeout: 800 }); clicked = true; } catch {}
  }
  await page.mouse.wheel(0, 4000);
  await page.waitForTimeout(900);
  if (!clicked) break;
}
const reviewsText = await page.evaluate(() => document.body.innerText);
fs.writeFileSync(path.join(outDir, 'naver_reviews.txt'), reviewsText);
fs.writeFileSync(path.join(outDir, 'naver_reviews.html'), await page.content());

// 구조화 시도: 리뷰 카드는 li 안에 본문과 날짜가 있다. 셀렉터가 바뀌면 txt를 대신 쓴다
const reviews = await page.evaluate(() => {
  const out = [];
  for (const li of document.querySelectorAll('li')) {
    const t = li.innerText || '';
    if (t.length < 20 || !/\d{1,2}\.\d{1,2}\.|\d{4}\.\d{1,2}\./.test(t)) continue;
    if (li.querySelector('li')) continue; // 중첩 목록의 바깥 li는 건너뜀
    out.push(t.replace(/\s+\n/g, '\n').trim());
  }
  return out;
});
const keywords = await page.evaluate(() => {
  const found = [];
  for (const el of document.querySelectorAll('span, div, li')) {
    const t = (el.innerText || '').trim();
    const m = t.match(/^"?(.{2,30}?)"?\s*\n?\s*이 키워드를 선택한 인원\s*([\d,]+)/);
    if (m) found.push({ keyword: m[1], count: Number(m[2].replace(/,/g, '')) });
  }
  return found;
});
fs.writeFileSync(path.join(outDir, 'naver_reviews.json'), JSON.stringify({ placeId: id, fetchedAt: new Date().toISOString(), keywords, reviews }, null, 1));

// 3) 사진 URL 목록 (실제 병원 사진 후보)
await open(`https://m.place.naver.com/hospital/${id}/photo`);
for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 3000); await page.waitForTimeout(600); }
const photos = await page.evaluate(() => Array.from(document.images).map(i => i.src).filter(s => /pstatic\.net/.test(s)));
fs.writeFileSync(path.join(outDir, 'naver_photos.json'), JSON.stringify([...new Set(photos)], null, 1));

console.log(`reviews: ${reviews.length}, keywords: ${keywords.length}, photos: ${new Set(photos).size} -> ${outDir}`);
await browser.close();

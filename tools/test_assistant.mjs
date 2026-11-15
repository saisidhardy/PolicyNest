import {chromium} from '@playwright/test';
import fs from 'node:fs';
import http from 'node:http';
import assert from 'node:assert/strict';
const server=http.createServer((req,res)=>{const name=req.url.split('?')[0];const file=name==='/web-vitals.iife.js'?'web-vitals.iife.js':name==='/kb.json'?'kb.json':'index.html';res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.json')?'application/json':'text/html');res.end(fs.readFileSync('policynest_mvp/site/'+file))});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
let browser;
try{
  for(const channel of ['msedge','chrome',undefined]){try{browser=await chromium.launch({channel,headless:true});break}catch{}}
  if(!browser)throw new Error('No supported browser installed');
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',r=>r.fulfill({status:503,contentType:'application/json',body:'{"error":"unavailable"}'}));
  await page.goto(`http://127.0.0.1:${server.address().port}/#apply`);
  await page.locator('#cp-fab').click();
  await page.locator('#guide-next').click();
  assert.match(await page.locator('#guide-status').innerText(),/checklist|Start onboarding/i);
  assert.equal(await page.locator('[data-act="begin-nofs"]').evaluate(e=>document.activeElement===e),true);
  await page.locator('#guide-appeal').click();
  assert.equal(await page.locator('#account-form').isVisible(),true);
  assert.match(await page.locator('#guide-status').innerText(),/Sign in/);
  await page.locator('#account-close').click();
  await page.locator('#cp-q').fill('What should I do next?');
  await page.locator('#cp-form button').click();
  await page.waitForFunction(()=>document.querySelector('#cp-log').innerText.includes('Start onboarding'));
  assert.deepEqual(errors,[]);
  console.log('PASS assistant next-action focus, signed-out appeal gate, deterministic fallback, no page errors');
}finally{if(browser)await browser.close();server.close()}

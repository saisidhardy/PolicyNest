import {chromium,request} from '@playwright/test';
import {spawn} from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const password=crypto.randomBytes(24).toString('hex');
const proc=spawn('.python-runtime/python.exe',['tools/browser_fixture.py'],{stdio:['pipe','pipe','inherit']});
proc.stdin.write(JSON.stringify({password})+'\n');
let browser;
try{
 const ready=await new Promise((resolve,reject)=>{let text='';proc.stdout.on('data',d=>{text+=d;if(text.includes('\n'))resolve(JSON.parse(text.split('\n')[0]))});proc.on('exit',c=>reject(new Error('Fixture exited '+c)));setTimeout(()=>reject(new Error('Fixture startup timed out')),20000).unref()});
 for(const channel of ['msedge','chrome',undefined]){try{browser=await chromium.launch({channel,headless:true});break}catch{}}
 if(!browser)throw new Error('No browser available');
 const context=await browser.newContext({viewport:{width:1280,height:900}});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',async route=>{const u=new URL(route.request().url());u.port='8788';const response=await route.fetch({url:u.toString()});await route.fulfill({response})});
 await page.goto('http://localhost:8000/#apply');
 await page.locator('#account-open').click();await page.locator('#account-name').fill('Synthetic Test Applicant');await page.locator('#account-email').fill('applicant@example.test');await page.locator('#account-password').fill(password);await page.locator('#account-form button[value=register]').click();
 await page.waitForFunction(()=>document.querySelector('#account-open').textContent.includes('Sign out'));
 await page.locator('#account-sync').check();await page.locator('#workspace-open').click();await page.waitForFunction(()=>document.querySelector('#workspace-body').innerText.includes('PN-'));
 const caseId=(await page.locator('#workspace-body').innerText()).match(/PN-[a-f0-9]+/)[0];await page.locator('#workspace-close').click();
 await page.locator('#cp-fab').click();await page.locator('#guide-appeal').click();await page.locator('#appeal-concern').fill('The document feedback is unclear. Please reassess the evidence.');await page.locator('#appeal-form button[type=submit]').click();await page.waitForFunction(()=>document.querySelector('#appeal-result').innerText.includes('Appeal submitted'));
 const reference=(await page.locator('#appeal-result').innerText()).match(/AP-[a-f0-9]+/)[0];await page.locator('#appeal-close').click();
 const admin=await request.newContext({baseURL:'http://localhost:8788',extraHTTPHeaders:{Origin:'http://localhost:8000'}});
 assert.equal((await admin.post('/api/auth/login',{data:{email:'admin@example.test',password}})).status(),200);
 assert.equal((await admin.post('/api/admin/assign',{data:{case_id:caseId,reviewer_id:ready.reviewer}})).status(),200);
 await page.locator('[data-act=cp-close]').click();await page.locator('#account-open').click();await page.waitForFunction(()=>document.querySelector('#account-open').textContent.includes('create account'));
 await page.locator('#account-open').click();await page.locator('#account-email').fill('reviewer@example.test');await page.locator('#account-password').fill(password);await page.locator('#account-form button[value=login]').click();await page.waitForFunction(()=>document.querySelector('#account-open').textContent.includes('Test Reviewer'));
 await page.locator('#workspace-open').click();await page.locator('[data-account-case]').click();await page.locator('[data-resolution-text]').fill('Please upload a clearer document through your application correction controls.');await page.locator('[data-resolution-status]').selectOption('MORE_INFO');await page.locator('[data-resolve-appeal]').click();await page.waitForFunction(()=>document.querySelector('#workspace-body').innerText.includes('MORE_INFO'));
 fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/reviewer-workspace.png',fullPage:true});
 await page.locator('#workspace-close').click();await page.locator('#account-open').click();await page.waitForFunction(()=>document.querySelector('#account-open').textContent.includes('create account'));
 await page.locator('#account-open').click();await page.locator('#account-email').fill('applicant@example.test');await page.locator('#account-password').fill(password);await page.locator('#account-form button[value=login]').click();await page.waitForFunction(()=>document.querySelector('#account-open').textContent.includes('Synthetic Test Applicant'));
 await page.locator('#workspace-open').click();await page.waitForFunction(()=>document.querySelector('#workspace-body').innerText.includes('MORE_INFO'));assert.match(await page.locator('#workspace-body').innerText(),new RegExp(reference));await page.locator('#workspace-close').click();
 await page.locator('#cp-fab').click();await page.locator('#cp-q').fill('Training Timer Not Progressing');await page.locator('#cp-form button').click();await page.waitForFunction(()=>document.querySelector('#cp-log').innerText.includes('POSP Manual'),{},{timeout:60000});
 await page.screenshot({path:'test-results/assistant-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/assistant-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);await admin.dispose();
 console.log('PASS registration, cookie session, progress sync, appeal submission, admin assignment, reviewer queue/resolution, applicant status, manual RAG citation, no JS errors');
}finally{if(browser)await browser.close();if(proc.exitCode===null){proc.stdin.write('stop\n');await new Promise(resolve=>{proc.once('exit',resolve);setTimeout(()=>{proc.kill();resolve()},5000).unref()})}}

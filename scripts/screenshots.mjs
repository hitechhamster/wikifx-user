import {chromium} from 'playwright';import fs from 'node:fs';
fs.mkdirSync('artifacts/screenshots',{recursive:true});
const browser=await chromium.launch({headless:true,channel:process.env.SCREENSHOT_CHANNEL||undefined});
const results=[];
try{for(const [name,width,height]of[['desktop',1280,900],['mobile',390,844]]){
 const page=await browser.newPage({viewport:{width,height},timezoneId:'Asia/Shanghai',deviceScaleFactor:1});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('https://review.wikifxusers.com/',{waitUntil:'networkidle'});await page.locator('#list section').first().waitFor();
 await page.screenshot({path:`artifacts/screenshots/review-${name}.png`,fullPage:true});
 results.push({name,width,height,errors,...await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,sections:document.querySelectorAll('#list section').length,summary:document.querySelector('.summary-row')?.textContent,total:document.querySelector('#total')?.textContent,footerPosition:getComputedStyle(document.querySelector('.foot')).position}))});await page.close();
}}finally{await browser.close();}fs.writeFileSync('artifacts/screenshots/checks.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));

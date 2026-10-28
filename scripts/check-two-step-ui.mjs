import {chromium} from 'playwright';
import fs from 'node:fs';
const browser=await chromium.launch({headless:true,channel:'chrome'});const checks=[];
try{for(const [name,width,height]of[['desktop',1280,900],['mobile',390,844]]){
const page=await browser.newPage({viewport:{width,height},timezoneId:'Asia/Shanghai'});const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('https://review.wikifxusers.com/');await page.locator('[data-preview]').first().click();await page.locator('.draft-body p').first().waitFor();
checks.push({name,errors,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),preview:await page.locator('.draft-body').count(),sourceLinks:await page.locator('.draft-body a').count(),sendDisabled:await page.locator('#send').isDisabled()});await page.screenshot({path:`artifacts/screenshots/two-step-${name}.png`,fullPage:true});await page.close();}
}finally{await browser.close();}fs.writeFileSync('artifacts/screenshots/two-step-checks.json',JSON.stringify(checks,null,2));console.log(JSON.stringify(checks));

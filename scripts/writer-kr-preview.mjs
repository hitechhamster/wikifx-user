import {execFileSync} from 'node:child_process';
execFileSync(process.execPath,['node_modules/wrangler/bin/wrangler.js','workflows','trigger','wikifx-signal-pipeline',JSON.stringify({kind:'article-preview',item:'09bee537ab5daaa391f5be68a426eb845f2ebdacded6da3c3d4453c13eea8b4d'}),'--id','writer-v2-kr-final2-20261027'],{stdio:'inherit'});


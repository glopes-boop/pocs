// Render .excalidraw -> PNG with the real Excalidraw (headless Chrome).
// Usage: node render.mjs in.excalidraw out.png   (needs: npm i in scripts/; CHROME_PATH opcional)
import p from 'puppeteer-core'; import fs from 'fs';
const [,,inp,out]=process.argv; const d=fs.readFileSync(inp,'utf8');
const html=`<html><body style="margin:0;background:#fff"><div id=o></div><script type=module>
import {exportToSvg} from "https://esm.sh/@excalidraw/excalidraw@0.18.0?bundle&deps=react@18.3.1,react-dom@18.3.1";
const d=${d};const s=await exportToSvg({elements:d.elements,appState:{...d.appState,exportBackground:true},files:{}});
document.getElementById('o').appendChild(s);document.title='done';</script></body></html>`;
const b=await p.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',args:['--no-sandbox']});
const pg=await b.newPage();await pg.setViewport({width:1600,height:1000,deviceScaleFactor:2});
await pg.setContent(html);await pg.waitForFunction('document.title=="done"',{timeout:60000});
await (await pg.$('svg')).screenshot({path:out});await b.close();console.log('wrote',out);

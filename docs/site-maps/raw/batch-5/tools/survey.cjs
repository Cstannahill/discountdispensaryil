// usage: node survey.cjs outdir '[["key","url"],...]' [--click]
const {chromium}=require('S:/Code/Other/terpscout_fullstack/frontend/node_modules/playwright');
const fs=require('fs');
const outdir=process.argv[2]; const targets=JSON.parse(process.argv[3]);
const UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36';
const SIG=[['jane',/iheartjane|ihj-|algolia\.net.*jane|api\.iheartjane/i],['dutchie',/dutchie\.com|dutchie-|"dutchie"/i],['sweed',/sweedpos|sweed\.|sweed-/i],['treez',/treez\.io|gapcommerce|treez-/i],['dispense',/dispenseapp|dispense\.|cdn\.dispense/i],['blaze',/blaze\.me|blazepos|blaze-menu|blaze\.com/i],['joint',/jointcommerce|joint-commerce/i],['greensling',/greensling/i],['flowhub',/flowhub/i],['weedmaps',/weedmaps/i],['leafly',/leafly\.com/i],['tymber',/tymber/i],['meadow',/getmeadow|meadow\.com/i],['cresco',/crescolabs|cresco/i],['curaleaf',/curaleaf/i],['shopify',/shopify/i],['leaflink',/leaflink/i],['wpjson',/wp-json/i],['rise',/risecannabis/i]];
function findArr(o,path,best,depth){
  if(depth>6||o===null||typeof o!=='object')return;
  if(Array.isArray(o)){
    if(o.length>=3&&o[0]&&typeof o[0]==='object'){const k=Object.keys(o[0]);const nm=k.some(x=>/^(name|title|productName|product_name|label)$/i.test(x));const pr=k.some(x=>/price|cost|amount|variants|prices/i.test(x));if(nm&&(pr||o.length>=10)&&(!best.n||o.length>best.n)){best.n=o.length;best.path=path;best.keys=k.slice(0,12)}}
    for(const [i,v] of o.slice(0,3).entries())findArr(v,path+'[]',best,depth+1);
  } else for(const k of Object.keys(o))findArr(o[k],path+'.'+k,best,depth+1);
}
async function one(ctx,key,url){
  const res={key,url,requests:[],json:[],frames:[]};
  const p=await ctx.newPage();
  const hosts={};
  p.on('request',r=>{try{const u=new URL(r.url());hosts[u.host]=(hosts[u.host]||0)+1}catch(e){}});
  p.on('response',async r=>{
    try{
      const u=r.url();const rt=r.request().resourceType();const ct=(r.headers()['content-type']||'');
      if(!(rt==='xhr'||rt==='fetch'||/json/.test(ct)))return;
      if(/google|facebook|doubleclick|segment|sentry|klaviyo|hotjar|clarity|onetrust|cookielaw|tiktok|snap|pinterest|gtm|analytics|fullstory|datadog|intercom/i.test(u))return;
      const rec={u:u.slice(0,200),m:r.request().method(),s:r.status(),ct:ct.slice(0,30)};
      if(/json/.test(ct)||/graphql|api|query|search/.test(u)){
        try{const b=await r.text();rec.len=b.length;if(b.length<6e6&&/^[\[{]/.test(b.trim())){const j=JSON.parse(b);const best={};findArr(j,'$',best,0);if(best.n)rec.arr=best}}catch(e){}
        if(r.request().method()==='POST'){try{rec.post=(r.request().postData()||'').slice(0,160)}catch(e){}}
      }
      res.json.push(rec);
    }catch(e){}
  });
  let status=null;
  try{
    const r=await p.goto(url,{timeout:40000,waitUntil:'domcontentloaded'});status=r&&r.status();
    res.status=status;
    await p.waitForTimeout(6000);
    // age gate detection
    const gateSel=await p.evaluate(()=>{const t=(document.body&&document.body.innerText||'').slice(0,4000);return /(are you|years? (of age|old)|21\+|age verif|date of birth|over 21|legal age|enter your birth)/i.test(t)?t.slice(0,300).replace(/\s+/g,' '):null});
    res.age_gate_text=gateSel;
    if(gateSel&&process.argv[4]==='--click'){
      const clicked=await p.evaluate(()=>{const els=[...document.querySelectorAll('button,a,[role=button],input[type=button],input[type=submit]')];const re=/^(yes|i am 21|i'm 21|i am over 21|i'm over 21|enter|i am 21 or older|i'm 21\+|i am 21\+|21\+|over 21|yes,? i am|confirm$|i'm at least 21|i am at least 21|at least 21|i'm of age|i am of age)/i;const bad=/google|facebook|apple|sign ?in|log ?in|account|create|register|subscribe|newsletter|cookie|accept all/i;const el=els.find(e=>{const t=(e.innerText||e.value||'').trim();return t.length<40&&re.test(t)&&!bad.test(t)});if(el){const t=(el.innerText||el.value||'').trim();el.click();return t}return null});
      res.age_click=clicked;if(clicked)await p.waitForTimeout(6000);
    }
    await p.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));await p.waitForTimeout(3000);
    res.final_url=p.url();res.title=await p.title();
    const info=await p.evaluate(()=>{const html=document.documentElement.outerHTML;const text=document.body?document.body.innerText:'';return {htmlLen:html.length,prices:(text.match(/\$\s?\d+(\.\d\d)?/g)||[]).length,textHead:text.slice(0,200).replace(/\s+/g,' '),iframes:[...document.querySelectorAll('iframe')].map(f=>f.src).filter(Boolean).slice(0,6),scripts:[...document.querySelectorAll('script[src]')].map(s=>s.src).slice(0,200),nextdata:!!document.getElementById('__NEXT_DATA__'),links:[...document.querySelectorAll('a[href]')].map(a=>a.href).filter(h=>/iheartjane|dutchie|sweed|treez|dispenseapp|blaze|jointcommerce|greensling|flowhub|weedmaps|leafly|tymber|getmeadow|shop\.|order\.|menu\./i.test(h)).slice(0,12),count_text:(text.match(/(\d[\d,]*)\s+(products|results|items)/i)||[])[0]||null}});
    Object.assign(res,info);
    res.frames=p.frames().map(f=>f.url()).filter(u=>u&&u!=='about:blank'&&u!==res.final_url).slice(0,8);
    const blob=JSON.stringify(Object.keys(hosts))+info.scripts.join(' ')+info.iframes.join(' ')+res.frames.join(' ')+info.links.join(' ')+url+res.final_url;
    res.platforms=SIG.filter(([n,re])=>re.test(blob)).map(x=>x[0]);
    res.hosts=Object.entries(hosts).sort((a,b)=>b[1]-a[1]).slice(0,14);
    delete res.scripts;
    await p.screenshot({path:outdir+'/'+key+'.png'}).catch(()=>{});
  }catch(e){res.error=e.message.slice(0,200)}
  res.json=res.json.slice(0,25);
  fs.writeFileSync(outdir+'/'+key+'.json',JSON.stringify(res,null,1));
  await p.close();
  return res;
}
(async()=>{
  const b=await chromium.launch({channel:'chrome',headless:true});
  const ctx=await b.newContext({userAgent:UA,viewport:{width:1366,height:900}});
  const q=[...targets];const out=[];
  async function worker(){while(q.length){const [k,u]=q.shift();const r=await one(ctx,k,u);
    const arrs=r.json.filter(j=>j.arr).map(j=>j.arr.n+'@'+(j.u.split('?')[0].slice(-60))).slice(0,3);
    console.log(k+' | '+(r.status||r.error)+' | '+(r.final_url||'').slice(0,90)+' | plat='+(r.platforms||[]).join(',')+' | $n='+r.prices+' | age='+(r.age_gate_text?'Y':'n')+(r.age_click?'(clicked:'+r.age_click+')':'')+' | arr='+arrs.join(';')+' | frames='+(r.frames||[]).map(f=>f.slice(0,60)).slice(0,2).join(','))}}
  await Promise.all([worker(),worker(),worker()]);
  await b.close();
})();

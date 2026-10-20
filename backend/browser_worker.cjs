/* Ordinary Chrome rendering through validated captured HTTP or a public-only
 * native tunnel. Shopping preferences are distinct from age confirmation. */
const { chromium } = require('../frontend/node_modules/playwright');
const readline = require('node:readline');
const {selectLocation}=require('./browser_locations.cjs');
const input = readline.createInterface({input:process.stdin});
const pending = new Map();
let nextId=1, started=false;
const diagnostics={};
const progress=async phase=>{diagnostics.phase=phase;await send({type:'progress',diagnostics:{...diagnostics}});};
const send = value => new Promise((resolve,reject)=>process.stdout.write(JSON.stringify(value)+'\n',error=>error?reject(error):resolve()));
input.on('line',line=>{
  let message;try {message=JSON.parse(line);} catch {return;}
  if(message.type==='start'&&!started){started=true;run(message).catch(async e=>{
    const message=diagnostics.requests>diagnostics.request_limit?`Browser request budget exceeded (${diagnostics.request_limit})`:e.message;
    diagnostics.stack=String(e.stack||'').slice(0,1500);
    await send({type:'error',message,diagnostics});process.exit(1);
  });}
  else if(pending.has(message.id)){pending.get(message.id)(message);pending.delete(message.id);}
});
async function request(data){const id=nextId++;return new Promise(resolve=>{pending.set(id,resolve);send({type:'request',id,...data});});}
async function navigateCatalog(page,url){
 for(let attempt=0;attempt<2;attempt++){
  try{return await page.goto(url,{waitUntil:'domcontentloaded',timeout:35000});}
  catch(error){
   const transient=/Timeout \d+ms exceeded|net::ERR_(?:FAILED|CONNECTION_RESET|CONNECTION_CLOSED|TIMED_OUT|EMPTY_RESPONSE)/.test(error.message);
   const exhausted=diagnostics.requests>diagnostics.request_limit||diagnostics.capture_errors?.some(message=>message.includes('budget exceeded'));
   if(attempt||!transient||exhausted)throw error;
   (diagnostics.navigation_retries??=[]).push({url,reason:error.message,attempt:attempt+1});
   await page.waitForTimeout(250);
  }
 }
}
async function selectMenuContext(page,options){
 const selected=options.license_type||'recreational';
 if(!['recreational','medicinal'].includes(selected))throw new Error('Unsupported menu license context');
 const name=selected==='medicinal'?/^(?:medical|medicinal)(?:\s+(?:use|menu|shopping|patient))?$/i:/^(?:recreational|adult[ -]use)(?:\s+(?:use|menu|shopping))?$/i;
 const transitions=[];
 for(let round=0;round<3;round++){
  let changed=false;
  for(const frame of page.frames()){
   const dialogs=frame.getByRole('dialog').filter({visible:true});
   // Restrict choice/continue clicks to an actual shopping-context dialog.
   for(let index=0;index<await dialogs.count();index++){
    const dialog=dialogs.nth(index),text=await dialog.innerText();
    if(!/medical|medicinal/i.test(text)||!/recreational|adult[ -]use/i.test(text))continue;
    let choice=null,role=null;
    for(const candidateRole of ['radio','button','link']){
     const candidate=dialog.getByRole(candidateRole,{name}).filter({visible:true});
     if(await candidate.count()===1){choice=candidate;role=candidateRole;break;}
    }
    if(!choice)continue;
    // An already-selected choice is not clicked: its wrapper overlay usually intercepts pointer events on it.
    const chosen=await choice.evaluate(node=>node.getAttribute('aria-pressed')==='true'||node.getAttribute('aria-checked')==='true'||node.getAttribute('data-selected')==='true'||node.checked===true).catch(()=>false);
    if(chosen)transitions.push({kind:'menu_context_already_selected',license_type:selected,frame_url:frame.url()});
    else{
     if(role==='radio')await choice.check({timeout:3000});
     else await choice.click({timeout:3000});
     transitions.push({kind:'menu_context',license_type:selected,frame_url:frame.url()});
    }
    changed=true;
    if(await dialog.isVisible()){
     const start=dialog.getByRole('button',{name:/^(?:start shopping|shop now|continue|view menu)$/i}).filter({visible:true});
     if(await start.count()===1&&await start.isEnabled())await start.click({timeout:3000});
    }
    await page.waitForTimeout(500);
    break;
   }
  }
  if(!changed)break;
 }
 return transitions;
}
async function waitForMenu(page,options){
 const started=Date.now(),limit=Math.min(30000,Math.max(250,Number(options.menu_readiness_ms)||12000));
 do{
  for(const frame of page.frames()){
   try{
    const ready=await frame.evaluate(()=>{
     const product=value=>value&&typeof value==='object'&&((Array.isArray(value['@type'])?value['@type']:[value['@type']]).includes('Product')||Object.values(value).some(product));
     const roots=[document];for(let i=0;i<roots.length;i++)for(const node of roots[i].querySelectorAll('*'))if(node.shadowRoot)roots.push(node.shadowRoot);
     if(roots.flatMap(root=>[...root.querySelectorAll('script[type="application/ld+json"]')]).some(node=>{try{return product(JSON.parse(node.textContent));}catch{return false;}}))return true;
     return roots.flatMap(root=>[...root.querySelectorAll('[data-product-id],[itemtype$="/Product"],[data-testid*="product-card"],[class*="product-card"],[class*="ProductCard"],[aria-label*="product card"]')]).some(node=>node.getClientRects().length&&/\$\s*\d/.test(node.innerText||''));
    });
    if(ready)return {observed_products:true,waited_ms:Date.now()-started,limit_ms:limit};
   }catch{/* Detached frames can be replaced while the menu initializes. */}
  }
  await page.waitForTimeout(250);
 }while(Date.now()-started<limit);
 return {observed_products:false,waited_ms:Date.now()-started,limit_ms:limit};
}
function shadowMarkup(){
 const roots=[document],sections=[];
 for(let i=0;i<roots.length;i++)for(const node of roots[i].querySelectorAll('*')){
  if(node.shadowRoot){roots.push(node.shadowRoot);sections.push('<section data-terpscout-shadow="open">'+node.shadowRoot.innerHTML+'</section>');}
 }
 return sections.join('');
}
let ageGateWaited=false;
// Age gates often initialise after DOMContentLoaded (some reload the page when confirmed): poll briefly for one.
async function confirmAge(page,options){
 if(!options.age_confirmed)return;
 const deadline=Date.now()+(ageGateWaited?0:6000);ageGateWaited=true;
 for(;;){
  const result=await retried(()=>confirmAgeOnce(page,options));
  if(result.changed||Date.now()>=deadline)break;
  const marker=await retried(()=>page.evaluate(()=>!!document.querySelector('[class*="age-gate"],[class*="agegate"],[id*="age-gate"],[id*="agegate"]')||/over 21|21 years|21\+|legal age|are you 21/i.test(document.body?.innerText||'')));
  if(!marker)break;
  await page.waitForTimeout(400);
 }
}
async function confirmAgeOnce(page,options){
 let changed=false;
 const age=page.getByRole('checkbox',{name:/21|at least/i});
 if(await age.count()===1&&await age.isVisible()&&!await age.isChecked()){
  const combined=await age.evaluate(el=>/terms|privacy|agree/i.test(el.labels?.[0]?.textContent||el.getAttribute('aria-label')||''));
  if(!combined||options.terms_accepted){await age.check();changed=true;}
 }
 const yes=page.getByRole('button',{name:/^(?:yes[,! ]*|i am |i'm |i’m ).*(?:21|older)|^yes$/i});
 const decision={yes_count:await yes.count(),yes_visible:null,clicked:false,url:page.url()};
 (diagnostics.age_decisions??=[]);
 if(decision.yes_count||!diagnostics.age_decisions.length)diagnostics.age_decisions.push(decision);
 if(decision.yes_count===1)decision.yes_visible=await yes.isVisible();
 if(decision.yes_count===1&&decision.yes_visible){await yes.click();changed=true;decision.clicked=true;}
 if(options.terms_accepted){
  const terms=page.getByRole('checkbox',{name:/terms|privacy|agree/i});
  for(let i=0;i<await terms.count();i++)if(await terms.nth(i).isVisible()&&!await terms.nth(i).isChecked()){await terms.nth(i).check();changed=true;}
 }
 const enter=page.getByRole('button',{name:/^(?:enter site|enter|continue|confirm age|yes,? i am 21.*)$/i});
 if(await enter.count()===1&&await enter.isVisible()&&await enter.isEnabled()){await enter.click();changed=true;}
 if(changed){
  // A consent form can reload the document; later steps must not run against a detaching frame.
  await page.waitForLoadState('load',{timeout:8000}).catch(()=>{});
  await page.waitForTimeout(1500);
 }
 return {changed};
}
// Drive an infinite-scroll or "load more" menu the way a visitor would, until it stops growing.
// A storefront's landing view is often "Featured". Open the unfiltered full list when the page offers one visible entry.
const detached=error=>/detached|Execution context was destroyed|Target (?:page|closed)/i.test(error.message);
async function retried(operation,attempts=3){
 for(let attempt=1;;attempt++){
  try{return await operation();}
  catch(error){if(attempt>=attempts||!detached(error))throw error;await new Promise(resolve=>setTimeout(resolve,500));}
 }
}
async function openAllProducts(page,captures){
 // Activated from inside the page (open shadow roots included): the control may sit in an overflowing carousel or
 // behind a fixed bar, where a pointer click is not actionable although the element is a normal visible button.
 const before=page.url(),seenBefore=captures?captures.length:0;
 const clicked=await retried(()=>page.evaluate(()=>{
  const roots=[document];for(let i=0;i<roots.length;i++)for(const node of roots[i].querySelectorAll('*'))if(node.shadowRoot)roots.push(node.shadowRoot);
  const label=node=>((node.getAttribute('aria-label')||node.textContent||'').replace(/\s+/g,' ').trim());
  const controls=roots.flatMap(root=>[...root.querySelectorAll('button,a[href],[role="tab"],[role="button"],[role="link"]')]).filter(node=>node.getClientRects().length);
  const priorities=[/^all products(?:, (?:un)?selected)?$/i,/^(?:shop all products|shop all|all items|view all products|see all products)$/i];
  for(const pattern of priorities){
   const control=controls.find(node=>pattern.test(label(node)));
   if(control){control.scrollIntoView({block:'center',inline:'center'});control.click();return {label:label(control).slice(0,60),tag:control.tagName};}
  }
  return null;
 }));
 if(!clicked)return {opened:false};
 await page.waitForLoadState('networkidle',{timeout:5000}).catch(()=>{});
 if(captures)await waitForCapture(page,captures,seenBefore,3000);
 await page.waitForTimeout(800);
 // A site-navigation link ("Shop All" in a header) is not the menu's own control. If it left the menu area and
 // nothing new loaded, go back instead of collecting from an unrelated page.
 const here=new URL(page.url()),was=new URL(before);
 if(page.url()!==before&&(!captures||captures.length===seenBefore)&&!(here.origin===was.origin&&here.pathname.startsWith(was.pathname.replace(/\/$/,'')))){
  await page.goBack({waitUntil:'domcontentloaded',timeout:15000}).catch(()=>{});
  await page.waitForTimeout(500);
  return {opened:false,reverted:true,label:clicked.label,left:page.url()!==before?page.url():before};
 }
 return {opened:true,method:'in_page_click',label:clicked.label,tag:clicked.tag,url_before:before,url:page.url(),url_changed:page.url()!==before};
}
// A visible "load more" style button, found inside open shadow roots. Names vary ("Load more", "All products View more").
async function clickMore(page){
 return page.evaluate(()=>{
  const roots=[document];for(let i=0;i<roots.length;i++)for(const node of roots[i].querySelectorAll('*'))if(node.shadowRoot)roots.push(node.shadowRoot);
  const pattern=/(?:load|show|view|see)\s+more/i;
  const candidates=roots.flatMap(root=>[...root.querySelectorAll('button')]).filter(node=>node.getClientRects().length&&!node.disabled&&
   pattern.test((node.getAttribute('aria-label')||'')+' '+(node.textContent||'')));
  const control=candidates[candidates.length-1];
  if(!control)return false;
  control.scrollIntoView({block:'center'});control.click();return true;
 });
}
// Observed read-only JSON queries (GET) whose response says there are more pages of the same query.
const pagedQueries=[],replayed=new Set();
// The storefront's own product-search POSTs (GapCommerce). Kept so the page's request can be replayed from the page.
const gapTemplates=[];
function noteIfPaged(url,headers,text){
 if(pagedQueries.length>200||text.length>4e6)return;
 let value;try{value=JSON.parse(text);}catch{return;}
 const queue=[[value,0]];
 while(queue.length){
  const [node,depth]=queue.shift();
  if(!node||typeof node!=='object'||depth>5)continue;
  if(Number.isInteger(node.totalPages)&&node.totalPages>1){pagedQueries.push({url,headers,pages:node.totalPages,total:Number.isInteger(node.totalCount)?node.totalCount:null});return;}
  for(const child of Object.values(node))if(child&&typeof child==='object')queue.push([child,depth+1]);
 }
}
// Replay each paged query with the next page numbers, from inside the page, so the same cookies and headers apply.
async function replayPagination(page,captures,deadline,sample=0){
 const summary={queries:0,fetched:0,errors:0};
 const parsed=pagedQueries.map(record=>{
  try{
   const target=new URL(record.url),raw=target.searchParams.get('variables');
   const variables=raw?JSON.parse(raw):null;
   if(!variables||!Number.isInteger(variables.page))return null;
   const filter=variables.productsFilter||{};
   // Anything beyond context/presentation keys narrows the result set (staffPicks, isOnSpecial, brand, ids, categories...).
   const benign=/^(?:dispensaryId|pricingType|strainTypes|subcategories|Status|types|useCache|isDefaultSort|sortBy|sortDirection|bypassOnlineThresholds|ignoreQuantityThresholds|isKioskMenu|removeProductsBelowOptionThresholds|platformType|preOrderType)$/;
   const narrowed=Object.keys(filter).some(key=>!benign.test(key)&&filter[key]&&!(Array.isArray(filter[key])&&!filter[key].length))||['types','strainTypes','subcategories'].some(key=>Array.isArray(filter[key])&&filter[key].length);
   // Id-list queries (carousels) cannot be paged by number; Dutchie category queries carry an empty productIds list.
   return {...record,target,variables,whole:!narrowed,hasIds:Array.isArray(filter.productIds)?filter.productIds.length>0:'productIds' in filter&&filter.productIds!=null};
  }catch{return null;}
 }).filter(Boolean).filter(record=>!record.hasIds);
 // A whole-catalog query makes per-category replays redundant.
 const wanted=parsed.some(record=>record.whole)?parsed.filter(record=>record.whole):parsed;
 summary.whole=parsed.some(record=>record.whole);
 for(const record of wanted){
  summary.queries++;
  // Numbered pages under a popularity sort drift when ranks tie (Cloud9: 1456 distinct of 1458 across 4 pages of 100,
  // the platform's page cap). A Dutchie product filter is re-read under a name sort from page 0, which pages stably.
  // Category queries name no sortBy at all (the storefront's default is popularity), so an absent sort is not a name sort.
  const filter=record.variables.productsFilter;
  const stable=!sample&&filter&&typeof filter==='object'&&filter.sortBy!=='name';
  const variables=stable?{...record.variables,productsFilter:{...filter,sortBy:'name',sortDirection:1,isDefaultSort:false}}:record.variables;
  if(stable)summary.stable_sort=(summary.stable_sort||0)+1;
  for(let next=stable?0:record.variables.page+1;next<record.pages&&(!sample||next-record.variables.page<sample)&&Date.now()<deadline&&summary.fetched<250;next++){
   const target=new URL(record.target.href);
   target.searchParams.set('variables',JSON.stringify({...variables,page:next}));
   if(replayed.has(target.href))continue;replayed.add(target.href);
   const seen=captures.length;
   const status=await retried(()=>page.evaluate(async ({url,headers})=>{
    try{const response=await fetch(url,{headers,credentials:new URL(url).origin===location.origin?'include':'same-origin'});await response.arrayBuffer();return response.status;}catch{return 0;}
   },{url:target.href,headers:record.headers}));
   if(status===200){summary.fetched++;await waitForCapture(page,captures,seen,4000);}else summary.errors++;
  }
 }
 return summary;
}
// REST listings that return a full first page of `limit` rows. Which parameter continues them is not declared, so it is
// learned: the first candidate whose response differs from page one wins and is reused for the same path.
const limitQueries=[],limitKeys=/^(?:limit|per_?page|page_?size|take|count)$/i;
function noteIfLimited(url,headers,text){
 if(limitQueries.length>100||text.length>4e6)return;
 let target,value;try{target=new URL(url);value=JSON.parse(text);}catch{return;}
 const entry=[...target.searchParams].find(([key,number])=>limitKeys.test(key)&&/^\d+$/.test(number)&&Number(number)>1);
 if(!entry||[...target.searchParams.keys()].some(key=>/^(?:offset|skip|start|page|cursor|after)$/i.test(key)))return;
 const rows=[];const queue=[[value,0]];
 while(queue.length){const [node,depth]=queue.shift();if(Array.isArray(node)){if(node.length&&typeof node[0]==='object')rows.push(node);continue;}
  if(node&&typeof node==='object'&&depth<4)for(const child of Object.values(node))queue.push([child,depth+1]);}
 const full=rows.find(array=>array.length===Number(entry[1]));
 if(full)limitQueries.push({url,headers,key:entry[0],limit:Number(entry[1]),first:JSON.stringify(full[0]).slice(0,300)});
}
async function replayOffsets(page,captures,deadline,sample=0){
 const summary={queries:0,fetched:0,errors:0,learned:{}};
 const attempt=(url,headers)=>retried(()=>page.evaluate(async ({url,headers})=>{
  try{
   const response=await fetch(url,{headers,credentials:new URL(url).origin===location.origin?'include':'same-origin'});const text=await response.text();let value=null;try{value=JSON.parse(text);}catch{}
   let first=null,length=0;const queue=[[value,0]];
   while(queue.length){const [node,depth]=queue.shift();if(Array.isArray(node)){if(node.length&&typeof node[0]==='object'){length=node.length;first=JSON.stringify(node[0]).slice(0,300);break;}continue;}
    if(node&&typeof node==='object'&&depth<4)for(const child of Object.values(node))queue.push([child,depth+1]);}
   return {status:response.status,length,first};
  }catch{return {status:0,length:0,first:null};}
 },{url,headers}));
 const withParameter=(url,name,value)=>{const target=new URL(url);target.searchParams.set(name,String(value));return target.href;};
 for(const query of limitQueries.splice(0)){
  if(Date.now()>deadline)break;summary.queries++;
  const path=new URL(query.url).pathname;
  const candidates=summary.learned[path]?[summary.learned[path]]:['offset','skip','start','page'];
  let chosen=null;
  for(const name of candidates){
   const probe=await attempt(withParameter(query.url,name,name==='page'?1:query.limit),query.headers);
   if(probe.status===200&&probe.length>0&&probe.first!==query.first){chosen=name;summary.fetched++;summary.learned[path]=name;
    let step=2,last=probe;
    while(last.length===query.limit&&step<=(sample||59)&&Date.now()<deadline&&summary.fetched<250){
     const seen=captures.length;
     last=await attempt(withParameter(query.url,name,name==='page'?step:query.limit*step),query.headers);
     if(last.status!==200||!last.length)break;summary.fetched++;step++;await waitForCapture(page,captures,seen,3000);
    }
    break;}
   if(probe.status!==200)summary.errors++;
  }
 }
 return summary;
}
// Replays the storefront's own product search from inside the page for one branch: the page's request with its collapse
// removed, 100 variants per request, sorted by id in both directions so two traversals can reconcile to the hit total.
// Every response is captured like any other page response, so the extractor reads it back from evidence.
async function replayGapSearch(page,captures,entity,deadline){
 const summary={templates:0,fetched:0,errors:0,sorts:[]};
 // The catalog query is the one whose filters are only the storefront's base filters; category and promotion queries narrow it.
 const baseClause=/^(?:customMinPrice|isAboveThreshold|isHideFromMenu)$/;
 const isCatalogQuery=value=>{try{const body=JSON.parse(value.body);const must=body.query&&body.query.bool&&body.query.bool.must;return Array.isArray(must)&&must.every(clause=>JSON.stringify(clause).split('"').some(word=>baseClause.test(word)))&&!value.body.includes('"_source":false');}catch{return false;}};
 const template=[...gapTemplates].reverse().find(value=>value.entity===entity&&value.body.includes('"collapse"')&&isCatalogQuery(value));
 if(!template)return summary;
 let base;try{base=JSON.parse(template.body);}catch{return summary;}
 delete base.collapse;delete base.aggs;delete base.aggregations;summary.templates=1;
 for(const direction of ['asc','desc']){
  const sort=[{_id:direction}];let total=null;
  for(let from=0;from<10000&&Date.now()<deadline;from+=100){
   const body={...base,from,size:100,sort};
   const seen=captures.length;
   const result=await retried(()=>page.evaluate(async ({url,headers,body})=>{
    try{
     const response=await fetch(url,{method:'POST',headers,body:JSON.stringify(body)});
     const value=await response.json().catch(()=>null);
     return {status:response.status,total:value&&value.hits&&value.hits.total?value.hits.total.value:null,hits:value&&value.hits?value.hits.hits.length:0};
    }catch(error){return {status:0,total:null,hits:0,error:String(error&&error.message||error).slice(0,200)};}
   },{url:template.url,headers:template.headers,body}));
   if(result.status!==200||!Number.isInteger(result.total)){summary.errors++;summary.error=result.error||('status '+result.status);break;}
   summary.fetched++;
   await waitForCapture(page,captures,seen,8000);
   if(total===null)total=result.total;
   if(result.total!==total){summary.errors++;break;}
   if(from+100>=total||!result.hits)break;
  }
  summary.sorts.push(direction);
 }
 return summary;
}
// Numbered-page pagination ("Next"), as used by storefronts that load one category page at a time.
async function clickNext(page){
 return page.evaluate(()=>{
  const roots=[document];for(let i=0;i<roots.length;i++)for(const node of roots[i].querySelectorAll('*'))if(node.shadowRoot)roots.push(node.shadowRoot);
  const label=node=>((node.getAttribute('aria-label')||node.textContent||'').replace(/\s+/g,' ').trim());
  const candidates=roots.flatMap(root=>[...root.querySelectorAll('button,a[href],[role="button"]')]).filter(node=>node.getClientRects().length&&
   /^(?:go to )?next(?: page)?$/i.test(label(node))&&!node.disabled&&node.getAttribute('aria-disabled')!=='true');
  // Prefer an explicit page control over a carousel "Next".
  const control=candidates.find(node=>/page/i.test(node.getAttribute('aria-label')||''))||candidates.pop();
  if(!control)return false;
  control.scrollIntoView({block:'center'});control.click();return true;
 });
}
async function waitForCapture(page,captures,seen,timeout){
 const start=Date.now();
 while(captures.length===seen&&Date.now()-start<timeout)await page.waitForTimeout(150);
 await page.waitForTimeout(150);
 return captures.length>seen;
}
// A response body is read after its headers arrive, so navigating first can strand it ("navigated away from"): the
// category's products then never reach the extractor and its total silently drops out. Let pending reads finish first.
async function settleCaptures(captures,timeout=8000){
 await Promise.race([Promise.allSettled(captures),new Promise(resolve=>setTimeout(resolve,timeout))]);
}
// Visit each category page the storefront links to and page through it. Union and totals are reconciled by the extractor.
async function exploreCategories(page,captures,deadline,{visitOnly=false,sample=0}={}){
 const links=await retried(()=>page.evaluate(()=>{
  const roots=[document];for(let i=0;i<roots.length;i++)for(const node of roots[i].querySelectorAll('*'))if(node.shadowRoot)roots.push(node.shadowRoot);
  const found=[];
  for(const anchor of roots.flatMap(root=>[...root.querySelectorAll('a[href]')])){
   let target;try{target=new URL(anchor.href,location.href);}catch{continue;}
   if(target.origin!==location.origin||!/\/(?:products|category|categories|collections)\/[^/?#]+\/?$/i.test(target.pathname))continue;
   found.push(target.origin+target.pathname);
  }
  return [...new Set(found)];
 }));
 const summary={categories:links.length,pages:0,visited:[]};
 for(const link of links.slice(0,sample?10:30)){
  if(Date.now()>deadline){summary.out_of_time=true;break;}
  await settleCaptures(captures);
  let seen=captures.length,captured=false,stopped=false;
  // A category that never loads or whose products never arrive is retried once. If it still yields nothing it is recorded
  // as uncaptured: its total must not drop out of the reconciled category sum silently.
  for(let attempt=0;attempt<2&&!captured;attempt++){
   const navigation=await page.goto(link,{waitUntil:'domcontentloaded',timeout:30000}).then(()=>null,error=>error.message.slice(0,120));
   if(navigation||page.url().startsWith('chrome-error:')){
    (summary.navigation_errors??=[]).push({link:link.slice(-60),error:navigation||'error page'});
    if(page.url().startsWith('chrome-error:')){summary.stopped='Browser error page; remaining categories skipped';stopped=true;break;}
    seen=captures.length;continue;
   }
   await waitForCapture(page,captures,seen,8000);
   // Pagination controls render after the first page of products does.
   await page.waitForTimeout(2500);
   await settleCaptures(captures);
   if(captures.length>seen)captured=true;
   else seen=captures.length;
  }
  if(stopped)break;
  if(!captured){summary.visited.push({link:link.slice(-60),pages:0,captured:false});continue;}
  let pages=0,stale=0;
  for(let n=0;n<(sample?sample-1:80)&&Date.now()<deadline&&!visitOnly;n++){
   const before=captures.length;
   let advanced=await retried(()=>clickNext(page));
   // The pager mounts after the first page of products; give a slow category up to ~9 s to show one.
   for(let wait=0;!advanced&&n===0&&wait<6;wait++){await page.waitForTimeout(1500);advanced=await retried(()=>clickNext(page));}
   if(!advanced)break;
   // Responses queue behind earlier evidence writes, so growth can lag a click by many seconds; stop only after two silent clicks.
   if(await waitForCapture(page,captures,before,15000)){stale=0;pages++;summary.pages++;}
   else if(++stale>=2)break;
  }
  summary.visited.push({link:link.slice(-60),pages,captured});
 }
 return summary;
}
async function scrollMenu(page,captures,options){
 let entry=await retried(()=>openAllProducts(page,captures));
 // sample_pages (troubleshooting only): N pages per category/query, a short scroll budget, no unbounded load-more.
 const sample=Math.max(0,Math.floor(Number(options.sample_pages)||0));
 const limit=sample?12:Math.min(200,Math.max(1,Number(options.scroll_max_steps)||60)),started=Date.now(),budget=sample?25000:Math.min(300000,Number(options.scroll_budget_ms)||200000);
 let steps=0,clicks=0,lastHeight=0,lastCaptures=captures.length,idle=0;const trace=[];
 // Names vary ("Load more", "All products View more"); a read-only pagination control either way.
 for(let round=0;round<2;round++){
  idle=0;
  while(steps<limit&&idle<4&&Date.now()-started<budget){
   steps++;
   trace.push({step:steps,y:await retried(()=>page.evaluate(()=>Math.round(scrollY))),h:lastHeight});
   if((!sample||clicks<sample-1)&&await retried(()=>clickMore(page))){
    clicks++;
    // Tracking beacons keep the network busy forever; wait for the next response to land instead of for idle.
    const seen=captures.length,waitStart=Date.now();
    while(captures.length===seen&&Date.now()-waitStart<2500)await page.waitForTimeout(150);
    await page.waitForTimeout(200);
    // A click that loads nothing new (button left over after the list ended) counts toward stopping.
    if(captures.length>seen){idle=0;lastCaptures=captures.length;continue;}
    idle++;continue;
   }
   await page.mouse.wheel(0,Math.round(await retried(()=>page.evaluate(()=>innerHeight))*0.9));
   await page.waitForLoadState('networkidle',{timeout:1500}).catch(()=>{});
   await page.waitForTimeout(300);
   const height=await retried(()=>page.evaluate(()=>Math.max(document.body.scrollHeight,document.documentElement.scrollHeight)));
   const grew=height>lastHeight||captures.length>lastCaptures;
   lastHeight=height;lastCaptures=captures.length;idle=grew?0:idle+1;
  }
  // A featured landing view usually ends with a "Shop all products" entry; open it once and keep scrolling.
  if(entry.opened||round===1)break;
  entry=await retried(()=>openAllProducts(page,captures));
  if(!entry.opened)break;
 }
 let replay=null,explore=null,offsets=null;
 if(clicks===0&&options.replay_pagination!==false){
  replay=await replayPagination(page,captures,started+budget,sample);
  // Without a whole-menu query the categories must each be seen once so their own paged queries can be replayed.
  if(!replay.whole&&options.explore_categories!==false){
   // Category pages page by id lists that cannot be replayed by number, so step through them with the pager as well.
   explore=await exploreCategories(page,captures,started+budget,{sample});
   // Exploring categories can use the whole scroll budget; replaying their pages is a few cheap GETs, so it keeps a grace window.
   const more=await replayPagination(page,captures,Math.max(started+budget,Date.now()+(sample?10000:60000)),sample);
   replay={queries:replay.queries+more.queries,fetched:replay.fetched+more.fetched,errors:replay.errors+more.errors,whole:more.whole,second_pass:true};
  }
 }
 if(clicks===0&&options.replay_pagination!==false)offsets=await replayOffsets(page,captures,started+budget,sample);
 if(clicks===0&&!(replay&&replay.fetched)&&!(offsets&&offsets.fetched)&&!explore&&options.explore_categories!==false)explore=await exploreCategories(page,captures,started+budget,{sample});
 return {entry,replay,offsets,explore,trace:trace.slice(-40),steps,clicks,idle,height:lastHeight,ms:Date.now()-started,hit_limit:steps>=limit};
}
// A large menu's serialized DOM can exceed the response limit through presentation markup alone (inline SVG, styles,
// srcset, data URIs, bundles). Drop that markup, keep content attributes and any script that carries data.
function reduceMarkup(html){
 const keep=/ld\+json|application\/json|__NEXT_DATA__|__sw_qc|initialSearchResponse|__next_f|data-terpscout/;
 return html
  .replace(/<!--[\s\S]*?-->/g,'')
  .replace(/<svg\b[\s\S]*?<\/svg>/gi,'')
  .replace(/<style\b[\s\S]*?<\/style>/gi,'')
  .replace(/<noscript\b[\s\S]*?<\/noscript>/gi,'')
  .replace(/<script\b[\s\S]*?<\/script>/gi,match=>keep.test(match.slice(0,400))?match:'')
  .replace(/\s(?:style|srcset|sizes)="[^"]*"/gi,'')
  .replace(/\s(?:src|href|poster)="data:[^"]*"/gi,'');
}
async function run({url,options,storage_state,native_proxy}){
 const browser=await chromium.launch({headless:true,channel:process.env.TERPSCOUT_BROWSER_CHANNEL||'chrome',
  ...(native_proxy?{proxy:{server:native_proxy,bypass:'<-loopback>'}}:{}),
  args:['--force-webrtc-ip-handling-policy=disable_non_proxied_udp','--disable-background-networking','--disable-quic',...(native_proxy?['--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1']:[])]});
 try {
  // Headless Chrome announces itself as "HeadlessChrome"; some storefront plugins treat that token as a crawler.
  // An explicit, honest product token replaces it only when requested (diagnostic arm), never silently.
  let userAgent;
  if(options.user_agent_token){
   const major=browser.version().split('.')[0];
   const platform={win32:'Windows NT 10.0; Win64; x64',darwin:'Macintosh; Intel Mac OS X 10_15_7',linux:'X11; Linux x86_64'}[process.platform]||'X11; Linux x86_64';
   userAgent=`Mozilla/5.0 (${platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${major}.0.0.0 Safari/537.36 ${options.user_agent_token}`;
   diagnostics.user_agent=userAgent;
  }
  // Fixed bottom navigation bars sit below a 720px viewport; click targets must be inside the window.
  const context=await browser.newContext({viewport:{width:1280,height:1000},serviceWorkers:'block',...(userAgent?{userAgent}:{}),...(storage_state?{storageState:storage_state}:{})});
  // WebSockets are closed by default; the allow_websockets option exists for diagnostic experiments only.
  if(options.allow_websockets!==true)await context.routeWebSocket('**/*',socket=>socket.close());
  let count=0;// Paging through a whole menu (category pages, numbered pages) legitimately makes thousands of requests.
  const requestLimit=options.catalog_navigation?8000:options.await_menu&&options.scroll_menu!==false?4000:600;
  let catalogPhase=false;diagnostics.request_limit=requestLimit;diagnostics.requests=0;diagnostics.auxiliary_requests_skipped=0;
  const staticCache=new Map(),cachedRequests=new WeakSet();let cacheBytes=0;
  await context.route('**/*',async route=>{
   const req=route.request();
   if(req.headers()['next-router-prefetch']==='1'){await route.abort();return;}
   if(!/^https?:/.test(req.url())||['image','media','font'].includes(req.resourceType())){await route.abort();return;}
   // After the requested branch is selected, maps/advertising are unrelated to
   // inventory acquisition. Repeated telemetry must not consume catalog budgets.
   const host=new URL(req.url()).hostname;
   const auxiliary=['googletagmanager.com','google-analytics.com','analytics.google.com','doubleclick.net','googleadservices.com','surfside.io','maps.googleapis.com','maps.gstatic.com'];
   if(catalogPhase&&auxiliary.some(domain=>host===domain||host.endsWith('.'+domain))){diagnostics.auxiliary_requests_skipped++;await route.abort();return;}
   if(options.catalog_navigation&&req.method()==='GET'&&staticCache.has(req.url())){
    cachedRequests.add(req);await route.fulfill(staticCache.get(req.url()));return;
   }
   diagnostics.requests=++count;
   if(count>requestLimit){await route.abort();return;}
   if(native_proxy){
    // POST bodies are inspected by the Python request policy (mutation / account detection); bound what crosses the pipe.
    const postData=req.method()==='POST'?(req.postData()||'').slice(0,70000):undefined;
    const validation=await request({url:req.url(),method:'VALIDATE',request_method:req.method(),post_data:postData,content_type:req.headers()['content-type']});
    if(validation.error){await route.abort();return;}
    await route.continue();return;
   }
   const headers=await req.allHeaders();
   const res=await request({url:req.url(),method:req.method(),body:req.postData(),cookie:headers.cookie||'',headers,origin:url});
   if(res.error){await route.abort();return;}
   await route.fulfill({status:res.status,headers:res.headers,body:Buffer.from(res.body,'base64')});
  });
  const page=await context.newPage();let mainStatus=200;
  diagnostics.page_errors=[];diagnostics.console_errors=[];
  const retainError=(key,message)=>{if(diagnostics[key].length<100)diagnostics[key].push(String(message).slice(0,1000));};
  page.on('pageerror',error=>retainError('page_errors',error.message));
  page.on('console',message=>{if(message.type()==='error')retainError('console_errors',message.text());});
  page.on('response',response=>{if(response.request().isNavigationRequest()&&response.frame()===page.mainFrame())mainStatus=response.status();});
  const captures=[],captureErrors=[],flightPages=[];let capturedBytes=0;
  diagnostics.capture_errors=captureErrors;diagnostics.streaming_responses_skipped=[];
  if(native_proxy)page.on('response',response=>{
   const capture=(async()=>{
    const req=response.request();
    if(cachedRequests.has(req))return;
    if(!/^https?:/.test(response.url())||['image','media','font'].includes(req.resourceType()))return;
    // Paging a whole catalog re-downloads framework bundles on every navigation; keeping each copy as evidence exhausted the
    // capture budget (Stash). Catalog documents, data and RSC responses are what the traversal needs.
    if(options.catalog_navigation&&['script','stylesheet'].includes(req.resourceType()))return;
    const responseHeaders=await response.allHeaders();
    if((responseHeaders['content-type']||'').split(';')[0].trim().toLowerCase()==='text/event-stream'){
     diagnostics.streaming_responses_skipped.push({url:response.url(),status:response.status(),reason:'Unbounded event stream; not a finite catalog response'});return;
    }
    const body=await response.body();capturedBytes+=body.length;diagnostics.captured_bytes=capturedBytes;
    if(req.method()==='POST'&&response.status()===200&&/^search-[a-z0-9]+\.gapcommerceapi\.com$/.test(new URL(response.url()).hostname)&&new URL(response.url()).pathname==='/product/search'&&gapTemplates.length<50){
     const all=await req.allHeaders();
     // Only headers a page script may set are kept; the browser drops the rest of a replay's headers anyway.
     gapTemplates.push({url:response.url(),headers:Object.fromEntries(['content-type','accept','entity-id','org-id','x-api-key'].filter(key=>all[key]).map(key=>[key,all[key]])),body:req.postData()||'',entity:all['entity-id']||''});
    }
    if(req.method()==='GET'&&response.status()===200&&(responseHeaders['content-type']||'').includes('json')){
     // Replays run inside the page and carry the request's own app headers (Cresco: the bundle's public key and the store/app ids).
     const keep=['accept','content-type','apollo-require-preflight','x-apollo-operation-name','apollographql-client-name','apollographql-client-version','x-api-key','x-client-version','store_id','ordering_app_id'],all=await req.allHeaders();
     const sent=Object.fromEntries(keep.filter(key=>all[key]).map(key=>[key,all[key]]));
     noteIfPaged(response.url(),sent,body.toString('utf8'));
     noteIfLimited(response.url(),sent,body.toString('utf8'));
    }
    if(options.catalog_navigation&&response.status()===200&&new URL(response.url()).origin===new URL(url).origin&&new URL(response.url()).pathname.startsWith('/_next/static/')&&responseHeaders['cache-control']?.includes('immutable')&&!responseHeaders['set-cookie']&&cacheBytes+body.length<32*1024*1024){
     staticCache.set(response.url(),{status:200,headers:{'content-type':responseHeaders['content-type']||'application/octet-stream'},body});cacheBytes+=body.length;
    }
    // Paged menus share the catalog budget: one Dutchie page of 100 products is ~2 MB, so 64 MB ran out mid-menu (Cloud9).
    if(body.length>25*1024*1024||capturedBytes>(options.catalog_navigation||options.await_menu&&options.scroll_menu!==false?256:64)*1024*1024)throw new Error('Browser response capture budget exceeded');
    if((await response.headerValue('content-type')||'').includes('text/x-component')){
     flightPages.push({url:response.url(),body:body.toString('utf8'),status:response.status()});
     if(flightPages.length>30)flightPages.shift();
    }
    await request({method:'CAPTURE',request_method:req.method(),url:response.url(),status:response.status(),post_data:req.method()==='POST'?(req.postData()||'').slice(0,8192):undefined,
      headers:await req.allHeaders(),response_headers:await response.allHeaders(),body:body.toString('base64')});
   })().catch(error=>captureErrors.push(error.message));
   captures.push(capture);
  });
  await progress('initial_navigation');
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:35000});
  await page.waitForTimeout(1500);
  await progress('age_confirmation');
  await confirmAge(page,options);
  await progress('shopping_context');
  const contextTransitions=[];
  const locationDecisions=[];
  diagnostics.context_transitions=contextTransitions;diagnostics.location_decisions=locationDecisions;
  let locationSelected=false;
  for(let round=0;round<3;round++){
   // A consent step can reload the page again; retry steps that interrogate the page rather than fail the render.
   const locations=locationSelected?[]:await retried(()=>selectLocation(page,options.target_store,locationDecisions));
   if(locations.length)locationSelected=true;
   const types=await retried(()=>selectMenuContext(page,options));
   contextTransitions.push(...locations,...types);
   if(!locations.length&&!types.length)break;
  }
  if(options.catalog_navigation){
   catalogPhase=true;
   for(let step=0;step<2000;step++){
    await page.waitForLoadState('networkidle',{timeout:5000}).catch(()=>{});
    await Promise.allSettled(captures.splice(0));
    if(captureErrors.some(message=>message.includes('budget exceeded')))throw new Error('Browser response capture budget exceeded');
    const current=new URL(page.url());
    const flight=[...flightPages].reverse().find(value=>{
     const target=new URL(value.url);return target.origin===current.origin&&target.pathname===current.pathname&&target.searchParams.get('page')===current.searchParams.get('page');
    });
    const links=await page.locator('a[href]').evaluateAll(nodes=>nodes.map(node=>({url:node.href,label:node.getAttribute('aria-label')||node.textContent||'',current:node.getAttribute('aria-current')})));
    const storeLabels=await page.getByRole('button',{name:/open store selector|change.*pickup location/i}).evaluateAll(nodes=>nodes.filter(node=>{
     const rect=node.getBoundingClientRect();return !node.closest('[aria-hidden=true],[inert]')&&rect.width>0&&rect.height>0&&rect.left<innerWidth&&rect.right>0&&rect.top<innerHeight&&rect.bottom>0;
    }).map(node=>node.innerText));
    const html=(await page.content())+(await page.evaluate(shadowMarkup));
    const decision=await request({method:'DOCUMENT',url:page.url(),status:flight?.status||mainStatus,html,flight:flight?.body,links,store_labels:storeLabels});
    if(decision.error)throw new Error(decision.error);
    if(decision.back){flightPages.length=0;await page.goBack({waitUntil:'domcontentloaded',timeout:35000});await confirmAge(page,options);continue;}
    if(decision.reload){flightPages.length=0;await navigateCatalog(page,page.url());await confirmAge(page,options);continue;}
    if(!decision.next_url)break;
    if(new URL(decision.next_url).origin!==current.origin)throw new Error('Catalog navigation cannot leave the retailer origin');
    const targets=await page.locator('a[href]').evaluateAll((nodes,url)=>nodes.map((node,index)=>({index,url:node.href})).filter(node=>node.url===url).map(node=>node.index),decision.next_url);
    const declaredProduct=decision.declared_product&&new URL(decision.next_url).pathname.startsWith('/product/')&&html.includes(new URL(decision.next_url).pathname);
    if(!targets.length&&!declaredProduct)throw new Error('Requested catalog page has no observed navigation link');
    flightPages.length=0;
    // Load the observed retailer document. A SPA click can only change the URL
    // while its separate search API fails, leaving the prior page's data in DOM.
    await navigateCatalog(page,decision.next_url);
    await page.waitForTimeout(250);
    await confirmAge(page,options);
    if(step===1999)throw new Error('Catalog navigation page limit reached');
   }
  }
  // Ordinary user-visible navigation/scrolling can trigger lazy product cards.
  for(let i=0;i<3;i++){await page.mouse.wheel(0,1200);await page.waitForTimeout(250);}
  if(options.gap_search){
   // The page's own search for the selected branch sets the request template; wait for it, then replay the catalog.
   const templateDeadline=Date.now()+30000;
   while(!gapTemplates.some(value=>value.entity===options.gap_entity)&&Date.now()<templateDeadline)await page.waitForTimeout(250);
   // Reported with the scroll summary: the render result carries that field to the evidence record.
   diagnostics.scroll=await replayGapSearch(page,captures,options.gap_entity,Date.now()+150000);
  }
  if(native_proxy)await page.waitForLoadState('networkidle',{timeout:5000}).catch(()=>{});
  await progress('menu_readiness');
  const menuReadiness=options.await_menu&&!options.catalog_navigation?await waitForMenu(page,options):null;
  // Page through the menu only once the storefront has rendered its first products.
  if(options.await_menu&&options.scroll_menu!==false&&!options.catalog_navigation){try{diagnostics.scroll=await scrollMenu(page,captures,options);}catch(error){diagnostics.scroll={error:error.message};}}
  const collectProducts=()=>{
   const hasProduct=value=>value&&typeof value==='object'&&(value['@type']==='Product'||Object.values(value).some(hasProduct));
   const roots=[document];for(let i=0;i<roots.length;i++)for(const node of roots[i].querySelectorAll('*'))if(node.shadowRoot)roots.push(node.shadowRoot);
   const structured=roots.flatMap(root=>[...root.querySelectorAll('script[type="application/ld+json"]')]);
   if(structured.some(script=>{try{return hasProduct(JSON.parse(script.textContent));}catch{return false;}}))return;
   const products=new Map();
   for(const a of roots.flatMap(root=>[...root.querySelectorAll('a[href]')])){
    const url=new URL(a.href,location.href);
    if(!/\/(?:products?)\/[^/]+|\/shop\/[^/]+\/[^/]+/.test(url.pathname)||/\/(?:categories|brands|collections)\//.test(url.pathname))continue;
    const card=a.closest('article,[data-product-id],[data-testid*="product-card"],[class*="product-card"],[class*="ProductCard"],[aria-label*="product card"]')||a.parentElement;
    const text=card?.innerText||'';
    const cardName=(card?.getAttribute('aria-label')||'').replace(/ product card(?:,.*)?$/i,'');
    const name=(card?.querySelector('h2,h3,h4,[data-testid*="product-name"]')?.textContent||cardName||a.textContent||'').trim();
    const amounts=value=>[...String(value||'').matchAll(/\$\s*(\d[\d,]*(?:\.\d{1,2})?)/g)].map(match=>Number(match[1].replaceAll(',',''))).filter(Number.isFinite).map(value=>value.toFixed(2));
    const prices=[...new Set(amounts(text))];
    const struck=[...new Set([...card.querySelectorAll('s,del,[class*="strikethrough"],[style*="line-through"]')].filter(node=>['S','DEL'].includes(node.tagName)||getComputedStyle(node).textDecorationLine.includes('line-through')).flatMap(node=>amounts(node.innerText)))];
    const active=prices.filter(value=>!struck.includes(value));
    if(!name||active.length!==1||prices.length>1&&struck.length!==1)continue;
    const weight=text.match(/(?:^|[\s·|(])(\d+(?:\.\d+)?|\.\d+)\s*(g|grams?|oz|ounces?)\b/i);
    const product={'@type':'Product',sku:url.href,url:url.href,name,sourceKind:'observed_visible_dom',observedText:text,
                   offers:{price:active[0],priceCurrency:'USD'}};
    if(struck.length===1&&Number(struck[0])>=Number(active[0]))product.offers.priceSpecification={price:struck[0],priceCurrency:'USD',priceType:'https://schema.org/StrikethroughPrice'};
    if(/with membership|member(?:s? only)? price|loyalty price|coupon required/i.test(text))product.offers.eligibleCustomerType='Source-declared conditional price';
    if(weight)product.weight={value:weight[1],unitText:weight[2]};
    products.set(url.href,product);
   }
   if(products.size){const script=document.createElement('script');script.type='application/ld+json';script.dataset.terpscout='dom-observations';script.textContent=JSON.stringify([...products.values()]);document.body.append(script);}
  };
  await progress('dom_collection');
  const frames=[];
  for(const frame of page.frames()){
   try{await frame.evaluate(collectProducts);if(frame!==page.mainFrame())frames.push({url:frame.url(),html:(await frame.content())+(await frame.evaluate(shadowMarkup))});}catch{/* A detached frame is not a complete source. */}
  }
  const frameHtml=frames.map(frame=>`<section data-terpscout-frame="${frame.url.replaceAll('"','&quot;')}">${frame.html}</section>`).join('');
  const screenshot=options.diagnostic_screenshot?(await page.screenshot({type:'png'})).toString('base64'):undefined;
  await progress('response_captures');
  await Promise.race([Promise.allSettled(captures),new Promise(resolve=>setTimeout(resolve,20000))]); // a response from a navigated-away page can stay pending
  let html=(await page.content())+(await page.evaluate(shadowMarkup))+frameHtml,htmlReduced=null;
  if(options.max_html_chars&&html.length>options.max_html_chars){const original=html.length;html=reduceMarkup(html);htmlReduced={from:original,to:html.length};}
  await send({type:'result',html_reduced:htmlReduced,scroll:diagnostics.scroll,screenshot,age_decisions:diagnostics.age_decisions||[],streaming_responses_skipped:diagnostics.streaming_responses_skipped,menu_readiness:menuReadiness,page_errors:diagnostics.page_errors,console_errors:diagnostics.console_errors,url:page.url(),status:mainStatus,html,requests:count,request_limit:requestLimit,request_limit_exceeded:count>requestLimit,auxiliary_requests_skipped:diagnostics.auxiliary_requests_skipped,captured_bytes:capturedBytes,navigation_retries:diagnostics.navigation_retries||[],storage_state:await context.storageState(),capture_errors:captureErrors,context_transitions:contextTransitions,location_decisions:locationDecisions});
 } finally {await browser.close();input.close();}
 process.exit(0);
}

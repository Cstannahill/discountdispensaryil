/* Read visible location choices, select one uniquely matching the requested
 * branch, then leave tenant/address verification to the ingestion pipeline. */
const normalize=value=>String(value||'').toLowerCase().replace(/\b(street|avenue|road|drive|boulevard|north|south|east|west)\b/g,word=>({street:'st',avenue:'ave',road:'rd',drive:'dr',boulevard:'blvd',north:'n',south:'s',east:'e',west:'w'}[word])).replace(/[^a-z0-9]+/g,' ').trim();
// A directional only one side writes ("12720 Western Ave" vs "12720 S Western Ave") is not a conflict; two different ones are.
function sameStreet(a,b){
 const directions=new Set(['n','s','e','w']);
 const x=a.split(' '),y=b.split(' ');
 const dx=x.find(t=>directions.has(t)),dy=y.find(t=>directions.has(t));
 if(dx&&dy&&dx!==dy)return false;
 const bare=tokens=>tokens.filter(word=>!directions.has(word)).join(' ');
 return bare(x)===bare(y);
}
function matchChoice(choices,target){
 const city=normalize(target.city),street=normalize(String(target.address||'').split(/\b(?:unit|suite|ste)\b|#/i)[0]);
 if(!city&&!street)return null;
 const contains=(text,part)=>part&&(' '+normalize(text)+' ').includes(' '+part+' ');
 const ranked=choices.map(choice=>{
  const generic=/^(?:select|choose|shop|shop now|view menu|order now|select location)$/i.test(choice.text.trim());
  const ownCity=contains(choice.text,city);
  const addressesIn=value=>normalize(value).match(/\b\d{1,6} (?:[a-z0-9]+ ){1,6}(?:st|ave|rd|dr|blvd|ln|pkwy|hwy|ct)\b/g)||[];
  const ownAddress=contains(choice.text,street)||addressesIn(choice.text).some(found=>sameStreet(found,street));
  const contextAddress=(generic||ownCity)&&(contains(choice.context,street)||addressesIn(choice.context).some(found=>sameStreet(found,street)));
  const addresses=normalize(choice.text+((generic||ownCity)?' '+choice.context:'')).match(/\b\d{1,6} (?:[a-z0-9]+ ){1,6}(?:st|ave|rd|dr|blvd|ln|pkwy|hwy|ct)\b/g)||[];
  if(street&&addresses.length&&!ownAddress&&!contextAddress)return {choice,score:0};
  const score=ownAddress||contextAddress?3:ownCity?2:generic&&contains(choice.context,city)?1:0;
  return {choice,score};
 }).filter(value=>value.score>0);
 ranked.sort((a,b)=>b.score-a.score);
 if(!ranked.length||ranked.length>1&&ranked[0].score===ranked[1].score)return null;
 return ranked[0].choice;
}
async function selectLocation(page,target,diagnostics=[]){
 if(!target)return [];
 for(const frame of page.frames()){
  const selects=frame.locator('select').filter({visible:true});
  for(let index=0;index<await selects.count();index++){
   const select=selects.nth(index);
   const label=await select.evaluate(el=>[el.getAttribute('aria-label'),el.name,el.id,...[...el.labels||[]].map(label=>label.textContent)].join(' '));
   if(!/location|store|dispensar/i.test(label))continue;
   const choices=await select.locator('option').evaluateAll(nodes=>nodes.filter(node=>!node.disabled&&node.value).map(node=>({value:node.value,text:node.textContent,context:''})));
   const match=matchChoice(choices,target);
   if(match){await select.selectOption(match.value,{timeout:3000});await page.waitForTimeout(600);return [{kind:'location_selection',store_id:target.id,selected_label:match.text,method:'select',frame_url:frame.url()}];}
  }
  const locationDialogs=()=>frame.getByRole('dialog',{name:/location|store|dispensar/i})
   .or(frame.getByRole('dialog').filter({has:frame.getByRole('heading',{name:/(?:choose|select|find).*(?:store|location|dispensary)/i})})).filter({visible:true});
  let scopes=locationDialogs();
  diagnostics.push({frame_url:frame.url(),location_dialogs:await scopes.count()});
  if(await scopes.count()===0){
   const heading=frame.getByRole('heading',{name:/(?:choose|select|find) (?:your |a |the )?(?:pickup )?(?:store|location|dispensary)/i}).filter({visible:true});
   if(await heading.count())scopes=frame.locator('body');
   else{
    const trigger=frame.getByRole('button',{name:/^(?:(?:select|choose|change) (?:your |a |the )?(?:store|location|dispensary)|open store selector(?: and purchase method)?)$/i}).filter({visible:true});
    const onscreen=await trigger.evaluateAll(nodes=>nodes.map((node,index)=>({node,index})).filter(({node})=>{
     const rect=node.getBoundingClientRect();
     return !node.closest('[aria-hidden=true],[inert]')&&rect.width>0&&rect.height>0&&rect.right>0&&rect.bottom>0&&rect.left<innerWidth&&rect.top<innerHeight;
    }).map(({index})=>index));
    diagnostics.push({frame_url:frame.url(),location_triggers:await trigger.count(),onscreen_triggers:onscreen.length});
    if(onscreen.length===1){await trigger.nth(onscreen[0]).click({timeout:3000});await page.waitForTimeout(300);scopes=locationDialogs();}
   }
  }
  // Some storefronts use an ordinary header popover rather than role=dialog.
  // Scope to the nearest heading container that actually contains choices.
  if(await scopes.count()===0){
   const heading=frame.getByRole('heading',{name:/(?:choose|select|find) (?:your |a |the )?(?:pickup )?(?:store|location|dispensary)/i}).filter({visible:true});
   if(await heading.count()===1){
    let parent=heading.locator('..');
    for(let depth=0;depth<4;depth++,parent=parent.locator('..')){
     if(await parent.locator('input[type=radio],[role=radio]').count()>0){scopes=parent;break;}
    }
   }
  }
  for(let index=0;index<await scopes.count();index++){
   const scope=scopes.nth(index),text=await scope.innerText();
   const label=await scope.getAttribute('aria-label')||'';
   if(!/location|store|dispensar/i.test(text+' '+label))continue;
   const controls=scope.locator('button,a[href],input[type=radio],[role=button],[role=radio]').filter({visible:true});
   const choices=await controls.evaluateAll(nodes=>nodes.map((node,index)=>{
    const text=node.getAttribute('aria-label')||[...node.labels||[]].map(label=>label.textContent).join(' ')||node.textContent||'';
    let parent=node.parentElement,context='';
    for(let depth=0;parent&&depth<3&&!['BODY','HTML'].includes(parent.tagName);depth++,parent=parent.parentElement){
     if(parent.getAttribute('role')==='dialog'||parent.querySelectorAll('input[type=radio],[role=radio]').length>1||parent.querySelectorAll('button,a[href],input[type=radio],[role=button],[role=radio]').length>3)break;
     context=parent.innerText||parent.textContent||context;
     if(/\b\d{1,6}\s+\S+/.test(context))break;
    }
    return {index,text,context};
   }));
   const match=matchChoice(choices,target);
   diagnostics.push({frame_url:frame.url(),choices:choices.map(choice=>({text:choice.text,context:choice.context.slice(0,350)})),selected_label:match?.text||null});
   if(!match)continue;
   const choice=controls.nth(match.index);
   if(await choice.getAttribute('type')==='radio'||await choice.getAttribute('role')==='radio')await choice.check({timeout:3000});
   else await choice.click({timeout:3000});
   if(await scope.isVisible()){
    const next=scope.getByRole('button',{name:/^(?:continue|start shopping|view menu|shop now|shop pickup)$/i}).filter({visible:true});
    if(await next.count()===1&&await next.isEnabled())await next.click({timeout:3000});
   }
   await page.waitForTimeout(600);
   return [{kind:'location_selection',store_id:target.id,selected_label:match.text,method:'visible_choice',frame_url:frame.url()}];
  }
 }
 return [];
}
module.exports={selectLocation,matchChoice};

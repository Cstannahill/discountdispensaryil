import { useMutation,useQuery,useQueryClient } from '@tanstack/react-query';
import { api } from './api';
import { Failure,Loading } from './ui';
type Options={enabled:boolean;age_confirmed:boolean;terms_accepted:boolean};
export function BrowserSettings(){
 const client=useQueryClient();
 const settings=useQuery({queryKey:['browser-settings'],queryFn:()=>api<Options>('/settings/browser')});
 const update=useMutation({mutationFn:(value:Options)=>api<Options>('/settings/browser',{method:'PATCH',body:JSON.stringify(value)}),onSuccess:value=>client.setQueryData(['browser-settings'],value)});
 if(settings.isPending)return <Loading/>;
 if(settings.isError)return <Failure error={settings.error} retry={()=>void settings.refetch()}/>;
 const value=settings.data;
 return <section className="glass-card rounded-2xl p-4 space-y-3"><h2 className="text-sm font-bold">Website discovery & browser fallback</h2><p className="text-xs text-slate-400">Unrecognized retailers enter public website search. Menu pages use platform detection, structured HTML extraction, then JavaScript rendering. Unspecified licenses use recreational. Partial observations remain inspectable.</p>
 <label className="flex gap-2 text-xs"><input type="checkbox" checked={value.enabled} disabled={update.isPending} onChange={e=>update.mutate({...value,enabled:e.target.checked})}/>Enable JavaScript browser fallback (requires installed Chrome and Node.js)</label>
 <label className="flex gap-2 text-xs"><input type="checkbox" checked={value.age_confirmed} disabled={update.isPending} onChange={e=>update.mutate({...value,age_confirmed:e.target.checked})}/>I confirm I am 21 or older and authorize ordinary retailer age-confirmation clicks</label>
 <label className="flex gap-2 text-xs"><input type="checkbox" checked={value.terms_accepted} disabled={update.isPending} onChange={e=>update.mutate({...value,terms_accepted:e.target.checked})}/>Allow the browser to accept retailer terms/privacy prompts for menu access</label>
 {update.isError&&<Failure error={update.error}/>}<p className="text-[11px] text-slate-400">Preferences persist. Browser sessions are stored locally by website. A failed or partial scrape preserves the last complete catalog.</p></section>;
}

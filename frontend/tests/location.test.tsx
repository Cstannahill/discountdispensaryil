import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import App from '../src/App';
it('uses persisted active region instead of the first region', async()=>{
  window.history.replaceState({},'', '/?view=sync');
  vi.stubGlobal('fetch', vi.fn(async (url:string)=>({ok:true,json:async()=>url.endsWith('/regions')?{active_region_id:2,items:[{id:1,label:'Old region',latitude:40,longitude:-90,radius_miles:25},{id:2,label:'Selected origin',latitude:41,longitude:-89,radius_miles:50}]}:url.includes('/coverage')?{region:null,source:{status:'never'},counts:{known_stores:0,menu_endpoints:0,fresh_menus:0,stale_menus:0,failed_menus:0,unsupported_menus:0,unresolved_menus:0,products:0,eligible_offers:0},territory:{supported_jurisdictions:[],unsupported_jurisdictions:[],status:'unknown'},limitations:[],endpoints:[]}:url.includes('/settings/schedule')?{frequency_per_day:4,timezone:'America/Chicago',slots:['00:00','06:00','12:00','18:00'],next_run_at:null}:url.includes('/health')?{status:'ok',scheduler_running:true}:{items:[],total:0,page:1,page_size:25}})));
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><App/></QueryClientProvider>);
  expect(await screen.findByText(/Selected origin/)).toBeInTheDocument();
  expect(screen.queryByText(/Old region/)).not.toBeInTheDocument();
});
it('creates a selected region from geocode metadata without sending server-forbidden evidence fields', async()=>{
  window.history.replaceState({},'', '/?view=sync');
  const region={id:'new',label:'Rutland, IL 61358',latitude:40.9844,longitude:-89.0388,radius_miles:50,precision:'approximate_zip_centroid'};
  let created=false;
  vi.stubGlobal('fetch',vi.fn(async(url:string,init?:RequestInit)=>{
    const body=init?.body?JSON.parse(String(init.body)):null;
    if(url.endsWith('/locations/resolve'))return {ok:true,json:async()=>({...region,id:undefined,raw:{places:[]},evidence_id:'hash',cached_at:'2026-10-17'})};
    if(url.endsWith('/regions')&&init?.method==='POST'){
      if(Object.keys(body).some(k=>!['latitude','longitude','label','radius_miles','precision','source_url'].includes(k)))return {ok:false,status:422,json:async()=>({detail:{message:'Unexpected region fields'}})};
      created=true;return {ok:true,json:async()=>region};
    }
    const value=url.endsWith('/regions')?{active_region_id:created?'new':null,items:created?[region]:[]}:url.includes('/coverage')?{region,source:{status:'not_imported'},counts:{known_stores:0,menu_endpoints:0,fresh_menus:0,stale_menus:0,failed_menus:0,unsupported_menus:0,unresolved_menus:0,products:0,eligible_offers:0},territory:{supported_jurisdictions:['IL'],unsupported_jurisdictions:[],status:'unknown'},limitations:[],endpoints:[]}:url.includes('/settings/schedule')?{frequency_per_day:4,timezone:'America/Chicago',slots:[],next_run_at:null}:{items:[],total:0};
    return {ok:true,json:async()=>value};
  }));
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><App/></QueryClientProvider>);
  await userEvent.setup().click(await screen.findByRole('button',{name:'Resolve 61358 · 50 miles'}));
  expect(await screen.findByText(/Rutland, IL 61358/)).toBeInTheDocument();
  expect(screen.queryByText('Unexpected region fields')).not.toBeInTheDocument();
});

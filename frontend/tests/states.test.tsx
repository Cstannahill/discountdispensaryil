import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CoverageSummary } from '../src/coverage';
import { DealsColumn } from '../src/deals';
import { useWatchlist, Watchlist } from '../src/watchlist';
import type { Coverage, Offer } from '../src/api';
const coverage: Coverage = { region: null, source: {status:'stale',error:'Registry fetch timed out'},counts:{known_stores:8,menu_endpoints:10,fresh_menus:2,stale_menus:1,failed_menus:3,unsupported_menus:2,unresolved_menus:2,products:30,eligible_offers:11},territory:{supported_jurisdictions:['Illinois'],unsupported_jurisdictions:['Iowa'],status:'partial'},limitations:['Operating status needs corroboration'],endpoints:[{id:1,store_name:'Store A',provider:'unknown',license_type:'recreational',status:'failed',error:'Access challenge'}] };
const offer = {id:'variant-1',endpoint_id:4,name:'Observed flower',store_name:'Store A',effective_price:'20.00',price_per_gram:'5.714285',freshness:'fresh'} as Offer;
function renderQuery(node: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{node}</QueryClientProvider>); }
describe('real data boundary', () => {
  it('groups duplicate failing targets by physical store while keeping license channels visible', () => {
    render(<CoverageSummary data={{...coverage,endpoints:[
      {...coverage.endpoints[0],id:'a',store_id:'physical',error:'Page fetch failed'},
      {...coverage.endpoints[0],id:'b',store_id:'physical',error:'Page fetch failed'},
      {...coverage.endpoints[0],id:'c',store_id:'physical',license_type:'medicinal',error:'Medical menu failed'},
    ]}}/>);
    expect(screen.getAllByText('Store A')).toHaveLength(1);
    expect(screen.getByText(/2 targets/)).toBeInTheDocument();
    expect(screen.getByText(/medicinal · unknown/)).toBeInTheDocument();
    expect(screen.getAllByText('Page fetch failed')).toHaveLength(1);
  });
  it('renders persisted extraction messages in coverage without serialized JSON', () => {
    render(<CoverageSummary data={{...coverage,endpoints:[{...coverage.endpoints[0],error:'{"code":"incomplete_generic_menu","message":"Browser rendering did not finish"}; missing_traversal_evidence'}]}}/>);
    expect(screen.getByText(/Browser rendering did not finish · Full-menu traversal has not been verified/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('"code"');
  });
  it('keeps failed imports and unsupported territory beside partial coverage', () => {
    render(<CoverageSummary data={coverage}/>);
    expect(screen.getByText(/2 \/ 10/)).toBeInTheDocument();
    expect(screen.getByText(/3 failed/)).toBeInTheDocument();
    expect(screen.getByText(/Iowa/)).toBeInTheDocument();
    expect(screen.getByText(/Registry fetch timed out/)).toBeInTheDocument();
    expect(screen.getByText(/Access challenge/)).toBeInTheDocument();
  });
  it('shows the server failure and retry instead of a sample deal', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false,status:503,json:async()=>({detail:{code:'upstream_unavailable',message:'Provider temporarily unavailable'}})}));
    renderQuery(<DealsColumn category="flower" query="" regionId={1} license="recreational" stale={false} onSave={()=>{}}/>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Provider temporarily unavailable');
    expect(screen.getByRole('button',{name:/retry/i})).toBeInTheDocument();
    expect(screen.queryByText('$5.71')).not.toBeInTheDocument();
  });
  it('distinguishes no eligible offers from a failed request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[],total:0,page:1,page_size:20,data_version:'v1'})}));
    renderQuery(<DealsColumn category="flower" query="" regionId={1} license="recreational" stale={false} onSave={()=>{}}/>);
    expect(await screen.findByText(/No comparable offers/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('persists saved stable identities after remount and removes them', async () => {
    function Harness(){ const list=useWatchlist(); return <><button onClick={()=>list.toggle(offer)}>Toggle</button><span>{list.items.map(o=>o.name).join(',')}</span></>; }
    const user=userEvent.setup();
    const first=render(<Harness/>);
    await user.click(screen.getByRole('button'));
    await waitFor(()=>expect(screen.getByText('Observed flower')).toBeInTheDocument());
    first.unmount(); render(<Harness/>);
    expect(screen.getByText('Observed flower')).toBeInTheDocument();
    await user.click(screen.getByRole('button'));
    expect(screen.queryByText('Observed flower')).not.toBeInTheDocument();
  });
  it('rechecks a saved offer by identity beyond the first menu page', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url:string) => ({ok:true,json:async()=>({items:url.includes('offer_id=variant-1')?[{...offer,effective_price:'17.00',price_per_gram:'4.86',available:true,last_seen_at:'2026-10-17T08:00:00Z'}]:[],total:1,page:1,page_size:1,menu:{id:4},snapshot:null})})));
    renderQuery(<Watchlist items={[offer]} onRemove={()=>{}}/>);
    expect(await screen.findByText(/\$17.00/)).toBeInTheDocument();
    expect(screen.queryByText(/not verified in the loaded menu page/)).not.toBeInTheDocument();
  });
  it('shows backend last_error beside a retained fresh menu', () => {
    render(<CoverageSummary data={{...coverage,endpoints:[{id:1,store_name:'Retained store',provider:'blaze',license_type:'recreational',status:'failed',last_error:'Latest page fetch failed'}]}}/>);
    expect(screen.getByText(/Latest page fetch failed/)).toBeInTheDocument();
  });
});

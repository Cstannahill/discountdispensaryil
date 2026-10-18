import {render,screen,waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {describe,it,expect,vi} from 'vitest';
import {StoreCard} from '../src/directory';
import type {Dispensary} from '../src/api';
describe('targeted store retry',()=>{
 it('retries one store and shows its actual discovery reason',async()=>{
  const calls:RequestInit[]=[];
  vi.stubGlobal('fetch',vi.fn(async(_url:string,init:RequestInit)=>{calls.push(init);return {ok:true,json:async()=>({id:'run',status:'queued'})};}));
  const shop={id:'store-id',name:'New retailer',address:'1 Main St',city:'Rutland',state:'IL',distance_miles:1,endpoints:[],product_count:0,menu_status:'unresolved',resolution:{message:'Website search found a candidate; menu extraction pending'}} as unknown as Dispensary;
  render(<QueryClientProvider client={new QueryClient()}><StoreCard store={shop} license="recreational" regionId="region-id" inspect={()=>{}}/></QueryClientProvider>);
  expect(screen.getByText(/Website search found/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button',{name:/Retry discovery/i}));
  await waitFor(()=>expect(calls).toHaveLength(1));
  expect(JSON.parse(String(calls[0].body))).toMatchObject({region_id:'region-id',store_ids:['store-id'],discover:false});
  expect(await screen.findByText(/Retry queued/)).toBeInTheDocument();
 });
});

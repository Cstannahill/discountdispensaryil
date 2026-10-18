import { render,screen,waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient,QueryClientProvider } from '@tanstack/react-query';
import { describe,it,expect,vi } from 'vitest';
import { BrowserSettings } from '../src/browser-settings';

describe('ordinary browser settings',()=>{
 it('does not assert age or accept terms until selected by the user',async()=>{
  const requests:RequestInit[]=[];
  vi.stubGlobal('fetch',vi.fn(async(_url:string,init?:RequestInit)=>{
   if(init?.method==='PATCH')requests.push(init);
   return {ok:true,json:async()=>init?.body?JSON.parse(String(init.body)):{enabled:true,age_confirmed:false,terms_accepted:false}};
  }));
  render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><BrowserSettings/></QueryClientProvider>);
  const age=await screen.findByRole('checkbox',{name:/I confirm/i});
  expect(age).not.toBeChecked();expect(requests).toHaveLength(0);
  await userEvent.click(age);
  await waitFor(()=>expect(requests).toHaveLength(1));
  expect(JSON.parse(String(requests[0].body))).toMatchObject({age_confirmed:true,terms_accepted:false});
 });
});

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { useDataRefresh } from '../src/data-refresh';

it('refreshes cached directory and catalog views when server revision changes', async()=>{
  const client=new QueryClient();
  const directory=vi.fn(async()=>({items:['Snap Canna - Pontiac']}));
  await client.fetchQuery({queryKey:['stores','region'],queryFn:directory});
  const wrapper=({children}:{children:React.ReactNode})=><QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const hook=renderHook(({revision})=>useDataRefresh(revision),{initialProps:{revision:'before'},wrapper});
  hook.rerender({revision:'after'});
  await waitFor(()=>expect(client.getQueryState(['stores','region'])?.isInvalidated).toBe(true));
  hook.unmount();client.clear();
});

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { PipelineSummary } from '../src/pipeline-summary';

it('distinguishes unattempted current work from extraction failures and accepted menus',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({pipeline_version:'current',total_stores:190,counts:{accepted:22,extraction_incomplete:14,source_unresolved:44,not_attempted_current_pipeline:110}})}));
  render(<QueryClientProvider client={new QueryClient()}><PipelineSummary regionId="region"/></QueryClientProvider>);
  expect(await screen.findByText('110 not yet run with this pipeline')).toBeInTheDocument();
  expect(screen.getByText('22 accepted in this pipeline')).toBeInTheDocument();
  expect(screen.getByText('14 menu extraction incomplete')).toBeInTheDocument();
});

it('shows a failed progress response without crashing the surrounding app',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[]})}));
  render(<QueryClientProvider client={new QueryClient()}><PipelineSummary regionId="region"/></QueryClientProvider>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Pipeline progress response is invalid');
});

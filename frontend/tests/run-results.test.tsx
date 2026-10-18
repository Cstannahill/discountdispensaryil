import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RunResults } from '../src/run-results';

describe('run progress', () => {
  it('shows the retained final observation count after a shorter verification pass fails', () => {
    render(<RunResults results={[
      {stage:'menu_progress',store_id:'peru',store_name:'Stash',endpoint_id:'menu',status:'partial',page:66,traversal:2,observed_variants:1385,advertised_total:1635},
      {stage:'menu',store_id:'peru',store_name:'Stash',endpoint_id:'menu',status:'partial',provider:'treez',license_type:'recreational',source_count:1616},
      {stage:'store_summary',store_id:'peru',store_name:'Stash',status:'partial',menu_targets_attempted:1,accepted_snapshots:0},
    ]}/>);
    expect(screen.getAllByText(/1616 observed records/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/1385 observed variants · source total/)).not.toBeInTheDocument();
  });
  it('reports live catalog pagination within one store card', () => {
    render(<RunResults running results={[{stage:'menu_progress',store_id:'peru',store_name:'Stash - Peru',status:'running',page:12,traversal:1,page_recheck:1,observed_variants:240,advertised_total:1636}]} />);
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.getAllByText(/240 observed variants/).length).toBeGreaterThan(0);
    expect(screen.getByText(/source total 1636/)).toBeInTheDocument();
    expect(screen.getAllByText(/overlap recheck 1/).length).toBeGreaterThan(0);
  });
  it('groups stage events by store and distinguishes medical and recreational menus', () => {
    render(<RunResults results={[
      { stage: 'discovery', status: 'complete' },
      { stage: 'menu', store_id: 'ivy', store_name: 'Ivy Hall', endpoint_id: 'rec', license_type: 'recreational', provider: 'sweed', status: 'complete' },
      { stage: 'menu', store_id: 'ivy', store_name: 'Ivy Hall', endpoint_id: 'med', license_type: 'medicinal', provider: 'sweed', status: 'complete' },
      { stage: 'store_summary', store_id: 'ivy', store_name: 'Ivy Hall', status: 'complete', menu_targets_attempted: 2, accepted_snapshots: 2 },
    ]} />);
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.getAllByRole('heading', { name: /Ivy Hall/ })).toHaveLength(1);
    const store = screen.getByRole('article');
    expect(within(store).getAllByText(/recreational/).length).toBeGreaterThan(0);
    expect(within(store).getAllByText(/medicinal/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Registry refresh/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Â|â€|incomplete_generic_menu/);
  });
  it('shows a readable error once per store overview and preserves stage details', () => {
    render(<RunResults results={[
      { stage: 'menu', store_id: 'stash', store_name: 'Stash', status: 'partial', errors: [{code: 'incomplete_generic_menu', message: 'No structured products extracted'}] },
      { stage: 'store_summary', store_id: 'stash', store_name: 'Stash', status: 'partial' },
    ]} />);
    expect(screen.getAllByRole('article')).toHaveLength(1);
    expect(screen.getByText('Stage details (1)')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('"code"');
  });
});

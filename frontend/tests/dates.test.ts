import {expect,it} from 'vitest';
import {date} from '../src/api';
it('preserves a source publication calendar date without timezone day shifts',()=>{
  expect(date('2026-10-08')).toBe('2026-10-08');
});

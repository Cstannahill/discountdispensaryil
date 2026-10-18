import { describe, expect, it } from 'vitest';
import { extractionMessage } from '../src/extraction-errors';

describe('extraction diagnostics', () => {
  it('reads persisted JSON errors and explains verification codes without exposing raw payloads', () => {
    expect(extractionMessage('{"code":"incomplete_generic_menu","message":"No structured products extracted"}; missing_traversal_evidence; missing_source_evidence')).toBe('No structured products extracted · Full-menu traversal has not been verified · Source response evidence is missing');
  });
  it('preserves semicolons and braces inside JSON messages and deduplicates errors', () => {
    expect(extractionMessage(['{"code":"incomplete_menu","message":"Page {2}; expected 24 records"}; missing_traversal_evidence', {message:'Page {2}; expected 24 records'}])).toBe('Page {2}; expected 24 records · Full-menu traversal has not been verified');
  });
  it('preserves plain source diagnostics and handles unknown codes without crashing', () => {
    expect(extractionMessage('\u001b[2mPage load timed out\u001b[22m')).toBe('Page load timed out');
    expect(extractionMessage('Public endpoint returned HTTP 403')).toBe('Public endpoint returned HTTP 403');
    expect(extractionMessage({code:'future_provider_error'})).toBe('future provider error');
    expect(extractionMessage(null)).toBe('');
  });
});

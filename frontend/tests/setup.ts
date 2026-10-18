import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
// Node 25 exposes its own localStorage; the browser contract under test is jsdom's.
vi.stubGlobal('localStorage', window.localStorage);
afterEach(() => { cleanup(); localStorage.clear(); });

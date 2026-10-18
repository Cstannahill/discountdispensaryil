import { createServer as createHttpServer, type Server } from 'node:http';
import { afterAll, beforeAll, expect, test } from 'vitest';
import { createServer, type ViteDevServer } from 'vite';
import config from '../vite.config';

let backend: Server;
let vite: ViteDevServer;
let origin: string;

beforeAll(async () => {
  // Mirror the API's origin guard at the actual HTTP proxy boundary.
  backend = createHttpServer((request, response) => {
    const foreign = request.headers.origin && new URL(request.headers.origin).host !== request.headers.host;
    response.writeHead(foreign ? 403 : 200, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ host: request.headers.host, origin: request.headers.origin }));
  });
  await new Promise<void>(resolve => backend.listen(0, '127.0.0.1', resolve));
  const address = backend.address();
  if (!address || typeof address === 'string') throw new Error('Missing backend port');
  const configured = config.server!.proxy!['/api'];
  const proxy = typeof configured === 'string' ? { target: configured, changeOrigin: true } : configured;
  vite = await createServer({ configFile: false, server: {
    host: '127.0.0.1', port: 0,
    proxy: { '/api': { ...proxy, target: `http://127.0.0.1:${address.port}` } },
  } });
  await vite.listen();
  const viteAddress = vite.httpServer!.address();
  if (!viteAddress || typeof viteAddress === 'string') throw new Error('Missing Vite port');
  origin = `http://127.0.0.1:${viteAddress.port}`;
});

afterAll(async () => {
  await vite?.close();
  if (backend) await new Promise<void>(resolve => backend.close(() => resolve()));
});

test('same-origin development writes retain matching Host and Origin through Vite', async () => {
  const response = await fetch(`${origin}/api/v1/regions`, {
    method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json' }, body: '{}',
  });
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ host: new URL(origin).host, origin });
});

test('the development proxy preserves a foreign Origin so the API can reject it', async () => {
  const response = await fetch(`${origin}/api/v1/regions`, {
    method: 'POST', headers: { Origin: 'https://unrelated.example' }, body: '{}',
  });
  expect(response.status).toBe(403);
});

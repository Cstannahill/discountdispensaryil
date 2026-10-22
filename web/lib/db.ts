import { neon } from '@neondatabase/serverless';

let client: ReturnType<typeof neon> | undefined;

export function sql() {
  const url = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL;
  if (!url) throw new Error('DATABASE_URL is not set');
  return (client ??= neon(url));
}

export async function rows<T = Record<string, unknown>>(text: string, params: unknown[] = []): Promise<T[]> {
  return (await sql().query(text, params)) as T[];
}

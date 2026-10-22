import { NextResponse } from 'next/server';
import { regions } from '@/lib/deals';

export const dynamic = 'force-dynamic';

export async function GET() {
  return NextResponse.json(await regions());
}

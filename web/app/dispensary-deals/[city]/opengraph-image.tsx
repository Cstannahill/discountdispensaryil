import { ImageResponse } from 'next/og';
import { cityBySlug } from '@/lib/cities';

export const alt = 'Cheapest cannabis per gram in Illinois';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default async function Image({ params }: { params: Promise<{ city: string }> }) {
  const city = cityBySlug((await params).city);
  const name = city?.name ?? 'Illinois';
  return new ImageResponse(
    (
      <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: 80, background: 'linear-gradient(135deg,#060a0d 0%,#0b1f1a 100%)', color: '#fff' }}>
        <div style={{ fontSize: 40, color: '#34d399', fontWeight: 700, letterSpacing: 2 }}>DISCOUNTDISPENSARYIL</div>
        <div style={{ fontSize: 76, fontWeight: 800, marginTop: 24, lineHeight: 1.1 }}>Cheapest weed in {name}</div>
        <div style={{ fontSize: 34, color: '#94a3b8', marginTop: 28 }}>Best price per gram, ranked from live dispensary menus</div>
      </div>
    ),
    size
  );
}

import { ImageResponse } from 'next/og';

export const alt = 'DiscountDispensaryIL: cheapest cannabis price per gram at Illinois dispensaries';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: 80,
          background: 'linear-gradient(135deg,#060a0d 0%,#0b1f1a 100%)',
          color: '#fff',
        }}
      >
        <div style={{ fontSize: 40, color: '#34d399', fontWeight: 700, letterSpacing: 2 }}>DISCOUNTDISPENSARYIL</div>
        <div style={{ fontSize: 76, fontWeight: 800, marginTop: 24, lineHeight: 1.1 }}>
          Cheapest cannabis $/g in Illinois
        </div>
        <div style={{ fontSize: 34, color: '#94a3b8', marginTop: 28 }}>
          Flower, concentrates, vapes and edibles, ranked by real menu price
        </div>
      </div>
    ),
    size
  );
}

import { ImageResponse } from 'next/og';

export const size = { width: 180, height: 180 };
export const contentType = 'image/png';

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#080d13',
          position: 'relative',
        }}
      >
        <div style={{ fontSize: 120, display: 'flex' }}>🌿</div>
        <div
          style={{
            position: 'absolute',
            right: 18,
            bottom: 18,
            width: 62,
            height: 62,
            borderRadius: 31,
            background: '#fbbf24',
            color: '#080d13',
            fontSize: 44,
            fontWeight: 800,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          $
        </div>
      </div>
    ),
    size,
  );
}

import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'TerpScout: cheapest cannabis $/g near you',
  description: 'Lowest observed price per gram for flower, concentrates and vapes at Illinois dispensaries, from full menu imports.',
  icons: { icon: '/favicon.svg' },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}

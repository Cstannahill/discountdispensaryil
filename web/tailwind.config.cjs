const palette = require('tailwindcss/colors');
const plugin = require('tailwindcss/plugin');

// The palettes the UI uses are exposed as CSS variables so a layout can re-theme the whole page
// (see the "app" layout in globals.css). The defaults are Tailwind's own values, so nothing changes
// for layouts that do not override them.
const THEMED = ['slate', 'emerald', 'amber', 'purple', 'rose'];
const channels = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
};
const vars = { '--c-white': '255 255 255' };
const colors = { white: 'rgb(var(--c-white) / <alpha-value>)' };
for (const name of THEMED) {
  colors[name] = {};
  for (const [shade, hex] of Object.entries(palette[name])) {
    vars[`--c-${name}-${shade}`] = channels(hex);
    colors[name][shade] = `rgb(var(--c-${name}-${shade}) / <alpha-value>)`;
  }
}

module.exports = {
  content: ['./app/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      colors: {
        ...colors,
        slate950: '#060a0d',
        slate900: '#0d151b',
        slate850: '#121d26',
        slate800: '#182632',
      },
    },
  },
  plugins: [plugin(({ addBase }) => addBase({ ':root': vars }))],
};

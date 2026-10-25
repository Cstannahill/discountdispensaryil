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
        slate950: '#060a0d',
        slate900: '#0d151b',
        slate850: '#121d26',
        slate800: '#182632',
      },
    },
  },
  plugins: [],
};

export default {
  poweredByHeader: false,
  // The /api/v1 routes are public, read-only and use no cookies, so any origin may read them. This lets the mobile
  // app's browser preview (Expo web on localhost) call the API; phone builds and the site itself never needed it.
  async headers() {
    return [
      {
        source: '/api/v1/:path*',
        headers: [
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET, OPTIONS' },
          { key: 'Access-Control-Allow-Headers', value: 'Accept, Content-Type' },
          { key: 'Access-Control-Max-Age', value: '86400' },
        ],
      },
    ];
  },
};

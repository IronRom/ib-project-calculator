/** @type {import('next').NextConfig} */
const nextConfig = {
  // Корень уводим на /projects правилом сервера, а не redirect() в RSC:
  // пререндер корневой страницы отдавал 307 БЕЗ заголовка Location (браузер
  // на голом домене получал ошибку вместо перехода).
  async redirects() {
    return [{ source: '/', destination: '/projects', permanent: false }]
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/:path*`,
      },
    ]
  },
}

module.exports = nextConfig

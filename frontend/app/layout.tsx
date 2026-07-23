import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'ИС·ПИР — Калькулятор проектно-изыскательских работ',
  description: 'AI-калькулятор стоимости ПИР по СБЦП',
}

// Без viewport meta мобильный Safari рендерит страницу в виртуальных ~980px:
// мобильные медиа-запросы не срабатывают, вёрстка «едет»
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  )
}

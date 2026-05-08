import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'ИС·ПИР — Калькулятор проектно-изыскательских работ',
  description: 'AI-калькулятор стоимости ПИР по СБЦП',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  )
}

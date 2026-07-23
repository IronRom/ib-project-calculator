'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { getMe, User } from '@/lib/api'
import { Sidebar } from '@/components/layout/Sidebar'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [user, setUser] = useState<User | null>(null)
  const [navOpen, setNavOpen] = useState(false)

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => router.push('/login'))
  }, [router])

  // закрывать мобильное меню при навигации
  useEffect(() => { setNavOpen(false) }, [pathname])

  function handleLogout() {
    localStorage.removeItem('pir_token')
    router.push('/login')
  }

  if (!user) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
        Загрузка…
      </div>
    )
  }

  return (
    <div className="app-shell">
      {/* мобильный бургер + оверлей */}
      <button
        className="mobile-burger"
        aria-label="Открыть меню"
        onClick={() => setNavOpen(v => !v)}
      >☰</button>
      {navOpen && <div className="sidebar-overlay" onClick={() => setNavOpen(false)} />}

      <div className={`app-sidebar ${navOpen ? 'open' : ''}`}>
        <Sidebar userEmail={user.email} userRole={user.role} onLogout={handleLogout} />
      </div>

      <main className="app-main" style={{ flex: 1, overflowY: 'auto', background: 'var(--bg-app)' }}>
        {children}
      </main>
    </div>
  )
}

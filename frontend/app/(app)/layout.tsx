'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getMe, User } from '@/lib/api'
import { Sidebar } from '@/components/layout/Sidebar'

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => router.push('/login'))
  }, [router])

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
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar userEmail={user.email} userRole={user.role} onLogout={handleLogout} />
      <main style={{ flex: 1, overflowY: 'auto', background: 'var(--bg-app)' }}>
        {children}
      </main>
    </div>
  )
}

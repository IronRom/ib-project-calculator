'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { login } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await login(email, password)
      localStorage.setItem('pir_token', res.access_token)
      router.push('/projects')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка входа')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg-app)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 48,
    }}>
      <div style={{
        width: 440,
        background: 'var(--bg-elevated)',
        border: 'var(--hairline)',
        borderRadius: 'var(--radius-xl)',
        padding: 36,
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
        boxShadow: 'var(--shadow-3)',
      }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.02em' }}>
            ИС·ПИР
          </div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
            Калькулятор проектно-изыскательских работ
          </div>
        </div>

        <div>
          <div style={{ fontSize: 24, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.005em' }}>
            Вход в систему
          </div>
          <div style={{ fontSize: 13, color: 'var(--fg-3)', marginTop: 4 }}>
            Используйте корпоративную почту организации
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Input
            label="Корпоративная почта"
            type="text"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Input
            label="Пароль"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          {error && (
            <div style={{ padding: '10px 12px', background: 'var(--danger-100)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--danger-400)' }}>
              {error}
            </div>
          )}

          <Button type="submit" variant="primary" size="lg" disabled={loading} fullWidth>
            {loading ? 'Вход…' : 'Войти'}
          </Button>
        </form>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--fg-4)', fontSize: 11, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          <div style={{ flex: 1, height: 1, background: 'var(--border-subtle)' }} />
          ИЛИ
          <div style={{ flex: 1, height: 1, background: 'var(--border-subtle)' }} />
        </div>

        <Link href="/register" style={{ textAlign: 'center', fontSize: 13, color: 'var(--fg-2)' }}>
          Создать новую учётную запись
        </Link>
      </div>
    </div>
  )
}

'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { login } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

/* Индустриальная сцена входа: blueprint-сетка, координатная разметка,
   живые метрики системы. Тон — станция управления, не маркетинг. */

const METRICS = [
  { k: 'СПРАВОЧНИКОВ В БАЗЕ', v: '181' },
  { k: 'СТРОК НОРМАТИВОВ', v: '43 000+' },
  { k: 'СХОДИМОСТЬ С ЭТАЛОНОМ', v: '± КОПЕЙКА' },
  { k: 'МЕТОДИКИ', v: 'МУ-620 · 707/пр · МРР' },
]

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setTick(x => x + 1), 2200)
    return () => clearInterval(t)
  }, [])

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
    <div style={{ minHeight: '100vh', display: 'flex', background: 'var(--ink-1000)' }}>

      {/* ═══ Бренд-панель ═══ */}
      <div className="ibps-brand" style={{
        flex: '1.3 1 0', position: 'relative', overflow: 'hidden',
        display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
        padding: '48px 56px',
        background: `
          linear-gradient(rgba(31,95,232,0.055) 1px, transparent 1px),
          linear-gradient(90deg, rgba(31,95,232,0.055) 1px, transparent 1px),
          linear-gradient(rgba(31,95,232,0.025) 1px, transparent 1px),
          linear-gradient(90deg, rgba(31,95,232,0.025) 1px, transparent 1px),
          radial-gradient(1100px 700px at 12% -8%, #0D1B36 0%, var(--ink-1000) 58%)
        `,
        backgroundSize: '120px 120px, 120px 120px, 24px 24px, 24px 24px, auto',
        borderRight: '1px solid var(--ink-600)',
      }}>
        {/* координатная линейка */}
        <div aria-hidden style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          fontFamily: 'var(--font-mono)', fontSize: 9,
          color: 'var(--ink-500)', letterSpacing: 1,
        }}>
          {[0, 1, 2, 3, 4, 5, 6].map(i => (
            <span key={i} style={{ position: 'absolute', left: 10, top: 118 * i + 6 }}>
              {String(i).padStart(2, '0')}·{String(i * 120).padStart(3, '0')}
            </span>
          ))}
        </div>

        <div style={{ position: 'relative' }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 10,
            fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 2,
            color: 'var(--blue-200)', border: '1px solid var(--ink-500)',
            padding: '6px 12px', borderRadius: 4, background: 'rgba(31,95,232,0.08)',
          }}>
            <span className="ibps-pulse" style={{
              width: 7, height: 7, borderRadius: '50%',
              background: 'var(--success-400)', boxShadow: '0 0 8px var(--success-400)',
            }} />
            СИСТЕМА АКТИВНА · БАЗА НОРМАТИВОВ СИНХРОНИЗИРОВАНА
          </div>

          <h1 style={{
            margin: '44px 0 0', fontWeight: 300, fontSize: 52, lineHeight: 1.07,
            color: 'var(--ink-100)', letterSpacing: -1,
          }}>
            Intellect Building
            <br />
            <span style={{ fontWeight: 650, color: '#FFFFFF' }}>PIR System</span>
          </h1>
          <p style={{
            margin: '22px 0 0', maxWidth: 540, fontSize: 15, lineHeight: 1.65,
            color: 'var(--ink-200)',
          }}>
            Промышленный расчёт стоимости проектно-изыскательских работ:
            извлечение из ТЗ, нормативные базы СБЦП · НЗ · МРР, смета 2ПС
            и коммерческое предложение — за минуты, с обоснованием каждой цифры.
          </p>
        </div>

        {/* живые метрики */}
        <div style={{
          position: 'relative', display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)', gap: 1,
          background: 'var(--ink-600)', border: '1px solid var(--ink-600)',
          borderRadius: 6, overflow: 'hidden',
        }}>
          {METRICS.map((m, i) => (
            <div key={m.k} style={{
              background: tick % 4 === i ? 'rgba(31,95,232,0.12)' : 'var(--ink-900)',
              transition: 'background 700ms ease', padding: '18px 16px',
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 9,
                letterSpacing: 1.5, color: 'var(--ink-300)',
              }}>{m.k}</div>
              <div style={{
                marginTop: 8, fontFamily: 'var(--font-mono)',
                fontSize: 16, fontWeight: 500, color: 'var(--ink-50)',
                whiteSpace: 'nowrap',
              }}>{m.v}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ═══ Форма входа ═══ */}
      <div style={{
        flex: '1 1 0', display: 'flex', alignItems: 'center',
        justifyContent: 'center', padding: 48, background: 'var(--ink-900)',
      }}>
        <form onSubmit={handleSubmit} style={{ width: 380, display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10,
            letterSpacing: 2, color: 'var(--ink-300)',
          }}>АВТОРИЗАЦИЯ ОПЕРАТОРА</div>
          <div style={{ fontSize: 26, fontWeight: 600, color: 'var(--ink-50)', marginTop: -6 }}>
            Вход в систему
          </div>

          <Input
            label="Корпоративная почта"
            type="text"
            name="username"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Input
            label="Пароль"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          {error && (
            <div style={{
              padding: '10px 14px', borderRadius: 6, fontSize: 13,
              background: 'rgba(220,38,38,0.10)', border: '1px solid rgba(220,38,38,0.35)',
              color: '#FCA5A5',
            }}>{error}</div>
          )}

          <Button type="submit" variant="primary" size="lg" disabled={loading} fullWidth>
            {loading ? 'Проверка доступа…' : 'Войти'}
          </Button>

          <div style={{
            marginTop: 6, paddingTop: 16, borderTop: '1px solid var(--ink-600)',
            fontFamily: 'var(--font-mono)', fontSize: 10, lineHeight: 1.9,
            color: 'var(--ink-400)', letterSpacing: 0.5,
          }}>
            ООО «ИНТЕЛЛЕКТ-СТРОЙ» · РАСЧЁТ ПИР
            <br />ДОСТУП ПРЕДОСТАВЛЯЕТСЯ АДМИНИСТРАТОРОМ СИСТЕМЫ
          </div>
        </form>
      </div>

      <style>{`
        @keyframes ibpsPulse { 0%,100% { opacity: 1 } 50% { opacity: .3 } }
        .ibps-pulse { animation: ibpsPulse 2.2s ease-in-out infinite }
        @media (prefers-reduced-motion: reduce) { .ibps-pulse { animation: none } }
        @media (max-width: 980px) { .ibps-brand { display: none !important } }
      `}</style>
    </div>
  )
}

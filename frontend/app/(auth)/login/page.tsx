'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { login } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

/* Сцена входа = вычислительный контур системы, не маркетинг.
   Схема пайплайна ТЗ → парсер → AI-экстрактор → движок → 2ПС с бегущим
   «пакетом» данных и живой консолью реальных стадий расчёта.  */

const PIPELINE = [
  { id: 'tz',   t: 'ТЗ',        s: 'PDF · DOCX' },
  { id: 'prs',  t: 'ПАРСЕР',    s: 'text · vision' },
  { id: 'ext',  t: 'ЭКСТРАКТОР', s: 'AI · 3 прохода' },
  { id: 'eng',  t: 'ДВИЖОК',    s: 'СБЦП · НЗ · МРР' },
  { id: 'out',  t: '2ПС · КП',  s: 'xlsx · docx · pdf' },
]

const INVENTORY = [
  { k: 'СПРАВОЧНИКИ', v: '181' },
  { k: 'СТРОКИ НОРМ', v: '43 000+' },
  { k: 'МЕТОДИКИ',    v: 'МУ-620 · 707/пр · МРР' },
]

const LOG_POOL: { m: string; tag?: string }[] = [
  { m: 'document_parser  PDF → plain text', tag: 'ok' },
  { m: 'entity_extractor pass 1/3 · позиции' },
  { m: 'entity_extractor pass 2/3 · коэффициенты' },
  { m: 'entity_extractor pass 3/3 · resolve X' },
  { m: 'calculator _match_row · МУ-620 экстрап.' },
  { m: 'calculator 707/пр ф.8.4 · Кэ = 0.31' },
  { m: 'book_conditions · АСУ К = 1.20' },
  { m: 'price_index Минстрой · Кпер 9.923' },
  { m: 'section_shares · ПД 86% · РД 93%' },
  { m: 'export 2ПС.xlsx · КП.docx · КП.pdf', tag: 'ok' },
  { m: 'audit_rows · непрерывность цен', tag: 'ok' },
]

type LogLine = { id: number; ts: string; m: string; tag?: string }

function clock(sec: number): string {
  const mm = String(Math.floor(sec / 60) % 60).padStart(2, '0')
  const ss = String(sec % 60).padStart(2, '0')
  return `00:${mm}:${ss}`
}

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [log, setLog] = useState<LogLine[]>([])
  const poolRef = useRef(0)
  const secRef = useRef(11)
  const idRef = useRef(0)

  useEffect(() => {
    // прогрев: заранее набить консоль, чтобы не пустовала
    const seed: LogLine[] = []
    for (let i = 0; i < 6; i++) {
      const item = LOG_POOL[poolRef.current % LOG_POOL.length]
      poolRef.current++
      secRef.current += 1 + (i % 3)
      seed.push({ id: idRef.current++, ts: clock(secRef.current), m: item.m, tag: item.tag })
    }
    setLog(seed)

    const iv = setInterval(() => {
      const item = LOG_POOL[poolRef.current % LOG_POOL.length]
      poolRef.current++
      secRef.current += 1 + (poolRef.current % 3)
      setLog(prev => [
        ...prev.slice(-6),
        { id: idRef.current++, ts: clock(secRef.current), m: item.m, tag: item.tag },
      ])
    }, 1400)
    return () => clearInterval(iv)
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
    <div style={{ minHeight: '100dvh', display: 'flex', background: 'var(--ink-1000)' }}>

      {/* ═══ Вычислительный контур ═══ */}
      <div className="ibps-stage" style={{
        flex: '1.35 1 0', position: 'relative', overflow: 'hidden',
        display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
        padding: '40px 52px 34px',
        background: `
          linear-gradient(rgba(31,95,232,0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(31,95,232,0.05) 1px, transparent 1px),
          linear-gradient(rgba(31,95,232,0.022) 1px, transparent 1px),
          linear-gradient(90deg, rgba(31,95,232,0.022) 1px, transparent 1px),
          radial-gradient(1200px 760px at 8% -10%, #0C1A34 0%, var(--ink-1000) 60%)
        `,
        backgroundSize: '128px 128px, 128px 128px, 32px 32px, 32px 32px, auto',
        borderRight: '1px solid var(--ink-600)',
      }}>
        {/* мягкий скан-луч */}
        <div aria-hidden className="ibps-scan" />

        {/* верх: статус-строка + инвентарь */}
        <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 24 }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 9,
            fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: 1.6,
            color: 'var(--blue-200)', border: '1px solid var(--ink-500)',
            padding: '6px 11px', borderRadius: 4, background: 'rgba(31,95,232,0.07)',
          }}>
            <span className="ibps-pulse" style={{
              width: 7, height: 7, borderRadius: '50%',
              background: 'var(--success-400)', boxShadow: '0 0 8px var(--success-400)',
            }} />
            IB-PIR · ВЫЧИСЛИТЕЛЬНЫЙ КОНТУР · ONLINE
          </div>
          <div style={{ display: 'flex', gap: 22 }}>
            {INVENTORY.map(m => (
              <div key={m.k} style={{ textAlign: 'right' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, letterSpacing: 1.4, color: 'var(--ink-300)' }}>{m.k}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--ink-50)', marginTop: 3, whiteSpace: 'nowrap' }}>{m.v}</div>
              </div>
            ))}
          </div>
        </div>

        {/* центр: вордмарк + схема пайплайна */}
        <div style={{ position: 'relative' }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 3,
            color: 'var(--ink-300)', marginBottom: 14,
          }}>
            ПРОЕКТНО-ИЗЫСКАТЕЛЬСКИЕ РАБОТЫ · СМЕТНЫЙ ДВИЖОК
          </div>
          <h1 style={{
            margin: 0, fontWeight: 300, fontSize: 54, lineHeight: 1.04,
            color: 'var(--ink-100)', letterSpacing: -1.4,
          }}>
            Intellect Building
            <br />
            <span style={{ fontWeight: 680, color: '#FFFFFF' }}>PIR System</span>
          </h1>

          {/* схема пайплайна */}
          <div className="ibps-pipe" style={{ marginTop: 40 }}>
            <div className="ibps-track" aria-hidden>
              <span className="ibps-pkt" />
            </div>
            <div className="ibps-nodes">
              {PIPELINE.map((n, i) => (
                <div key={n.id} className="ibps-node" style={{ animationDelay: `${(i * 3.6 / PIPELINE.length).toFixed(2)}s` }}>
                  <div className="ibps-node-t">{n.t}</div>
                  <div className="ibps-node-s">{n.s}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* низ: живая консоль пайплайна */}
        <div style={{ position: 'relative' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
            fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: 1.4, color: 'var(--ink-300)',
          }}>
            <span style={{ color: 'var(--success-400)' }}>▸</span> ЖУРНАЛ ПАЙПЛАЙНА
          </div>
          <div className="ibps-console">
            {log.map(l => (
              <div key={l.id} className="ibps-line">
                <span className="ibps-ts">{l.ts}</span>
                <span className="ibps-msg">{l.m}</span>
                {l.tag && <span className="ibps-tag">{l.tag}</span>}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ═══ Форма входа ═══ */}
      <div style={{
        flex: '1 1 0', display: 'flex', alignItems: 'center',
        justifyContent: 'center', padding: '32px 20px', background: 'var(--ink-900)',
      }}>
        <form onSubmit={handleSubmit} style={{ width: 380, maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 10,
            letterSpacing: 2, color: 'var(--ink-300)',
          }}>ДОСТУП К СИСТЕМЕ</div>
          <div style={{ fontSize: 26, fontWeight: 600, color: 'var(--ink-50)', marginTop: -6 }}>
            Вход
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
            ООО «ИНТЕЛЛЕКТ-СТРОЙ»
            <br />ДОСТУП ВЫДАЁТ АДМИНИСТРАТОР СИСТЕМЫ
          </div>
        </form>
      </div>

      <style>{`
        @keyframes ibpsPulse { 0%,100% { opacity: 1 } 50% { opacity: .3 } }
        .ibps-pulse { animation: ibpsPulse 2.2s ease-in-out infinite }

        /* скан-луч */
        .ibps-scan {
          position: absolute; left: 0; right: 0; top: 0; height: 220px;
          pointer-events: none;
          background: linear-gradient(180deg, rgba(31,95,232,0.10), transparent);
          animation: ibpsScan 7s linear infinite;
        }
        @keyframes ibpsScan {
          0% { transform: translateY(-240px) }
          100% { transform: translateY(100vh) }
        }

        /* пайплайн */
        .ibps-pipe { position: relative; }
        .ibps-track {
          position: relative; height: 2px; margin: 0 6% 18px;
          background: linear-gradient(90deg, var(--ink-600), var(--ink-500), var(--ink-600));
          border-radius: 2px;
        }
        .ibps-pkt {
          position: absolute; top: 50%; width: 10px; height: 10px; margin-top: -5px;
          border-radius: 50%; background: var(--blue-300);
          box-shadow: 0 0 12px 2px var(--blue-400), 0 0 3px #fff;
          animation: ibpsPkt 3.6s cubic-bezier(.65,0,.35,1) infinite;
        }
        @keyframes ibpsPkt {
          0%   { left: 0%;  opacity: 0 }
          8%   { opacity: 1 }
          92%  { opacity: 1 }
          100% { left: 100%; opacity: 0 }
        }
        .ibps-nodes {
          display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px;
        }
        .ibps-node {
          text-align: center; padding: 12px 8px;
          border: 1px solid var(--ink-600); border-radius: 6px;
          background: var(--ink-900);
          animation: ibpsNode 3.6s ease-in-out infinite;
        }
        @keyframes ibpsNode {
          0%, 72%, 100% { border-color: var(--ink-600); background: var(--ink-900); box-shadow: none; }
          14%, 22% { border-color: var(--blue-500); background: rgba(31,95,232,0.10);
                     box-shadow: 0 0 0 1px rgba(31,95,232,0.25), 0 6px 22px -10px rgba(31,95,232,0.6); }
        }
        .ibps-node-t {
          font-family: var(--font-mono); font-size: 12.5px; font-weight: 600;
          letter-spacing: .5px; color: var(--ink-50);
        }
        .ibps-node-s {
          font-family: var(--font-mono); font-size: 9px; letter-spacing: .6px;
          color: var(--ink-300); margin-top: 5px; white-space: nowrap;
        }

        /* консоль */
        .ibps-console {
          font-family: var(--font-mono); font-size: 11.5px; line-height: 1.75;
          background: rgba(5,8,13,0.55); border: 1px solid var(--ink-600);
          border-radius: 6px; padding: 12px 14px; height: 148px; overflow: hidden;
          display: flex; flex-direction: column; justify-content: flex-end;
        }
        .ibps-line {
          display: flex; align-items: baseline; gap: 10px; white-space: nowrap;
          animation: ibpsLineIn .5s ease both;
        }
        @keyframes ibpsLineIn {
          from { opacity: 0; transform: translateY(4px) }
          to   { opacity: 1; transform: none }
        }
        .ibps-ts  { color: var(--ink-400); }
        .ibps-msg { color: var(--ink-100); }
        .ibps-tag {
          margin-left: auto; color: var(--success-400);
          border: 1px solid rgba(34,197,94,0.35); border-radius: 3px;
          padding: 0 6px; font-size: 9.5px; letter-spacing: 1px; text-transform: uppercase;
        }

        @media (prefers-reduced-motion: reduce) {
          .ibps-pulse, .ibps-scan, .ibps-pkt, .ibps-node, .ibps-line { animation: none !important }
        }
        @media (max-width: 980px) { .ibps-stage { display: none !important } }
      `}</style>
    </div>
  )
}

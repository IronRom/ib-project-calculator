'use client'

import { useEffect, useState } from 'react'
import { getMe, getTelegramLinkCode, unlinkTelegram, User } from '@/lib/api'

/* Карточка привязки Telegram-бота в кабинете. Показывает статус привязки
   и генерирует одноразовую deep-link ссылку на @ib_pir_bot. */
export function TelegramConnect() {
  const [user, setUser] = useState<User | null>(null)
  const [link, setLink] = useState<string | null>(null)
  const [botUsername, setBotUsername] = useState('ib_pir_bot')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { getMe().then(setUser).catch(() => {}) }, [])

  async function genLink() {
    setLoading(true); setErr(null)
    try {
      const r = await getTelegramLinkCode()
      setLink(r.deep_link)
      setBotUsername(r.bot_username)
    } catch (e) {
      setErr((e as Error).message)
    } finally { setLoading(false) }
  }

  async function unlink() {
    if (!confirm('Отвязать Telegram от аккаунта?')) return
    await unlinkTelegram()
    setLink(null)
    setUser((u) => u ? { ...u, telegram_linked: false, telegram_username: null } : u)
  }

  if (!user) return null

  const linked = !!user.telegram_linked

  return (
    <div style={{
      border: 'var(--hairline)', borderRadius: 'var(--radius-lg)',
      background: 'var(--bg-surface)', padding: '16px 18px',
      display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
    }}>
      <div style={{ fontSize: 26 }}>✈️</div>
      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg-1)' }}>
          Telegram-бот
        </div>
        <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>
          {linked
            ? <>Привязан{user.telegram_username ? `: @${user.telegram_username}` : ''}. Управляйте проектами и расчётами прямо из <b>@{botUsername}</b>.</>
            : <>Подключите <b>@{botUsername}</b>, чтобы вести расчёты со смартфона без входа в веб.</>}
        </div>
        {err && <div style={{ fontSize: 12, color: 'var(--red-400, #e5484d)', marginTop: 6 }}>{err}</div>}
        {link && !linked && (
          <div style={{ marginTop: 10 }}>
            <a href={link} target="_blank" rel="noopener noreferrer" style={{
              display: 'inline-block', padding: '8px 14px', borderRadius: 'var(--radius-md)',
              background: 'var(--blue-700)', color: '#fff', fontSize: 13, fontWeight: 500,
              textDecoration: 'none',
            }}>Открыть @{botUsername} и привязать →</a>
            <div style={{ fontSize: 11, color: 'var(--fg-4)', marginTop: 6 }}>
              Ссылка действует 15 минут. Откройте её на телефоне с установленным Telegram.
            </div>
          </div>
        )}
      </div>
      <div>
        {linked ? (
          <button onClick={unlink} style={btnGhost}>Отвязать</button>
        ) : (
          <button onClick={genLink} disabled={loading} style={btnPrimary}>
            {loading ? '…' : link ? 'Обновить ссылку' : 'Подключить'}
          </button>
        )}
      </div>
    </div>
  )
}

const btnPrimary: React.CSSProperties = {
  padding: '8px 16px', borderRadius: 'var(--radius-md)', border: 'none',
  background: 'var(--blue-700)', color: '#fff', fontSize: 13, fontWeight: 500, cursor: 'pointer',
}
const btnGhost: React.CSSProperties = {
  padding: '8px 16px', borderRadius: 'var(--radius-md)', border: 'var(--hairline)',
  background: 'transparent', color: 'var(--fg-2)', fontSize: 13, cursor: 'pointer',
}

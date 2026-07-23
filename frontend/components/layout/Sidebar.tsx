'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ITEMS = [
  { href: '/projects', label: 'Проекты', icon: '📁' },
  { href: '/projects/new', label: 'Новый расчёт', icon: '+' },
]

const ADMIN_ITEMS = [
  { href: '/admin/users', label: 'Пользователи', icon: '👤' },
  { href: '/admin/references', label: 'Справочники', icon: '📚' },
  { href: '/admin/indices', label: 'Коэффициенты', icon: '📊' },
  { href: '/admin/settings', label: 'Настройки', icon: '⚙' },
]

interface SidebarProps {
  userEmail?: string
  userRole?: string
  onLogout?: () => void
}

export function Sidebar({ userEmail, userRole, onLogout }: SidebarProps) {
  const pathname = usePathname()

  const initials = userEmail
    ? userEmail.split('@')[0].slice(0, 2).toUpperCase()
    : '??'

  return (
    <aside className="sidebar-root" style={{
      width: 240,
      flex: 'none',
      background: 'var(--bg-surface)',
      borderRight: 'var(--hairline)',
      display: 'flex',
      flexDirection: 'column',
      position: 'sticky',
      top: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: '20px 18px 16px', borderBottom: 'var(--hairline)' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.02em' }}>
          ИС·ПИР
        </div>
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--fg-3)', marginTop: 2 }}>
          Калькулятор ПИР
        </div>
      </div>

      {/* Nav */}
      <nav style={{ padding: 12, flex: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.href} item={item} active={pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href) && item.href !== '/projects/new')} />
        ))}

        {userRole === 'admin' && (
          <>
            <div style={{ margin: '12px 8px 4px', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-4)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Администрирование
            </div>
            {ADMIN_ITEMS.map((item) => (
              <NavLink key={item.href} item={item} active={pathname.startsWith(item.href)} />
            ))}
          </>
        )}
      </nav>

      {/* User */}
      <div style={{ padding: '12px 12px calc(12px + env(safe-area-inset-bottom))', borderTop: 'var(--hairline)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 8px' }}>
          <div style={{
            width: 28, height: 28, borderRadius: '50%',
            background: 'var(--blue-700)', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
          }}>
            {initials}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, color: 'var(--fg-1)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {userEmail}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)' }}>
              {userRole === 'admin' ? 'Администратор' : 'Пользователь'}
            </div>
          </div>
          <button
            onClick={onLogout}
            title="Выйти"
            style={{ background: 'transparent', border: 'none', color: 'var(--fg-3)', padding: 6, borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontSize: 14 }}
          >
            ↪
          </button>
        </div>
      </div>
    </aside>
  )
}

function NavLink({ item, active }: { item: { href: string; label: string; icon: string }; active: boolean }) {
  return (
    <Link
      href={item.href}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 10px',
        background: active ? 'var(--accent-tint)' : 'transparent',
        color: active ? 'var(--blue-300)' : 'var(--fg-2)',
        borderRadius: 'var(--radius-md)',
        fontSize: 13,
        fontWeight: active ? 500 : 400,
        textDecoration: 'none',
        position: 'relative',
        transition: 'background var(--duration-1) var(--ease-out)',
      }}
    >
      {active && (
        <span style={{
          position: 'absolute', left: -12, top: 6, bottom: 6,
          width: 2, background: 'var(--blue-500)', borderRadius: 2,
        }} />
      )}
      <span style={{ fontSize: 14 }}>{item.icon}</span>
      {item.label}
    </Link>
  )
}

interface TopbarProps {
  title: string
  breadcrumb?: string
  actions?: React.ReactNode
}

export function Topbar({ title, breadcrumb, actions }: TopbarProps) {
  return (
    <header style={{
      height: 56,
      flex: 'none',
      borderBottom: 'var(--hairline)',
      background: 'var(--bg-app)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 28px',
      gap: 16,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        {breadcrumb && (
          <div className="t-overline" style={{ marginBottom: 2 }}>{breadcrumb}</div>
        )}
        <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.005em' }}>
          {title}
        </div>
      </div>
      {actions}
    </header>
  )
}

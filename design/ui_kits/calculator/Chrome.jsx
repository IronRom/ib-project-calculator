// Sidebar + Topbar — app chrome

function Sidebar({ active, onNav, onLogout }) {
  const items = [
    { id: 'projects', label: 'Проекты', icon: <window.Folder size={16}/> },
    { id: 'new',      label: 'Новый расчёт', icon: <window.Plus size={16}/> },
    { id: 'refs',     label: 'Справочники', icon: <window.ListChecks size={16}/> },
    { id: 'billing',  label: 'Подписка', icon: <window.FileText size={16}/> },
    { id: 'settings', label: 'Настройки', icon: <window.Settings size={16}/> },
  ];
  return (
    <aside style={{
      width: 240, flex: 'none', background: 'var(--bg-surface)',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex', flexDirection: 'column', height: '100%',
    }}>
      <div style={{ padding: '20px 18px 16px 18px', borderBottom: '1px solid var(--border-subtle)' }}>
        <img src="../../assets/logo-wordmark-dark.svg" width="216" height="40" alt="ИС·ПИР"/>
      </div>
      <nav style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
        {items.map((it) => {
          const isActive = active === it.id;
          return (
            <button key={it.id} onClick={() => onNav?.(it.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 10px',
                background: isActive ? 'var(--accent-tint)' : 'transparent',
                color: isActive ? 'var(--blue-300)' : 'var(--fg-2)',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: isActive ? 500 : 400,
                cursor: 'pointer', textAlign: 'left',
                position: 'relative',
              }}
              onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = 'var(--bg-hover)'; }}
              onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}>
              {isActive && <span style={{ position:'absolute', left: -12, top: 6, bottom: 6, width: 2, background:'var(--blue-500)', borderRadius:2 }}/>}
              {it.icon}
              {it.label}
            </button>
          );
        })}
      </nav>
      <div style={{ padding: 12, borderTop: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 8px' }}>
          <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--blue-700)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600 }}>АВ</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--fg-1)', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>А. Воронин</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)' }}>ООО «СтройПроект»</div>
          </div>
          <button onClick={onLogout} title="Выход"
            style={{ background: 'transparent', border: 'none', color: 'var(--fg-3)', cursor: 'pointer', padding: 6, borderRadius: 'var(--radius-sm)' }}>
            <window.LogOut size={14}/>
          </button>
        </div>
      </div>
    </aside>
  );
}

function Topbar({ title, breadcrumb, actions }) {
  return (
    <header style={{
      height: 56, flex: 'none',
      borderBottom: '1px solid var(--border-subtle)',
      background: 'var(--bg-app)',
      display: 'flex', alignItems: 'center', padding: '0 28px', gap: 16,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        {breadcrumb && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 2 }}>
            {breadcrumb}
          </div>
        )}
        <div style={{ fontFamily: 'var(--font-sans)', fontSize: 18, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.005em' }}>{title}</div>
      </div>
      {actions}
    </header>
  );
}

Object.assign(window, { Sidebar, Topbar });

// DashboardScreen — list of user's calculation projects

const SAMPLE_PROJECTS = [
  { id: 'PR-2026-0184', name: 'ЖК «Северный», корпус 4', date: '07.05.2026', area: '12 540', items: 47, total: '2 384 500', status: 'success' },
  { id: 'PR-2026-0181', name: 'Реконструкция котельной №3', date: '04.05.2026', area: '480',    items: 18, total: '418 200',   status: 'success' },
  { id: 'PR-2026-0179', name: 'Школа на 1100 мест, г. Лобня', date: '02.05.2026', area: '8 240',  items: 62, total: '3 120 000', status: 'warning' },
  { id: 'PR-2026-0177', name: 'Переустройство сетей водоснабжения', date: '28.04.2026', area: '—', items: 24, total: null, status: 'info' },
  { id: 'PR-2026-0172', name: 'Промышленное здание, ул. Заводская', date: '21.04.2026', area: '4 100',  items: 31, total: '1 480 200', status: 'success' },
];

function DashboardScreen({ onNew, onOpen }) {
  return (
    <div style={{ flex: 1, padding: '24px 28px 48px', overflowY: 'auto', background: 'var(--bg-app)' }}>
      {/* Filter / search bar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, alignItems: 'center' }}>
        <div style={{ flex: 1, maxWidth: 380, background: 'var(--bg-input)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', height: 36, display: 'flex', alignItems: 'center', padding: '0 12px', gap: 8 }}>
          <span style={{ color: 'var(--fg-3)' }}><window.Search size={14}/></span>
          <input placeholder="Поиск по названию или коду…"
            style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: 'var(--fg-1)', fontFamily: 'var(--font-sans)', fontSize: 13 }}/>
        </div>
        <window.Select value="all" onChange={() => {}} options={[
          { value: 'all', label: 'Все статусы' },
          { value: 'done', label: 'Готовые' },
          { value: 'progress', label: 'В обработке' },
        ]}/>
        <div style={{ flex: 1 }}/>
        <window.Button variant="primary" icon={<window.Plus size={14}/>} onClick={onNew}>Новый расчёт</window.Button>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { l: 'Расчётов в этом месяце', v: '14', sub: 'из 25 по тарифу «Бюро»' },
          { l: 'Активных проектов', v: '5', sub: '2 ожидают согласования' },
          { l: 'Суммарный объём', v: '₽ 8.4 М', sub: 'за май 2026' },
          { l: 'Средний срок расчёта', v: '6 мин', sub: '−14% к апрелю' },
        ].map((k) => (
          <div key={k.l} style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', padding: 16, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k.l}</div>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 28, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.015em', fontVariantNumeric: 'tabular-nums' }}>{k.v}</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Project table */}
      <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
        <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--fg-1)' }}>Проекты</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{SAMPLE_PROJECTS.length} записей</div>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-1)' }}>
          <thead style={{ background: 'var(--bg-raised)' }}>
            <tr>
              {['Код', 'Наименование', 'Дата', 'Площадь', 'Позиций', 'Стоимость', 'Статус', ''].map((h, i) => (
                <th key={i} style={{ textAlign: i >= 3 && i <= 5 ? 'right' : 'left', padding: '10px 14px', fontSize: 10, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-default)' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody style={{ fontVariantNumeric: 'tabular-nums' }}>
            {SAMPLE_PROJECTS.map((p, i) => (
              <tr key={p.id} onClick={() => onOpen?.(p)}
                style={{ cursor: 'pointer', borderBottom: i < SAMPLE_PROJECTS.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
                <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--blue-300)' }}>{p.id}</td>
                <td style={{ padding: '12px 14px' }}>{p.name}</td>
                <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', color: 'var(--fg-2)', fontSize: 12 }}>{p.date}</td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{p.area === '—' ? <span style={{ color: 'var(--fg-3)' }}>—</span> : <>{p.area}<span style={{ color: 'var(--fg-3)', marginLeft: 4 }}>м²</span></>}</td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{p.items}</td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{p.total ? <>{p.total}<span style={{ color: 'var(--fg-3)', marginLeft: 4 }}>₽</span></> : <span style={{ color: 'var(--fg-3)' }}>—</span>}</td>
                <td style={{ padding: '12px 14px' }}>
                  {p.status === 'success' && <window.Chip tone="success">Готов</window.Chip>}
                  {p.status === 'warning' && <window.Chip tone="warning">Требует согласования</window.Chip>}
                  {p.status === 'info' && <window.Chip tone="info">В обработке</window.Chip>}
                </td>
                <td style={{ padding: '12px 14px', color: 'var(--fg-3)' }}><window.ChevronRight size={14}/></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

Object.assign(window, { DashboardScreen });

// LandingScreen — marketing page that takes the user to auth.

function LandingScreen({ onCTA, onSignIn }) {
  return (
    <div style={{ minHeight: '100%', background: 'var(--bg-app)', color: 'var(--fg-1)', display: 'flex', flexDirection: 'column' }}>
      {/* Sticky nav */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 10,
        height: 64, padding: '0 48px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        borderBottom: '1px solid var(--border-subtle)',
        background: 'rgba(5, 8, 13, 0.72)', backdropFilter: 'blur(12px)',
      }}>
        <img src="../../assets/logo-wordmark-dark.svg" width="238" height="44" alt="ИС·ПИР"/>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <a href="#features" style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-2)', textDecoration: 'none' }}>Возможности</a>
          <a href="#pricing" style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-2)', textDecoration: 'none' }}>Тарифы</a>
          <a href="#docs" style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-2)', textDecoration: 'none' }}>Документация</a>
          <window.Button variant="ghost" size="sm" onClick={onSignIn}>Войти</window.Button>
          <window.Button variant="primary" size="sm" onClick={onCTA}>Начать расчёт</window.Button>
        </div>
      </nav>

      {/* Hero */}
      <section style={{
        padding: '96px 48px 80px',
        backgroundImage: "url('../../assets/grid-tile.svg')",
        backgroundSize: '80px 80px',
        backgroundRepeat: 'repeat',
        position: 'relative',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 0%, rgba(31,95,232,0.18), transparent 60%)', pointerEvents: 'none' }}/>
        <div style={{ position: 'relative', maxWidth: 1080, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 28, alignItems: 'flex-start' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--blue-300)', letterSpacing: '0.08em', textTransform: 'uppercase', padding: '4px 10px', background: 'var(--accent-tint)', border: '1px solid rgba(31,95,232,0.3)', borderRadius: 'var(--radius-sm)' }}>
            ИИ-АГЕНТ ДЛЯ РАСЧЁТА ПИР
          </span>
          <h1 style={{ fontFamily: 'var(--font-sans)', fontSize: 64, fontWeight: 600, lineHeight: 1.05, letterSpacing: '-0.02em', margin: 0, maxWidth: 920 }}>
            Стоимость проектно-изыскательных работ
            <br/>
            <span style={{ color: 'var(--blue-300)' }}>за 6 минут вместо 2 недель</span>
          </h1>
          <p style={{ fontFamily: 'var(--font-sans)', fontSize: 18, color: 'var(--fg-2)', lineHeight: 1.5, maxWidth: 720, margin: 0 }}>
            Загрузите техническое задание — агент извлечёт состав работ, сопоставит со справочниками базовых цен и подготовит расчёт ПИР в формате XLSX.
          </p>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <window.Button variant="primary" size="lg" onClick={onCTA} icon={<window.ArrowRight size={16}/>}>Запустить пробный расчёт</window.Button>
            <window.Button variant="secondary" size="lg">Смотреть демо</window.Button>
          </div>
          <div style={{ display: 'flex', gap: 32, marginTop: 16, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
            <div><span style={{ color: 'var(--fg-1)', fontSize: 18 }}>СБЦ-2020</span><br/>совместимые справочники</div>
            <div><span style={{ color: 'var(--fg-1)', fontSize: 18 }}>340+</span><br/>организаций используют</div>
            <div><span style={{ color: 'var(--fg-1)', fontSize: 18 }}>15 минут</span><br/>средний расчёт</div>
          </div>
        </div>
      </section>

      {/* Pipeline */}
      <section id="features" style={{ padding: '80px 48px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ maxWidth: 1080, margin: '0 auto' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>Как это работает</div>
          <h2 style={{ fontFamily: 'var(--font-sans)', fontSize: 38, fontWeight: 600, letterSpacing: '-0.015em', margin: '0 0 48px 0', maxWidth: 720 }}>
            Четыре шага от ТЗ до готовой сметы
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
            {[
              { n: '01', t: 'Загрузка ТЗ', d: 'PDF или DOCX до 50 МБ. Принимаются ТЗ в свободной форме и по ГОСТ 21.101.' },
              { n: '02', t: 'Извлечение работ', d: 'Агент анализирует документ и формирует структурированный список наименований работ.' },
              { n: '03', t: 'Согласование', d: 'Просмотр предварительного списка. Редактирование наименований, единиц, объёмов.' },
              { n: '04', t: 'Расчёт и экспорт', d: 'Сопоставление со справочниками. Выгрузка XLSX с разбивкой по разделам.' },
            ].map((s) => (
              <div key={s.n} style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', padding: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--blue-300)', letterSpacing: '0.06em' }}>ШАГ {s.n}</div>
                <div style={{ fontFamily: 'var(--font-sans)', fontSize: 17, fontWeight: 600, color: 'var(--fg-1)' }}>{s.t}</div>
                <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.5 }}>{s.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" style={{ padding: '80px 48px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ maxWidth: 1080, margin: '0 auto' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>Тарифы</div>
          <h2 style={{ fontFamily: 'var(--font-sans)', fontSize: 38, fontWeight: 600, letterSpacing: '-0.015em', margin: '0 0 48px 0' }}>Подписка по числу расчётов</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            {[
              { name: 'Старт', price: '12 000', recs: 'до 5 расчётов в месяц', feats: ['Все справочники СБЦ-2020', 'Экспорт XLSX', 'История расчётов 6 мес.'], ftd: false },
              { name: 'Бюро',  price: '34 000', recs: 'до 25 расчётов в месяц', feats: ['Всё из Старта', 'Командный доступ · 5 мест', 'API-интеграция', 'Приоритетная поддержка'], ftd: true },
              { name: 'Корпорация', price: 'По договору', recs: 'безлимит', feats: ['Всё из Бюро', 'Локальная установка', 'SLA 99.9%', 'Кастомные справочники'], ftd: false },
            ].map((p) => (
              <div key={p.name} style={{
                background: p.ftd ? 'linear-gradient(180deg, rgba(31,95,232,0.06), var(--bg-elevated))' : 'var(--bg-elevated)',
                border: `1px solid ${p.ftd ? 'var(--blue-500)' : 'var(--border-subtle)'}`,
                borderRadius: 'var(--radius-xl)',
                padding: 28,
                display: 'flex', flexDirection: 'column', gap: 16,
                position: 'relative',
              }}>
                {p.ftd && <span style={{ position: 'absolute', top: -10, left: 28, background: 'var(--blue-500)', color: '#fff', fontFamily: 'var(--font-mono)', fontSize: 10, padding: '3px 8px', borderRadius: 'var(--radius-sm)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Рекомендуем</span>}
                <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600, color: 'var(--fg-1)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{p.name}</div>
                <div>
                  <span style={{ fontFamily: 'var(--font-sans)', fontSize: 38, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.015em' }}>{p.price}</span>
                  {p.price !== 'По договору' && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--fg-3)', marginLeft: 6 }}>₽ / мес</span>}
                </div>
                <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-2)' }}>{p.recs}</div>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {p.feats.map((f) => (
                    <li key={f} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-2)' }}>
                      <span style={{ color: 'var(--success-400)', flex: 'none' }}><window.Check size={14}/></span>
                      {f}
                    </li>
                  ))}
                </ul>
                <window.Button variant={p.ftd ? 'primary' : 'secondary'} size="md" onClick={onCTA} style={{ marginTop: 'auto' }}>
                  {p.price === 'По договору' ? 'Связаться' : 'Подключить'}
                </window.Button>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer style={{ padding: '32px 48px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
        <span>© 2026 Интеллектуальное Строительство</span>
        <span>v 1.4.2 · СБЦ-2020</span>
      </footer>
    </div>
  );
}

Object.assign(window, { LandingScreen });

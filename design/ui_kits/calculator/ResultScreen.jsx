// ResultScreen — completed calculation, ready to export

const RESULT_ROWS = [
  { code: 'СБЦ-01.04', name: 'Инженерно-геодезические изыскания', section: 'Изыскания', qty: '1,00 объект',  base: '420 000', k: '1,15', total: '483 000' },
  { code: 'СБЦ-01.07', name: 'Инженерно-геологические изыскания', section: 'Изыскания', qty: '1,00 объект',  base: '380 000', k: '1,15', total: '437 000' },
  { code: 'СБЦ-02.11', name: 'Раздел АР',                          section: 'ПД',         qty: '12 540 м²',    base: '985 200', k: '1,26', total: '1 241 352' },
  { code: 'СБЦ-03.07', name: 'Раздел КР',                          section: 'ПД',         qty: '12 540 м²',    base: '522 600', k: '1,26', total: '658 476' },
  { code: 'СБЦ-04.02', name: 'ИОС · ОВиК',                          section: 'ПД',         qty: '12 540 м²',    base: '198 400', k: '1,26', total: '249 984' },
  { code: 'СБЦ-04.04', name: 'ИОС · ВиВ',                           section: 'ПД',         qty: '12 540 м²',    base: '152 800', k: '1,26', total: '192 528' },
  { code: 'СБЦ-04.06', name: 'ИОС · ЭС',                            section: 'ПД',         qty: '12 540 м²',    base: '142 600', k: '1,26', total: '179 676' },
  { code: 'СБЦ-05.03', name: 'Авторский надзор',                    section: 'Сопровождение', qty: '12 мес.',   base: '180 000', k: '1,00', total: '180 000' },
];

function ResultScreen({ onBackToProjects }) {
  return (
    <div style={{ flex: 1, padding: '24px 28px 48px', overflowY: 'auto', background: 'var(--bg-app)' }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <window.Stepper steps={['Загрузка ТЗ', 'Согласование', 'Расчёт', 'Экспорт']} current={3}/>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <window.Chip tone="success">Расчёт завершён</window.Chip>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 26, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.01em', marginTop: 4 }}>ЖК «Северный», корпус 4</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', letterSpacing: '0.04em' }}>PR-2026-0184 · 07.05.2026 · 12 540 м² · СБЦ-2020</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <window.Button variant="secondary" icon={<window.FileText size={14}/>}>PDF</window.Button>
            <window.Button variant="primary" icon={<window.Download size={14}/>}>Скачать XLSX</window.Button>
          </div>
        </div>

        {/* Total panel */}
        <div style={{ background: 'linear-gradient(180deg, rgba(31,95,232,0.08), var(--bg-elevated))', border: '1px solid var(--blue-700)', borderRadius: 'var(--radius-lg)', padding: 24, display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 24, alignItems: 'center' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--blue-300)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Итоговая стоимость ПИР</div>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 48, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums' }}>3 622 016 <span style={{ color: 'var(--fg-3)', fontSize: 28 }}>₽</span></div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>с учётом регионального коэффициента К=1,26 · без НДС</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Изыскания</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--fg-1)' }}>920 000 ₽</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)' }}>25,4%</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Проектирование</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--fg-1)' }}>2 522 016 ₽</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)' }}>69,6%</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Сопровождение</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--fg-1)' }}>180 000 ₽</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)' }}>5,0%</div>
          </div>
        </div>

        {/* Detail table */}
        <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 600 }}>Расшифровка по позициям</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{RESULT_ROWS.length} позиций</div>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-1)' }}>
            <thead style={{ background: 'var(--bg-raised)' }}>
              <tr>
                {['Код', 'Раздел', 'Наименование', 'Объём', 'Базовая', 'К', 'Стоимость'].map((h, i) => (
                  <th key={i} style={{ textAlign: i >= 3 ? 'right' : 'left', padding: '8px 14px', fontSize: 10, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-default)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody style={{ fontVariantNumeric: 'tabular-nums' }}>
              {RESULT_ROWS.map((r, i) => (
                <tr key={r.code + i} style={{ borderBottom: i < RESULT_ROWS.length - 1 ? '1px solid var(--border-subtle)' : 'none' }}>
                  <td style={{ padding: '9px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--blue-300)' }}>{r.code}</td>
                  <td style={{ padding: '9px 14px', color: 'var(--fg-2)', fontSize: 12 }}>{r.section}</td>
                  <td style={{ padding: '9px 14px' }}>{r.name}</td>
                  <td style={{ padding: '9px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>{r.qty}</td>
                  <td style={{ padding: '9px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>{r.base} ₽</td>
                  <td style={{ padding: '9px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>{r.k}</td>
                  <td style={{ padding: '9px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--fg-1)', fontWeight: 500 }}>{r.total} ₽</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ background: 'var(--bg-raised)' }}>
                <td colSpan="6" style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Итого</td>
                <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--fg-1)' }}>3 622 016 ₽</td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
          <window.Button variant="ghost" onClick={onBackToProjects}>← К списку проектов</window.Button>
          <div style={{ display: 'flex', gap: 8 }}>
            <window.Button variant="secondary" icon={<window.FileSpreadsheet size={14}/>}>Локальная смета</window.Button>
            <window.Button variant="primary" icon={<window.Download size={14}/>}>Скачать XLSX</window.Button>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ResultScreen });

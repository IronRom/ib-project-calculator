// ReviewScreen — extracted work items, editable

const INITIAL_ITEMS = [
  { id: 1, code: 'СБЦ-01.04', section: 'Изыскания',     name: 'Инженерно-геодезические изыскания',                 unit: 'объект', qty: '1,00',   confidence: 0.97 },
  { id: 2, code: 'СБЦ-01.07', section: 'Изыскания',     name: 'Инженерно-геологические изыскания',                 unit: 'объект', qty: '1,00',   confidence: 0.94 },
  { id: 3, code: 'СБЦ-02.11', section: 'ПД',            name: 'Раздел АР · архитектурные решения',                 unit: 'м²',     qty: '12 540', confidence: 0.99 },
  { id: 4, code: 'СБЦ-03.07', section: 'ПД',            name: 'Раздел КР · конструктивные решения',                unit: 'м²',     qty: '12 540', confidence: 0.99 },
  { id: 5, code: 'СБЦ-04.02', section: 'ПД',            name: 'Раздел ИОС · отопление, вентиляция, кондиционирование', unit: 'м²', qty: '12 540', confidence: 0.91 },
  { id: 6, code: 'СБЦ-04.04', section: 'ПД',            name: 'Раздел ИОС · водоснабжение и водоотведение',        unit: 'м²',     qty: '12 540', confidence: 0.93 },
  { id: 7, code: 'СБЦ-04.06', section: 'ПД',            name: 'Раздел ИОС · электроснабжение',                     unit: 'м²',     qty: '12 540', confidence: 0.96 },
  { id: 8, code: '—',         section: 'ПД',            name: 'Раздел СС · сети связи',                            unit: 'м²',     qty: '12 540', confidence: 0.62 },
  { id: 9, code: 'СБЦ-05.03', section: 'Сопровождение', name: 'Авторский надзор',                                  unit: 'мес.',   qty: '12',     confidence: 0.88 },
];

function ConfidenceDot({ value }) {
  const tone = value >= 0.9 ? 'var(--success-400)' : value >= 0.75 ? 'var(--warning-400)' : 'var(--danger-400)';
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 6, height: 6, borderRadius: 999, background: tone, flex: 'none' }}/>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', fontVariantNumeric: 'tabular-nums' }}>{Math.round(value * 100)}%</span>
    </div>
  );
}

function ReviewScreen({ onCalculate }) {
  const [items, setItems] = React.useState(INITIAL_ITEMS);
  const [editId, setEditId] = React.useState(null);

  const update = (id, patch) => setItems(items.map((it) => it.id === id ? { ...it, ...patch } : it));
  const remove = (id) => setItems(items.filter((it) => it.id !== id));
  const add = () => {
    const newId = Math.max(...items.map((i) => i.id)) + 1;
    setItems([...items, { id: newId, code: '—', section: 'ПД', name: 'Новая позиция', unit: 'шт.', qty: '1', confidence: 1 }]);
    setEditId(newId);
  };

  return (
    <div style={{ flex: 1, padding: '24px 28px 48px', overflowY: 'auto', background: 'var(--bg-app)' }}>
      <div style={{ maxWidth: 1180, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <window.Stepper steps={['Загрузка ТЗ', 'Согласование', 'Расчёт', 'Экспорт']} current={1}/>

        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 22, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.005em' }}>
              Извлечено {items.length} позиций
            </div>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-2)' }}>
              Проверьте и при необходимости отредактируйте состав работ. Низкая уверенность отмечена жёлтым/красным.
            </div>
          </div>
          <window.Button variant="primary" icon={<window.Calculator size={14}/>} onClick={onCalculate}>Запустить расчёт</window.Button>
        </div>

        {/* Warning banner */}
        <div style={{ background: 'var(--status-warning-bg)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: 'var(--radius-md)', padding: '10px 14px', display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ color: 'var(--warning-400)', flex: 'none' }}><window.AlertTriangle size={16}/></span>
          <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-2)' }}>
            Для позиции <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-1)' }}>«Раздел СС · сети связи»</span> не найден код в справочнике. Назначьте код вручную или удалите позицию.
          </span>
        </div>

        {/* Items table */}
        <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-1)' }}>
            <thead style={{ background: 'var(--bg-raised)' }}>
              <tr>
                {['№', 'Код', 'Раздел', 'Наименование работы', 'Ед.', 'Кол-во', 'Точность', ''].map((h, i) => (
                  <th key={i} style={{
                    textAlign: i === 5 ? 'right' : 'left',
                    padding: '10px 12px',
                    fontSize: 10, fontWeight: 600, color: 'var(--fg-3)',
                    textTransform: 'uppercase', letterSpacing: '0.06em',
                    borderBottom: '1px solid var(--border-default)',
                    width: i === 0 ? 36 : i === 1 ? 110 : i === 2 ? 130 : i === 4 ? 60 : i === 5 ? 100 : i === 6 ? 90 : i === 7 ? 70 : 'auto',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody style={{ fontVariantNumeric: 'tabular-nums' }}>
              {items.map((it, i) => {
                const isEdit = editId === it.id;
                return (
                  <tr key={it.id} style={{ borderBottom: i < items.length - 1 ? '1px solid var(--border-subtle)' : 'none', background: isEdit ? 'var(--accent-tint)' : 'transparent' }}>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{(i + 1).toString().padStart(2, '0')}</td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: it.code === '—' ? 'var(--danger-400)' : 'var(--blue-300)' }}>{it.code}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--fg-2)', fontSize: 12 }}>{it.section}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--fg-1)' }}>
                      {isEdit ? (
                        <input value={it.name} onChange={(e) => update(it.id, { name: e.target.value })}
                          autoFocus
                          style={{ width: '100%', background: 'var(--bg-input)', border: '1px solid var(--blue-500)', borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--fg-1)', fontFamily: 'var(--font-sans)', fontSize: 13, outline: 'none' }}/>
                      ) : (
                        <span onDoubleClick={() => setEditId(it.id)} style={{ cursor: 'text' }}>{it.name}</span>
                      )}
                    </td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>{it.unit}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{it.qty}</td>
                    <td style={{ padding: '10px 12px' }}><ConfidenceDot value={it.confidence}/></td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                        <button onClick={() => setEditId(isEdit ? null : it.id)} title={isEdit ? 'Готово' : 'Редактировать'}
                          style={{ background: 'transparent', border: 'none', color: isEdit ? 'var(--success-400)' : 'var(--fg-3)', cursor: 'pointer', padding: 4, borderRadius: 'var(--radius-sm)' }}>
                          {isEdit ? <window.Check size={14}/> : <window.Settings size={13}/>}
                        </button>
                        <button onClick={() => remove(it.id)} title="Удалить"
                          style={{ background: 'transparent', border: 'none', color: 'var(--fg-3)', cursor: 'pointer', padding: 4, borderRadius: 'var(--radius-sm)' }}>
                          <window.Trash size={13}/>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <window.Button variant="ghost" size="sm" icon={<window.Plus size={13}/>} onClick={add}>Добавить позицию</window.Button>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
              {items.length} позиций · средняя точность {Math.round(items.reduce((a, b) => a + b.confidence, 0) / items.length * 100)}%
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ReviewScreen });

// UploadScreen — drop a ТЗ; faked "AI extracting" progress

function UploadScreen({ onExtracted }) {
  const [file, setFile] = React.useState(null);
  const [progress, setProgress] = React.useState(0);
  const [stage, setStage] = React.useState(0);
  const [drag, setDrag] = React.useState(false);

  const stages = [
    'Чтение документа',
    'Извлечение разделов',
    'Распознавание наименований работ',
    'Сопоставление со справочниками',
    'Подготовка к согласованию',
  ];

  const startProcess = (f) => {
    setFile(f);
    setProgress(0); setStage(0);
    let p = 0;
    const t = setInterval(() => {
      p += 4;
      setProgress(p);
      setStage(Math.min(stages.length - 1, Math.floor((p / 100) * stages.length)));
      if (p >= 100) {
        clearInterval(t);
        setTimeout(() => onExtracted?.(), 400);
      }
    }, 90);
  };

  return (
    <div style={{ flex: 1, padding: '24px 28px 48px', overflowY: 'auto', background: 'var(--bg-app)' }}>
      <div style={{ maxWidth: 880, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 24 }}>
        <window.Stepper steps={['Загрузка ТЗ', 'Согласование', 'Расчёт', 'Экспорт']} current={0}/>

        {/* Project meta */}
        <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 15, fontWeight: 600, color: 'var(--fg-1)' }}>Параметры расчёта</div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12 }}>
            <window.Input label="Наименование объекта" value="ЖК «Северный», корпус 4" onChange={() => {}}/>
            <window.Select label="Стадия" value="pd" onChange={() => {}} options={[
              { value: 'pd', label: 'Проектная документация' },
              { value: 'rd', label: 'Рабочая документация' },
              { value: 'pd_rd', label: 'ПД + РД' },
            ]}/>
            <window.Input label="Площадь, м²" value="12 540" mono onChange={() => {}}/>
          </div>
        </div>

        {/* Upload zone */}
        {!file ? (
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); startProcess({ name: 'ТЗ_ЖК_Северный_корпус_4.pdf', size: '4.2 МБ' }); }}
            style={{
              background: drag ? 'var(--accent-tint)' : 'var(--bg-elevated)',
              border: `1px dashed ${drag ? 'var(--blue-500)' : 'var(--border-default)'}`,
              borderRadius: 'var(--radius-lg)',
              padding: 56,
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
              transition: 'background var(--duration-2) var(--ease-out)',
            }}>
            <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--accent-tint)', color: 'var(--blue-300)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <window.UploadCloud size={28}/>
            </div>
            <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 17, fontWeight: 600, color: 'var(--fg-1)' }}>Перетащите файл технического задания</div>
              <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-3)' }}>PDF или DOCX, до 50 МБ. ТЗ принимается в свободной форме и по ГОСТ&nbsp;21.101.</div>
            </div>
            <window.Button variant="primary" onClick={() => startProcess({ name: 'ТЗ_ЖК_Северный_корпус_4.pdf', size: '4.2 МБ' })}>Выбрать файл</window.Button>
          </div>
        ) : (
          <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', padding: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <div style={{ width: 40, height: 40, borderRadius: 'var(--radius-md)', background: 'var(--accent-tint)', color: 'var(--blue-300)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <window.FileText size={20}/>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: 'var(--font-sans)', fontSize: 14, fontWeight: 500, color: 'var(--fg-1)' }}>{file.name}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{file.size} · PDF</div>
              </div>
              <window.Chip tone="info">Шаг {stage + 1} из {stages.length}</window.Chip>
            </div>

            {/* Progress */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)' }}>
                <span>{stages[stage]}</span>
                <span>{progress}%</span>
              </div>
              <div style={{ height: 4, background: 'var(--bg-raised)', borderRadius: 999, overflow: 'hidden' }}>
                <div style={{ height: '100%', background: 'var(--blue-500)', width: `${progress}%`, transition: 'width var(--duration-2) linear' }}/>
              </div>
            </div>

            {/* Stage list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
              {stages.map((s, i) => (
                <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <div style={{
                    width: 18, height: 18, borderRadius: '50%', flex: 'none',
                    background: i < stage ? 'var(--success-400)' : i === stage ? 'var(--blue-500)' : 'var(--bg-raised)',
                    border: i > stage ? '1px solid var(--border-default)' : 'none',
                    color: '#fff',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {i < stage ? <window.Check size={11}/> : i === stage ? <window.Sparkles size={11}/> : null}
                  </div>
                  <span style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: i <= stage ? 'var(--fg-1)' : 'var(--fg-3)' }}>{s}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { UploadScreen });

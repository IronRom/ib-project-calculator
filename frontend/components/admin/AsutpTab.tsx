'use client'

import React, { useEffect, useState } from 'react'
import {
  listAsutpFactors, createAsutpFactor, updateAsutpFactor, deleteAsutpFactor,
  listAsutpModules, updateAsutpModule,
  AsutpFactorOption, AsutpFactorOptionIn, AsutpModule, AsutpModulePatch,
} from '@/lib/api'

const SCORE_COLS = ['score_or', 'score_oo', 'score_io', 'score_to', 'score_mo', 'score_po'] as const
const SCORE_LABELS = ['ОР', 'ОО', 'ИО', 'ТО', 'МО', 'ПО']

interface Props { bookId: number }

export function AsutpTab({ bookId }: Props) {
  const [innerTab, setInnerTab] = useState<'factors' | 'modules'>('factors')
  const [factors, setFactors]   = useState<AsutpFactorOption[]>([])
  const [modules, setModules]   = useState<AsutpModule[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [editingId, setEditingId]   = useState<number | null>(null)
  const [editDraft, setEditDraft]   = useState<AsutpFactorOptionIn | null>(null)
  const [addDraft, setAddDraft]     = useState<AsutpFactorOptionIn | null>(null)
  const [moduleEdits, setModuleEdits] = useState<Record<number, AsutpModulePatch>>({})

  useEffect(() => {
    Promise.all([listAsutpFactors(bookId), listAsutpModules(bookId)])
      .then(([f, m]) => { setFactors(f); setModules(m) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [bookId])

  async function handleSaveEdit(id: number) {
    if (!editDraft) return
    try {
      const updated = await updateAsutpFactor(bookId, id, editDraft)
      setFactors(f => f.map(x => x.id === id ? updated : x))
      setEditingId(null); setEditDraft(null)
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Ошибка') }
  }

  async function handleDelete(id: number) {
    if (!confirm('Удалить вариант фактора?')) return
    try {
      await deleteAsutpFactor(bookId, id)
      setFactors(f => f.filter(x => x.id !== id))
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Ошибка') }
  }

  async function handleAdd() {
    if (!addDraft) return
    try {
      const created = await createAsutpFactor(bookId, addDraft)
      setFactors(f => [...f, created])
      setAddDraft(null)
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Ошибка') }
  }

  async function handleSaveModule(id: number) {
    const patch = moduleEdits[id]
    if (!patch) return
    try {
      const updated = await updateAsutpModule(bookId, id, patch)
      setModules(m => m.map(x => x.id === id ? updated : x))
      setModuleEdits(e => { const n = {...e}; delete n[id]; return n })
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Ошибка') }
  }

  if (loading) return <div style={{ padding: 16, color: '#64748b' }}>Загрузка...</div>

  const grouped = new Map<string, AsutpFactorOption[]>()
  for (const f of factors) {
    if (!grouped.has(f.factor_code)) grouped.set(f.factor_code, [])
    grouped.get(f.factor_code)!.push(f)
  }

  const cellStyle: React.CSSProperties = {
    padding: '4px 8px', border: '1px solid #e2e8f0', fontSize: 12,
  }
  const numInputStyle: React.CSSProperties = {
    width: 44, textAlign: 'center', border: '1px solid #cbd5e1',
    borderRadius: 4, padding: '2px 4px', fontSize: 12,
  }

  return (
    <div style={{ padding: '12px 0' }}>
      {error && <div style={{ color: '#dc2626', marginBottom: 8, fontSize: 13 }}>{error}</div>}

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['factors', 'modules'] as const).map(t => (
          <button key={t} onClick={() => setInnerTab(t)} style={{
            padding: '4px 14px', borderRadius: 6, fontSize: 13,
            border: innerTab === t ? '2px solid #3b82f6' : '1px solid #cbd5e1',
            background: innerTab === t ? '#eff6ff' : 'white',
            fontWeight: innerTab === t ? 600 : 400, cursor: 'pointer',
          }}>
            {t === 'factors' ? 'Факторы' : 'Модули'}
          </button>
        ))}
      </div>

      {innerTab === 'factors' && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                <th style={cellStyle}>Фак.</th>
                <th style={cellStyle}>Код</th>
                <th style={{ ...cellStyle, minWidth: 220 }}>Описание</th>
                {SCORE_LABELS.map(l => <th key={l} style={{ ...cellStyle, textAlign: 'center' }}>{l}</th>)}
                <th style={cellStyle}></th>
              </tr>
            </thead>
            <tbody>
              {Array.from(grouped.entries()).map(([fcode, opts]) => (
                <React.Fragment key={fcode}>
                  <tr>
                    <td colSpan={3 + SCORE_LABELS.length + 1}
                        style={{ ...cellStyle, background: '#f0f4ff', fontWeight: 600, color: '#1e40af' }}>
                      {fcode} — {opts[0]?.factor_name}
                    </td>
                  </tr>
                  {opts.map(opt => (
                    <tr key={opt.id}>
                      {editingId === opt.id && editDraft ? (
                        <>
                          <td style={cellStyle}>{opt.factor_code}</td>
                          <td style={cellStyle}>
                            <input value={editDraft.option_code ?? ''}
                              onChange={e => setEditDraft({...editDraft, option_code: e.target.value})}
                              style={{ width: 60, ...numInputStyle }} />
                          </td>
                          <td style={cellStyle}>
                            <input value={editDraft.option_description ?? ''}
                              onChange={e => setEditDraft({...editDraft, option_description: e.target.value})}
                              style={{ width: '100%', border: '1px solid #cbd5e1', borderRadius: 4, padding: '2px 4px', fontSize: 12 }} />
                          </td>
                          {SCORE_COLS.map(k => (
                            <td key={k} style={{ ...cellStyle, textAlign: 'center' }}>
                              <input type="number" value={editDraft[k] ?? ''}
                                onChange={e => setEditDraft({...editDraft, [k]: e.target.value === '' ? null : Number(e.target.value)})}
                                style={numInputStyle} />
                            </td>
                          ))}
                          <td style={{ ...cellStyle, whiteSpace: 'nowrap' }}>
                            <button onClick={() => handleSaveEdit(opt.id)}
                              style={{ marginRight: 4, color: '#16a34a', cursor: 'pointer', background: 'none', border: 'none', fontWeight: 600 }}>✓</button>
                            <button onClick={() => { setEditingId(null); setEditDraft(null) }}
                              style={{ color: '#dc2626', cursor: 'pointer', background: 'none', border: 'none' }}>✕</button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td style={cellStyle}>{opt.factor_code}</td>
                          <td style={cellStyle}>{opt.option_code}</td>
                          <td style={cellStyle}>{opt.option_description}</td>
                          {SCORE_COLS.map(k => (
                            <td key={k} style={{ ...cellStyle, textAlign: 'center' }}>{opt[k] ?? '—'}</td>
                          ))}
                          <td style={{ ...cellStyle, whiteSpace: 'nowrap' }}>
                            <button onClick={() => { setEditingId(opt.id); setEditDraft({ ...opt }) }}
                              style={{ marginRight: 6, cursor: 'pointer', background: 'none', border: 'none', color: '#3b82f6' }}>✎</button>
                            <button onClick={() => handleDelete(opt.id)}
                              style={{ cursor: 'pointer', background: 'none', border: 'none', color: '#dc2626' }}>🗑</button>
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </React.Fragment>
              ))}
              {addDraft ? (
                <tr style={{ background: '#f0fdf4' }}>
                  <td style={cellStyle}>
                    <input value={addDraft.factor_code ?? ''} onChange={e => setAddDraft({...addDraft, factor_code: e.target.value})}
                      placeholder="Ф2" style={{ width: 40, ...numInputStyle }} />
                  </td>
                  <td style={cellStyle}>
                    <input value={addDraft.option_code ?? ''} onChange={e => setAddDraft({...addDraft, option_code: e.target.value})}
                      placeholder="п.1.1" style={{ width: 60, ...numInputStyle }} />
                  </td>
                  <td style={cellStyle}>
                    <input value={addDraft.option_description ?? ''} onChange={e => setAddDraft({...addDraft, option_description: e.target.value})}
                      placeholder="Описание варианта"
                      style={{ width: '100%', border: '1px solid #cbd5e1', borderRadius: 4, padding: '2px 4px', fontSize: 12 }} />
                  </td>
                  {SCORE_COLS.map(k => (
                    <td key={k} style={{ ...cellStyle, textAlign: 'center' }}>
                      <input type="number" value={addDraft[k] ?? ''}
                        onChange={e => setAddDraft({...addDraft, [k]: e.target.value === '' ? null : Number(e.target.value)})}
                        style={numInputStyle} />
                    </td>
                  ))}
                  <td style={{ ...cellStyle, whiteSpace: 'nowrap' }}>
                    <button onClick={handleAdd}
                      style={{ marginRight: 4, color: '#16a34a', cursor: 'pointer', background: 'none', border: 'none', fontWeight: 600 }}>✓</button>
                    <button onClick={() => setAddDraft(null)}
                      style={{ color: '#dc2626', cursor: 'pointer', background: 'none', border: 'none' }}>✕</button>
                  </td>
                </tr>
              ) : (
                <tr>
                  <td colSpan={3 + SCORE_LABELS.length + 1} style={{ padding: 8 }}>
                    <button onClick={() => setAddDraft({
                      factor_code: '', factor_name: '', option_code: '', option_description: '',
                      score_or: null, score_oo: null, score_io: null, score_to: null, score_mo: null, score_po: null,
                    })} style={{ fontSize: 12, color: '#3b82f6', cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}>
                      + Добавить вариант
                    </button>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {innerTab === 'modules' && (
        <table style={{ borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#f8fafc' }}>
              <th style={cellStyle}>Код</th>
              <th style={cellStyle}>S (тыс.руб.)</th>
              <th style={cellStyle}>Стадия Р мин%</th>
              <th style={cellStyle}>Стадия Р макс%</th>
              <th style={cellStyle}>Стадия П мин%</th>
              <th style={cellStyle}>Стадия П макс%</th>
              <th style={cellStyle}></th>
            </tr>
          </thead>
          <tbody>
            {modules.map(mod => {
              const patch = moduleEdits[mod.id] ?? {}
              const v = (field: keyof AsutpModule) =>
                (patch as Record<string, unknown>)[field] !== undefined
                  ? (patch as Record<string, unknown>)[field]
                  : mod[field]
              return (
                <tr key={mod.id}>
                  <td style={{ ...cellStyle, fontWeight: 600 }}>{mod.module_code}</td>
                  {(['s_value', 'stage_r_min', 'stage_r_max', 'stage_p_min', 'stage_p_max'] as const).map(f => (
                    <td key={f} style={cellStyle}>
                      <input type="number" value={String(v(f))}
                        onChange={e => setModuleEdits(eds => ({
                          ...eds, [mod.id]: { ...(eds[mod.id] ?? {}), [f]: Number(e.target.value) },
                        }))}
                        style={{ ...numInputStyle, width: f === 's_value' ? 70 : 50 }} />
                    </td>
                  ))}
                  <td style={cellStyle}>
                    {moduleEdits[mod.id] && (
                      <button onClick={() => handleSaveModule(mod.id)}
                        style={{ color: '#16a34a', cursor: 'pointer', background: 'none', border: 'none', fontWeight: 600 }}>
                        Сохранить
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

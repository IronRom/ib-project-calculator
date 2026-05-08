'use client'

import { useEffect, useState } from 'react'
import { listIndices, createIndex, deleteIndex, PriceIndex } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

export default function AdminIndicesPage() {
  const [indices, setIndices] = useState<PriceIndex[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ year: new Date().getFullYear(), quarter: 1, index_type: 'project', index_value: '', source_ref: '' })
  const [error, setError] = useState('')

  useEffect(() => {
    listIndices().then(setIndices).finally(() => setLoading(false))
  }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const idx = await createIndex({
        year: form.year,
        quarter: form.quarter,
        index_type: form.index_type,
        index_value: parseFloat(form.index_value),
        source_ref: form.source_ref,
      })
      setIndices((prev) => [idx, ...prev])
      setShowForm(false)
      setForm({ year: new Date().getFullYear(), quarter: 1, index_type: 'project', index_value: '', source_ref: '' })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    }
  }

  async function handleDelete(id: number) {
    if (!confirm('Удалить индекс?')) return
    await deleteIndex(id)
    setIndices((prev) => prev.filter((x) => x.id !== id))
  }

  return (
    <>
      <Topbar
        title="Индексы Минстроя"
        breadcrumb="Администрирование"
        actions={<Button variant="primary" onClick={() => setShowForm(!showForm)}>+ Добавить индекс</Button>}
      />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ fontSize: 13, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>
          Источник: квартальные письма Минстроя, Приложение №3, п.1 = проектные работы
        </div>

        {showForm && (
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', padding: 24 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Новый индекс</div>
            <form onSubmit={handleCreate} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <Input label="Год" type="number" value={String(form.year)} onChange={(e) => setForm({ ...form, year: parseInt(e.target.value) })} required />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-2)' }}>Квартал</label>
                <select
                  value={form.quarter}
                  onChange={(e) => setForm({ ...form, quarter: parseInt(e.target.value) })}
                  style={{ background: 'var(--bg-input)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', padding: '8px 12px', fontSize: 13, color: 'var(--fg-1)', outline: 'none' }}
                >
                  {[1, 2, 3, 4].map((q) => <option key={q} value={q}>Q{q}</option>)}
                </select>
              </div>
              <Input label="Значение индекса" type="number" value={form.index_value} onChange={(e) => setForm({ ...form, index_value: e.target.value })} placeholder="6.88" required />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-2)' }}>Тип</label>
                <select
                  value={form.index_type}
                  onChange={(e) => setForm({ ...form, index_type: e.target.value })}
                  style={{ background: 'var(--bg-input)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', padding: '8px 12px', fontSize: 13, color: 'var(--fg-1)', outline: 'none' }}
                >
                  <option value="project">Проектные работы</option>
                  <option value="survey">Изыскательские работы</option>
                </select>
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <Input label="Источник (письмо Минстроя)" value={form.source_ref} onChange={(e) => setForm({ ...form, source_ref: e.target.value })} placeholder="№62725-ИФ/09 от 20.10.2025, Прил.3 п.1" required />
              </div>
              {error && <div style={{ gridColumn: '1 / -1', color: 'var(--danger-400)', fontSize: 13 }}>{error}</div>}
              <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 10 }}>
                <Button type="submit" variant="primary">Сохранить</Button>
                <Button variant="secondary" onClick={() => setShowForm(false)}>Отмена</Button>
              </div>
            </form>
          </div>
        )}

        {!loading && (
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Загруженные индексы</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{indices.length} записей</div>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead style={{ background: 'var(--bg-raised)' }}>
                <tr>
                  {['Год / Квартал', 'Тип', 'Значение', 'Источник', ''].map((h, i) => (
                    <th key={i} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-default)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {indices.map((idx, i) => (
                  <tr key={idx.id} style={{ borderBottom: i < indices.length - 1 ? 'var(--hairline)' : 'none' }}>
                    <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{idx.year} Q{idx.quarter}</td>
                    <td style={{ padding: '12px 14px', color: 'var(--fg-2)' }}>{idx.index_type === 'project' ? 'Проектные' : 'Изыскательские'}</td>
                    <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--blue-300)' }}>{idx.index_value}</td>
                    <td style={{ padding: '12px 14px', fontSize: 12, color: 'var(--fg-3)' }}>{idx.source_ref}</td>
                    <td style={{ padding: '12px 14px', textAlign: 'right' }}>
                      <Button size="sm" variant="danger" onClick={() => handleDelete(idx.id)}>×</Button>
                    </td>
                  </tr>
                ))}
                {indices.length === 0 && (
                  <tr><td colSpan={5} style={{ padding: 32, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>Индексы не добавлены</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

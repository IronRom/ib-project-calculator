'use client'

import React, { useEffect, useRef, useState } from 'react'
import { listReferences, activateReference, rollbackReference, exportReferenceExcel, importReferenceExcel, deleteReference, listHints, createHint, updateHint, deleteHint, ReferenceBook, ExtractionHint, ExtractionHintIn } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const STATUS_LABELS: Record<string, { label: string; tone: 'success' | 'warning' | 'info' | 'danger' | 'default' }> = {
  requires_parsing:    { label: 'Требует парсинга',  tone: 'warning'  },
  requires_validation: { label: 'Требует валидации', tone: 'warning'  },
  consistent:          { label: 'Консистентен',      tone: 'success'  },
  archived:            { label: 'Архив',              tone: 'default'  },
  error:               { label: 'Ошибка',            tone: 'danger'   },
}

interface ParseState {
  bookId: number
  message: string
  page: number
  total: number
  done: boolean
  error: string
}

export default function AdminReferencesPage() {
  const [books, setBooks] = useState<ReferenceBook[]>([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState<number | null>(null)
  const [parseState, setParseState] = useState<ParseState | null>(null)
  const [error, setError] = useState('')
  const [expandedHintsId, setExpandedHintsId] = useState<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const importingBookId = useRef<number | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    listReferences().then(setBooks).finally(() => setLoading(false))
    return () => { esRef.current?.close() }
  }, [])

  async function handleActivate(book: ReferenceBook) {
    try {
      const updated = await activateReference(book.id)
      setBooks((prev) => prev.map((b) => b.code === updated.code ? (b.id === updated.id ? updated : { ...b, is_active: false }) : b))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка')
    }
  }

  async function handleDelete(book: ReferenceBook) {
    if (!confirm(`Удалить справочник ${book.code} v${book.version}? Все строки будут удалены.`)) return
    try {
      await deleteReference(book.id)
      setBooks((prev) => prev.filter((b) => b.id !== book.id))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка удаления')
    }
  }

  async function handleRollback(book: ReferenceBook) {
    if (!confirm('Откатить активный справочник к предыдущей версии?')) return
    try {
      const updated = await rollbackReference(book.id)
      setBooks((prev) => prev.map((b) => b.id === updated.id ? updated : b))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка')
    }
  }

  async function handleExport(book: ReferenceBook) {
    try {
      await exportReferenceExcel(book.id, `${book.code}_v${book.version}.xlsx`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка экспорта')
    }
  }

  function handleImportClick(bookId: number) {
    importingBookId.current = bookId
    fileInputRef.current?.click()
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    const bookId = importingBookId.current
    if (!file || !bookId) return
    e.target.value = ''
    setImporting(bookId)
    setError('')
    try {
      const updated = await importReferenceExcel(bookId, file)
      setBooks((prev) => prev.map((b) => b.id === updated.id ? updated : b))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка импорта')
    } finally {
      setImporting(null)
      importingBookId.current = null
    }
  }

  function handleParse(book: ReferenceBook) {
    esRef.current?.close()
    const token = typeof window !== 'undefined' ? localStorage.getItem('pir_token') : ''
    const url = `${BASE}/admin/references/${book.id}/parse${token ? `?token=${token}` : ''}`
    const es = new EventSource(url)
    esRef.current = es

    setParseState({ bookId: book.id, message: 'Запуск…', page: 0, total: 0, done: false, error: '' })
    setError('')

    es.addEventListener('progress', (e) => {
      const d = JSON.parse(e.data)
      setParseState((prev) => prev ? { ...prev, message: d.message, page: d.page, total: d.total } : prev)
    })

    es.addEventListener('done', (e) => {
      const d = JSON.parse(e.data)
      es.close()
      setParseState((prev) => prev ? { ...prev, done: true, message: `Готово: ${d.rows_parsed} строк` } : prev)
      listReferences().then(setBooks)
    })

    es.addEventListener('error', (e) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const msg = (e as any).data ? JSON.parse((e as any).data).message : 'Ошибка парсинга'
      es.close()
      setParseState((prev) => prev ? { ...prev, error: msg } : prev)
    })
  }

  const isParsing = (bookId: number) => parseState?.bookId === bookId && !parseState.done && !parseState.error

  return (
    <>
      <Topbar title="Справочники СБЦП / МРР" breadcrumb="Администрирование" />
      <input ref={fileInputRef} type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleFileChange} />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {error && (
          <div style={{ padding: '10px 14px', background: 'var(--status-danger-bg)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--danger-400)' }}>
            {error}
          </div>
        )}

        {parseState && (
          <div style={{
            padding: '12px 16px',
            background: parseState.error ? 'var(--status-danger-bg)' : parseState.done ? 'var(--status-success-bg)' : 'var(--bg-elevated)',
            border: `1px solid ${parseState.error ? 'var(--danger-500)' : parseState.done ? 'var(--success-500)' : 'var(--border-default)'}`,
            borderRadius: 'var(--radius-md)',
            fontSize: 13,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}>
            {!parseState.done && !parseState.error && (
              <div style={{ width: 14, height: 14, border: '2px solid var(--blue-400)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite', flexShrink: 0 }} />
            )}
            <div style={{ flex: 1 }}>
              <div style={{ color: parseState.error ? 'var(--danger-400)' : parseState.done ? 'var(--success-400)' : 'var(--fg-1)' }}>
                {parseState.error || parseState.message}
              </div>
              {!parseState.done && !parseState.error && parseState.total > 0 && (
                <div style={{ marginTop: 6, height: 4, background: 'var(--bg-raised)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${(parseState.page / parseState.total) * 100}%`, background: 'var(--blue-400)', transition: 'width 0.3s ease', borderRadius: 2 }} />
                </div>
              )}
            </div>
            {(parseState.done || parseState.error) && (
              <button onClick={() => setParseState(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-3)', fontSize: 16, lineHeight: 1, padding: 0 }}>×</button>
            )}
          </div>
        )}

        {loading ? (
          <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>
        ) : books.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            Справочники не загружены. Используйте API или загрузите PDF через endpoint POST /admin/references
          </div>
        ) : (
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Справочники</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{books.length} записей</div>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead style={{ background: 'var(--bg-raised)' }}>
                <tr>
                  {['Код', 'Наименование', 'Версия', 'Статус', 'Загружен', ''].map((h, i) => (
                    <th key={i} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-default)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {books.map((book, i) => {
                  const st = STATUS_LABELS[book.status] || { label: book.status, tone: 'default' as const }
                  const isImporting = importing === book.id
                  const parsing = isParsing(book.id)
                  return (
                    <React.Fragment key={book.id}>
                      <tr style={{ borderBottom: expandedHintsId === book.id ? 'none' : i < books.length - 1 ? 'var(--hairline)' : 'none' }}>
                        <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--blue-300)' }}>
                          {book.code}
                          {book.is_active && <Chip tone="info" style={{ marginLeft: 8 }}>Активен</Chip>}
                        </td>
                        <td style={{ padding: '12px 14px', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {book.official_name}
                        </td>
                        <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>v{book.version}</td>
                        <td style={{ padding: '12px 14px' }}>
                          <Chip tone={st.tone}>{st.label}</Chip>
                        </td>
                        <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                          {new Date(book.uploaded_at).toLocaleDateString('ru-RU')}
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                            {book.status === 'requires_parsing' && (
                              <Button size="sm" variant="secondary" disabled={parsing} onClick={() => handleParse(book)}>
                                {parsing
                                  ? `${parseState!.page}/${parseState!.total || '?'} стр.`
                                  : 'Парсить PDF'}
                              </Button>
                            )}
                            <Button size="sm" variant="secondary" onClick={() => handleExport(book)}>
                              ↓ Excel
                            </Button>
                            <Button size="sm" variant="secondary" disabled={isImporting} onClick={() => handleImportClick(book.id)}>
                              {isImporting ? 'Загрузка…' : '↑ Excel'}
                            </Button>
                            {book.status === 'consistent' && !book.is_active && (
                              <Button size="sm" variant="primary" onClick={() => handleActivate(book)}>Активировать</Button>
                            )}
                            {book.is_active && (
                              <Button size="sm" variant="danger" onClick={() => handleRollback(book)}>Откатить</Button>
                            )}
                            {!book.is_active && (
                              <Button size="sm" variant="danger" onClick={() => handleDelete(book)}>Удалить</Button>
                            )}
                            <Button
                              size="sm"
                              variant={expandedHintsId === book.id ? 'primary' : 'secondary'}
                              onClick={() => setExpandedHintsId(expandedHintsId === book.id ? null : book.id)}
                            >
                              Условия
                            </Button>
                          </div>
                        </td>
                      </tr>
                      {expandedHintsId === book.id && (
                        <tr>
                          <td colSpan={6} style={{ padding: 0, background: 'var(--bg-surface)', borderBottom: i < books.length - 1 ? 'var(--hairline)' : 'none' }}>
                            <HintsPanel bookId={book.id} bookCode={book.code} onClose={() => setExpandedHintsId(null)} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  )
}

const EMPTY_HINT: ExtractionHintIn = {
  trigger_condition: '',
  implied_work: '',
  hint_for_ai: '',
  justification: '',
  is_active: true,
  sort_order: 0,
}

function HintsPanel({ bookId, bookCode, onClose }: { bookId: number; bookCode: string; onClose: () => void }) {
  const [hints, setHints] = useState<ExtractionHint[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [form, setForm] = useState<ExtractionHintIn>(EMPTY_HINT)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    listHints(bookId).then(setHints).finally(() => setLoading(false))
  }, [bookId])

  function startEdit(h: ExtractionHint) {
    setEditingId(h.id)
    const { id: _id, book_version_id: _bv, ...rest } = h
    setForm(rest)
    setError('')
  }

  function startNew() {
    setEditingId('new')
    setForm({ ...EMPTY_HINT, sort_order: hints.length * 10 })
    setError('')
  }

  async function handleSave() {
    setSaving(true); setError('')
    try {
      if (editingId === 'new') {
        const h = await createHint(bookId, form)
        setHints(prev => [...prev, h].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id))
      } else {
        const h = await updateHint(bookId, editingId as number, form)
        setHints(prev => prev.map(x => x.id === h.id ? h : x))
      }
      setEditingId(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(h: ExtractionHint) {
    if (!confirm('Удалить условие извлечения?')) return
    try {
      await deleteHint(bookId, h.id)
      setHints(prev => prev.filter(x => x.id !== h.id))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка удаления')
    }
  }

  const ta: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box', padding: '6px 8px', fontSize: 12,
    background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-sm)', color: 'var(--fg-1)', resize: 'vertical',
    fontFamily: 'inherit', lineHeight: 1.5,
  }

  return (
    <div style={{ padding: '16px 20px', borderTop: '1px solid var(--blue-500)', background: 'var(--bg-surface)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>
          Условия извлечения — <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--blue-300)' }}>{bookCode}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {editingId === null && (
            <Button size="sm" variant="primary" onClick={startNew}>+ Добавить</Button>
          )}
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-3)', fontSize: 18, lineHeight: 1, padding: '0 4px' }}>×</button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '8px 12px', background: 'var(--status-danger-bg)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-sm)', fontSize: 12, color: 'var(--danger-400)', marginBottom: 10 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ fontSize: 12, color: 'var(--fg-3)', padding: '8px 0' }}>Загрузка…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>

          {hints.map(h => editingId === h.id ? (
            <HintForm key={h.id} form={form} setForm={setForm} saving={saving} onSave={handleSave} onCancel={() => setEditingId(null)} error={error} ta={ta} />
          ) : (
            <div key={h.id} style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', padding: '10px 14px', display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <div style={{ minWidth: 32, textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', paddingTop: 2 }}>{h.sort_order}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 2 }}>{h.trigger_condition}</div>
                <div style={{ fontSize: 12, color: 'var(--blue-300)' }}>→ {h.implied_work}</div>
                {h.justification && (
                  <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 4, fontStyle: 'italic' }}>{h.justification}</div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                {!h.is_active && <span style={{ fontSize: 10, padding: '2px 6px', background: 'var(--bg-raised)', borderRadius: 99, color: 'var(--fg-4)' }}>откл.</span>}
                <Button size="sm" variant="secondary" onClick={() => startEdit(h)}>Ред.</Button>
                <Button size="sm" variant="danger" onClick={() => handleDelete(h)}>✕</Button>
              </div>
            </div>
          ))}

          {editingId === 'new' && (
            <HintForm form={form} setForm={setForm} saving={saving} onSave={handleSave} onCancel={() => setEditingId(null)} error={error} ta={ta} isNew />
          )}

          {hints.length === 0 && editingId === null && (
            <div style={{ fontSize: 12, color: 'var(--fg-3)', padding: '8px 0' }}>Нет условий. Нажмите «+ Добавить» чтобы создать первое.</div>
          )}
        </div>
      )}
    </div>
  )
}

function HintForm({ form, setForm, saving, onSave, onCancel, error: _error, ta, isNew }: {
  form: ExtractionHintIn
  setForm: React.Dispatch<React.SetStateAction<ExtractionHintIn>>
  saving: boolean
  onSave: () => void
  onCancel: () => void
  error: string
  ta: React.CSSProperties
  isNew?: boolean
}) {
  const f = (key: keyof ExtractionHintIn) => (
    (e: React.ChangeEvent<HTMLTextAreaElement | HTMLInputElement>) =>
      setForm(prev => ({ ...prev, [key]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value }))
  )

  return (
    <div style={{ background: 'var(--bg-raised)', border: '1px solid var(--blue-500)', borderRadius: 'var(--radius-md)', padding: '12px 14px' }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--blue-300)', marginBottom: 10 }}>
        {isNew ? 'Новое условие' : 'Редактирование'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
        <div>
          <label style={{ fontSize: 11, color: 'var(--fg-3)', display: 'block', marginBottom: 3 }}>Триггер (когда применяется)</label>
          <textarea rows={2} value={form.trigger_condition} onChange={f('trigger_condition')} style={ta} />
        </div>
        <div>
          <label style={{ fontSize: 11, color: 'var(--fg-3)', display: 'block', marginBottom: 3 }}>Подразумеваемая работа</label>
          <textarea rows={2} value={form.implied_work} onChange={f('implied_work')} style={ta} />
        </div>
      </div>
      <div style={{ marginBottom: 10 }}>
        <label style={{ fontSize: 11, color: 'var(--fg-3)', display: 'block', marginBottom: 3 }}>Инструкция для AI (hint_for_ai) — инжектируется в контекст извлечения</label>
        <textarea rows={4} value={form.hint_for_ai} onChange={f('hint_for_ai')} style={{ ...ta, fontFamily: 'var(--font-mono)', fontSize: 11 }} />
      </div>
      <div style={{ marginBottom: 10 }}>
        <label style={{ fontSize: 11, color: 'var(--fg-3)', display: 'block', marginBottom: 3 }}>Обоснование (показывается пользователю под объектом ПИР)</label>
        <textarea rows={2} value={form.justification} onChange={f('justification')} style={ta} />
      </div>
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 10 }}>
        <div>
          <label style={{ fontSize: 11, color: 'var(--fg-3)', display: 'block', marginBottom: 3 }}>Порядок сортировки</label>
          <input type="number" value={form.sort_order} onChange={f('sort_order')} style={{ ...ta, width: 80, resize: 'none' }} />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer', marginTop: 12 }}>
          <input type="checkbox" checked={form.is_active} onChange={f('is_active')} />
          Активно
        </label>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Button size="sm" variant="primary" disabled={saving} onClick={onSave}>{saving ? 'Сохранение…' : 'Сохранить'}</Button>
        <Button size="sm" variant="secondary" onClick={onCancel}>Отмена</Button>
      </div>
    </div>
  )
}

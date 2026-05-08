'use client'

import { useEffect, useRef, useState } from 'react'
import { listReferences, activateReference, rollbackReference, exportReferenceExcel, importReferenceExcel, deleteReference, ReferenceBook } from '@/lib/api'
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
                    <tr key={book.id} style={{ borderBottom: i < books.length - 1 ? 'var(--hairline)' : 'none' }}>
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
                        </div>
                      </td>
                    </tr>
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

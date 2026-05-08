'use client'

import { useEffect, useState } from 'react'
import { listReferences, activateReference, rollbackReference, ReferenceBook } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'

const STATUS_LABELS: Record<string, { label: string; tone: 'success' | 'warning' | 'info' | 'danger' | 'default' }> = {
  requires_validation: { label: 'Требует валидации', tone: 'warning'  },
  consistent:          { label: 'Консистентен',      tone: 'success'  },
  archived:            { label: 'Архив',              tone: 'default'  },
  error:               { label: 'Ошибка',            tone: 'danger'   },
}

export default function AdminReferencesPage() {
  const [books, setBooks] = useState<ReferenceBook[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listReferences().then(setBooks).finally(() => setLoading(false))
  }, [])

  async function handleActivate(book: ReferenceBook) {
    const updated = await activateReference(book.id)
    setBooks((prev) => prev.map((b) => b.code === updated.code ? (b.id === updated.id ? updated : { ...b, is_active: false }) : b))
  }

  async function handleRollback(book: ReferenceBook) {
    if (!confirm('Откатить активный справочник к предыдущей версии?')) return
    const updated = await rollbackReference(book.id)
    setBooks((prev) => prev.map((b) => b.id === updated.id ? updated : b))
  }

  return (
    <>
      <Topbar title="Справочники СБЦП / МРР" breadcrumb="Администрирование" />
      <div style={{ padding: '24px 28px' }}>
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
                        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                          {book.status === 'consistent' && !book.is_active && (
                            <Button size="sm" variant="primary" onClick={() => handleActivate(book)}>Активировать</Button>
                          )}
                          {book.is_active && (
                            <Button size="sm" variant="danger" onClick={() => handleRollback(book)}>Откатить</Button>
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
    </>
  )
}

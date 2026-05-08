'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { getCalculation, Calculation, ExtractedEntity } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'

const CATEGORY_LABELS: Record<string, string> = {
  new_construction: 'Новое строительство',
  reconstruction:   'Реконструкция',
  overhaul:         'Капремонт',
}

const CATEGORY_TONES: Record<string, 'success' | 'warning' | 'info'> = {
  new_construction: 'success',
  reconstruction:   'warning',
  overhaul:         'info',
}

export default function EntitiesPage() {
  const { id } = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const calcId = searchParams.get('calc')
  const router = useRouter()
  const [calc, setCalc] = useState<Calculation | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!calcId) return
    getCalculation(Number(id), Number(calcId))
      .then(setCalc)
      .finally(() => setLoading(false))
  }, [id, calcId])

  if (loading) return <div style={{ padding: 28, color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>

  const result = calc?.extracted_entities
  const entities = result?.entities ?? []

  return (
    <>
      <Topbar
        title="Извлечённые объекты"
        breadcrumb="Проекты / Анализ ТЗ"
        actions={
          <div style={{ display: 'flex', gap: 10 }}>
            <Button variant="secondary" onClick={() => router.push(`/projects/${id}`)}>
              ← Назад к проекту
            </Button>
          </div>
        }
      />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Confidence + missing data */}
        {result && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <ConfidenceBadge value={result.overall_confidence} />
            {result.stage && (
              <div style={{ padding: '6px 12px', background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }}>
                Стадия: <strong style={{ color: 'var(--fg-1)' }}>{result.stage}</strong>
              </div>
            )}
            {result.region && (
              <div style={{ padding: '6px 12px', background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }}>
                Регион: <strong style={{ color: 'var(--fg-1)' }}>{result.region}</strong>
              </div>
            )}
          </div>
        )}

        {result?.missing_data && result.missing_data.length > 0 && (
          <div style={{ padding: '12px 16px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--warning-400)', marginBottom: 6 }}>
              Не удалось определить из ТЗ:
            </div>
            <ul style={{ margin: 0, padding: '0 0 0 16px', fontSize: 12, color: 'var(--warning-400)' }}>
              {result.missing_data.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </div>
        )}

        {/* Entities table */}
        {entities.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            AI не смог извлечь объекты из ТЗ. Попробуйте загрузить другой файл или обратитесь к администратору.
          </div>
        ) : (
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Объекты ПИР</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{entities.length} позиций</div>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead style={{ background: 'var(--bg-raised)' }}>
                  <tr>
                    {['Категория', 'Тип объекта', 'Наименование', 'Адрес', 'X', 'Ед.', 'Коэф.', 'Уверенность'].map((h, i) => (
                      <th key={i} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-default)', whiteSpace: 'nowrap' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {entities.map((entity, i) => (
                    <EntityRow key={i} entity={entity} isLast={i === entities.length - 1} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {entities.length > 0 && (
          <div style={{ display: 'flex', gap: 12, padding: '16px 0' }}>
            <div style={{ flex: 1, padding: '14px 18px', background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', fontSize: 13, color: 'var(--fg-2)' }}>
              Проверьте корректность извлечённых данных. При необходимости — вернитесь к проекту и загрузите уточнённое ТЗ.
            </div>
          </div>
        )}
      </div>
    </>
  )
}

function EntityRow({ entity, isLast }: { entity: ExtractedEntity; isLast: boolean }) {
  const tone = CATEGORY_TONES[entity.category] || 'default'
  const label = CATEGORY_LABELS[entity.category] || entity.category

  return (
    <tr style={{ borderBottom: isLast ? 'none' : 'var(--hairline)' }}>
      <td style={{ padding: '12px 14px' }}>
        <Chip tone={tone}>{label}</Chip>
      </td>
      <td style={{ padding: '12px 14px', fontWeight: 500 }}>{entity.object_type}</td>
      <td style={{ padding: '12px 14px', color: 'var(--fg-2)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entity.object_name}</td>
      <td style={{ padding: '12px 14px', color: 'var(--fg-3)', fontSize: 12, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entity.address || '—'}</td>
      <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, textAlign: 'right' }}>
        {entity.x_value != null ? entity.x_value.toLocaleString('ru-RU', { maximumFractionDigits: 4 }) : '—'}
      </td>
      <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{entity.x_unit || '—'}</td>
      <td style={{ padding: '12px 14px' }}>
        {entity.coefficients && entity.coefficients.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {entity.coefficients.map((c, i) => (
              <span key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)' }}>
                ×{c.value} {c.name}
              </span>
            ))}
          </div>
        ) : <span style={{ color: 'var(--fg-4)', fontSize: 12 }}>—</span>}
      </td>
      <td style={{ padding: '12px 14px' }}>
        <ConfidenceBadge value={entity.confidence ?? 0} small />
      </td>
    </tr>
  )
}

function ConfidenceBadge({ value, small }: { value: number; small?: boolean }) {
  const pct = Math.round(value * 100)
  const tone = pct >= 80 ? 'success' : pct >= 60 ? 'warning' : 'danger'
  if (small) return <Chip tone={tone}>{pct}%</Chip>
  return (
    <div style={{ padding: '8px 14px', background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>Уверенность AI:</span>
      <Chip tone={tone}>{pct}%</Chip>
    </div>
  )
}

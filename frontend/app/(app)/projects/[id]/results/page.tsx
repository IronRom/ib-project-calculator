'use client'

import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { computeCalculation, getCalculation, CalculationResult, CalcPosition } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'

function fmt(n: number): string {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

const th: React.CSSProperties = {
  textAlign: 'left', padding: '9px 12px', fontSize: 11, fontWeight: 600,
  color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em',
  borderBottom: '1px solid var(--border-default)', whiteSpace: 'nowrap',
}
const td: React.CSSProperties = { padding: '10px 12px', fontSize: 13, verticalAlign: 'top' }
const tdMono: React.CSSProperties = { ...td, fontFamily: 'var(--font-mono)', fontSize: 12 }

function SummaryRow({ label, value, bold, indent, note }: { label: string; value?: string; bold?: boolean; indent?: boolean; note?: string }) {
  return (
    <tr>
      <td colSpan={5} style={{ ...td, paddingLeft: indent ? 28 : 12, fontWeight: bold ? 600 : 400, color: 'var(--fg-2)', fontSize: 13 }}>
        {label}
        {note && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginLeft: 8 }}>{note}</span>}
      </td>
      <td style={{ ...td, fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: bold ? 700 : 400, color: bold ? 'var(--fg-1)' : 'var(--fg-2)', textAlign: 'right', whiteSpace: 'nowrap' }}>
        {value ?? ''}
      </td>
    </tr>
  )
}

export default function ResultsPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const projectId = Number(params.id)
  const calcId = Number(searchParams.get('calc'))

  const [result, setResult] = useState<CalculationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!calcId) return
    // Check if calculation_result already exists
    getCalculation(projectId, calcId).then((calc) => {
      if (calc.calculation_result) {
        setResult(calc.calculation_result as unknown as CalculationResult)
      }
    })
  }, [projectId, calcId])

  async function handleCompute() {
    setLoading(true); setError('')
    try {
      const r = await computeCalculation(projectId, calcId)
      setResult(r)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка расчёта')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Topbar
        title="Расчёт стоимости ПИР"
        breadcrumb="Проект"
        actions={
          <Button variant="primary" disabled={loading || !calcId} onClick={handleCompute}>
            {loading ? 'Расчёт…' : result ? 'Пересчитать' : 'Рассчитать'}
          </Button>
        }
      />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {!calcId && (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            Откройте эту страницу из проекта с параметром ?calc=ID
          </div>
        )}

        {error && (
          <div style={{ padding: '10px 14px', background: 'var(--status-danger-bg)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--danger-400)' }}>
            {error}
          </div>
        )}

        {result && result.errors.length > 0 && (
          <div style={{ padding: '12px 16px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--warning-400)' }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Не удалось найти данные для позиций:</div>
            {result.errors.map((e, i) => <div key={i} style={{ marginLeft: 12 }}>• {e}</div>)}
          </div>
        )}

        {result && (
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
            {/* Header */}
            <div style={{ padding: '16px 20px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)' }}>Форма 2ПС ИР — Сметный расчёт</div>
                <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
                  Стадия: {result.stage} · Индекс: {result.price_index} ({result.price_index_period})
                </div>
              </div>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead style={{ background: 'var(--bg-raised)' }}>
                  <tr>
                    <th style={{ ...th, width: 36 }}>№</th>
                    <th style={th}>Наименование работ</th>
                    <th style={{ ...th, width: 90 }}>Ед. изм.</th>
                    <th style={{ ...th, width: 70 }}>Кол-во</th>
                    <th style={th}>Обоснование стоимости</th>
                    <th style={th}>Расчёт стоимости</th>
                    <th style={{ ...th, textAlign: 'right', width: 130 }}>Стоимость, руб.</th>
                  </tr>
                  <tr style={{ background: 'var(--bg-raised)' }}>
                    {[1,2,3,4,5,6,7].map((n) => (
                      <td key={n} style={{ ...tdMono, color: 'var(--fg-3)', textAlign: 'center', borderBottom: '1px solid var(--border-default)', paddingTop: 4, paddingBottom: 8 }}>{n}</td>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.positions.map((pos: CalcPosition, i: number) => (
                    <tr key={i} style={{ borderTop: 'var(--hairline)' }}>
                      <td style={{ ...tdMono, color: 'var(--fg-3)', textAlign: 'center' }}>{pos.num}</td>
                      <td style={td}>{pos.name}</td>
                      <td style={{ ...tdMono, color: 'var(--fg-2)' }}>{pos.unit}</td>
                      <td style={{ ...tdMono, textAlign: 'right' }}>{pos.quantity}</td>
                      <td style={{ ...td, fontSize: 12, color: 'var(--fg-3)', maxWidth: 280 }}>{pos.justification}</td>
                      <td style={{ ...tdMono, fontSize: 11, color: 'var(--fg-2)' }}>{pos.formula}</td>
                      <td style={{ ...tdMono, textAlign: 'right', fontWeight: 600 }}>{fmt(pos.cost)}</td>
                    </tr>
                  ))}

                  {/* Divider */}
                  <tr><td colSpan={7} style={{ height: 1, background: 'var(--border-strong)', padding: 0 }} /></tr>

                  {/* Summary rows */}
                  <SummaryRow
                    label="Базовая стоимость основных проектных работ"
                    value={fmt(result.base_cost)}
                    bold
                    note="МУ №620 п.2.1.1"
                  />
                  <SummaryRow
                    label={`Коэффициент пересчёта базовой стоимости на ${result.price_index_period}`}
                    value={String(result.price_index)}
                    note={result.price_index_justification}
                  />
                  <SummaryRow
                    label="Текущая стоимость основных проектных работ"
                    value={fmt(result.current_cost)}
                    bold
                    note="МУ №620 п.2.2.3"
                  />
                  {result.stage_factor !== 1 && (
                    <>
                      <SummaryRow
                        label={`Доля стоимости проектных работ (стадия ${result.stage})`}
                        value={String(result.stage_factor)}
                        note="СБЦП 81-2001-17 п.1.7"
                      />
                      <SummaryRow
                        label={`Итого с долей стоимости проектирования К=${result.stage_factor}`}
                        value={fmt(result.cost_with_stage)}
                        bold
                      />
                    </>
                  )}
                  <SummaryRow
                    label={`НДС ${result.vat_rate}%`}
                    value={fmt(result.vat_amount)}
                  />
                  <SummaryRow
                    label="ИТОГО с НДС"
                    value={fmt(result.total_with_vat)}
                    bold
                  />
                </tbody>
              </table>
            </div>
          </div>
        )}

        {!result && !loading && calcId && (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            Нажмите «Рассчитать» чтобы построить смету по извлечённым данным
          </div>
        )}
      </div>
    </>
  )
}

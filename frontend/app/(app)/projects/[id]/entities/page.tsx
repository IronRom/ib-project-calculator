'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { getCalculation, getProject, computeCalculation, patchEntityXValue, getUnitCheck, Calculation, ExtractedEntity, CalculationResult, CalcPosition, Project, UnitCheckItem } from '@/lib/api'
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

function fmt(n: number): string {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

export default function EntitiesPage() {
  const { id } = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const calcId = searchParams.get('calc')
  const router = useRouter()
  const [calc, setCalc] = useState<Calculation | null>(null)
  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [calcResult, setCalcResult] = useState<CalculationResult | null>(null)
  const [computing, setComputing] = useState(false)
  const [calcError, setCalcError] = useState('')
  const [unitChecks, setUnitChecks] = useState<UnitCheckItem[]>([])

  useEffect(() => {
    if (!calcId) return
    Promise.all([
      getProject(Number(id)),
      getCalculation(Number(id), Number(calcId)),
    ]).then(([proj, c]) => {
      setProject(proj)
      setCalc(c)
      if (c.calculation_result) setCalcResult(c.calculation_result)
      return getUnitCheck(Number(id), Number(calcId))
    }).then((checks) => {
      setUnitChecks(checks)
    }).finally(() => setLoading(false))
  }, [id, calcId])

  async function handleCompute() {
    setComputing(true); setCalcError('')
    try {
      const r = await computeCalculation(Number(id), Number(calcId))
      setCalcResult(r)
    } catch (e: unknown) {
      setCalcError(e instanceof Error ? e.message : 'Ошибка расчёта')
    } finally {
      setComputing(false)
    }
  }

  if (loading) return <div style={{ padding: 28, color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>

  const result = calc?.extracted_entities
  const entities = result?.entities ?? []

  const th: React.CSSProperties = { textAlign: 'left', padding: '9px 12px', fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid var(--border-default)', whiteSpace: 'nowrap' }
  const td: React.CSSProperties = { padding: '10px 12px', fontSize: 13, verticalAlign: 'top' }
  const tdMono: React.CSSProperties = { ...td, fontFamily: 'var(--font-mono)', fontSize: 12 }

  return (
    <>
      <Topbar
        title={project ? project.name : 'Анализ ТЗ'}
        breadcrumb="Проекты / Извлечённые объекты"
        actions={
          <Button variant="secondary" onClick={() => router.push(`/projects/${id}`)}>
            ← Назад к проекту
          </Button>
        }
      />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Confidence + stage + region */}
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
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--warning-400)', marginBottom: 6 }}>Не удалось определить из ТЗ:</div>
            <ul style={{ margin: 0, padding: '0 0 0 16px', fontSize: 12, color: 'var(--warning-400)' }}>
              {result.missing_data.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </div>
        )}

        {/* Entities table */}
        {entities.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            AI не смог извлечь объекты из ТЗ.
          </div>
        ) : (() => {
          const obvious = entities.filter(e => (e.confidence ?? 1) >= 0.7)
          const suggested = entities.filter(e => (e.confidence ?? 1) < 0.7)
          const colHeaders = ['Категория', 'Тип объекта', 'Наименование', 'Адрес', 'X (из ТЗ)', 'Ед.', 'X (таблица)', 'Уверенность']
          const projectIdNum = Number(id)
          const calcIdNum = Number(calcId)
          const theadRow = (
            <tr>
              {colHeaders.map((h, i) => (
                <th key={i} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-default)', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          )
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Obvious positions */}
              <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
                <div style={{ padding: '14px 18px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>Объекты ПИР</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{obvious.length} позиций</div>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead style={{ background: 'var(--bg-raised)' }}>{theadRow}</thead>
                    <tbody>
                      {obvious.map((entity, i) => {
                        const globalIdx = entities.indexOf(entity)
                        return <EntityRow key={i} entity={entity} entityIdx={globalIdx} projectId={projectIdNum} calcId={calcIdNum} unitCheck={unitChecks[globalIdx]} isLast={i === obvious.length - 1} onXValueSaved={(val, unit) => { entity.x_value = val; entity.x_unit = unit ?? entity.x_unit ?? ''; entity.x_value_missing_reason = undefined; setCalc(c => c ? { ...c } : c) }} />
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* AI-suggested positions */}
              {suggested.length > 0 && (
                <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
                  <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--warning-500)', background: 'var(--status-warning-bg)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--warning-400)' }}>Предложено AI — требует проверки</div>
                      <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>
                        Позиции нормативно обязательны, но прямо не указаны в ТЗ
                      </div>
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--warning-400)' }}>{suggested.length} позиций</div>
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead style={{ background: 'var(--bg-raised)' }}>{theadRow}</thead>
                      <tbody>
                        {suggested.map((entity, i) => {
                          const globalIdx = entities.indexOf(entity)
                          return <EntityRow key={i} entity={entity} entityIdx={globalIdx} projectId={projectIdNum} calcId={calcIdNum} unitCheck={unitChecks[globalIdx]} isLast={i === suggested.length - 1} suggested onXValueSaved={(val, unit) => { entity.x_value = val; entity.x_unit = unit ?? entity.x_unit ?? ''; entity.x_value_missing_reason = undefined; setCalc(c => c ? { ...c } : c) }} />
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )
        })()}

        {/* Рассчитать button below table */}
        {entities.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Button variant="primary" disabled={computing || !calcId} onClick={handleCompute}>
              {computing ? 'Расчёт…' : calcResult ? 'Пересчитать' : 'Рассчитать стоимость ПИР'}
            </Button>
            {calcError && <span style={{ fontSize: 13, color: 'var(--danger-400)' }}>{calcError}</span>}
          </div>
        )}

        {/* ── Calculation result (2ПС) ── */}
        {calcResult && (
          <>
            {calcResult.errors.length > 0 && (
              <div style={{ padding: '12px 16px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--warning-400)' }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>Не найдены данные для позиций:</div>
                {calcResult.errors.map((e, i) => <div key={i} style={{ marginLeft: 12 }}>• {e}</div>)}
              </div>
            )}

            <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
              <div style={{ padding: '14px 20px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>Форма 2ПС ИР — Сметный расчёт</div>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
                    Стадия: {calcResult.stage} · Индекс: {calcResult.price_index} ({calcResult.price_index_period})
                  </div>
                </div>
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead style={{ background: 'var(--bg-raised)' }}>
                    <tr>
                      <th style={{ ...th, width: 36 }}>№</th>
                      <th style={th}>Наименование работ</th>
                      <th style={th}>Тип работ по справочнику</th>
                      <th style={{ ...th, width: 90 }}>Ед. изм.</th>
                      <th style={{ ...th, width: 70 }}>Кол-во</th>
                      <th style={th}>Обоснование стоимости</th>
                      <th style={th}>Расчёт стоимости</th>
                      <th style={{ ...th, textAlign: 'right', width: 140 }}>Стоимость, руб.</th>
                    </tr>
                    <tr style={{ background: 'var(--bg-raised)' }}>
                      {[1,2,3,4,5,6,7,8].map((n) => (
                        <td key={n} style={{ ...tdMono, color: 'var(--fg-3)', textAlign: 'center', borderBottom: '1px solid var(--border-default)', paddingTop: 3, paddingBottom: 6, fontSize: 11 }}>{n}</td>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {calcResult.positions.map((pos: CalcPosition, i: number) => (
                      <tr key={i} style={{ borderTop: 'var(--hairline)' }}>
                        <td style={{ ...tdMono, color: 'var(--fg-3)', textAlign: 'center' }}>{pos.num}</td>
                        <td style={td}>{pos.name}</td>
                        <td style={{ ...td, fontSize: 12, color: 'var(--fg-2)', maxWidth: 260 }}>{pos.row_description}</td>
                        <td style={{ ...tdMono, color: 'var(--fg-2)' }}>{pos.unit}</td>
                        <td style={{ ...tdMono, textAlign: 'right' }}>{pos.quantity}</td>
                        <td style={{ ...td, fontSize: 11, color: 'var(--fg-3)', maxWidth: 220 }}>{pos.justification}</td>
                        <td style={{ ...tdMono, fontSize: 11, color: 'var(--fg-2)' }}>{pos.formula}</td>
                        <td style={{ ...tdMono, textAlign: 'right', fontWeight: 600 }}>{fmt(pos.cost)}</td>
                      </tr>
                    ))}

                    {/* divider */}
                    <tr><td colSpan={8} style={{ height: 1, background: 'var(--border-strong)', padding: 0 }} /></tr>

                    {/* Summary */}
                    <SummaryRow cols={8} label="Базовая стоимость основных проектных работ" value={fmt(calcResult.base_cost)} bold note="МУ №620 п.2.1.1" />
                    <SummaryRow cols={8} label={`Коэффициент пересчёта базовой стоимости на ${calcResult.price_index_period}`} value={String(calcResult.price_index)} note={calcResult.price_index_justification} />
                    <SummaryRow cols={8} label="Текущая стоимость основных проектных работ" value={fmt(calcResult.current_cost)} bold note="МУ №620 п.2.2.3" />
                    {calcResult.stage_factor !== 1 && <>
                      <SummaryRow cols={8} label={`Доля стоимости проектных работ (стадия ${calcResult.stage})`} value={String(calcResult.stage_factor)} />
                      <SummaryRow cols={8} label={`Итого с долей стоимости проектирования К=${calcResult.stage_factor}`} value={fmt(calcResult.cost_with_stage)} bold />
                    </>}
                    <SummaryRow cols={8} label={`НДС ${calcResult.vat_rate}%`} value={fmt(calcResult.vat_amount)} />
                    <SummaryRow cols={8} label="ИТОГО с НДС" value={fmt(calcResult.total_with_vat)} bold />
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

      </div>
    </>
  )
}

function SummaryRow({ cols, label, value, bold, note }: { cols: number; label: string; value: string; bold?: boolean; note?: string }) {
  return (
    <tr>
      <td colSpan={cols - 1} style={{ padding: '10px 12px', fontSize: 13, fontWeight: bold ? 600 : 400, color: 'var(--fg-2)' }}>
        {label}
        {note && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginLeft: 8 }}>{note}</span>}
      </td>
      <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: bold ? 700 : 400, textAlign: 'right', whiteSpace: 'nowrap', color: bold ? 'var(--fg-1)' : 'var(--fg-2)' }}>
        {value}
      </td>
    </tr>
  )
}

function EntityRow({ entity, entityIdx, projectId, calcId, unitCheck, isLast, suggested, onXValueSaved }: {
  entity: ExtractedEntity
  entityIdx: number
  projectId: number
  calcId: number
  unitCheck?: UnitCheckItem
  isLast: boolean
  suggested?: boolean
  onXValueSaved?: (val: number, unit?: string) => void
}) {
  const tone = CATEGORY_TONES[entity.category] || 'default'
  const label = CATEGORY_LABELS[entity.category] || entity.category
  const rowBg = suggested ? 'var(--status-warning-bg)' : undefined
  const [editing, setEditing] = useState(false)
  const [inputVal, setInputVal] = useState('')
  const [saving, setSaving] = useState(false)

  const xMissing = entity.x_value == null

  async function handleSave() {
    const num = parseFloat(inputVal.replace(',', '.'))
    if (isNaN(num)) return
    setSaving(true)
    try {
      await patchEntityXValue(projectId, calcId, entityIdx, num)
      onXValueSaved?.(num)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  let unitCell: React.ReactNode = <span style={{ color: 'var(--fg-4)', fontSize: 11 }}>—</span>
  if (unitCheck) {
    if (!unitCheck.ok) {
      unitCell = (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--danger-400)' }}>
          ⚠ {unitCheck.note}
        </span>
      )
    } else if (unitCheck.note) {
      const xEff = unitCheck.x_effective?.toLocaleString('ru-RU', { maximumFractionDigits: 4 }) ?? ''
      unitCell = (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: unitCheck.extrapolated ? 'var(--warning-400)' : 'var(--fg-3)' }}>
          {xEff} {unitCheck.x_unit_table}
          {unitCheck.extrapolated && <span style={{ marginLeft: 4, fontSize: 10, color: 'var(--warning-400)' }}>экстрапол.</span>}
        </span>
      )
    } else {
      unitCell = <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--success-400)' }}>✓</span>
    }
  }

  const xCell = xMissing ? (
    editing ? (
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <input
          autoFocus
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') setEditing(false) }}
          style={{ width: 80, fontFamily: 'var(--font-mono)', fontSize: 12, padding: '3px 6px', background: 'var(--bg-default)', border: '1px solid var(--warning-500)', borderRadius: 4, color: 'var(--fg-1)', outline: 'none' }}
          placeholder="0.0"
        />
        <button onClick={handleSave} disabled={saving} style={{ fontSize: 11, padding: '3px 8px', background: 'var(--warning-500)', color: '#000', border: 'none', borderRadius: 4, cursor: 'pointer' }}>
          {saving ? '…' : '✓'}
        </button>
        <button onClick={() => setEditing(false)} style={{ fontSize: 11, padding: '3px 6px', background: 'transparent', color: 'var(--fg-3)', border: 'none', cursor: 'pointer' }}>✕</button>
      </div>
    ) : (
      <button
        onClick={() => setEditing(true)}
        title={entity.x_value_missing_reason ?? 'Не указано в ТЗ'}
        style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '3px 8px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 4, color: 'var(--warning-400)', fontSize: 11, cursor: 'pointer', fontFamily: 'var(--font-mono)' }}
      >
        ⚠ ввести
      </button>
    )
  ) : (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
      {entity.x_value!.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}
    </span>
  )

  const hasFooter = !!(entity.notes || entity.tz_quote || (xMissing && entity.x_value_missing_reason))

  return (
    <>
      <tr style={{ borderBottom: (isLast && !hasFooter) ? 'none' : 'var(--hairline)', background: xMissing ? 'color-mix(in srgb, var(--status-warning-bg) 60%, transparent)' : rowBg }}>
        <td style={{ padding: '12px 14px' }}><Chip tone={tone}>{label}</Chip></td>
        <td style={{ padding: '12px 14px', fontWeight: 500 }}>{entity.object_type}</td>
        <td style={{ padding: '12px 14px', color: 'var(--fg-2)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entity.object_name}</td>
        <td style={{ padding: '12px 14px', color: 'var(--fg-3)', fontSize: 12, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entity.address || '—'}</td>
        <td style={{ padding: '12px 14px', textAlign: 'right' }}>{xCell}</td>
        <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{entity.x_unit || '—'}</td>
        <td style={{ padding: '12px 14px' }}>{unitCell}</td>
        <td style={{ padding: '12px 14px' }}>
          <ConfidenceBadge value={entity.confidence ?? 0} small />
        </td>
      </tr>
      {hasFooter && (
        <tr style={{ borderBottom: isLast ? 'none' : 'var(--hairline)', background: xMissing ? 'color-mix(in srgb, var(--status-warning-bg) 60%, transparent)' : rowBg }}>
          <td colSpan={8} style={{ padding: '4px 14px 10px 14px' }}>
            {xMissing && entity.x_value_missing_reason && (
              <div style={{ fontSize: 11, color: 'var(--warning-400)', marginBottom: 4 }}>
                ⚠ {entity.x_value_missing_reason}
              </div>
            )}
            {entity.tz_quote && (
              <div style={{ fontSize: 11, color: 'var(--fg-4)', fontFamily: 'var(--font-mono)', marginBottom: entity.notes ? 4 : 0 }}>
                <span style={{ color: 'var(--fg-3)', marginRight: 4 }}>ТЗ:</span>«{entity.tz_quote}»
              </div>
            )}
            {entity.notes && (
              <div style={{ fontSize: 12, color: 'var(--fg-3)', fontStyle: 'italic' }}>
                {entity.notes}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
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

'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import {
  getCalculation, getProject, computeCalculation, patchEntity,
  getUnitCheck, Calculation, ExtractedEntity, CalculationResult,
  CalcPosition, Project, UnitCheckItem,
} from '@/lib/api'
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

// ── Local override types ──────────────────────────────────────────────────────
interface EntityOverride {
  x_value?: number | null
  x_unit?: string
  deleted?: boolean
}

// ── Column width constants ────────────────────────────────────────────────────
const COL_CAT   = '110px'
const COL_TYPE  = '170px'
const COL_NAME  = '200px'
const COL_ADDR  = '140px'
const COL_X     = '110px'
const COL_UNIT  = '90px'
const COL_XTBL  = '130px'
const COL_CONF  = '80px'
const COL_ACT   = '80px'

export default function EntitiesPage() {
  const { id } = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const calcId = searchParams.get('calc')
  const router = useRouter()

  const [calc, setCalc]             = useState<Calculation | null>(null)
  const [project, setProject]       = useState<Project | null>(null)
  const [loading, setLoading]       = useState(true)
  const [calcResult, setCalcResult] = useState<CalculationResult | null>(null)
  const [computing, setComputing]   = useState(false)
  const [calcError, setCalcError]   = useState('')
  const [unitChecks, setUnitChecks] = useState<UnitCheckItem[]>([])
  const [overrides, setOverrides]   = useState<Record<number, EntityOverride>>({})
  const [dirty, setDirty]           = useState(false)

  useEffect(() => {
    if (!calcId) return
    Promise.all([
      getProject(Number(id)),
      getCalculation(Number(id), Number(calcId)),
    ]).then(([proj, c]) => {
      setProject(proj)
      setCalc(c)
      if (c.calculation_result) setCalcResult(c.calculation_result)
      // Init overrides from existing deleted/x_value state in DB
      const init: Record<number, EntityOverride> = {}
      ;(c.extracted_entities?.entities ?? []).forEach((e: ExtractedEntity, i: number) => {
        if (e.deleted) init[i] = { deleted: true }
      })
      setOverrides(init)
      return getUnitCheck(Number(id), Number(calcId))
    }).then(setUnitChecks).finally(() => setLoading(false))
  }, [id, calcId])

  function applyOverride(idx: number, patch: Partial<EntityOverride>) {
    setOverrides(prev => ({ ...prev, [idx]: { ...prev[idx], ...patch } }))
    setDirty(true)
  }

  async function handleCompute() {
    setComputing(true); setCalcError('')
    try {
      // Save all pending overrides
      const saves = Object.entries(overrides).map(([idxStr, ov]) => {
        const idx = Number(idxStr)
        const patch: Partial<{ x_value: number | null; x_unit: string; deleted: boolean }> = {}
        if (ov.x_value !== undefined) patch.x_value = ov.x_value
        if (ov.x_unit  !== undefined) patch.x_unit  = ov.x_unit
        if (ov.deleted !== undefined) patch.deleted  = ov.deleted
        return Object.keys(patch).length ? patchEntity(Number(id), Number(calcId), idx, patch) : Promise.resolve()
      })
      await Promise.all(saves)
      setDirty(false)
      const r = await computeCalculation(Number(id), Number(calcId))
      setCalcResult(r)
      // Refresh unit checks
      getUnitCheck(Number(id), Number(calcId)).then(setUnitChecks)
    } catch (e: unknown) {
      setCalcError(e instanceof Error ? e.message : 'Ошибка расчёта')
    } finally {
      setComputing(false)
    }
  }

  if (loading) return <div style={{ padding: 28, color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>

  const result   = calc?.extracted_entities
  const entities: ExtractedEntity[] = result?.entities ?? []

  const th: React.CSSProperties = {
    textAlign: 'left', padding: '9px 12px', fontSize: 11, fontWeight: 600,
    color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em',
    borderBottom: '1px solid var(--border-default)', whiteSpace: 'nowrap',
  }
  const tdBase: React.CSSProperties = { padding: '10px 12px', fontSize: 13, verticalAlign: 'top' }
  const tdMono: React.CSSProperties = { ...tdBase, fontFamily: 'var(--font-mono)', fontSize: 12 }

  const obvious   = entities.filter((_, i) => (entities[i].confidence ?? 1) >= 0.7)
  const suggested = entities.filter((_, i) => (entities[i].confidence ?? 1) < 0.7)

  const colHeaders = ['Категория','Тип объекта','Наименование','Адрес','X (из ТЗ)','Ед.','X (таблица)','Увер.','']
  const colWidths  = [COL_CAT, COL_TYPE, COL_NAME, COL_ADDR, COL_X, COL_UNIT, COL_XTBL, COL_CONF, COL_ACT]

  function makeColGroup() {
    return (
      <colgroup>
        {colWidths.map((w, i) => <col key={i} style={{ width: w }} />)}
      </colgroup>
    )
  }

  const theadRow = (
    <tr>
      {colHeaders.map((h, i) => (
        <th key={i} style={{ ...th, width: colWidths[i] }}>{h}</th>
      ))}
    </tr>
  )

  return (
    <>
      <Topbar
        title={project ? project.name : 'Анализ ТЗ'}
        breadcrumb="Проекты / Извлечённые объекты"
        actions={
          <Button variant="secondary" onClick={() => router.push(`/projects/${id}`)}>
            ← Назад
          </Button>
        }
      />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Badges */}
        {result && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <ConfidenceBadge value={result.overall_confidence} />
            {result.stage && <MetaBadge label="Стадия" value={result.stage} />}
            {result.region && <MetaBadge label="Регион" value={result.region} />}
            {dirty && (
              <span style={{ fontSize: 12, color: 'var(--warning-400)', fontFamily: 'var(--font-mono)' }}>
                ● несохранённые изменения
              </span>
            )}
          </div>
        )}

        {/* Missing data banner */}
        {result?.missing_data && result.missing_data.length > 0 && (
          <div style={{ padding: '12px 16px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--warning-400)', marginBottom: 6 }}>Не удалось определить из ТЗ:</div>
            <ul style={{ margin: 0, padding: '0 0 0 16px', fontSize: 12, color: 'var(--warning-400)' }}>
              {result.missing_data.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </div>
        )}

        {/* Entities tables */}
        {entities.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            AI не смог извлечь объекты из ТЗ.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Obvious */}
            <EntityTable
              title="Объекты ПИР"
              entities={entities}
              subset={obvious}
              unitChecks={unitChecks}
              overrides={overrides}
              projectId={Number(id)}
              calcId={Number(calcId)}
              onOverride={applyOverride}
              theadRow={theadRow}
              makeColGroup={makeColGroup}
            />
            {/* Suggested */}
            {suggested.length > 0 && (
              <EntityTable
                title="Предложено AI — требует проверки"
                subtitle="Позиции нормативно обязательны, но прямо не указаны в ТЗ"
                entities={entities}
                subset={suggested}
                unitChecks={unitChecks}
                overrides={overrides}
                projectId={Number(id)}
                calcId={Number(calcId)}
                onOverride={applyOverride}
                theadRow={theadRow}
                makeColGroup={makeColGroup}
                warn
              />
            )}
          </div>
        )}

        {/* Recalculate button */}
        {entities.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Button variant="primary" disabled={computing || !calcId} onClick={handleCompute}>
              {computing ? 'Расчёт…' : calcResult ? 'Пересчитать' : 'Рассчитать стоимость ПИР'}
            </Button>
            {dirty && !computing && (
              <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>Нажмите, чтобы применить изменения</span>
            )}
            {calcError && <span style={{ fontSize: 13, color: 'var(--danger-400)' }}>{calcError}</span>}
          </div>
        )}

        {/* 2ПС result */}
        {calcResult && (
          <>
            {calcResult.errors.length > 0 && (
              <div style={{ padding: '12px 16px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--warning-400)' }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>Не найдены данные для позиций:</div>
                {calcResult.errors.map((e, i) => <div key={i} style={{ marginLeft: 12 }}>• {e}</div>)}
              </div>
            )}
            <ResultTable result={calcResult} tdBase={tdBase} tdMono={tdMono} th={th} />
          </>
        )}
      </div>
    </>
  )
}

// ── Entity table block ────────────────────────────────────────────────────────
function EntityTable({
  title, subtitle, entities, subset, unitChecks, overrides, projectId, calcId, onOverride, theadRow, makeColGroup, warn,
}: {
  title: string; subtitle?: string; entities: ExtractedEntity[]; subset: ExtractedEntity[]
  unitChecks: UnitCheckItem[]; overrides: Record<number, EntityOverride>
  projectId: number; calcId: number
  onOverride: (idx: number, patch: Partial<EntityOverride>) => void
  theadRow: React.ReactNode; makeColGroup: () => React.ReactNode; warn?: boolean
}) {
  const borderColor = warn ? 'var(--warning-500)' : 'var(--border-default)'
  return (
    <div style={{ background: 'var(--bg-elevated)', border: `1px solid ${borderColor}`, borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ padding: '14px 18px', borderBottom: `1px solid ${borderColor}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: warn ? 'var(--status-warning-bg)' : undefined }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: warn ? 'var(--warning-400)' : undefined }}>{title}</div>
          {subtitle && <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>{subtitle}</div>}
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: warn ? 'var(--warning-400)' : 'var(--fg-3)' }}>{subset.length} позиций</div>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          {makeColGroup()}
          <thead style={{ background: 'var(--bg-raised)' }}>{theadRow}</thead>
          <tbody>
            {subset.map((entity, i) => {
              const globalIdx = entities.indexOf(entity)
              const ov = overrides[globalIdx] ?? {}
              const isDeleted = ov.deleted ?? entity.deleted ?? false
              return (
                <EntityRow
                  key={globalIdx}
                  entity={entity}
                  entityIdx={globalIdx}
                  projectId={projectId}
                  calcId={calcId}
                  unitCheck={unitChecks[globalIdx]}
                  isLast={i === subset.length - 1}
                  override={ov}
                  isDeleted={isDeleted}
                  onOverride={(patch) => onOverride(globalIdx, patch)}
                />
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Single entity row ─────────────────────────────────────────────────────────
function EntityRow({ entity, entityIdx, projectId, calcId, unitCheck, isLast, override, isDeleted, onOverride }: {
  entity: ExtractedEntity; entityIdx: number; projectId: number; calcId: number
  unitCheck?: UnitCheckItem; isLast: boolean
  override: EntityOverride; isDeleted: boolean
  onOverride: (patch: Partial<EntityOverride>) => void
}) {
  const [editing, setEditing] = useState(false)
  const [inputVal, setInputVal] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const effectiveX    = override.x_value !== undefined ? override.x_value : entity.x_value
  const effectiveUnit = override.x_unit  !== undefined ? override.x_unit  : entity.x_unit
  const xMissing      = effectiveX == null

  const tone  = CATEGORY_TONES[entity.category] || 'default'
  const label = CATEGORY_LABELS[entity.category] || entity.category

  const strikeStyle: React.CSSProperties = isDeleted ? { textDecoration: 'line-through', opacity: 0.45 } : {}

  function startEdit() {
    setInputVal(effectiveX != null ? String(effectiveX).replace('.', ',') : '')
    setEditing(true)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  function commitEdit() {
    const num = parseFloat(inputVal.replace(',', '.'))
    if (!isNaN(num)) onOverride({ x_value: num })
    setEditing(false)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter')  { commitEdit(); return }
    if (e.key === 'Escape') { setEditing(false) }
  }

  // X (таблица) cell
  let unitCell: React.ReactNode = <span style={{ color: 'var(--fg-4)', fontSize: 11 }}>—</span>
  if (unitCheck) {
    if (!unitCheck.ok) {
      unitCell = <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--danger-400)', wordBreak: 'break-word' }}>⚠ {unitCheck.note}</span>
    } else if (unitCheck.note) {
      const xEff = unitCheck.x_effective?.toLocaleString('ru-RU', { maximumFractionDigits: 4 }) ?? ''
      unitCell = (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: unitCheck.extrapolated ? 'var(--warning-400)' : 'var(--success-400)' }}>
          {xEff} {unitCheck.x_unit_table}
          {unitCheck.extrapolated && <span style={{ marginLeft: 4, fontSize: 10 }}>экстрап.</span>}
        </span>
      )
    } else {
      unitCell = <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--success-400)' }}>✓</span>
    }
  }

  // X (из ТЗ) cell — always editable
  const xCell = editing ? (
    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
      <input
        ref={inputRef}
        value={inputVal}
        onChange={e => setInputVal(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={commitEdit}
        style={{ width: 74, fontFamily: 'var(--font-mono)', fontSize: 12, padding: '3px 6px', background: 'var(--bg-default)', border: '1px solid var(--accent-500)', borderRadius: 4, color: 'var(--fg-1)', outline: 'none', textAlign: 'right' }}
        placeholder="0.0"
      />
    </div>
  ) : (
    <div
      onClick={isDeleted ? undefined : startEdit}
      title={xMissing ? (entity.x_value_missing_reason ?? 'Не указано в ТЗ') : 'Нажмите для редактирования'}
      style={{
        cursor: isDeleted ? 'default' : 'pointer',
        display: 'block', width: '100%', textAlign: 'right',
        fontFamily: 'var(--font-mono)', fontSize: 12,
        padding: '3px 8px', borderRadius: 4,
        background: xMissing ? 'color-mix(in srgb, var(--warning-500) 15%, transparent)' : 'transparent',
        border: xMissing ? '1px solid var(--warning-500)' : '1px solid transparent',
        color: xMissing ? 'var(--warning-400)' : 'inherit',
        boxSizing: 'border-box',
        ...strikeStyle,
      }}
    >
      {xMissing ? '⚠ —' : effectiveX!.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}
    </div>
  )

  const hasFooter = !!(entity.notes || entity.tz_quote || (xMissing && entity.x_value_missing_reason))
  const rowBg = isDeleted ? 'color-mix(in srgb, var(--danger-500) 8%, transparent)' : undefined

  return (
    <>
      <tr style={{ borderBottom: (isLast && !hasFooter) ? 'none' : 'var(--hairline)', background: rowBg }}>
        <td style={{ padding: '10px 12px', ...strikeStyle }}><Chip tone={tone}>{label}</Chip></td>
        <td style={{ padding: '10px 12px', fontWeight: 500, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...strikeStyle }}>{entity.object_type}</td>
        <td style={{ padding: '10px 12px', color: 'var(--fg-2)', fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...strikeStyle }}>{entity.object_name}</td>
        <td style={{ padding: '10px 12px', color: 'var(--fg-3)', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', ...strikeStyle }}>{entity.address || '—'}</td>
        <td style={{ padding: '10px 12px', textAlign: 'right' }}>{xCell}</td>
        <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', ...strikeStyle }}>{effectiveUnit || '—'}</td>
        <td style={{ padding: '10px 12px' }}>{unitCell}</td>
        <td style={{ padding: '10px 12px' }}><ConfidenceBadge value={entity.confidence ?? 0} small /></td>
        <td style={{ padding: '10px 12px', textAlign: 'center' }}>
          {isDeleted ? (
            <button
              onClick={() => onOverride({ deleted: false })}
              style={{ fontSize: 11, padding: '3px 8px', background: 'transparent', border: '1px solid var(--fg-3)', borderRadius: 4, color: 'var(--fg-3)', cursor: 'pointer' }}
            >↩ вернуть</button>
          ) : (
            <button
              onClick={() => onOverride({ deleted: true })}
              style={{ fontSize: 11, padding: '3px 8px', background: 'transparent', border: '1px solid var(--danger-400)', borderRadius: 4, color: 'var(--danger-400)', cursor: 'pointer' }}
            >удалить</button>
          )}
        </td>
      </tr>
      {hasFooter && (
        <tr style={{ borderBottom: isLast ? 'none' : 'var(--hairline)', background: rowBg }}>
          <td colSpan={9} style={{ padding: '2px 12px 8px 12px' }}>
            {xMissing && entity.x_value_missing_reason && (
              <div style={{ fontSize: 11, color: 'var(--warning-400)', marginBottom: 2, ...strikeStyle }}>⚠ {entity.x_value_missing_reason}</div>
            )}
            {entity.tz_quote && (
              <div style={{ fontSize: 11, color: 'var(--fg-4)', fontFamily: 'var(--font-mono)', marginBottom: entity.notes ? 2 : 0, ...strikeStyle }}>
                <span style={{ color: 'var(--fg-3)', marginRight: 4 }}>ТЗ:</span>«{entity.tz_quote}»
              </div>
            )}
            {entity.notes && (
              <div style={{ fontSize: 12, color: 'var(--fg-3)', fontStyle: 'italic', ...strikeStyle }}>{entity.notes}</div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ── 2ПС result table ──────────────────────────────────────────────────────────
function ResultTable({ result, tdBase, tdMono, th }: { result: CalculationResult; tdBase: React.CSSProperties; tdMono: React.CSSProperties; th: React.CSSProperties }) {
  return (
    <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ padding: '14px 20px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Форма 2ПС ИР — Сметный расчёт</div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
            Стадия: {result.stage} · Индекс: {result.price_index} ({result.price_index_period})
          </div>
        </div>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          <colgroup>
            <col style={{ width: 36 }} />
            <col style={{ width: '14%' }} />
            <col style={{ width: '22%' }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 70 }} />
            <col style={{ width: '22%' }} />
            <col style={{ width: '20%' }} />
            <col style={{ width: 140 }} />
          </colgroup>
          <thead style={{ background: 'var(--bg-raised)' }}>
            <tr>
              <th style={{ ...th, textAlign: 'center' }}>№</th>
              <th style={th}>Наименование работ</th>
              <th style={th}>Тип работ по справочнику</th>
              <th style={{ ...th, textAlign: 'center' }}>Ед. изм.</th>
              <th style={{ ...th, textAlign: 'right' }}>Кол-во</th>
              <th style={th}>Обоснование стоимости</th>
              <th style={th}>Расчёт стоимости</th>
              <th style={{ ...th, textAlign: 'right' }}>Стоимость, руб.</th>
            </tr>
            <tr style={{ background: 'var(--bg-raised)' }}>
              {[1,2,3,4,5,6,7,8].map(n => (
                <td key={n} style={{ ...tdMono, color: 'var(--fg-3)', textAlign: 'center', borderBottom: '1px solid var(--border-default)', paddingTop: 3, paddingBottom: 6, fontSize: 11 }}>{n}</td>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.positions.map((pos: CalcPosition, i: number) => (
              <tr key={i} style={{ borderTop: 'var(--hairline)' }}>
                <td style={{ ...tdMono, color: 'var(--fg-3)', textAlign: 'center' }}>{pos.num}</td>
                <td style={{ ...tdBase, fontSize: 13 }}>{pos.name}</td>
                <td style={{ ...tdBase, fontSize: 12, color: 'var(--fg-2)' }}>{pos.row_description}</td>
                <td style={{ ...tdMono, textAlign: 'center', color: 'var(--fg-2)' }}>{pos.unit}</td>
                <td style={{ ...tdMono, textAlign: 'right' }}>{pos.quantity}</td>
                <td style={{ ...tdBase, fontSize: 11, color: 'var(--fg-3)' }}>{pos.justification}</td>
                <td style={{ ...tdMono, fontSize: 11, color: 'var(--fg-2)', wordBreak: 'break-all' }}>{pos.formula}</td>
                <td style={{ ...tdMono, textAlign: 'right', fontWeight: 600 }}>{fmt(pos.cost)}</td>
              </tr>
            ))}
            <tr><td colSpan={8} style={{ height: 1, background: 'var(--border-strong)', padding: 0 }} /></tr>
            <SummaryRow cols={8} label="Базовая стоимость основных проектных работ" value={fmt(result.base_cost)} bold note="МУ №620 п.2.1.1" />
            <SummaryRow cols={8} label={`Коэффициент пересчёта на ${result.price_index_period}`} value={String(result.price_index)} note={result.price_index_justification} />
            <SummaryRow cols={8} label="Текущая стоимость основных проектных работ" value={fmt(result.current_cost)} bold note="МУ №620 п.2.2.3" />
            {result.stage_factor !== 1 && <>
              <SummaryRow cols={8} label={`Доля стоимости (стадия ${result.stage})`} value={String(result.stage_factor)} />
              <SummaryRow cols={8} label={`Итого с долей К=${result.stage_factor}`} value={fmt(result.cost_with_stage)} bold />
            </>}
            <SummaryRow cols={8} label={`НДС ${result.vat_rate}%`} value={fmt(result.vat_amount)} />
            <SummaryRow cols={8} label="ИТОГО с НДС" value={fmt(result.total_with_vat)} bold />
          </tbody>
        </table>
      </div>
    </div>
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

function MetaBadge({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: '6px 12px', background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }}>
      {label}: <strong style={{ color: 'var(--fg-1)' }}>{value}</strong>
    </div>
  )
}

function ConfidenceBadge({ value, small }: { value: number; small?: boolean }) {
  const pct  = Math.round(value * 100)
  const tone = pct >= 80 ? 'success' : pct >= 60 ? 'warning' : 'danger'
  if (small) return <Chip tone={tone}>{pct}%</Chip>
  return (
    <div style={{ padding: '8px 14px', background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>Уверенность AI:</span>
      <Chip tone={tone}>{pct}%</Chip>
    </div>
  )
}

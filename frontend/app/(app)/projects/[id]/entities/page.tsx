'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import {
  getCalculation, getProject, computeCalculation,
  downloadExport2PS, downloadExportKP, patchEntity,
  getUnitCheck, streamExtraction, listCalculations,
  clarifyCalc, finalizeCalc, createVersion, downloadExportFile,
  Calculation, ExtractedEntity, CalculationResult,
  CalcPosition, Project, UnitCheckItem, CalcListItem, ClarifyDiff,
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

const EXPORT_LABELS: Record<string, string> = {
  '2ps_xlsx': '2ПС (Excel)',
  kp_pdf: 'КП (PDF)',
  kp_docx: 'КП (Word)',
}

function fmt(n: number): string {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

// ── Local override types ──────────────────────────────────────────────────────
interface EntityOverride {
  x_value?: number | null
  x_unit?: string
  deleted?: boolean
  pd_sections_pct?: number | null
  rd_sections_pct?: number | null
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

function groupBySections(entities: ExtractedEntity[]) {
  const sections: Map<number, { name: string; indices: number[] }> = new Map()
  entities.forEach((e, i) => {
    const num = e.section_num ?? 0
    const name = e.section_name ?? ''
    if (!sections.has(num)) sections.set(num, { name, indices: [] })
    sections.get(num)!.indices.push(i)
  })
  // Staged groups (1,2,3...) first, ungrouped (0) last
  return Array.from(sections.entries()).sort(([a], [b]) => {
    if (a === 0) return 1
    if (b === 0) return -1
    return a - b
  })
}

export default function CalcWorkspacePage() {
  const { id } = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const calcId = searchParams.get('calc')
  const router = useRouter()

  const [calc, setCalc]             = useState<Calculation | null>(null)
  const [project, setProject]       = useState<Project | null>(null)
  const [meta, setMeta]             = useState<CalcListItem | null>(null)
  const [loading, setLoading]       = useState(true)
  const [calcResult, setCalcResult] = useState<CalculationResult | null>(null)
  const [computing, setComputing]   = useState(false)
  const [calcError, setCalcError]   = useState('')
  const [unitChecks, setUnitChecks] = useState<UnitCheckItem[]>([])
  const [overrides, setOverrides]   = useState<Record<number, EntityOverride>>({})
  const [dirty, setDirty]           = useState(false)

  // AI-анализ ТЗ (SSE) прямо на этом экране
  const [extracting, setExtracting]           = useState(false)
  const [extractProgress, setExtractProgress] = useState({ step: 0, total: 3, message: 'Инициализация…' })
  const [extractError, setExtractError]       = useState('')
  const extractStartedRef = useRef(false)
  const esRef = useRef<EventSource | null>(null)

  // Уточнение свободным текстом (предпросмотр диффа → применение)
  const [clarifyText, setClarifyText] = useState('')
  const [clarifyBusy, setClarifyBusy] = useState(false)
  const [clarifyDiff, setClarifyDiff] = useState<ClarifyDiff | null>(null)

  const [finalizing, setFinalizing] = useState(false)

  const readOnly = meta?.status === 'final'

  const refreshMeta = useCallback(async () => {
    const list = await listCalculations(Number(id))
    const m = list.find(x => x.id === Number(calcId)) ?? null
    setMeta(m)
    return m
  }, [id, calcId])

  const startExtraction = useCallback(() => {
    setExtracting(true)
    setExtractError('')
    setExtractProgress({ step: 0, total: 3, message: 'Инициализация…' })
    esRef.current?.close()
    const es = streamExtraction(Number(id), Number(calcId))
    esRef.current = es
    es.addEventListener('progress', (e) => {
      setExtractProgress(JSON.parse((e as MessageEvent).data))
    })
    es.addEventListener('done', async () => {
      es.close()
      const c = await getCalculation(Number(id), Number(calcId))
      setCalc(c)
      // свежая экстракция: локальные правки и старый результат больше не актуальны
      const init: Record<number, EntityOverride> = {}
      ;(c.extracted_entities?.entities ?? []).forEach((e: ExtractedEntity, i: number) => {
        if (e.deleted) init[i] = { deleted: true }
      })
      setOverrides(init)
      setDirty(false)
      setCalcResult(c.calculation_result ?? null)
      setExtracting(false)
      getUnitCheck(Number(id), Number(calcId)).then(setUnitChecks).catch(() => {})
    })
    es.addEventListener('error', (e) => {
      es.close()
      try {
        setExtractError(JSON.parse((e as MessageEvent).data).message)
      } catch {
        setExtractError('Ошибка AI-анализа ТЗ. Попробуйте ещё раз.')
      }
      setExtracting(false)
    })
  }, [id, calcId])

  useEffect(() => {
    if (!calcId) return
    Promise.all([
      getProject(Number(id)),
      getCalculation(Number(id), Number(calcId)),
      refreshMeta(),
    ]).then(([proj, c, m]) => {
      setProject(proj)
      setCalc(c)
      if (c.calculation_result) setCalcResult(c.calculation_result)
      const init: Record<number, EntityOverride> = {}
      ;(c.extracted_entities?.entities ?? []).forEach((e: ExtractedEntity, i: number) => {
        if (e.deleted) init[i] = { deleted: true }
      })
      setOverrides(init)
      const hasEntities = (c.extracted_entities?.entities?.length ?? 0) > 0
      if (hasEntities) {
        getUnitCheck(Number(id), Number(calcId)).then(setUnitChecks).catch(() => {})
      } else if (m?.status !== 'final' && !extractStartedRef.current) {
        // новый расчёт: сразу запускаем AI-анализ ТЗ
        extractStartedRef.current = true
        startExtraction()
      }
    }).finally(() => setLoading(false))
    return () => esRef.current?.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, calcId])

  function applyOverride(idx: number, patch: Partial<EntityOverride>) {
    setOverrides(prev => ({ ...prev, [idx]: { ...prev[idx], ...patch } }))
    setDirty(true)
  }

  async function savePendingOverrides() {
    const saves = Object.entries(overrides).map(([idxStr, ov]) => {
      const idx = Number(idxStr)
      const patch: Partial<{ x_value: number | null; x_unit: string; deleted: boolean; pd_sections_pct: number | null; rd_sections_pct: number | null }> = {}
      if (ov.x_value !== undefined)          patch.x_value          = ov.x_value
      if (ov.x_unit  !== undefined)          patch.x_unit           = ov.x_unit
      if (ov.deleted !== undefined)          patch.deleted           = ov.deleted
      if (ov.pd_sections_pct !== undefined)  patch.pd_sections_pct  = ov.pd_sections_pct
      if (ov.rd_sections_pct !== undefined)  patch.rd_sections_pct  = ov.rd_sections_pct
      return Object.keys(patch).length ? patchEntity(Number(id), Number(calcId), idx, patch) : Promise.resolve()
    })
    await Promise.all(saves)
    setDirty(false)
  }

  async function handleCompute() {
    setComputing(true); setCalcError('')
    try {
      await savePendingOverrides()
      const r = await computeCalculation(Number(id), Number(calcId))
      setCalcResult(r)
      getUnitCheck(Number(id), Number(calcId)).then(setUnitChecks)
      refreshMeta().catch(() => {})
    } catch (e: unknown) {
      setCalcError(e instanceof Error ? e.message : 'Ошибка расчёта')
    } finally {
      setComputing(false)
    }
  }

  async function handleClarifyPreview() {
    if (!clarifyText.trim()) return
    setClarifyBusy(true); setCalcError(''); setClarifyDiff(null)
    try {
      const r = await clarifyCalc(Number(id), Number(calcId), clarifyText, true)
      setClarifyDiff(r.diff)
    } catch (e: unknown) {
      setCalcError(e instanceof Error ? e.message : 'Ошибка уточнения')
    } finally {
      setClarifyBusy(false)
    }
  }

  async function handleClarifyApply() {
    setClarifyBusy(true); setCalcError('')
    try {
      const r = await clarifyCalc(Number(id), Number(calcId), clarifyText, false)
      if (r.result) setCalcResult(r.result as CalculationResult)
      setClarifyDiff(null)
      setClarifyText('')
      const c = await getCalculation(Number(id), Number(calcId))
      setCalc(c)
      getUnitCheck(Number(id), Number(calcId)).then(setUnitChecks)
      refreshMeta().catch(() => {})
    } catch (e: unknown) {
      setCalcError(e instanceof Error ? e.message : 'Ошибка применения уточнения')
    } finally {
      setClarifyBusy(false)
    }
  }

  async function handleFinalize() {
    if (!confirm('Финализировать расчёт? Версия будет заморожена — правки будут возможны только в новой версии. Будут сформированы файлы 2ПС и КП.')) return
    setFinalizing(true); setCalcError('')
    try {
      await savePendingOverrides()
      await finalizeCalc(Number(id), Number(calcId))
      await refreshMeta()
      const c = await getCalculation(Number(id), Number(calcId))
      setCalc(c)
      if (c.calculation_result) setCalcResult(c.calculation_result)
    } catch (e: unknown) {
      setCalcError(e instanceof Error ? e.message : 'Ошибка финализации')
    } finally {
      setFinalizing(false)
    }
  }

  async function handleNewVersion() {
    try {
      const v = await createVersion(Number(id), Number(calcId))
      router.push(`/projects/${id}/entities?calc=${v.id}`)
    } catch (e: unknown) {
      setCalcError(e instanceof Error ? e.message : 'Ошибка создания версии')
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

  const extractPct = extractProgress.total > 0 ? Math.round((extractProgress.step / extractProgress.total) * 100) : 0

  return (
    <>
      <Topbar
        title={meta ? `Расчёт №${meta.id} · v${meta.version_num}` : 'Расчёт'}
        breadcrumb={project ? `Проекты / ${project.name}` : 'Проекты'}
        actions={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {!readOnly && entities.length > 0 && (
              <Button variant="secondary" size="sm" onClick={() => router.push(`/projects/${id}/geology?calc=${calcId}`)}>
                Добавить ИГИ
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={() => router.push(`/projects/${id}`)}>
              ← В проект
            </Button>
          </div>
        }
      />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* Финализированный расчёт: файлы + новая версия */}
        {readOnly && meta && (
          <div style={{ padding: '14px 18px', background: 'var(--status-success-bg)', border: '1px solid var(--success-500)', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--success-400)' }}>
              ✓ Расчёт финализирован{meta.finalized_at ? ` ${new Date(meta.finalized_at).toLocaleString('ru-RU')}` : ''} — версия заморожена
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              {meta.exports.map((ex) => (
                <button key={ex.kind}
                  onClick={() => downloadExportFile(Number(id), Number(calcId), ex.kind, ex.filename).catch(e => setCalcError(e.message))}
                  title={ex.filename}
                  style={{
                    fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 0.3,
                    padding: '6px 12px', borderRadius: 6, cursor: 'pointer',
                    background: 'var(--success-100)', color: 'var(--success-400)',
                    border: '1px solid var(--success-500)',
                  }}>
                  ↓ {EXPORT_LABELS[ex.kind] || ex.kind}
                </button>
              ))}
              <button
                onClick={handleNewVersion}
                title="Создать новую редактируемую версию на базе этого расчёта"
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, padding: '6px 12px',
                  borderRadius: 6, cursor: 'pointer',
                  background: 'transparent', color: 'var(--fg-2)',
                  border: '1px solid var(--border-default)',
                }}>⎇ Новая версия</button>
            </div>
          </div>
        )}

        {/* AI-анализ ТЗ: прогресс / ошибка */}
        {extracting && (
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', padding: '24px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>AI-анализ технического задания</div>
              <div style={{ fontSize: 13, color: 'var(--fg-3)' }}>
                Шаг {extractProgress.step} из {extractProgress.total}: {extractProgress.message}
              </div>
            </div>
            <div style={{ background: 'var(--bg-raised)', borderRadius: 'var(--radius-full)', height: 6, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${extractPct}%`, background: 'var(--accent)', borderRadius: 'var(--radius-full)', transition: 'width 0.3s ease' }} />
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)', textAlign: 'right' }}>{extractPct}%</div>
          </div>
        )}
        {extractError && !extracting && (
          <div style={{ padding: '14px 18px', background: 'var(--danger-100)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 13, color: 'var(--danger-400)' }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Ошибка AI-анализа ТЗ</div>
              {extractError}
            </div>
            <div>
              <Button variant="secondary" size="sm" onClick={startExtraction}>↻ Повторить анализ</Button>
            </div>
          </div>
        )}

        {/* Badges */}
        {result && entities.length > 0 && (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <ConfidenceBadge value={result.overall_confidence} />
            {result.stage && <MetaBadge label="Стадия" value={result.stage} />}
            {result.region && <MetaBadge label="Регион" value={result.region} />}
            {dirty && (
              <span style={{ fontSize: 12, color: 'var(--warning-400)', fontFamily: 'var(--font-mono)' }}>
                ● несохранённые изменения
              </span>
            )}
            {!readOnly && !extracting && (
              <button
                onClick={() => { if (confirm('Повторить AI-анализ ТЗ? Текущие позиции и правки будут заменены заново извлечёнными.')) startExtraction() }}
                style={{ fontFamily: 'var(--font-mono)', fontSize: 11, padding: '4px 10px', borderRadius: 4, cursor: 'pointer', background: 'transparent', color: 'var(--fg-3)', border: '1px solid var(--border-default)' }}
              >↻ повторить анализ ТЗ</button>
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

        {/* used_minimum warning banner */}
        {calcResult && calcResult.positions.some(p => p.used_minimum) && (
          <div style={{
            background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 6,
            padding: '8px 14px', fontSize: 13, color: 'var(--warning-400)',
          }}>
            ⚠️ Часть позиций рассчитана по минимальным значениям. Уточните параметры для точной стоимости.
          </div>
        )}

        {/* Entities tables */}
        {!extracting && !extractError && entities.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            AI не смог извлечь объекты из ТЗ.
          </div>
        ) : entities.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Obvious */}
            <EntityTable
              title="Объекты ПИР"
              entities={entities}
              subset={obvious}
              unitChecks={unitChecks}
              overrides={overrides}
              onOverride={applyOverride}
              theadRow={theadRow}
              makeColGroup={makeColGroup}
              calcResult={calcResult}
              readOnly={readOnly}
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
                onOverride={applyOverride}
                theadRow={theadRow}
                makeColGroup={makeColGroup}
                calcResult={calcResult}
                readOnly={readOnly}
                warn
              />
            )}
          </div>
        )}

        {/* Уточнение свободным текстом (AI-патч с предпросмотром) */}
        {!readOnly && entities.length > 0 && (
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Уточнение расчёта</div>
              <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>
                Опишите правку свободным текстом — AI изменит позиции, вы увидите изменения до применения
              </div>
            </div>
            <textarea
              value={clarifyText}
              onChange={e => { setClarifyText(e.target.value); setClarifyDiff(null) }}
              placeholder="Например: «мощность котельной 2 МВт, а не 4», «убери АСУТП», «добавь наружное освещение 1,2 км»"
              rows={2}
              style={{
                padding: '8px 10px', fontSize: 13,
                border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)',
                resize: 'vertical', fontFamily: 'inherit', color: 'var(--fg-1)',
                background: 'var(--bg-input)',
              }}
            />
            {clarifyDiff ? (
              <div style={{ border: '1px solid var(--blue-700)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
                <div style={{ padding: '10px 14px', background: 'var(--accent-tint)', fontSize: 13, fontWeight: 600, color: 'var(--blue-300)' }}>
                  Предпросмотр изменений
                </div>
                <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {clarifyDiff.summary && (
                    <div style={{ fontSize: 13, color: 'var(--fg-2)' }}>{clarifyDiff.summary}</div>
                  )}
                  {clarifyDiff.changes?.length > 0 && (
                    <ul style={{ margin: 0, padding: '0 0 0 16px', fontSize: 12, color: 'var(--fg-2)', display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {clarifyDiff.changes.map((ch, i) => (
                        <li key={i}>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginRight: 6 }}>
                            {ch.type === 'add' ? '+ добавить' : ch.type === 'remove' ? '− убрать' : '± изменить'}
                          </span>
                          {ch.object_name}
                          {ch.field && (
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
                              {' '}· {ch.field}: {String(ch.old ?? '—')} → {String(ch.new ?? '—')}
                            </span>
                          )}
                          {ch.reason && <span style={{ color: 'var(--fg-3)' }}> — {ch.reason}</span>}
                        </li>
                      ))}
                    </ul>
                  )}
                  {(clarifyDiff.total_before != null || clarifyDiff.total_after != null) && (
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-1)' }}>
                      Итог с НДС: {clarifyDiff.total_before != null ? fmt(clarifyDiff.total_before) : '—'} → <strong>{clarifyDiff.total_after != null ? fmt(clarifyDiff.total_after) : '—'}</strong> ₽
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
                    <Button variant="primary" size="sm" disabled={clarifyBusy} onClick={handleClarifyApply}>
                      {clarifyBusy ? 'Применение…' : 'Применить и пересчитать'}
                    </Button>
                    <Button variant="ghost" size="sm" disabled={clarifyBusy} onClick={() => setClarifyDiff(null)}>
                      Отмена
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div>
                <Button variant="secondary" size="sm" disabled={clarifyBusy || !clarifyText.trim()} onClick={handleClarifyPreview}>
                  {clarifyBusy ? 'AI анализирует…' : 'Предпросмотр изменений'}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Рассчитать / статус */}
        {!readOnly && entities.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <Button variant="primary" disabled={computing || !calcId} onClick={handleCompute}>
              {computing ? 'Расчёт…' : calcResult ? 'Пересчитать' : 'Рассчитать стоимость ПИР'}
            </Button>
            {dirty && !computing && (
              <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>Нажмите, чтобы применить изменения</span>
            )}
          </div>
        )}
        {calcError && (
          <div style={{ padding: '10px 14px', background: 'var(--danger-100)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--danger-400)' }}>
            {calcError}
          </div>
        )}

        {/* Результат: ошибки, предупреждения, 2ПС, финализация */}
        {calcResult && (
          <>
            {calcResult.errors.length > 0 && (
              <div style={{ padding: '12px 16px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--warning-400)' }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>Не найдены данные для позиций:</div>
                {calcResult.errors.map((e, i) => <div key={i} style={{ marginLeft: 12 }}>• {e}</div>)}
              </div>
            )}
            {(calcResult.warnings?.length ?? 0) > 0 && (
              <div style={{ padding: '12px 16px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--warning-400)' }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>⚠ Предупреждения расчёта (влияют на точность цены):</div>
                {calcResult.warnings!.map((w, i) => <div key={i} style={{ marginLeft: 12 }}>• {w}</div>)}
              </div>
            )}
            <ResultTable result={calcResult} tdBase={tdBase} tdMono={tdMono} th={th} />
            {calcId && !readOnly && (
              <div style={{ display: 'flex', gap: 10, marginTop: 4, flexWrap: 'wrap', alignItems: 'center' }}>
                <Button variant="primary" disabled={finalizing || computing || dirty} onClick={handleFinalize}>
                  {finalizing ? 'Финализация…' : '✓ Финализировать расчёт'}
                </Button>
                <Button variant="secondary" onClick={() => downloadExport2PS(Number(id), Number(calcId)).catch(e => setCalcError(e.message))}>
                  ↓ 2ПС ИР (черновик)
                </Button>
                <Button variant="secondary" onClick={() => downloadExportKP(Number(id), Number(calcId)).catch(e => setCalcError(e.message))}>
                  ↓ КП (черновик)
                </Button>
                {dirty && (
                  <span style={{ fontSize: 12, color: 'var(--warning-400)' }}>
                    Сначала пересчитайте — есть несохранённые изменения
                  </span>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}

// ── Entity table block ────────────────────────────────────────────────────────
function EntityTable({
  title, subtitle, entities, subset, unitChecks, overrides, onOverride, theadRow, makeColGroup, calcResult, readOnly, warn,
}: {
  title: string; subtitle?: string; entities: ExtractedEntity[]; subset: ExtractedEntity[]
  unitChecks: UnitCheckItem[]; overrides: Record<number, EntityOverride>
  onOverride: (idx: number, patch: Partial<EntityOverride>) => void
  theadRow: React.ReactNode; makeColGroup: () => React.ReactNode
  calcResult: CalculationResult | null; readOnly: boolean; warn?: boolean
}) {
  const borderColor = warn ? 'var(--warning-500)' : 'var(--border-default)'

  // Build section groups from the subset (using global indices into entities array)
  const subsetGlobalIndices = subset.map(e => entities.indexOf(e))
  const subsetEntitiesForGrouping = subsetGlobalIndices.map(gi => entities[gi])
  // groupBySections uses array index relative to subsetEntitiesForGrouping,
  // so we need a mapping back to global indices
  const sections = groupBySections(subsetEntitiesForGrouping)
  const hasMultipleSections = sections.some(([num]) => num > 0)

  // Column count for colSpan (9 columns total)
  const COL_COUNT = 9

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
            {sections.map(([sectionNum, { name, indices: localIndices }]) => {
              // localIndices are offsets into subsetEntitiesForGrouping; map to global entity indices
              const globalIndices = localIndices.map(li => subsetGlobalIndices[li])
              const sectionEntities = globalIndices.map(gi => entities[gi])

              // Compute per-section subtotal from calcResult positions (pos.num is 1-based global index)
              const sectionCost = calcResult
                ? globalIndices
                    .map(gi => calcResult.positions.find(p => p.num === gi + 1)?.cost ?? 0)
                    .reduce((s, v) => s + v, 0)
                : 0

              return (
                <React.Fragment key={`section-${sectionNum}`}>
                  {/* Section header row */}
                  {hasMultipleSections && (
                    <tr>
                      <td colSpan={COL_COUNT} style={{
                        background: 'var(--accent-tint)', padding: '6px 12px',
                        fontWeight: 600, fontSize: 13, color: 'var(--blue-300)',
                        borderTop: '2px solid var(--blue-500)',
                      }}>
                        {sectionNum === 0 ? 'Без этапа' : `Этап ${sectionNum}${name ? `: ${name}` : ''}`}
                      </td>
                    </tr>
                  )}

                  {/* Entity rows for this section */}
                  {sectionEntities.map((entity, i) => {
                    const globalIdx = globalIndices[i]
                    const ov = overrides[globalIdx] ?? {}
                    const isDeleted = ov.deleted ?? entity.deleted ?? false
                    // isLast only matters for border; use section subtotal row as visual separator
                    const isLastOverall = !hasMultipleSections && globalIdx === subsetGlobalIndices[subsetGlobalIndices.length - 1]
                    return (
                      <EntityRow
                        key={globalIdx}
                        entity={entity}
                        unitCheck={unitChecks[globalIdx]}
                        isLast={hasMultipleSections ? false : isLastOverall}
                        override={ov}
                        isDeleted={isDeleted}
                        stage={calcResult?.stage ?? 'П+Р'}
                        readOnly={readOnly}
                        onOverride={(patch) => onOverride(globalIdx, patch)}
                      />
                    )
                  })}

                  {/* Section subtotal row */}
                  {hasMultipleSections && sectionNum > 0 && sectionCost > 0 && (
                    <tr style={{ background: 'var(--bg-raised)' }}>
                      <td colSpan={COL_COUNT - 1} style={{ padding: '4px 12px', textAlign: 'right', fontSize: 12, color: 'var(--fg-3)' }}>
                        Итог этапа:
                      </td>
                      <td style={{ padding: '4px 12px', textAlign: 'right', fontWeight: 600, fontSize: 12 }}>
                        {fmt(sectionCost)}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Single entity row ─────────────────────────────────────────────────────────
function EntityRow({ entity, unitCheck, isLast, override, isDeleted, stage, readOnly, onOverride }: {
  entity: ExtractedEntity
  unitCheck?: UnitCheckItem; isLast: boolean
  override: EntityOverride; isDeleted: boolean
  stage?: string
  readOnly: boolean
  onOverride: (patch: Partial<EntityOverride>) => void
}) {
  const [editing, setEditing] = useState(false)
  const [inputVal, setInputVal] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const showStagePct = stage === 'П+Р' && !isDeleted

  const effectiveX    = override.x_value !== undefined ? override.x_value : entity.x_value
  const effectiveUnit = override.x_unit  !== undefined ? override.x_unit  : entity.x_unit
  const xMissing      = effectiveX == null

  const tone  = CATEGORY_TONES[entity.category] || 'default'
  const label = CATEGORY_LABELS[entity.category] || entity.category

  const strikeStyle: React.CSSProperties = isDeleted ? { textDecoration: 'line-through', opacity: 0.45 } : {}

  function startEdit() {
    if (readOnly) return
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

  // X (из ТЗ) cell — editable in draft
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
      onClick={(isDeleted || readOnly) ? undefined : startEdit}
      title={xMissing ? (entity.x_value_missing_reason ?? 'Не указано в ТЗ') : readOnly ? undefined : 'Нажмите для редактирования'}
      style={{
        cursor: (isDeleted || readOnly) ? 'default' : 'pointer',
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

  const hasPct = showStagePct
  const pdPct = override.pd_sections_pct ?? entity.pd_sections_pct ?? null
  const rdPct = override.rd_sections_pct ?? entity.rd_sections_pct ?? null
  const hasFooter = !!(entity.notes || entity.tz_quote || (xMissing && entity.x_value_missing_reason) || hasPct)
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
          {readOnly ? null : isDeleted ? (
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
            {hasPct && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 6, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, color: 'var(--fg-3)', fontWeight: 600 }}>Разделы %:</span>
                {(['ПД', 'РД'] as const).map((lbl) => {
                  const field = lbl === 'ПД' ? 'pd_sections_pct' : 'rd_sections_pct'
                  const val = lbl === 'ПД' ? pdPct : rdPct
                  return (
                    <label key={lbl} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                      <span style={{
                        padding: '1px 5px', borderRadius: 3, fontSize: 10, fontWeight: 700,
                        background: lbl === 'ПД' ? 'var(--accent-tint)' : 'var(--bg-raised)',
                        color: lbl === 'ПД' ? 'var(--blue-300)' : 'var(--fg-2)',
                        border: '1px solid var(--border-default)',
                      }}>{lbl}</span>
                      <input
                        type="number"
                        min={0} max={100} step={0.5}
                        placeholder="100"
                        disabled={readOnly}
                        value={val != null ? Math.round(val * 100) : ''}
                        onChange={e => {
                          const n = parseFloat(e.target.value)
                          onOverride({ [field]: isNaN(n) ? null : n / 100 } as Partial<EntityOverride>)
                        }}
                        style={{
                          width: 56, fontFamily: 'var(--font-mono)', fontSize: 12,
                          padding: '2px 5px', background: 'var(--bg-default)',
                          border: '1px solid var(--border-default)', borderRadius: 4,
                          color: 'var(--fg-1)', outline: 'none', textAlign: 'right',
                        }}
                      />
                      <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>%</span>
                    </label>
                  )
                })}
                <span style={{ fontSize: 11, color: 'var(--fg-4)' }}>
                  {pdPct != null || rdPct != null
                    ? `ПД×${((pdPct ?? 1) * 0.4 * 100).toFixed(1)}% + РД×${((rdPct ?? 1) * 0.6 * 100).toFixed(1)}% от базы`
                    : 'по умолчанию: ПД 40% + РД 60%'}
                </span>
              </div>
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
                <td style={{ ...tdBase, fontSize: 13 }}>
                  {pos.stage_label && (
                    <span style={{
                      display: 'inline-block', marginRight: 5,
                      padding: '1px 5px', borderRadius: 3, fontSize: 10, fontWeight: 700,
                      background: pos.stage_label === 'ПД' ? 'var(--accent-tint)' : 'var(--bg-raised)',
                      color: pos.stage_label === 'ПД' ? 'var(--blue-300)' : 'var(--fg-2)',
                      border: '1px solid var(--border-default)',
                    }}>{pos.stage_label}</span>
                  )}
                  {pos.name}
                </td>
                <td style={{ ...tdBase, fontSize: 12, color: 'var(--fg-2)' }}>{pos.row_description}</td>
                <td style={{ ...tdMono, textAlign: 'center', color: 'var(--fg-2)' }}>{pos.unit}</td>
                <td style={{ ...tdMono, textAlign: 'right' }}>{pos.quantity}</td>
                <td style={{ ...tdBase, fontSize: 11, color: 'var(--fg-3)' }}>{pos.justification}</td>
                <td style={{ ...tdMono, fontSize: 11, color: 'var(--fg-2)', wordBreak: 'break-all' }}>{pos.formula}</td>
                <td style={{ ...tdMono, textAlign: 'right', fontWeight: 600 }}>
                  {pos.used_minimum && (
                    <span
                      title="Рассчитано по минимальному X. Уточните параметры для точного расчёта."
                      style={{
                        display: 'inline-block', marginRight: 4,
                        background: 'var(--status-warning-bg)', color: 'var(--warning-400)',
                        border: '1px solid var(--warning-500)', borderRadius: 4,
                        fontSize: 10, padding: '1px 5px', fontWeight: 600,
                        verticalAlign: 'middle',
                      }}
                    >
                      Минимум
                    </span>
                  )}
                  {fmt(pos.cost)}
                </td>
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

'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import {
  getCalculation, getProject, computeCalculation, patchEntity,
  getUnitCheck, startExtractionJob, getExtractionStatus, listCalculations,
  clarifyCalc, finalizeCalc, createVersion, downloadExportFile,
  Calculation, ExtractedEntity, CalculationResult,
  Project, UnitCheckItem, CalcListItem, ClarifyDiff,
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
function fmtRub(n: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(n) + ' ₽'
}

// ── Local override types ──────────────────────────────────────────────────────
interface EntityOverride {
  x_value?: number | null
  x_unit?: string
  deleted?: boolean
  pd_sections_pct?: number | null
  rd_sections_pct?: number | null
}

function groupBySections(indices: number[], entities: ExtractedEntity[]) {
  const sections: Map<number, { name: string; indices: number[] }> = new Map()
  indices.forEach((gi) => {
    const e = entities[gi]
    const num = e.section_num ?? 0
    const name = e.section_name ?? ''
    if (!sections.has(num)) sections.set(num, { name, indices: [] })
    sections.get(num)!.indices.push(gi)
  })
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
  const [tab, setTab]               = useState<'objects' | 'basis'>('objects')
  // варнинги, исчезнувшие после пересчёта — показываем зачёркнутыми
  const [resolvedWarnings, setResolvedWarnings] = useState<string[]>([])

  // AI-анализ ТЗ — фоновая задача на сервере, экран лишь опрашивает статус.
  const [extracting, setExtracting]           = useState(false)
  const [extractProgress, setExtractProgress] = useState({ step: 0, total: 6, message: 'Инициализация…' })
  const [extractError, setExtractError]       = useState('')
  const extractStartedRef = useRef(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

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

  const stopPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = null
  }, [])

  // авторасчёт: цены видны сразу, без ручного «Рассчитать»
  const autoCompute = useCallback(async () => {
    setComputing(true)
    try {
      const r = await computeCalculation(Number(id), Number(calcId))
      setCalcResult(r)
      getUnitCheck(Number(id), Number(calcId)).then(setUnitChecks).catch(() => {})
      refreshMeta().catch(() => {})
    } catch {
      // не смогли — цены появятся после ручного «Пересчитать»
    } finally {
      setComputing(false)
    }
  }, [id, calcId, refreshMeta])

  const finishExtraction = useCallback(async () => {
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
    if (!c.calculation_result && (c.extracted_entities?.entities?.length ?? 0) > 0) {
      autoCompute()
    }
  }, [id, calcId, autoCompute])

  const beginPolling = useCallback(() => {
    stopPolling()
    setExtracting(true)
    setExtractError('')
    pollRef.current = setInterval(async () => {
      try {
        const st = await getExtractionStatus(Number(id), Number(calcId))
        if (st.progress) setExtractProgress(st.progress)
        if (st.status === 'done') {
          stopPolling()
          await finishExtraction()
        } else if (st.status === 'error') {
          stopPolling()
          setExtractError(st.error || 'Ошибка AI-анализа ТЗ. Попробуйте ещё раз.')
          setExtracting(false)
        }
      } catch {
        // сеть мигнула — продолжаем опрос
      }
    }, 2500)
  }, [id, calcId, stopPolling, finishExtraction])

  const startExtraction = useCallback(async () => {
    setExtracting(true)
    setExtractError('')
    setExtractProgress({ step: 0, total: 6, message: 'Инициализация…' })
    try {
      const r = await startExtractionJob(Number(id), Number(calcId))
      if (r.progress) setExtractProgress(r.progress)
      beginPolling()
    } catch (e: unknown) {
      setExtractError(e instanceof Error ? e.message : 'Не удалось запустить анализ ТЗ')
      setExtracting(false)
    }
  }, [id, calcId, beginPolling])

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
        if (!c.calculation_result && m?.status !== 'final') autoCompute()
      } else if (m?.status !== 'final' && !extractStartedRef.current) {
        extractStartedRef.current = true
        // анализ мог уже идти в фоне — тогда продолжаем опрос, иначе стартуем
        getExtractionStatus(Number(id), Number(calcId)).then((st) => {
          if (st.status === 'running') {
            if (st.progress) setExtractProgress(st.progress)
            beginPolling()
          } else if (st.status === 'error') {
            setExtractError(st.error || 'Ошибка AI-анализа ТЗ. Попробуйте ещё раз.')
          } else {
            startExtraction()
          }
        }).catch(() => startExtraction())
      }
    }).finally(() => setLoading(false))
    return () => stopPolling()
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

  // пересчёт: варнинги, которых больше нет — в «решённые» (зачёркиваем)
  function absorbResult(r: CalculationResult) {
    const oldW = calcResult?.warnings ?? []
    const curW = r.warnings ?? []
    setResolvedWarnings(prev => {
      const gone = oldW.filter(w => !curW.includes(w))
      return Array.from(new Set([...prev.filter(w => !curW.includes(w)), ...gone]))
    })
    setCalcResult(r)
  }

  async function handleCompute() {
    setComputing(true); setCalcError('')
    try {
      await savePendingOverrides()
      const r = await computeCalculation(Number(id), Number(calcId))
      absorbResult(r)
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
      if (r.result) absorbResult(r.result as CalculationResult)
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
    if (!confirm('Финализировать расчёт? Версия будет заморожена, будут сформированы файлы 2ПС и КП; правки — только в новой версии.')) return
    setFinalizing(true); setCalcError('')
    try {
      await savePendingOverrides()
      await finalizeCalc(Number(id), Number(calcId))
      await refreshMeta()
      const c = await getCalculation(Number(id), Number(calcId))
      setCalc(c)
      if (c.calculation_result) setCalcResult(c.calculation_result)
    } catch (e: unknown) {
      setCalcError(e instanceof Error ? e.message : 'Ошибка применения')
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

  const effectiveX = (gi: number) => {
    const ov = overrides[gi] ?? {}
    return ov.x_value !== undefined ? ov.x_value : entities[gi]?.x_value
  }
  const isDeleted = (gi: number) => {
    const ov = overrides[gi] ?? {}
    return ov.deleted ?? entities[gi]?.deleted ?? false
  }

  const obviousIdx   = entities.map((_, i) => i).filter(i => (entities[i].confidence ?? 1) >= 0.7)
  const suggestedIdx = entities.map((_, i) => i).filter(i => (entities[i].confidence ?? 1) < 0.7)

  // цена позиции: сумма строк расчёта (ПД+РД) с num = глоб.индекс + 1
  const costFor = (gi: number): number | null => {
    if (!calcResult) return null
    const rows = calcResult.positions.filter(p => p.num === gi + 1)
    if (!rows.length) return null
    return rows.reduce((s, p) => s + p.cost, 0)
  }
  const usedMinimumFor = (gi: number): boolean =>
    !!calcResult?.positions.some(p => p.num === gi + 1 && p.used_minimum)

  // «Нет X: …» из ТЗ считаем решённым, когда у соответствующей позиции X заполнен
  const missingItems = (result?.missing_data ?? []).map((m) => {
    const resolved = entities.some((e, gi) =>
      e.object_name && m.includes(e.object_name) && effectiveX(gi) != null && !isDeleted(gi))
    return { text: m, resolved }
  })

  const curWarnings = calcResult?.warnings ?? []
  const curErrors   = calcResult?.errors ?? []
  const basisCount  = curWarnings.length + curErrors.length + missingItems.filter(m => !m.resolved).length

  const extractPct = extractProgress.total > 0 ? Math.round((extractProgress.step / extractProgress.total) * 100) : 0

  const tabBtn = (key: 'objects' | 'basis', label: string, badge?: number) => (
    <button
      onClick={() => setTab(key)}
      style={{
        padding: '9px 16px', fontSize: 13, fontWeight: tab === key ? 600 : 400,
        background: 'transparent', border: 'none', cursor: 'pointer',
        color: tab === key ? 'var(--fg-1)' : 'var(--fg-3)',
        borderBottom: tab === key ? '2px solid var(--blue-500)' : '2px solid transparent',
        display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
      }}
    >
      {label}
      {badge != null && badge > 0 && (
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600,
          background: 'var(--status-warning-bg)', color: 'var(--warning-400)',
          border: '1px solid var(--warning-500)', borderRadius: 999, padding: '1px 7px',
        }}>{badge}</span>
      )}
    </button>
  )

  return (
    <>
      <Topbar
        title={meta
          ? `Расчёт от ${new Date(meta.created_at).toLocaleDateString('ru-RU')}${meta.version_num > 1 ? ` · v${meta.version_num}` : ''}`
          : 'Расчёт'}
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
      <div style={{ padding: '20px 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* Финализированный расчёт: файлы + новая версия */}
        {readOnly && meta && (
          <div style={{ padding: '14px 18px', background: 'var(--status-success-bg)', border: '1px solid var(--success-500)', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--success-400)' }}>
              ✓ Расчёт применён{meta.finalized_at ? ` ${new Date(meta.finalized_at).toLocaleString('ru-RU')}` : ''} — версия заморожена
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
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>AI-анализ технического задания</div>
              <div style={{ fontSize: 13, color: 'var(--fg-3)' }}>
                Шаг {extractProgress.step} из {extractProgress.total}: {extractProgress.message}
              </div>
            </div>
            <div style={{ background: 'var(--bg-raised)', borderRadius: 'var(--radius-full)', height: 6, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${extractPct}%`, background: 'var(--accent)', borderRadius: 'var(--radius-full)', transition: 'width 0.3s ease' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>
                Анализ выполняется на сервере — страницу можно закрыть и вернуться позже
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>{extractPct}%</div>
            </div>
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

        {!extracting && !extractError && entities.length === 0 && (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            AI не смог извлечь объекты из ТЗ.
          </div>
        )}

        {calcError && (
          <div style={{ padding: '10px 14px', background: 'var(--danger-100)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--danger-400)' }}>
            {calcError}
          </div>
        )}

        {entities.length > 0 && (
          <>
            {/* Вкладки */}
            <div style={{ borderBottom: 'var(--hairline)', display: 'flex', gap: 4, overflowX: 'auto' }}>
              {tabBtn('objects', 'Объекты ПИР')}
              {tabBtn('basis', 'Обоснование', basisCount)}
            </div>

            {/* ═══ Вкладка «Объекты ПИР» ═══ */}
            {tab === 'objects' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {dirty && (
                  <div style={{ fontSize: 12, color: 'var(--warning-400)', fontFamily: 'var(--font-mono)' }}>
                    ● есть изменения — нажмите «Пересчитать»
                  </div>
                )}

                {/* Основные позиции по этапам */}
                {groupBySections(obviousIdx, entities).map(([sectionNum, { name, indices }]) => (
                  <React.Fragment key={`s${sectionNum}`}>
                    {sectionNum > 0 && (
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--blue-300)', marginTop: 4 }}>
                        Этап {sectionNum}{name ? `: ${name}` : ''}
                      </div>
                    )}
                    {indices.map(gi => (
                      <EntityCard
                        key={gi}
                        num={gi + 1}
                        entity={entities[gi]}
                        unitCheck={unitChecks[gi]}
                        override={overrides[gi] ?? {}}
                        deleted={isDeleted(gi)}
                        cost={costFor(gi)}
                        usedMinimum={usedMinimumFor(gi)}
                        stage={result?.stage}
                        readOnly={readOnly}
                        onOverride={(patch) => applyOverride(gi, patch)}
                      />
                    ))}
                  </React.Fragment>
                ))}

                {/* Предложено AI */}
                {suggestedIdx.length > 0 && (
                  <>
                    <div style={{ marginTop: 4 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--warning-400)' }}>
                        Предложено AI — требует проверки
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>
                        Позиции нормативно обязательны, но прямо не указаны в ТЗ
                      </div>
                    </div>
                    {suggestedIdx.map(gi => (
                      <EntityCard
                        key={gi}
                        num={gi + 1}
                        entity={entities[gi]}
                        unitCheck={unitChecks[gi]}
                        override={overrides[gi] ?? {}}
                        deleted={isDeleted(gi)}
                        cost={costFor(gi)}
                        usedMinimum={usedMinimumFor(gi)}
                        stage={result?.stage}
                        readOnly={readOnly}
                        warn
                        onOverride={(patch) => applyOverride(gi, patch)}
                      />
                    ))}
                  </>
                )}

                {/* Итог */}
                {calcResult && (
                  <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <TotalRow label="Базовая стоимость" value={fmt(calcResult.base_cost)} />
                    <TotalRow label={`Индекс пересчёта (${calcResult.price_index_period})`} value={`× ${calcResult.price_index}`} />
                    {calcResult.stage_factor !== 1 && (
                      <TotalRow label={`Доля стадии ${calcResult.stage}`} value={`× ${calcResult.stage_factor}`} />
                    )}
                    <TotalRow label={`НДС ${calcResult.vat_rate}%`} value={fmt(calcResult.vat_amount)} />
                    <div style={{ borderTop: '1px solid var(--border-default)', paddingTop: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 14, fontWeight: 600 }}>ИТОГО с НДС</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 20, fontWeight: 700, color: 'var(--fg-1)' }}>
                        {fmtRub(calcResult.total_with_vat)}
                      </span>
                    </div>
                    {basisCount > 0 && (
                      <button onClick={() => setTab('basis')} style={{
                        alignSelf: 'flex-start', marginTop: 2, background: 'transparent', border: 'none',
                        cursor: 'pointer', fontSize: 12, color: 'var(--warning-400)', padding: 0, textDecoration: 'underline',
                      }}>
                        {basisCount} замечаний к расчёту — открыть «Обоснование»
                      </button>
                    )}
                  </div>
                )}

                {/* Уточнение */}
                {!readOnly && (
                  <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>Комментарий / уточнение</div>
                    <textarea
                      value={clarifyText}
                      onChange={e => { setClarifyText(e.target.value); setClarifyDiff(null) }}
                      placeholder="Например: «ячеек 21 шт», «кабельные линии 300 п.м», «убери АСУТП»"
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
                        <div style={{ padding: '8px 12px', background: 'var(--accent-tint)', fontSize: 13, fontWeight: 600, color: 'var(--blue-300)' }}>
                          Что изменится
                        </div>
                        <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                          {clarifyDiff.summary && <div style={{ fontSize: 13, color: 'var(--fg-2)' }}>{clarifyDiff.summary}</div>}
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
                                </li>
                              ))}
                            </ul>
                          )}
                          {(clarifyDiff.total_before != null || clarifyDiff.total_after != null) && (
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                              Итог: {clarifyDiff.total_before != null ? fmtRub(clarifyDiff.total_before) : '—'} → <strong>{clarifyDiff.total_after != null ? fmtRub(clarifyDiff.total_after) : '—'}</strong>
                            </div>
                          )}
                          <div style={{ display: 'flex', gap: 8, marginTop: 2, flexWrap: 'wrap' }}>
                            <Button variant="primary" size="sm" disabled={clarifyBusy} onClick={handleClarifyApply}>
                              {clarifyBusy ? 'Применение…' : 'Подтвердить'}
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
                          {clarifyBusy ? 'AI анализирует…' : 'Применить уточнения'}
                        </Button>
                      </div>
                    )}
                  </div>
                )}

                {/* Действия */}
                {!readOnly && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', paddingBottom: 8 }}>
                    <Button variant={calcResult ? 'secondary' : 'primary'} disabled={computing || finalizing} onClick={handleCompute}>
                      {computing ? 'Расчёт…' : '↻ Пересчитать'}
                    </Button>
                    {calcResult && (
                      <Button variant="primary" disabled={finalizing || computing} onClick={handleFinalize}>
                        {finalizing ? 'Финализация…' : '✓ Финализировать расчёт'}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ═══ Вкладка «Обоснование» ═══ */}
            {tab === 'basis' && result && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <MetaBadge label="Уверенность AI" value={`${Math.round((result.overall_confidence ?? 0) * 100)}%`} />
                  {result.stage && <MetaBadge label="Стадия" value={result.stage} />}
                  {result.region && <MetaBadge label="Регион" value={result.region} />}
                  {calcResult && <MetaBadge label="Индекс" value={`${calcResult.price_index} (${calcResult.price_index_period})`} />}
                </div>

                {curErrors.length > 0 && (
                  <BasisBlock title="Не найдены данные для позиций" tone="danger">
                    {curErrors.map((e, i) => <BasisItem key={i} text={e} tone="danger" />)}
                  </BasisBlock>
                )}

                {missingItems.length > 0 && (
                  <BasisBlock title="Не удалось определить из ТЗ" tone="warning">
                    {missingItems.map((m, i) => (
                      <BasisItem key={i} text={m.text} tone="warning" resolved={m.resolved}
                                 resolvedNote="указано вручную" />
                    ))}
                  </BasisBlock>
                )}

                {(curWarnings.length > 0 || resolvedWarnings.length > 0) && (
                  <BasisBlock title="Предупреждения расчёта" tone="warning">
                    {curWarnings.map((w, i) => <BasisItem key={`c${i}`} text={w} tone="warning" />)}
                    {resolvedWarnings.map((w, i) => (
                      <BasisItem key={`r${i}`} text={w} tone="warning" resolved
                                 resolvedNote="устранено после пересчёта" />
                    ))}
                  </BasisBlock>
                )}

                {basisCount === 0 && resolvedWarnings.length === 0 && (
                  <div style={{ padding: 32, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
                    Замечаний нет — расчёт без предупреждений.
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}

// ── Карточка позиции ──────────────────────────────────────────────────────────
function EntityCard({ num, entity, unitCheck, override, deleted, cost, usedMinimum, stage, readOnly, warn, onOverride }: {
  num: number
  entity: ExtractedEntity
  unitCheck?: UnitCheckItem
  override: EntityOverride
  deleted: boolean
  cost: number | null
  usedMinimum?: boolean
  stage?: string
  readOnly: boolean
  warn?: boolean
  onOverride: (patch: Partial<EntityOverride>) => void
}) {
  const [editing, setEditing] = useState(false)
  const [inputVal, setInputVal] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const effX    = override.x_value !== undefined ? override.x_value : entity.x_value
  const effUnit = override.x_unit  !== undefined ? override.x_unit  : entity.x_unit
  const xMissing = effX == null

  const tone  = CATEGORY_TONES[entity.category] || 'default'
  const label = CATEGORY_LABELS[entity.category] || entity.category
  const strike: React.CSSProperties = deleted ? { textDecoration: 'line-through', opacity: 0.5 } : {}

  const showPct = stage === 'П+Р' && !deleted
  const pdPct = override.pd_sections_pct ?? entity.pd_sections_pct ?? null
  const rdPct = override.rd_sections_pct ?? entity.rd_sections_pct ?? null

  function startEdit() {
    if (readOnly || deleted) return
    setInputVal(effX != null ? String(effX).replace('.', ',') : '')
    setEditing(true)
    setTimeout(() => inputRef.current?.focus(), 0)
  }
  function commitEdit() {
    const n = parseFloat(inputVal.replace(',', '.'))
    if (!isNaN(n)) onOverride({ x_value: n })
    setEditing(false)
  }

  return (
    <div style={{
      background: deleted ? 'color-mix(in srgb, var(--danger-500) 6%, var(--bg-elevated))' : 'var(--bg-elevated)',
      border: warn ? '1px solid var(--warning-500)' : 'var(--hairline)',
      borderRadius: 'var(--radius-lg)', padding: '12px 14px',
      display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0,
    }}>
      {/* строка 1: номер + чипы + удалить */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-4)' }}>№{num}</span>
        <Chip tone={tone}>{label}</Chip>
        {(entity.confidence ?? 1) < 0.7 && <Chip tone="warning">AI {Math.round((entity.confidence ?? 0) * 100)}%</Chip>}
        {usedMinimum && !deleted && <Chip tone="warning">X условный</Chip>}
        <span style={{ flex: 1 }} />
        {!readOnly && (
          deleted ? (
            <button onClick={() => onOverride({ deleted: false })}
              style={{ fontSize: 11, padding: '3px 10px', background: 'transparent', border: '1px solid var(--fg-3)', borderRadius: 4, color: 'var(--fg-3)', cursor: 'pointer', whiteSpace: 'nowrap' }}
            >↩ вернуть</button>
          ) : (
            <button onClick={() => onOverride({ deleted: true })} title="Удалить позицию"
              style={{ fontSize: 13, padding: '2px 9px', background: 'transparent', border: '1px solid var(--border-default)', borderRadius: 4, color: 'var(--fg-3)', cursor: 'pointer' }}
            >×</button>
          )
        )}
      </div>

      {/* строка 2: цена слева + название */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700, color: cost != null ? 'var(--fg-1)' : 'var(--fg-4)', whiteSpace: 'nowrap', ...strike }}>
          {deleted ? '—' : cost != null ? fmtRub(cost) : '· · ·'}
        </span>
        <span style={{ fontSize: 13, fontWeight: 600, minWidth: 0, ...strike }}>{entity.object_type}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--fg-3)', ...strike }}>
        {entity.object_name}{entity.address ? ` · ${entity.address}` : ''}
      </div>

      {/* строка 3: X */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>X:</span>
        {editing ? (
          <input
            ref={inputRef}
            value={inputVal}
            onChange={e => setInputVal(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') setEditing(false) }}
            onBlur={commitEdit}
            inputMode="decimal"
            style={{ width: 90, fontFamily: 'var(--font-mono)', fontSize: 13, padding: '4px 8px', background: 'var(--bg-input)', border: '1px solid var(--border-focus)', borderRadius: 4, color: 'var(--fg-1)', outline: 'none' }}
            placeholder="0,0"
          />
        ) : (
          <span
            onClick={startEdit}
            title={xMissing ? (entity.x_value_missing_reason ?? 'Не указано в ТЗ') : readOnly ? undefined : 'Нажмите для редактирования'}
            style={readOnly ? {
              // финал: X — просто текст, без намёка на редактируемость
              fontFamily: 'var(--font-mono)', fontSize: 13, padding: '3px 0',
              color: xMissing ? 'var(--fg-3)' : 'var(--fg-1)',
              ...strike,
            } : {
              cursor: deleted ? 'default' : 'pointer',
              fontFamily: 'var(--font-mono)', fontSize: 13,
              padding: '3px 10px', borderRadius: 4,
              background: xMissing ? 'color-mix(in srgb, var(--warning-500) 15%, transparent)' : 'var(--bg-raised)',
              border: xMissing ? '1px solid var(--warning-500)' : '1px solid var(--border-subtle)',
              color: xMissing ? 'var(--warning-400)' : 'var(--fg-1)',
              ...strike,
            }}
          >
            {xMissing ? (readOnly ? '— (условно)' : '⚠ указать') : effX!.toLocaleString('ru-RU', { maximumFractionDigits: 4 })}
          </span>
        )}
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{effUnit || ''}</span>
        {unitCheck && (
          !unitCheck.ok ? (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--danger-400)' }}>⚠ {unitCheck.note}</span>
          ) : unitCheck.note ? (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: unitCheck.extrapolated ? 'var(--warning-400)' : 'var(--success-400)' }}>
              → {unitCheck.x_effective?.toLocaleString('ru-RU', { maximumFractionDigits: 4 })} {unitCheck.x_unit_table}
              {unitCheck.extrapolated ? ' (экстрап.)' : ''}
            </span>
          ) : (
            <span style={{ fontSize: 11, color: 'var(--success-400)' }}>✓</span>
          )
        )}
      </div>

      {/* проценты разделов (только П+Р) */}
      {showPct && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, color: 'var(--fg-3)', fontWeight: 600 }}>Разделы %:</span>
          {(['ПД', 'РД'] as const).map((lbl) => {
            const field = lbl === 'ПД' ? 'pd_sections_pct' : 'rd_sections_pct'
            const val = lbl === 'ПД' ? pdPct : rdPct
            return (
              <label key={lbl} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                <span style={{ color: 'var(--fg-3)' }}>{lbl}</span>
                <input
                  type="number" min={0} max={100} step={0.5} placeholder="100"
                  disabled={readOnly}
                  value={val != null ? Math.round(val * 100) : ''}
                  onChange={e => {
                    const n = parseFloat(e.target.value)
                    onOverride({ [field]: isNaN(n) ? null : n / 100 } as Partial<EntityOverride>)
                  }}
                  style={{
                    width: 56, fontFamily: 'var(--font-mono)', fontSize: 12,
                    padding: '2px 6px', background: 'var(--bg-input)',
                    border: '1px solid var(--border-default)', borderRadius: 4,
                    color: 'var(--fg-1)', outline: 'none', textAlign: 'right',
                  }}
                />
                <span style={{ color: 'var(--fg-3)' }}>%</span>
              </label>
            )
          })}
        </div>
      )}

      {/* подробности: цитата ТЗ + примечания — свёрнуты, чтобы не сливалось */}
      {(entity.tz_quote || entity.notes || (xMissing && entity.x_value_missing_reason)) && (
        <details style={{ fontSize: 12 }}>
          <summary style={{ cursor: 'pointer', color: 'var(--fg-4)', fontSize: 11, userSelect: 'none' }}>
            подробности из ТЗ
          </summary>
          <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {xMissing && entity.x_value_missing_reason && (
              <div style={{ color: 'var(--warning-400)', fontSize: 11 }}>⚠ {entity.x_value_missing_reason}</div>
            )}
            {entity.tz_quote && (
              <div style={{ color: 'var(--fg-4)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                <span style={{ color: 'var(--fg-3)', marginRight: 4 }}>ТЗ:</span>«{entity.tz_quote}»
              </div>
            )}
            {entity.notes && <div style={{ color: 'var(--fg-3)', fontStyle: 'italic' }}>{entity.notes}</div>}
          </div>
        </details>
      )}
    </div>
  )
}

// ── Итоговая строка ───────────────────────────────────────────────────────────
function TotalRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13, color: 'var(--fg-2)', flexWrap: 'wrap' }}>
      <span>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)' }}>{value}</span>
    </div>
  )
}

// ── Блоки вкладки «Обоснование» ───────────────────────────────────────────────
function BasisBlock({ title, tone, children }: { title: string; tone: 'warning' | 'danger'; children: React.ReactNode }) {
  const color = tone === 'danger' ? 'var(--danger-400)' : 'var(--warning-400)'
  const border = tone === 'danger' ? 'var(--danger-500)' : 'var(--warning-500)'
  return (
    <div style={{ border: `1px solid ${border}`, borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', fontSize: 13, fontWeight: 600, color, borderBottom: `1px solid ${border}` }}>
        {title}
      </div>
      <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {children}
      </div>
    </div>
  )
}

function BasisItem({ text, tone, resolved, resolvedNote }: {
  text: string; tone: 'warning' | 'danger'; resolved?: boolean; resolvedNote?: string
}) {
  const color = tone === 'danger' ? 'var(--danger-400)' : 'var(--warning-400)'
  return (
    <div style={{ fontSize: 12, lineHeight: 1.5 }}>
      <span style={{
        color: resolved ? 'var(--fg-4)' : color,
        textDecoration: resolved ? 'line-through' : 'none',
      }}>
        {text}
      </span>
      {resolved && resolvedNote && (
        <span style={{ color: 'var(--success-400)', marginLeft: 8, fontSize: 11, whiteSpace: 'nowrap' }}>
          ✓ {resolvedNote}
        </span>
      )}
    </div>
  )
}

function MetaBadge({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: '6px 12px', background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }}>
      {label}: <strong style={{ color: 'var(--fg-1)' }}>{value}</strong>
    </div>
  )
}

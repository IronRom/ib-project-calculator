'use client'

import { useEffect, useState } from 'react'
import { listIndices, createIndex, updateIndex, PriceIndex } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

const ROMAN: Record<number, string> = { 1: 'I', 2: 'II', 3: 'III', 4: 'IV' }

export default function AdminCoefficientsPage() {
  const [priceIndex, setPriceIndex] = useState<PriceIndex | null>(null)
  const [vatIndex, setVatIndex]     = useState<PriceIndex | null>(null)
  const [loading, setLoading] = useState(true)

  // editable state — price index
  const [piYear,    setPiYear]    = useState('')
  const [piQuarter, setPiQuarter] = useState('4')
  const [piValue,   setPiValue]   = useState('')
  const [piRef,     setPiRef]     = useState('')
  const [piSaving,  setPiSaving]  = useState(false)
  const [piError,   setPiError]   = useState('')
  const [piOk,      setPiOk]      = useState(false)

  // editable state — vat
  const [vatValue,  setVatValue]  = useState('')
  const [vatSaving, setVatSaving] = useState(false)
  const [vatError,  setVatError]  = useState('')
  const [vatOk,     setVatOk]     = useState(false)

  useEffect(() => {
    listIndices().then((all) => {
      const pi = all.filter((i) => i.index_type === 'project').sort((a, b) => b.year - a.year || b.quarter - a.quarter)[0] ?? null
      const vat = all.filter((i) => i.index_type === 'vat').sort((a, b) => b.year - a.year)[0] ?? null
      setPriceIndex(pi)
      setVatIndex(vat)
      if (pi) { setPiYear(String(pi.year)); setPiQuarter(String(pi.quarter)); setPiValue(String(Number(pi.index_value))); setPiRef(pi.source_ref) }
      if (vat) { setVatValue(String(Number(vat.index_value))) }
    }).finally(() => setLoading(false))
  }, [])

  async function savePriceIndex() {
    setPiSaving(true); setPiError(''); setPiOk(false)
    try {
      const payload = { year: parseInt(piYear), quarter: parseInt(piQuarter), index_value: parseFloat(piValue), source_ref: piRef, index_type: 'project' }
      if (priceIndex) {
        const updated = await updateIndex(priceIndex.id, payload)
        setPriceIndex(updated)
      } else {
        const { createIndex: create } = await import('@/lib/api')
        const created = await create(payload)
        setPriceIndex(created)
      }
      setPiOk(true)
      setTimeout(() => setPiOk(false), 2000)
    } catch (e: unknown) { setPiError(e instanceof Error ? e.message : 'Ошибка') }
    finally { setPiSaving(false) }
  }

  async function saveVat() {
    setVatSaving(true); setVatError(''); setVatOk(false)
    try {
      const payload = { year: new Date().getFullYear(), quarter: 0, index_value: parseFloat(vatValue), source_ref: '', index_type: 'vat' }
      if (vatIndex) {
        const updated = await updateIndex(vatIndex.id, { index_value: parseFloat(vatValue) })
        setVatIndex(updated)
      } else {
        const { createIndex: create } = await import('@/lib/api')
        const created = await create(payload)
        setVatIndex(created)
      }
      setVatOk(true)
      setTimeout(() => setVatOk(false), 2000)
    } catch (e: unknown) { setVatError(e instanceof Error ? e.message : 'Ошибка') }
    finally { setVatSaving(false) }
  }

  const card: React.CSSProperties = {
    background: 'var(--bg-elevated)', border: 'var(--hairline)',
    borderRadius: 'var(--radius-lg)', padding: 24,
  }
  const label: React.CSSProperties = { fontSize: 12, fontWeight: 500, color: 'var(--fg-2)', marginBottom: 6, display: 'block' }
  const sel: React.CSSProperties = {
    background: 'var(--bg-input)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)',
    padding: '8px 12px', fontSize: 13, color: 'var(--fg-1)', width: '100%',
  }

  if (loading) return <div style={{ padding: 28, color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>

  return (
    <>
      <Topbar title="Коэффициенты" breadcrumb="Администрирование" />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 28, maxWidth: 720 }}>

        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Обязательные
        </div>

        {/* ── Коэффициент пересчёта ── */}
        <div style={card}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Коэффициент пересчёта базовой стоимости</div>
          <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 20 }}>
            Квартальные письма Минстроя, Приложение №3, п.1
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 16 }}>
            <div>
              <label style={label}>Квартал</label>
              <select style={sel} value={piQuarter} onChange={(e) => setPiQuarter(e.target.value)}>
                {[1,2,3,4].map((q) => <option key={q} value={q}>{ROMAN[q]}</option>)}
              </select>
            </div>
            <Input label="Год" type="number" value={piYear} onChange={(e) => setPiYear(e.target.value)} />
            <Input label="Коэффициент" type="number" step="0.01" value={piValue} onChange={(e) => setPiValue(e.target.value)} placeholder="6.88" />
          </div>

          <div style={{ marginBottom: 20 }}>
            <Input
              label="Обоснование (письмо Минстроя)"
              value={piRef}
              onChange={(e) => setPiRef(e.target.value)}
              placeholder="№62725-ИФ/09 от 20.10.2025, Прил.3 п.1"
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Button variant="primary" size="sm" disabled={piSaving} onClick={savePriceIndex}>
              {piSaving ? 'Сохранение…' : 'Сохранить'}
            </Button>
            {piOk    && <span style={{ fontSize: 13, color: 'var(--success-400)' }}>Сохранено</span>}
            {piError && <span style={{ fontSize: 13, color: 'var(--danger-400)' }}>{piError}</span>}
          </div>
        </div>

        {/* ── НДС ── */}
        <div style={card}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>НДС</div>
          <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 20 }}>
            Применяется к итоговой стоимости проектных работ
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 16, alignItems: 'end', marginBottom: 20 }}>
            <Input label="Ставка НДС (%)" type="number" step="0.01" value={vatValue} onChange={(e) => setVatValue(e.target.value)} placeholder="22" />
            <div />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Button variant="primary" size="sm" disabled={vatSaving} onClick={saveVat}>
              {vatSaving ? 'Сохранение…' : 'Сохранить'}
            </Button>
            {vatOk    && <span style={{ fontSize: 13, color: 'var(--success-400)' }}>Сохранено</span>}
            {vatError && <span style={{ fontSize: 13, color: 'var(--danger-400)' }}>{vatError}</span>}
          </div>
        </div>

      </div>
    </>
  )
}

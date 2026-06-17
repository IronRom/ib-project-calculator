'use client'

import React, { useCallback, useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import {
  getIgiBookRows, saveGeologicalSurveys,
  GeologicalSurvey, IgiItem, IgiObjectType, IgiBookRow,
  IgiWorkCategory, CalculationResult,
} from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'

const CAT_LABELS: Record<IgiWorkCategory, string> = {
  field: 'Полевые',
  lab: 'Лабораторные',
  kameral: 'Камеральные',
  program: 'Программа',
}

function fmt(n: number) {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(n)
}

export default function GeologyPage() {
  const { id } = useParams<{ id: string }>()
  const sp = useSearchParams()
  const calcId = sp.get('calc')

  const [bookData, setBookData] = useState<{ bookId: number; bookCode: string; objectTypes: IgiObjectType[] } | null>(null)
  const [survey, setSurvey] = useState<GeologicalSurvey>({
    book_id: 0,
    book_code: '',
    complexity_category: 2,
    k1: 0.70,
    winter_pct: 0.29,
    k2: 1.0,
    items: [],
  })
  const [result, setResult] = useState<CalculationResult | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Picker state
  const [pickerOtype, setPickerOtype] = useState<IgiObjectType | null>(null)
  const [pickerRow, setPickerRow] = useState<IgiBookRow | null>(null)
  const [pickerVolume, setPickerVolume] = useState('')

  useEffect(() => {
    if (!calcId) return
    getIgiBookRows(Number(id), Number(calcId)).then(d => {
      setBookData({ bookId: d.book_id, bookCode: d.book_code, objectTypes: d.object_types })
      setSurvey(prev => ({ ...prev, book_id: d.book_id, book_code: d.book_code }))
    }).catch(e => setError(String(e)))
  }, [id, calcId])

  const addItem = useCallback(() => {
    if (!pickerOtype || !pickerRow || !pickerVolume) return
    const vol = parseFloat(pickerVolume)
    if (isNaN(vol) || vol <= 0) return

    const workCat = (pickerOtype.work_category as IgiWorkCategory) || 'field'
    const item: IgiItem = {
      work_category: workCat,
      object_type_name: pickerOtype.object_type_name,
      table_num: pickerOtype.table_num,
      row_num: pickerRow.row_num,
      description: pickerRow.description ?? '',
      volume: vol,
      x_unit: pickerRow.x_unit ?? '',
      b: pickerRow.b,
    }
    setSurvey(prev => ({ ...prev, items: [...prev.items, item] }))
    setPickerRow(null)
    setPickerVolume('')
  }, [pickerOtype, pickerRow, pickerVolume])

  const removeItem = useCallback((idx: number) => {
    setSurvey(prev => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== idx),
    }))
  }, [])

  const handleSave = async () => {
    if (!calcId) return
    setSaving(true)
    setError('')
    try {
      const res = await saveGeologicalSurveys(Number(id), Number(calcId), [survey])
      setResult(res)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const igiPositions = result?.positions?.filter(p => p.section_name === 'ИГИ') ?? []
  const igiTotal = igiPositions.length > 0 ? igiPositions.reduce((s, p) => s + p.cost, 0) : null

  if (!calcId) return (
    <div className="min-h-screen bg-neutral-950 text-white flex items-center justify-center">
      <p className="text-neutral-400">Откройте страницу из расчёта (параметр ?calc= отсутствует)</p>
    </div>
  )

  return (
    <div className="min-h-screen bg-neutral-950 text-white">
      <Topbar title="ИГИ" />
      <div className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-semibold mb-6">Инженерно-геологические изыскания (ИГИ)</h1>

        {/* Survey parameters */}
        <div className="bg-neutral-900 rounded-xl p-5 mb-6 flex gap-6 flex-wrap">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-400">Кат. сложности ИГИ</span>
            <select
              className="bg-neutral-800 rounded px-3 py-1.5 text-white"
              value={survey.complexity_category}
              onChange={e => setSurvey(p => ({ ...p, complexity_category: Number(e.target.value) }))}
            >
              <option value={1}>I</option>
              <option value={2}>II</option>
              <option value={3}>III</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-400">К1 (место работы)</span>
            <input
              type="number" step="0.01" min="0.5" max="1"
              className="bg-neutral-800 rounded px-3 py-1.5 text-white w-24"
              value={survey.k1}
              onChange={e => setSurvey(p => ({ ...p, k1: Number(e.target.value) }))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-400">Зимний % (доля, 0.29=29%)</span>
            <input
              type="number" step="0.01" min="0" max="1"
              className="bg-neutral-800 rounded px-3 py-1.5 text-white w-24"
              value={survey.winter_pct}
              onChange={e => setSurvey(p => ({ ...p, winter_pct: Number(e.target.value) }))}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-neutral-400">К2 (климат)</span>
            <input
              type="number" step="0.01" min="1" max="2"
              className="bg-neutral-800 rounded px-3 py-1.5 text-white w-24"
              value={survey.k2}
              onChange={e => setSurvey(p => ({ ...p, k2: Number(e.target.value) }))}
            />
          </label>
        </div>

        {/* Picker */}
        {bookData && (
          <div className="bg-neutral-900 rounded-xl p-5 mb-6">
            <h2 className="font-medium mb-4 text-neutral-300">Добавить позицию</h2>
            <div className="flex gap-3 flex-wrap items-end">
              <div className="flex flex-col gap-1 text-sm">
                <span className="text-neutral-400">Вид работ</span>
                <select
                  className="bg-neutral-800 rounded px-3 py-1.5 text-white min-w-[260px]"
                  value={pickerOtype?.object_type_id ?? ''}
                  onChange={e => {
                    const ot = bookData.objectTypes.find(o => o.object_type_id === Number(e.target.value)) ?? null
                    setPickerOtype(ot)
                    setPickerRow(null)
                  }}
                >
                  <option value="">— выберите —</option>
                  {bookData.objectTypes.map(ot => (
                    <option key={ot.object_type_id} value={ot.object_type_id}>
                      {ot.object_type_name}
                    </option>
                  ))}
                </select>
              </div>
              {pickerOtype && (
                <div className="flex flex-col gap-1 text-sm">
                  <span className="text-neutral-400">Строка таблицы {pickerOtype.table_num}</span>
                  <select
                    className="bg-neutral-800 rounded px-3 py-1.5 text-white min-w-[320px]"
                    value={pickerRow?.id ?? ''}
                    onChange={e => {
                      const r = pickerOtype.rows.find(r => r.id === Number(e.target.value)) ?? null
                      setPickerRow(r)
                    }}
                  >
                    <option value="">— выберите —</option>
                    {pickerOtype.rows.map(r => (
                      <option key={r.id} value={r.id}>
                        {r.row_num} — {(r.description ?? '').slice(0, 80)}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {pickerRow && (
                <>
                  <div className="flex flex-col gap-1 text-sm">
                    <span className="text-neutral-400">Объём ({pickerRow.x_unit})</span>
                    <input
                      type="number" min="0"
                      className="bg-neutral-800 rounded px-3 py-1.5 text-white w-28"
                      value={pickerVolume}
                      onChange={e => setPickerVolume(e.target.value)}
                      placeholder="0"
                    />
                  </div>
                  <Button onClick={addItem} disabled={!pickerVolume}>+ Добавить</Button>
                </>
              )}
            </div>
          </div>
        )}

        {/* Items table */}
        {survey.items.length > 0 && (
          <div className="bg-neutral-900 rounded-xl mb-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-800 text-neutral-400">
                  <th className="px-4 py-3 text-left">Вид</th>
                  <th className="px-4 py-3 text-left">Наименование</th>
                  <th className="px-4 py-3 text-left">Таблица</th>
                  <th className="px-4 py-3 text-right">Объём</th>
                  <th className="px-4 py-3 text-left">Ед.</th>
                  <th className="px-4 py-3 text-right">Ставка (руб)</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {survey.items.map((item, i) => (
                  <tr key={`${item.table_num}-${item.row_num}-${i}`} className="border-b border-neutral-800/50 hover:bg-neutral-800/40">
                    <td className="px-4 py-2">
                      <span className="text-xs bg-neutral-700 rounded px-2 py-0.5">
                        {CAT_LABELS[item.work_category]}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-neutral-200 max-w-xs truncate" title={item.description}>
                      {item.object_type_name}
                    </td>
                    <td className="px-4 py-2 text-neutral-400">
                      Табл.{item.table_num} {item.row_num}
                    </td>
                    <td className="px-4 py-2 text-right">{item.volume}</td>
                    <td className="px-4 py-2 text-neutral-400 text-xs">{item.x_unit}</td>
                    <td className="px-4 py-2 text-right font-mono">{fmt(item.b)}</td>
                    <td className="px-4 py-2">
                      <button
                        onClick={() => removeItem(i)}
                        className="text-neutral-500 hover:text-red-400 text-xs"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

        <div className="flex gap-4 items-center">
          <Button onClick={handleSave} disabled={saving || survey.items.length === 0 || survey.book_id === 0}>
            {saving ? 'Сохраняю…' : 'Сохранить и рассчитать'}
          </Button>
          {igiTotal !== null && (
            <span className="text-neutral-300">
              ИГИ итого: <strong>{fmt(igiTotal)} руб.</strong> без НДС
            </span>
          )}
        </div>

        {/* Result positions */}
        {igiPositions.length > 0 && (
          <div className="mt-8">
            <h2 className="font-medium mb-4 text-neutral-300">Результат расчёта ИГИ</h2>
            <div className="bg-neutral-900 rounded-xl overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-neutral-800 text-neutral-400">
                    <th className="px-4 py-3 text-left">№</th>
                    <th className="px-4 py-3 text-left">Наименование</th>
                    <th className="px-4 py-3 text-left">Обоснование</th>
                    <th className="px-4 py-3 text-right">Стоимость, руб.</th>
                  </tr>
                </thead>
                <tbody>
                  {igiPositions.map(p => (
                    <tr key={p.num} className="border-b border-neutral-800/50">
                      <td className="px-4 py-2 text-neutral-400">{p.num}</td>
                      <td className="px-4 py-2">{p.name}</td>
                      <td className="px-4 py-2 text-neutral-400 text-xs">{p.justification}</td>
                      <td className="px-4 py-2 text-right font-mono">{fmt(p.cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

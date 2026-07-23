'use client'

import { useEffect, useState } from 'react'
import { getAdminSettings, putAdminSettings, listOpenRouterModels, OpenRouterModel } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'

const KEYS: { key: string; label: string; hint: string }[] = [
  { key: 'extraction_model', label: 'Модель извлечения из ТЗ', hint: 'Полный трёхпроходный анализ технического задания' },
  { key: 'clarification_model', label: 'Модель уточнений', hint: 'Точечные правки расчёта по свободному тексту менеджера' },
  { key: 'ocr_model', label: 'Модель OCR сканов', hint: 'Распознавание PDF без текстового слоя' },
]

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [models, setModels] = useState<OpenRouterModel[]>([])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [modelsError, setModelsError] = useState(false)

  useEffect(() => {
    getAdminSettings().then(setSettings).catch(() => {})
    listOpenRouterModels()
      .then((ms) => { setModels(ms); setModelsError(ms.length === 0) })
      .catch(() => setModelsError(true))
  }, [])

  async function save() {
    setSaving(true)
    setSaved(false)
    try {
      await putAdminSettings(settings)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Topbar title="Настройки системы" breadcrumb="Администрирование"
        actions={<Button variant="primary" disabled={saving} onClick={save}>
          {saving ? 'Сохранение…' : saved ? '✓ Сохранено' : 'Сохранить'}
        </Button>} />
      <div style={{ padding: '24px 28px', maxWidth: 760, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: 1,
          color: 'var(--fg-3)',
        }}>МОДЕЛИ AI · ПРИМЕНЯЮТСЯ КО ВСЕМ НОВЫМ ОПЕРАЦИЯМ · TEMPERATURE=0</div>
        {modelsError && (
          <div style={{
            padding: '12px 16px', borderRadius: 'var(--radius-md)', fontSize: 13,
            background: 'rgba(217,119,6,0.10)', border: '1px solid var(--warning-500)',
            color: 'var(--warning-400)', lineHeight: 1.6,
          }}>
            Список моделей OpenRouter недоступен с этого сервера (гео-блок «Access
            denied by security policy»). Идентификаторы можно ввести вручную —
            но AI-операции заработают только после настройки прокси
            (OPENROUTER_PROXY в /opt/pir/.env).
          </div>
        )}
        {KEYS.map(({ key, label, hint }) => (
          <div key={key} style={{
            background: 'var(--bg-elevated)', border: 'var(--hairline)',
            borderRadius: 'var(--radius-lg)', padding: '16px 18px',
            display: 'flex', flexDirection: 'column', gap: 8,
          }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>{label}</div>
            <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>{hint}</div>
            {models.length > 0 ? (
              <select
                value={settings[key] || ''}
                onChange={(e) => setSettings((s) => ({ ...s, [key]: e.target.value }))}
                style={{
                  background: 'var(--bg-input)', border: 'var(--hairline)',
                  borderRadius: 'var(--radius-md)', padding: '8px 10px',
                  fontSize: 12, color: 'var(--fg-1)', fontFamily: 'var(--font-mono)',
                }}>
                {settings[key] && !models.find((m) => m.id === settings[key]) && (
                  <option value={settings[key]}>{settings[key]}</option>
                )}
                {models.map((m) => (
                  <option key={m.id} value={m.id}>{m.id}</option>
                ))}
              </select>
            ) : (
              <input
                value={settings[key] || ''}
                onChange={(e) => setSettings((s) => ({ ...s, [key]: e.target.value }))}
                placeholder="например: qwen/qwen3.7-plus"
                style={{
                  background: 'var(--bg-input)', border: 'var(--hairline)',
                  borderRadius: 'var(--radius-md)', padding: '8px 10px',
                  fontSize: 12, color: 'var(--fg-1)', fontFamily: 'var(--font-mono)',
                }} />
            )}
          </div>
        ))}
      </div>
    </>
  )
}

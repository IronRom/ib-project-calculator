'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { Topbar } from '@/components/layout/Topbar'

interface ProgressState {
  step: number
  total: number
  message: string
}

export default function ProcessingPage() {
  const { id } = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const calcId = searchParams.get('calc')
  const orModel = searchParams.get('model')
  const router = useRouter()
  const [progress, setProgress] = useState<ProgressState>({ step: 0, total: 3, message: 'Инициализация…' })
  const [error, setError] = useState('')

  useEffect(() => {
    if (!calcId) return

    const token = localStorage.getItem('pir_token')
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const params = new URLSearchParams()
    if (token) params.set('token', token)
    if (orModel) params.set('model', orModel)
    const url = `${apiUrl}/projects/${id}/calculations/${calcId}/stream?${params.toString()}`
    const es = new EventSource(url)

    es.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data)
      setProgress(data)
    })

    es.addEventListener('done', (e) => {
      es.close()
      const data = JSON.parse(e.data)
      router.push(`/projects/${id}/entities?calc=${data.calc_id}`)
    })

    es.addEventListener('error', (e) => {
      es.close()
      try {
        const data = JSON.parse((e as MessageEvent).data)
        setError(data.message)
      } catch {
        setError('Ошибка извлечения данных')
      }
    })

    return () => es.close()
  }, [id, calcId, orModel, router])

  const pct = progress.total > 0 ? Math.round((progress.step / progress.total) * 100) : 0

  return (
    <>
      <Topbar title="Анализ технического задания" breadcrumb="Проекты" />
      <div style={{ padding: '48px 28px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 32, maxWidth: 560, margin: '0 auto' }}>
        {error ? (
          <div style={{ width: '100%', padding: '16px 20px', background: 'var(--danger-100)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-lg)', fontSize: 13, color: 'var(--danger-400)' }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Ошибка обработки</div>
            {error}
          </div>
        ) : (
          <div style={{ width: '100%', background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', padding: 32, display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>AI-анализ технического задания</div>
              <div style={{ fontSize: 13, color: 'var(--fg-3)' }}>
                Шаг {progress.step} из {progress.total}: {progress.message}
              </div>
            </div>

            {/* Progress bar */}
            <div style={{ background: 'var(--bg-raised)', borderRadius: 'var(--radius-full)', height: 6, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent)', borderRadius: 'var(--radius-full)', transition: 'width 0.3s ease' }} />
            </div>

            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)', textAlign: 'right' }}>
              {pct}%
            </div>
          </div>
        )}
      </div>
    </>
  )
}

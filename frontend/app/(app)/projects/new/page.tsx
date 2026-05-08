'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createProject } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

export default function NewProjectPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setError('Введите наименование проекта'); return }
    setLoading(true)
    try {
      const project = await createProject(name.trim())
      router.push(`/projects/${project.id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка создания')
      setLoading(false)
    }
  }

  return (
    <>
      <Topbar title="Новый расчёт" breadcrumb="Проекты" />
      <div style={{ padding: '24px 28px', maxWidth: 560 }}>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Параметры проекта</div>
            <Input
              label="Наименование проекта"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="КНС г. Тюмень, ул. Ленина 42"
              required
              error={error}
            />
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <Button variant="secondary" onClick={() => router.push('/projects')}>Отмена</Button>
            <Button type="submit" variant="primary" disabled={loading}>
              {loading ? 'Создание…' : 'Создать проект'}
            </Button>
          </div>
        </form>
      </div>
    </>
  )
}

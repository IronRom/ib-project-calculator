'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { listProjects, deleteProject, Project } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'

const STATUS_MAP: Record<string, { label: string; tone: 'success' | 'warning' | 'info' | 'default' }> = {
  draft:      { label: 'Черновик',   tone: 'default'  },
  processing: { label: 'Обработка', tone: 'info'     },
  extracted:  { label: 'Извлечено', tone: 'warning'  },
  calculated: { label: 'Рассчитан', tone: 'success'  },
  exported:   { label: 'Готов',     tone: 'success'  },
}

export default function ProjectsPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listProjects().then(setProjects).finally(() => setLoading(false))
  }, [])

  async function handleDelete(id: number, e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm('Удалить проект?')) return
    await deleteProject(id)
    setProjects((p) => p.filter((x) => x.id !== id))
  }

  return (
    <>
      <Topbar
        title="Проекты"
        breadcrumb="ИС·ПИР"
        actions={
          <Button variant="primary" onClick={() => router.push('/projects/new')}>
            + Новый расчёт
          </Button>
        }
      />
      <div style={{ padding: '24px 28px' }}>
        {loading ? (
          <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>
        ) : projects.length === 0 ? (
          <EmptyState onNew={() => router.push('/projects/new')} />
        ) : (
          <ProjectTable projects={projects} onOpen={(p) => router.push(`/projects/${p.id}`)} onDelete={handleDelete} />
        )}
      </div>
    </>
  )
}

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 0', gap: 16, color: 'var(--fg-3)' }}>
      <div style={{ fontSize: 48 }}>📂</div>
      <div style={{ fontSize: 15, color: 'var(--fg-2)', fontWeight: 500 }}>Нет проектов</div>
      <div style={{ fontSize: 13 }}>Создайте первый расчёт ПИР</div>
      <Button variant="primary" onClick={onNew}>Создать проект</Button>
    </div>
  )
}

function ProjectTable({ projects, onOpen, onDelete }: {
  projects: Project[]
  onOpen: (p: Project) => void
  onDelete: (id: number, e: React.MouseEvent) => void
}) {
  return (
    <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ padding: '14px 18px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>Проекты</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{projects.length} записей</div>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead style={{ background: 'var(--bg-raised)' }}>
          <tr>
            {['Наименование', 'Файлов', 'Статус', 'Создан', ''].map((h, i) => (
              <th key={i} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-default)' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {projects.map((p, i) => {
            const st = STATUS_MAP[p.status] || { label: p.status, tone: 'default' as const }
            return (
              <tr
                key={p.id}
                onClick={() => onOpen(p)}
                style={{ cursor: 'pointer', borderBottom: i < projects.length - 1 ? 'var(--hairline)' : 'none' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-hover)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <td style={{ padding: '12px 14px', fontWeight: 500 }}>{p.name}</td>
                <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>
                  {p.files?.length ?? 0}
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <Chip tone={st.tone}>{st.label}</Chip>
                </td>
                <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                  {new Date(p.created_at).toLocaleDateString('ru-RU')}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right' }}>
                  <button
                    onClick={(e) => handleDeleteWrapper(p.id, e, onDelete)}
                    style={{ background: 'transparent', border: 'none', color: 'var(--fg-4)', cursor: 'pointer', fontSize: 16 }}
                    title="Удалить"
                  >
                    ×
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function handleDeleteWrapper(id: number, e: React.MouseEvent, onDelete: (id: number, e: React.MouseEvent) => void) {
  e.stopPropagation()
  onDelete(id, e)
}

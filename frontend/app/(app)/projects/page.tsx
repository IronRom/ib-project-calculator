'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { listProjects, deleteProject, Project } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'

const STATUS_MAP: Record<string, { label: string; tone: 'success' | 'warning' | 'info' | 'default' }> = {
  draft:      { label: 'Черновик',  tone: 'default' },
  processing: { label: 'Обработка', tone: 'info'    },
  extracted:  { label: 'Извлечено', tone: 'warning' },
  calculated: { label: 'Рассчитан', tone: 'success' },
  exported:   { label: 'Готов',     tone: 'success' },
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
    if (!confirm('Удалить проект со всеми расчётами?')) return
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
            + Новый проект
          </Button>
        }
      />
      <div style={{ padding: '24px 28px' }}>
        {loading ? (
          <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>
        ) : projects.length === 0 ? (
          <EmptyState onNew={() => router.push('/projects/new')} />
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: 16,
          }}>
            {projects.map((p) => (
              <ProjectCard key={p.id} p={p}
                onOpen={() => router.push(`/projects/${p.id}`)}
                onDelete={(e) => handleDelete(p.id, e)} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}

/* Плитка проекта: номер-шифр, имя, статус, файлы, дата. Индустриальная
   карточка с моно-деталями и синим кантом при наведении. */
function ProjectCard({ p, onOpen, onDelete }: {
  p: Project
  onOpen: () => void
  onDelete: (e: React.MouseEvent) => void
}) {
  const st = STATUS_MAP[p.status] || { label: p.status, tone: 'default' as const }
  const [hover, setHover] = useState(false)
  return (
    <div
      onClick={onOpen}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: 'relative', cursor: 'pointer',
        background: 'var(--bg-elevated)',
        border: hover ? '1px solid var(--blue-500)' : 'var(--hairline)',
        borderRadius: 'var(--radius-lg)',
        padding: '18px 18px 14px',
        display: 'flex', flexDirection: 'column', gap: 12,
        transition: 'border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease',
        transform: hover ? 'translateY(-2px)' : 'none',
        boxShadow: hover ? '0 8px 24px rgba(0,0,0,0.35)' : 'none',
        minHeight: 150,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 1.2,
          color: hover ? 'var(--blue-300)' : 'var(--fg-4)',
          transition: 'color 160ms ease',
        }}>
          ПРОЕКТ №{String(p.id).padStart(4, '0')}
        </div>
        <button
          onClick={onDelete}
          title="Удалить проект"
          style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--fg-4)', fontSize: 16, lineHeight: 1, padding: 2,
            opacity: hover ? 1 : 0, transition: 'opacity 160ms ease',
          }}
        >×</button>
      </div>

      <div style={{
        fontSize: 15, fontWeight: 600, color: 'var(--fg-1)',
        lineHeight: 1.35, flex: 1,
        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
      }}>
        {p.name}
      </div>

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        paddingTop: 12, borderTop: 'var(--hairline)',
      }}>
        <Chip tone={st.tone}>{st.label}</Chip>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)',
          display: 'flex', gap: 12,
        }}>
          <span title="Файлов в проекте">⎘ {p.files?.length ?? 0}</span>
          <span>{new Date(p.created_at).toLocaleDateString('ru-RU')}</span>
        </div>
      </div>
    </div>
  )
}

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '80px 0', gap: 16, color: 'var(--fg-3)' }}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 40, color: 'var(--fg-4)',
        border: '1px dashed var(--border-default)', borderRadius: 12, padding: '18px 26px',
      }}>∅</div>
      <div style={{ fontSize: 15, color: 'var(--fg-2)', fontWeight: 500 }}>Проектов пока нет</div>
      <div style={{ fontSize: 13 }}>Создайте проект и загрузите техническое задание</div>
      <Button variant="primary" onClick={onNew}>Создать проект</Button>
    </div>
  )
}

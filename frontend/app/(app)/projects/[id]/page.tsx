'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { getProject, startCalculation, uploadFile, deleteFile, getMe, listOpenRouterModels, Project, ProjectFile, OpenRouterModel } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'

const FILE_TYPE_LABELS: Record<string, string> = {
  tz: 'Техническое задание',
  additional_tz: 'Дополнительное ТЗ',
  other: 'Прочее',
}

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [project, setProject] = useState<Project | null>(null)
  const [canCalculate, setCanCalculate] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [calculating, setCalculating] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [orModels, setOrModels] = useState<OpenRouterModel[]>([])
  const [orModel, setOrModel] = useState('')
  const [orCalculating, setOrCalculating] = useState(false)

  useEffect(() => {
    Promise.all([getProject(Number(id)), getMe()]).then(([proj, user]) => {
      setProject(proj)
      setCanCalculate(user.can_calculate || user.role === 'admin')
    })
    listOpenRouterModels().then((models) => {
      setOrModels(models)
      if (models.length > 0) setOrModel(models[0].id)
    }).catch(() => {})
  }, [id])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>, fileType = 'tz') {
    if (!e.target.files?.length || !project) return
    setUploading(true)
    setError('')
    try {
      const file = e.target.files[0]
      const pf = await uploadFile(project.id, file, fileType)
      setProject((prev) => prev ? { ...prev, files: [...prev.files, pf] } : prev)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleDelete(fileId: number) {
    if (!project) return
    await deleteFile(project.id, fileId)
    setProject((prev) => prev ? { ...prev, files: prev.files.filter((f) => f.id !== fileId) } : prev)
  }

  async function handleCalculate(model?: string) {
    if (!project) return
    model ? setOrCalculating(true) : setCalculating(true)
    setError('')
    try {
      const calc = await startCalculation(project.id)
      const qs = new URLSearchParams({ calc: String(calc.id) })
      if (model) qs.set('model', model)
      router.push(`/projects/${project.id}/processing?${qs.toString()}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка запуска расчёта')
      model ? setOrCalculating(false) : setCalculating(false)
    }
  }

  if (!project) return <div style={{ padding: 28, color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>

  return (
    <>
      <Topbar
        title={project.name}
        breadcrumb="Проекты"
        actions={
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {!canCalculate && (
              <span style={{ fontSize: 12, color: 'var(--warning-400)', fontFamily: 'var(--font-mono)' }}>
                Расчёты не активированы
              </span>
            )}
            {project.last_calculation_id && (
              <Button
                variant="secondary"
                onClick={() => router.push(`/projects/${id}/geology?calc=${project.last_calculation_id}`)}
              >
                Добавить ИГИ
              </Button>
            )}
            <Button
              variant="primary"
              disabled={!canCalculate || project.files.length === 0 || calculating || orCalculating}
              onClick={() => handleCalculate()}
            >
              {calculating ? 'Запуск…' : 'Рассчитать (Claude)'}
            </Button>
          </div>
        }
      />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {error && (
          <div style={{ padding: '10px 14px', background: 'var(--danger-100)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--danger-400)' }}>
            {error}
          </div>
        )}

        {/* Files card */}
        <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <div style={{ padding: '14px 18px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Файлы технического задания</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.doc"
                style={{ display: 'none' }}
                onChange={(e) => handleUpload(e, 'tz')}
              />
              <Button variant="secondary" size="sm" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
                {uploading ? 'Загрузка…' : '+ Добавить файл'}
              </Button>
            </div>
          </div>

          {project.files.length === 0 ? (
            <div
              style={{ padding: 48, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, color: 'var(--fg-3)', cursor: 'pointer' }}
              onClick={() => fileInputRef.current?.click()}
            >
              <div style={{ fontSize: 32 }}>📄</div>
              <div style={{ fontSize: 14, color: 'var(--fg-2)' }}>Нажмите для загрузки или перетащите файл</div>
              <div style={{ fontSize: 12 }}>PDF, DOCX — до 50 МБ</div>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <tbody>
                {project.files.map((f, i) => (
                  <FileRow
                    key={f.id}
                    file={f}
                    isLast={i === project.files.length - 1}
                    onDelete={() => handleDelete(f.id)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* OpenRouter */}
        {canCalculate && project.files.length > 0 && (
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Анализ через OpenRouter</div>
            {orModels.length === 0 ? (
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                Добавьте <code>OPENROUTER_API_KEY</code> в <code>.env</code> и перезапустите backend
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                  <select
                    value={orModel}
                    onChange={(e) => setOrModel(e.target.value)}
                    style={{ flex: 1, background: 'var(--bg-input)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)', padding: '7px 10px', fontSize: 12, color: 'var(--fg-1)', fontFamily: 'var(--font-mono)' }}
                  >
                    {orModels.map((m) => (
                      <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                  </select>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!orModel || orCalculating || calculating}
                    onClick={() => handleCalculate(orModel)}
                  >
                    {orCalculating ? 'Запуск…' : 'Рассчитать'}
                  </Button>
                </div>
                {orModel && (() => {
                  const m = orModels.find((x) => x.id === orModel)
                  if (!m) return null
                  const prompt = m.pricing?.prompt ? `$${(parseFloat(m.pricing.prompt) * 1e6).toFixed(2)}/M` : ''
                  const ctx = m.context_length ? `${(m.context_length / 1000).toFixed(0)}K ctx` : ''
                  return (
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
                      {[m.id, ctx, prompt].filter(Boolean).join(' · ')}
                    </div>
                  )
                })()}
              </>
            )}
          </div>
        )}

        {/* Hint */}
        {project.files.length > 0 && !canCalculate && (
          <div style={{ padding: '12px 16px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--warning-400)' }}>
            Файлы загружены. Обратитесь к администратору для активации доступа к расчётам.
          </div>
        )}
      </div>
    </>
  )
}

function FileRow({ file, isLast, onDelete }: { file: ProjectFile; isLast: boolean; onDelete: () => void }) {
  return (
    <tr style={{ borderBottom: isLast ? 'none' : 'var(--hairline)' }}>
      <td style={{ padding: '12px 18px', display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 16 }}>📄</span>
        <div>
          <div style={{ fontWeight: 500 }}>{file.filename}</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginTop: 2 }}>
            {new Date(file.uploaded_at).toLocaleString('ru-RU')}
          </div>
        </div>
      </td>
      <td style={{ padding: '12px 18px' }}>
        <Chip>{FILE_TYPE_LABELS[file.file_type] || file.file_type}</Chip>
      </td>
      <td style={{ padding: '12px 18px', textAlign: 'right' }}>
        <button
          onClick={onDelete}
          style={{ background: 'transparent', border: 'none', color: 'var(--fg-4)', cursor: 'pointer', fontSize: 18 }}
          title="Удалить файл"
        >
          ×
        </button>
      </td>
    </tr>
  )
}

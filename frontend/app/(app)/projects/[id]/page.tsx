'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { getProject, startCalculation, uploadFile, deleteFile, getMe, listCalculations, createVersion, downloadExportFile, Project, CalcListItem } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'

const FILE_TYPE_LABELS: Record<string, string> = {
  tz: 'ТЗ',
  additional_tz: 'Доп. ТЗ',
  other: 'Прочее',
}

const EXPORT_LABELS: Record<string, string> = {
  '2ps_xlsx': '2ПС',
  kp_pdf: 'КП PDF',
  kp_docx: 'КП DOC',
}

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [project, setProject] = useState<Project | null>(null)
  const [canCalculate, setCanCalculate] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [calcs, setCalcs] = useState<CalcListItem[]>([])
  const [dragOver, setDragOver] = useState(false)

  useEffect(() => {
    Promise.all([getProject(Number(id)), getMe()]).then(([proj, user]) => {
      setProject(proj)
      setCanCalculate(user.can_calculate || user.role === 'admin')
    })
    listCalculations(Number(id)).then(setCalcs).catch(() => {})
  }, [id])

  async function uploadOne(file: File, fileType = 'tz') {
    if (!project) return
    setUploading(true)
    setError('')
    try {
      const pf = await uploadFile(project.id, file, fileType)
      setProject((prev) => prev ? { ...prev, files: [...prev.files, pf] } : prev)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>, fileType = 'tz') {
    if (!e.target.files?.length) return
    for (const f of Array.from(e.target.files)) await uploadOne(f, fileType)
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer.files || []).filter(f =>
      /\.(pdf|docx?|xls|xlsx)$/i.test(f.name))
    if (!files.length) { setError('Поддерживаются PDF, DOC(X), XLS(X)'); return }
    files.forEach(f => uploadOne(f))
  }

  async function handleDeleteFile(fileId: number, filename: string) {
    if (!project) return
    if (!confirm(`Удалить файл «${filename}»?`)) return
    try {
      await deleteFile(project.id, fileId)
      setProject((prev) => prev ? { ...prev, files: prev.files.filter((f) => f.id !== fileId) } : prev)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка удаления файла')
    }
  }

  async function handleNewCalc() {
    if (!project) return
    setCreating(true)
    setError('')
    try {
      const calc = await startCalculation(project.id)
      router.push(`/projects/${project.id}/entities?calc=${calc.id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка создания расчёта')
      setCreating(false)
    }
  }

  async function handleNewVersion(calcId: number) {
    try {
      const v = await createVersion(Number(id), calcId)
      router.push(`/projects/${id}/entities?calc=${v.id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Ошибка создания версии')
    }
  }

  if (!project) return <div style={{ padding: 28, color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>

  return (
    <>
      <Topbar
        title={project.name}
        breadcrumb="Проекты"
        actions={
          !canCalculate ? (
            <span style={{ fontSize: 12, color: 'var(--warning-400)', fontFamily: 'var(--font-mono)' }}>
              Расчёты не активированы
            </span>
          ) : undefined
        }
      />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {error && (
          <div style={{ padding: '10px 14px', background: 'var(--danger-100)', border: '1px solid var(--danger-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--danger-400)' }}>
            {error}
          </div>
        )}

        {/* ── Файлы ТЗ (drag&drop на всю карточку) ── */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={(e) => { if (e.currentTarget === e.target) setDragOver(false) }}
          onDrop={onDrop}
          style={{
            background: dragOver ? 'rgba(31,95,232,0.06)' : 'var(--bg-elevated)',
            border: dragOver ? '1px dashed var(--blue-400)' : 'var(--hairline)',
            borderRadius: 'var(--radius-lg)', overflow: 'hidden',
            transition: 'background 150ms ease, border-color 150ms ease',
          }}>
          <div style={{ padding: '14px 18px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Файлы ТЗ</div>
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

          {project.files.length === 0 ? (
            <div
              style={{ padding: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, color: 'var(--fg-3)', cursor: 'pointer' }}
              onClick={() => fileInputRef.current?.click()}
            >
              <div style={{ fontSize: 32 }}>📄</div>
              <div style={{ fontSize: 14, color: 'var(--fg-2)', textAlign: 'center' }}>Нажмите или перетащите файлы сюда</div>
              <div style={{ fontSize: 12 }}>PDF, DOCX — до 50 МБ</div>
            </div>
          ) : (
            <div>
              {project.files.map((f, i) => (
                <div key={f.id} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 18px',
                  borderBottom: i < project.files.length - 1 ? 'var(--hairline)' : 'none',
                  minWidth: 0,
                }}>
                  <span style={{ fontSize: 16, flex: 'none' }}>📄</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {f.filename}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {FILE_TYPE_LABELS[f.file_type] || f.file_type} · {new Date(f.uploaded_at).toLocaleString('ru-RU')}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteFile(f.id, f.filename)}
                    title="Удалить файл"
                    style={{
                      flex: 'none', background: 'transparent',
                      border: '1px solid var(--border-default)', borderRadius: 6,
                      color: 'var(--fg-3)', cursor: 'pointer', fontSize: 14,
                      width: 30, height: 30, lineHeight: 1,
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Расчёты ── */}
        <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <div style={{ padding: '14px 18px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Расчёты</div>
              {calcs.length > 0 && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{calcs.length}</div>
              )}
            </div>
            <Button
              variant="primary"
              size="sm"
              disabled={!canCalculate || project.files.length === 0 || creating}
              onClick={handleNewCalc}
            >
              {creating ? 'Создание…' : '+ Новый расчёт'}
            </Button>
          </div>

          {calcs.length === 0 ? (
            <div style={{ padding: '32px 18px', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
              {project.files.length === 0
                ? 'Загрузите файлы ТЗ, чтобы начать расчёт'
                : 'Расчётов пока нет — нажмите «Новый расчёт»'}
            </div>
          ) : (
            <div style={{
              padding: 14,
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))',
              gap: 12,
            }}>
              {calcs.map((c, i) => (
                <CalcTile
                  key={c.id}
                  calc={c}
                  num={i + 1}
                  onOpen={() => router.push(`/projects/${id}/entities?calc=${c.id}`)}
                  onDownload={(kind, filename) =>
                    downloadExportFile(Number(id), c.id, kind, filename).catch(e => setError(e.message))}
                  onNewVersion={() => handleNewVersion(c.id)}
                />
              ))}
            </div>
          )}
        </div>

        {project.files.length > 0 && !canCalculate && (
          <div style={{ padding: '12px 16px', background: 'var(--status-warning-bg)', border: '1px solid var(--warning-500)', borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--warning-400)' }}>
            Файлы загружены. Обратитесь к администратору для активации доступа к расчётам.
          </div>
        )}
      </div>
    </>
  )
}

/* Плитка расчёта: номер, версия, дата, статус, сумма; у финала — файлы. */
function CalcTile({ calc: c, num, onOpen, onDownload, onNewVersion }: {
  calc: CalcListItem
  num: number
  onOpen: () => void
  onDownload: (kind: string, filename: string) => void
  onNewVersion: () => void
}) {
  const [hover, setHover] = useState(false)
  const final = c.status === 'final'
  return (
    <div
      onClick={onOpen}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        cursor: 'pointer',
        background: 'var(--bg-raised)',
        border: hover ? '1px solid var(--blue-500)' : '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg)',
        padding: '14px 14px 12px',
        display: 'flex', flexDirection: 'column', gap: 10,
        transition: 'border-color 160ms ease',
        minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>Расчёт {num}</div>
        {final
          ? <Chip tone="success">Расчёт окончен</Chip>
          : <Chip tone="warning">Не подтверждён</Chip>}
      </div>

      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
        №{c.id} · v{c.version_num} · {new Date(c.created_at).toLocaleDateString('ru-RU')}
      </div>

      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 600, color: c.total_with_vat != null ? 'var(--fg-1)' : 'var(--fg-4)' }}>
        {c.total_with_vat != null
          ? c.total_with_vat.toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
          : '—'}
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginTop: 'auto' }} onClick={(e) => e.stopPropagation()}>
        {final ? (
          <>
            {c.exports.map((ex) => (
              <button key={ex.kind}
                onClick={() => onDownload(ex.kind, ex.filename)}
                title={ex.filename}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 0.5,
                  padding: '5px 9px', borderRadius: 4, cursor: 'pointer',
                  background: 'var(--success-100)', color: 'var(--success-400)',
                  border: '1px solid var(--success-500)',
                }}>
                ↓ {EXPORT_LABELS[ex.kind] || ex.kind}
              </button>
            ))}
            <button
              onClick={onNewVersion}
              title="Создать новую версию для правок"
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, padding: '5px 9px',
                borderRadius: 4, cursor: 'pointer',
                background: 'transparent', color: 'var(--fg-3)',
                border: '1px solid var(--border-default)',
              }}>⎇ версия</button>
          </>
        ) : (
          <button
            onClick={onOpen}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, padding: '5px 9px',
              borderRadius: 4, cursor: 'pointer',
              background: 'transparent', color: 'var(--blue-300)',
              border: '1px solid var(--blue-700)',
            }}>продолжить →</button>
        )}
      </div>
    </div>
  )
}

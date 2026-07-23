'use client'

import { useEffect, useState } from 'react'
import { listUsers, updateUser, deleteUser, createUser, getMe, User } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'
import { Input } from '@/components/ui/Input'

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [meId, setMeId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ email: '', password: '', company: '', role: 'user', can_calculate: true })
  const [formError, setFormError] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    Promise.all([listUsers(), getMe()])
      .then(([us, me]) => { setUsers(us); setMeId(me.id) })
      .finally(() => setLoading(false))
  }, [])

  async function toggleCalculate(user: User) {
    const updated = await updateUser(user.id, { can_calculate: !user.can_calculate })
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
  }

  async function toggleActive(user: User) {
    const blocking = user.is_active !== false
    if (blocking && !confirm(`Заблокировать ${user.email}? Вход будет запрещён.`)) return
    const updated = await updateUser(user.id, { is_active: !blocking ? true : false })
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
  }

  async function handleDelete(user: User) {
    if (!confirm(`Удалить ${user.email} безвозвратно? Обычно достаточно блокировки.`)) return
    await deleteUser(user.id)
    setUsers((prev) => prev.filter((u) => u.id !== user.id))
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setFormError('')
    setCreating(true)
    try {
      const u = await createUser({
        email: form.email, password: form.password,
        company: form.company || undefined,
        role: form.role, can_calculate: form.can_calculate,
      })
      setUsers((prev) => [u, ...prev])
      setForm({ email: '', password: '', company: '', role: 'user', can_calculate: true })
      setShowForm(false)
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Ошибка создания')
    } finally {
      setCreating(false)
    }
  }

  return (
    <>
      <Topbar title="Пользователи" breadcrumb="Администрирование"
        actions={
          <Button variant="primary" onClick={() => setShowForm(v => !v)}>
            {showForm ? 'Отмена' : '+ Новый пользователь'}
          </Button>
        } />
      <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {showForm && (
          <form onSubmit={handleCreate} style={{
            background: 'var(--bg-elevated)', border: '1px solid var(--blue-600)',
            borderRadius: 'var(--radius-lg)', padding: '18px',
            display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto auto auto', gap: 12, alignItems: 'end',
          }}>
            <Input label="Email" type="email" value={form.email} required
                   onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))} />
            <Input label="Пароль (≥6 символов)" type="text" value={form.password} required
                   onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))} />
            <Input label="Организация" type="text" value={form.company}
                   onChange={(e) => setForm(f => ({ ...f, company: e.target.value }))} />
            <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'flex', flexDirection: 'column', gap: 6 }}>
              Роль
              <select value={form.role} onChange={(e) => setForm(f => ({ ...f, role: e.target.value }))}
                style={{ background: 'var(--bg-input)', border: 'var(--hairline)', borderRadius: 'var(--radius-md)',
                         padding: '8px 10px', fontSize: 13, color: 'var(--fg-1)' }}>
                <option value="user">Пользователь</option>
                <option value="admin">Администратор</option>
              </select>
            </label>
            <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 10 }}>
              <input type="checkbox" checked={form.can_calculate}
                     onChange={(e) => setForm(f => ({ ...f, can_calculate: e.target.checked }))} />
              Расчёты
            </label>
            <Button type="submit" variant="primary" disabled={creating}>
              {creating ? 'Создание…' : 'Создать'}
            </Button>
            {formError && (
              <div style={{ gridColumn: '1 / -1', fontSize: 13, color: 'var(--danger-400)' }}>{formError}</div>
            )}
          </form>
        )}

        {loading ? (
          <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>Загрузка…</div>
        ) : (
          <div style={{ background: 'var(--bg-elevated)', border: 'var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: 'var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Пользователи</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{users.length} записей</div>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead style={{ background: 'var(--bg-raised)' }}>
                <tr>
                  {['Email', 'Организация', 'Роль', 'Статус', 'Расчёты', 'Создан', ''].map((h, i) => (
                    <th key={i} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-default)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((user, i) => {
                  const blocked = user.is_active === false
                  const isMe = user.id === meId
                  return (
                    <tr key={user.id} style={{
                      borderBottom: i < users.length - 1 ? 'var(--hairline)' : 'none',
                      opacity: blocked ? 0.55 : 1,
                    }}>
                      <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                        {user.email}{isMe && <span style={{ color: 'var(--fg-4)' }}> · вы</span>}
                      </td>
                      <td style={{ padding: '12px 14px', color: 'var(--fg-2)' }}>{user.company || '—'}</td>
                      <td style={{ padding: '12px 14px' }}>
                        <Chip tone={user.role === 'admin' ? 'warning' : 'default'}>
                          {user.role === 'admin' ? 'Администратор' : 'Пользователь'}
                        </Chip>
                      </td>
                      <td style={{ padding: '12px 14px' }}>
                        {blocked
                          ? <Chip tone="default">Заблокирован</Chip>
                          : <Chip tone="success">Активен</Chip>}
                      </td>
                      <td style={{ padding: '12px 14px' }}>
                        <button
                          onClick={() => toggleCalculate(user)}
                          style={{
                            width: 36, height: 20, borderRadius: 'var(--radius-full)',
                            background: user.can_calculate ? 'var(--accent)' : 'var(--bg-raised)',
                            border: 'var(--hairline)', cursor: 'pointer', position: 'relative',
                            transition: 'background var(--duration-2)',
                          }}
                          title={user.can_calculate ? 'Отключить расчёты' : 'Включить расчёты'}
                        >
                          <span style={{
                            position: 'absolute', top: 2, left: user.can_calculate ? 18 : 2,
                            width: 14, height: 14, borderRadius: '50%', background: 'white',
                            transition: 'left var(--duration-2)',
                          }} />
                        </button>
                      </td>
                      <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                        {new Date(user.created_at).toLocaleDateString('ru-RU')}
                      </td>
                      <td style={{ padding: '12px 14px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {!isMe && (
                          <span style={{ display: 'inline-flex', gap: 8 }}>
                            <Button variant="secondary" size="sm" onClick={() => toggleActive(user)}>
                              {blocked ? 'Разблокировать' : 'Заблокировать'}
                            </Button>
                            <Button variant="danger" size="sm" onClick={() => handleDelete(user)}>Удалить</Button>
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

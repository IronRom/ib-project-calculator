'use client'

import { useEffect, useState } from 'react'
import { listUsers, updateUser, deleteUser, User } from '@/lib/api'
import { Topbar } from '@/components/layout/Topbar'
import { Button } from '@/components/ui/Button'
import { Chip } from '@/components/ui/Chip'

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listUsers().then(setUsers).finally(() => setLoading(false))
  }, [])

  async function toggleCalculate(user: User) {
    const updated = await updateUser(user.id, { can_calculate: !user.can_calculate })
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
  }

  async function handleDelete(userId: number) {
    if (!confirm('Удалить пользователя?')) return
    await deleteUser(userId)
    setUsers((prev) => prev.filter((u) => u.id !== userId))
  }

  return (
    <>
      <Topbar title="Пользователи" breadcrumb="Администрирование" />
      <div style={{ padding: '24px 28px' }}>
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
                  {['Email', 'Организация', 'Роль', 'Расчёты', 'Зарегистрирован', ''].map((h, i) => (
                    <th key={i} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border-default)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((user, i) => (
                  <tr key={user.id} style={{ borderBottom: i < users.length - 1 ? 'var(--hairline)' : 'none' }}>
                    <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{user.email}</td>
                    <td style={{ padding: '12px 14px', color: 'var(--fg-2)' }}>{user.company || '—'}</td>
                    <td style={{ padding: '12px 14px' }}>
                      <Chip tone={user.role === 'admin' ? 'warning' : 'default'}>
                        {user.role === 'admin' ? 'Администратор' : 'Пользователь'}
                      </Chip>
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <button
                        onClick={() => toggleCalculate(user)}
                        style={{
                          width: 36, height: 20, borderRadius: 'var(--radius-full)',
                          background: user.can_calculate ? 'var(--accent)' : 'var(--bg-raised)',
                          border: 'var(--hairline)',
                          cursor: 'pointer',
                          position: 'relative',
                          transition: 'background var(--duration-2)',
                        }}
                        title={user.can_calculate ? 'Отключить расчёты' : 'Включить расчёты'}
                      >
                        <span style={{
                          position: 'absolute',
                          top: 2, left: user.can_calculate ? 18 : 2,
                          width: 14, height: 14,
                          borderRadius: '50%',
                          background: 'white',
                          transition: 'left var(--duration-2)',
                        }} />
                      </button>
                    </td>
                    <td style={{ padding: '12px 14px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
                      {new Date(user.created_at).toLocaleDateString('ru-RU')}
                    </td>
                    <td style={{ padding: '12px 14px', textAlign: 'right' }}>
                      {user.role !== 'admin' && (
                        <Button variant="danger" size="sm" onClick={() => handleDelete(user.id)}>Удалить</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

// AuthScreen — sign in / sign up

function AuthScreen({ onSubmit, onBack }) {
  const [mode, setMode] = React.useState('signin');  // 'signin' | 'signup'
  const [email, setEmail] = React.useState('a.voronin@stroyproekt.ru');
  const [password, setPassword] = React.useState('••••••••');
  const [company, setCompany] = React.useState('ООО «СтройПроект»');

  return (
    <div style={{
      minHeight: '100%',
      background: 'var(--bg-app)',
      backgroundImage: "url('../../assets/grid-tile.svg')",
      backgroundSize: '80px 80px',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 48,
    }}>
      <div style={{
        width: 440,
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-xl)',
        padding: 36,
        display: 'flex', flexDirection: 'column', gap: 20,
        boxShadow: 'var(--shadow-3)',
      }}>
        <img src="../../assets/logo-wordmark-dark.svg" width="238" height="44" alt="ИС·ПИР"/>
        <div>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 24, fontWeight: 600, color: 'var(--fg-1)', letterSpacing: '-0.005em' }}>
            {mode === 'signin' ? 'Вход в систему' : 'Регистрация'}
          </div>
          <div style={{ fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--fg-3)', marginTop: 4 }}>
            {mode === 'signin' ? 'Используйте корпоративную почту организации' : 'Создайте учётную запись для вашей организации'}
          </div>
        </div>

        {mode === 'signup' && (
          <window.Input label="Организация" value={company} onChange={(e) => setCompany(e.target.value)}/>
        )}
        <window.Input label="Корпоративная почта" type="email" value={email} onChange={(e) => setEmail(e.target.value)}/>
        <window.Input label="Пароль" type="password" value={password} onChange={(e) => setPassword(e.target.value)}/>

        {mode === 'signin' && (
          <a href="#" style={{ fontFamily: 'var(--font-sans)', fontSize: 12, color: 'var(--blue-300)', textDecoration: 'none', alignSelf: 'flex-start' }}>Забыли пароль?</a>
        )}

        <window.Button variant="primary" size="lg" onClick={onSubmit} style={{ width: '100%', justifyContent: 'center' }}>
          {mode === 'signin' ? 'Войти' : 'Создать учётную запись'}
        </window.Button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          <div style={{ flex: 1, height: 1, background: 'var(--border-subtle)' }}/>
          ИЛИ
          <div style={{ flex: 1, height: 1, background: 'var(--border-subtle)' }}/>
        </div>

        <button onClick={() => setMode(mode === 'signin' ? 'signup' : 'signin')}
          style={{ background: 'transparent', border: 'none', color: 'var(--fg-2)', fontFamily: 'var(--font-sans)', fontSize: 13, cursor: 'pointer', padding: 0 }}>
          {mode === 'signin' ? 'Создать новую учётную запись' : 'У меня уже есть аккаунт — войти'}
        </button>

        <button onClick={onBack}
          style={{ background: 'transparent', border: 'none', color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer', padding: 0, marginTop: -8, alignSelf: 'flex-start' }}>
          ← На главную
        </button>
      </div>
    </div>
  );
}

Object.assign(window, { AuthScreen });

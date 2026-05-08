// Primitive components: Button, Input, Select, Chip, Stepper

function Button({ children, variant = 'primary', size = 'md', icon, onClick, disabled, type = 'button', style, ...rest }) {
  const sizes = {
    sm: { h: 28, px: 12, fs: 12, rd: 'var(--radius-sm)' },
    md: { h: 36, px: 16, fs: 13, rd: 'var(--radius-md)' },
    lg: { h: 44, px: 20, fs: 14, rd: 'var(--radius-md)' },
  }[size];

  const variants = {
    primary: { bg: 'var(--blue-500)', fg: '#fff', bd: 'transparent' },
    secondary: { bg: 'var(--bg-elevated)', fg: 'var(--fg-1)', bd: 'var(--border-default)' },
    ghost: { bg: 'transparent', fg: 'var(--fg-2)', bd: 'transparent' },
    danger: { bg: 'transparent', fg: 'var(--danger-400)', bd: 'rgba(239,68,68,0.35)' },
  }[variant];

  const [hover, setHover] = React.useState(false);
  const hoverBg = {
    primary: 'var(--blue-400)',
    secondary: 'var(--bg-hover)',
    ghost: 'var(--bg-hover)',
    danger: 'rgba(239,68,68,0.08)',
  }[variant];

  return (
    <button type={type} onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        background: hover && !disabled ? hoverBg : variants.bg,
        color: variants.fg,
        border: `1px solid ${variants.bd}`,
        height: sizes.h,
        padding: `0 ${sizes.px}px`,
        borderRadius: sizes.rd,
        fontFamily: 'var(--font-sans)',
        fontSize: sizes.fs,
        fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        whiteSpace: 'nowrap',
        transition: 'background var(--duration-1) var(--ease-out)',
        ...style,
      }} {...rest}>
      {icon}{children}
    </button>
  );
}

function Input({ label, value, onChange, placeholder, type = 'text', mono = false, suffix, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5, ...style }}>
      {label && <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, fontWeight: 500, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</span>}
      <div style={{
        background: 'var(--bg-input)',
        border: `1px solid ${focus ? 'var(--blue-500)' : 'var(--border-default)'}`,
        borderRadius: 'var(--radius-md)',
        height: 36,
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        boxShadow: focus ? 'var(--shadow-focus)' : 'none',
        transition: 'border-color var(--duration-1) var(--ease-out)',
      }}>
        <input
          type={type}
          value={value ?? ''}
          onChange={onChange}
          placeholder={placeholder}
          onFocus={() => setFocus(true)}
          onBlur={() => setFocus(false)}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            color: 'var(--fg-1)',
            fontFamily: mono ? 'var(--font-mono)' : 'var(--font-sans)',
            fontSize: 13,
            fontVariantNumeric: 'tabular-nums',
          }}
          {...rest}
        />
        {suffix && <span style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', fontSize: 12, marginLeft: 8 }}>{suffix}</span>}
      </div>
    </label>
  );
}

function Select({ label, value, onChange, options, style }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5, ...style }}>
      {label && <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, fontWeight: 500, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</span>}
      <div style={{ position: 'relative' }}>
        <select value={value} onChange={onChange}
          style={{
            width: '100%',
            background: 'var(--bg-input)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)',
            height: 36,
            padding: '0 36px 0 12px',
            color: 'var(--fg-1)',
            fontFamily: 'var(--font-sans)',
            fontSize: 13,
            outline: 'none',
            appearance: 'none',
          }}>
          {options.map((o) => (
            <option key={o.value} value={o.value} style={{ background: 'var(--bg-elevated)' }}>{o.label}</option>
          ))}
        </select>
        <span style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--fg-3)', pointerEvents: 'none' }}>
          <window.ChevronDown size={14}/>
        </span>
      </div>
    </label>
  );
}

function Chip({ children, tone = 'neutral', dot = true }) {
  const tones = {
    neutral: { bg: 'var(--bg-raised)', fg: 'var(--fg-2)', bd: 'var(--border-subtle)' },
    success: { bg: 'var(--status-success-bg)', fg: 'var(--status-success-fg)', bd: 'rgba(34,197,94,0.25)' },
    warning: { bg: 'var(--status-warning-bg)', fg: 'var(--status-warning-fg)', bd: 'rgba(245,158,11,0.25)' },
    danger:  { bg: 'var(--status-danger-bg)',  fg: 'var(--status-danger-fg)',  bd: 'rgba(239,68,68,0.25)' },
    info:    { bg: 'var(--status-info-bg)',    fg: 'var(--status-info-fg)',    bd: 'rgba(31,95,232,0.3)' },
  }[tone];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: tones.bg, color: tones.fg, border: `1px solid ${tones.bd}`,
      padding: '2px 10px', borderRadius: 'var(--radius-full)',
      fontFamily: 'var(--font-sans)', fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap',
    }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: 999, background: 'currentColor' }}/>}
      {children}
    </span>
  );
}

function Stepper({ steps, current }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
      {steps.map((label, i) => {
        const state = i < current ? 'done' : i === current ? 'current' : 'todo';
        return (
          <React.Fragment key={i}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 22, height: 22, borderRadius: '50%',
                background: state === 'current' ? 'var(--blue-500)' : state === 'done' ? 'var(--success-400)' : 'var(--bg-raised)',
                border: state === 'todo' ? '1px solid var(--border-default)' : 'none',
                color: state === 'todo' ? 'var(--fg-3)' : '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
              }}>
                {state === 'done' ? <window.Check size={12}/> : (i + 1).toString().padStart(2, '0')}
              </div>
              <span style={{
                fontFamily: 'var(--font-sans)', fontSize: 12,
                fontWeight: state === 'current' ? 600 : 400,
                color: state === 'current' ? 'var(--fg-1)' : state === 'done' ? 'var(--fg-2)' : 'var(--fg-3)',
                whiteSpace: 'nowrap',
              }}>{label}</span>
            </div>
            {i < steps.length - 1 && (
              <div style={{ flex: 'none', width: 32, height: 1, background: 'var(--border-subtle)', margin: '0 16px' }}/>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

Object.assign(window, { Button, Input, Select, Chip, Stepper });

import { CSSProperties } from 'react'

interface InputProps {
  label?: string
  type?: string
  value?: string
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void
  placeholder?: string
  required?: boolean
  error?: string
  style?: CSSProperties
  step?: string | number
  min?: string | number
  max?: string | number
}

export function Input({ label, type = 'text', value, onChange, placeholder, required, error, style, step, min, max }: InputProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, ...style }}>
      {label && (
        <label style={{ fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 500, color: 'var(--fg-2)' }}>
          {label}
          {required && <span style={{ color: 'var(--danger-400)', marginLeft: 4 }}>*</span>}
        </label>
      )}
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        step={step}
        min={min}
        max={max}
        style={{
          width: '100%',
          background: 'var(--bg-input)',
          border: error ? '1px solid var(--danger-500)' : 'var(--hairline)',
          borderRadius: 'var(--radius-md)',
          padding: '8px 12px',
          fontFamily: 'var(--font-sans)',
          fontSize: 13,
          color: 'var(--fg-1)',
          outline: 'none',
          transition: 'border-color var(--duration-1)',
        }}
        onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--border-focus)' }}
        onBlur={(e) => { e.currentTarget.style.borderColor = error ? 'var(--danger-500)' : 'var(--border-subtle)' }}
      />
      {error && (
        <span style={{ fontFamily: 'var(--font-sans)', fontSize: 11, color: 'var(--danger-400)' }}>{error}</span>
      )}
    </div>
  )
}

import { CSSProperties, ReactNode } from 'react'

interface ButtonProps {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
  style?: CSSProperties
  fullWidth?: boolean
}

const BASE: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 8,
  border: 'none',
  borderRadius: 'var(--radius-md)',
  fontFamily: 'var(--font-sans)',
  fontWeight: 500,
  cursor: 'pointer',
  transition: 'background var(--duration-1) var(--ease-out)',
  whiteSpace: 'nowrap',
}

const VARIANTS: Record<string, CSSProperties> = {
  primary: { background: 'var(--accent)', color: 'var(--accent-fg)' },
  secondary: { background: 'var(--bg-elevated)', color: 'var(--fg-1)', border: 'var(--hairline)' },
  ghost: { background: 'transparent', color: 'var(--fg-2)' },
  danger: { background: 'var(--danger-100)', color: 'var(--danger-400)', border: '1px solid var(--danger-500)' },
}

const SIZES: Record<string, CSSProperties> = {
  sm: { padding: '5px 12px', fontSize: 12 },
  md: { padding: '7px 14px', fontSize: 13 },
  lg: { padding: '10px 20px', fontSize: 14 },
}

export function Button({
  children, onClick, variant = 'secondary', size = 'md',
  disabled, type = 'button', style, fullWidth,
}: ButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        ...BASE,
        ...VARIANTS[variant],
        ...SIZES[size],
        ...(fullWidth ? { width: '100%' } : {}),
        ...(disabled ? { opacity: 0.45, cursor: 'not-allowed' } : {}),
        ...style,
      }}
    >
      {children}
    </button>
  )
}

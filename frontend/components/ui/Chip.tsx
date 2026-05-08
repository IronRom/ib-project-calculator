import { CSSProperties, ReactNode } from 'react'

type Tone = 'success' | 'warning' | 'danger' | 'info' | 'default'

interface ChipProps {
  children: ReactNode
  tone?: Tone
  style?: CSSProperties
}

const TONES: Record<Tone, { bg: string; color: string }> = {
  success: { bg: 'var(--status-success-bg)', color: 'var(--status-success-fg)' },
  warning: { bg: 'var(--status-warning-bg)', color: 'var(--status-warning-fg)' },
  danger:  { bg: 'var(--status-danger-bg)',  color: 'var(--status-danger-fg)'  },
  info:    { bg: 'var(--status-info-bg)',    color: 'var(--status-info-fg)'    },
  default: { bg: 'var(--bg-raised)',         color: 'var(--fg-2)'              },
}

export function Chip({ children, tone = 'default', style }: ChipProps) {
  const { bg, color } = TONES[tone]
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      padding: '3px 8px',
      borderRadius: 'var(--radius-full)',
      background: bg,
      color,
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      fontWeight: 500,
      letterSpacing: '0.02em',
      whiteSpace: 'nowrap',
      ...style,
    }}>
      {children}
    </span>
  )
}

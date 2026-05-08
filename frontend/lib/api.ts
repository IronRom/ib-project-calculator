const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('pir_token')
}

function headers(extra?: Record<string, string>): HeadersInit {
  const token = getToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...headers(), ...(init?.headers || {}) },
  })
  if (res.status === 204) return undefined as T
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
  return data as T
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export function login(email: string, password: string) {
  return request<{ access_token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function register(email: string, password: string, company?: string) {
  return request<User>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, company }),
  })
}

export function getMe() {
  return request<User>('/auth/me')
}

// ── Projects ──────────────────────────────────────────────────────────────────

export function listProjects() {
  return request<Project[]>('/projects')
}

export function createProject(name: string) {
  return request<Project>('/projects', { method: 'POST', body: JSON.stringify({ name }) })
}

export function getProject(id: number) {
  return request<Project>(`/projects/${id}`)
}

export function deleteProject(id: number) {
  return request<void>(`/projects/${id}`, { method: 'DELETE' })
}

export function uploadFile(projectId: number, file: File, fileType = 'tz') {
  const form = new FormData()
  form.append('file', file)
  const token = getToken()
  return fetch(`${BASE}/projects/${projectId}/files?file_type=${fileType}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  }).then(async (res) => {
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
    return data as ProjectFile
  })
}

export function deleteFile(projectId: number, fileId: number) {
  return request<void>(`/projects/${projectId}/files/${fileId}`, { method: 'DELETE' })
}

// ── Calculations ──────────────────────────────────────────────────────────────

export function startCalculation(projectId: number) {
  return request<Calculation>(`/projects/${projectId}/calculations`, { method: 'POST' })
}

export function getCalculation(projectId: number, calcId: number) {
  return request<Calculation>(`/projects/${projectId}/calculations/${calcId}`)
}

export function streamExtraction(projectId: number, calcId: number): EventSource {
  const token = getToken()
  const url = `${BASE}/projects/${projectId}/calculations/${calcId}/stream${token ? `?token=${token}` : ''}`
  return new EventSource(url)
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export function listUsers() {
  return request<User[]>('/admin/users')
}

export function updateUser(userId: number, data: { can_calculate?: boolean; role?: string }) {
  return request<User>(`/admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export function deleteUser(userId: number) {
  return request<void>(`/admin/users/${userId}`, { method: 'DELETE' })
}

export function listReferences() {
  return request<ReferenceBook[]>('/admin/references')
}

export function activateReference(bookId: number) {
  return request<ReferenceBook>(`/admin/references/${bookId}/activate`, { method: 'POST' })
}

export function rollbackReference(bookId: number) {
  return request<ReferenceBook>(`/admin/references/${bookId}/rollback`, { method: 'POST' })
}

export function listIndices() {
  return request<PriceIndex[]>('/admin/indices')
}

export function createIndex(data: { year: number; quarter: number; index_type: string; index_value: number; source_ref: string }) {
  return request<PriceIndex>('/admin/indices', { method: 'POST', body: JSON.stringify(data) })
}

export function deleteIndex(indexId: number) {
  return request<void>(`/admin/indices/${indexId}`, { method: 'DELETE' })
}

export function getCurrentIndex() {
  return request<PriceIndex>('/admin/indices/current')
}

export function staleIndexWarning() {
  return request<{ stale: boolean; message: string }>('/admin/indices/stale-warning')
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface User {
  id: number
  email: string
  role: string
  can_calculate: boolean
  company?: string
  created_at: string
}

export interface ProjectFile {
  id: number
  filename: string
  file_type: string
  uploaded_at: string
}

export interface Project {
  id: number
  name: string
  status: string
  created_at: string
  files: ProjectFile[]
}

export interface Calculation {
  id: number
  project_id: number
  extracted_entities?: ExtractionResult
  confirmed_positions?: unknown
  calculation_result?: unknown
  created_at: string
}

export interface ExtractedEntity {
  category: 'new_construction' | 'reconstruction' | 'overhaul'
  object_type: string
  object_name: string
  address: string
  sbts_code?: string
  sbts_table?: number
  x_value?: number
  x_unit?: string
  coefficients?: { name: string; value: number; source?: string }[]
  notes?: string
  confidence?: number
}

export interface ExtractionResult {
  entities: ExtractedEntity[]
  stage: 'П' | 'Р' | 'П+Р'
  region: string
  missing_data: string[]
  overall_confidence: number
}

export interface ReferenceBook {
  id: number
  code: string
  official_name: string
  version: number
  status: string
  is_active: boolean
  pdf_filename?: string
  uploaded_at: string
  activated_at?: string
  notes?: string
}

export interface PriceIndex {
  id: number
  year: number
  quarter: number
  index_type: string
  index_value: number
  source_ref: string
}

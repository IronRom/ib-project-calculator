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

export function streamExtraction(projectId: number, calcId: number, model?: string): EventSource {
  const token = getToken()
  const params = new URLSearchParams()
  if (token) params.set('token', token)
  if (model) params.set('model', model)
  const qs = params.toString()
  return new EventSource(`${BASE}/projects/${projectId}/calculations/${calcId}/stream${qs ? `?${qs}` : ''}`)
}

export interface OpenRouterModel {
  id: string
  name: string
  context_length?: number
  pricing?: { prompt?: string; completion?: string }
}

export function listOpenRouterModels() {
  return request<OpenRouterModel[]>('/openrouter/models')
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

export async function exportReferenceExcel(bookId: number, filename: string): Promise<void> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('pir_token') : ''
  const res = await fetch(`${BASE}/admin/references/${bookId}/export`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function importReferenceExcel(bookId: number, file: File): Promise<ReferenceBook> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('pir_token') : ''
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/admin/references/${bookId}/import`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
  return data as ReferenceBook
}

export function deleteReference(bookId: number) {
  return request<void>(`/admin/references/${bookId}`, { method: 'DELETE' })
}

// ── Extraction Hints ──────────────────────────────────────────────────────────

export interface ExtractionHint {
  id: number
  book_version_id: number
  trigger_condition: string
  implied_work: string
  hint_for_ai: string
  justification: string
  is_active: boolean
  sort_order: number
}

export type ExtractionHintIn = Omit<ExtractionHint, 'id' | 'book_version_id'>

export function listHints(bookId: number) {
  return request<ExtractionHint[]>(`/admin/references/${bookId}/hints`)
}

export function createHint(bookId: number, data: ExtractionHintIn) {
  return request<ExtractionHint>(`/admin/references/${bookId}/hints`, { method: 'POST', body: JSON.stringify(data) })
}

export function updateHint(bookId: number, hintId: number, data: ExtractionHintIn) {
  return request<ExtractionHint>(`/admin/references/${bookId}/hints/${hintId}`, { method: 'PUT', body: JSON.stringify(data) })
}

export function deleteHint(bookId: number, hintId: number) {
  return request<void>(`/admin/references/${bookId}/hints/${hintId}`, { method: 'DELETE' })
}

// ── ASUTP admin ───────────────────────────────────────────────────────────────

export interface AsutpFactorOption {
  id: number
  factor_code: string
  factor_name: string
  option_code: string
  option_description: string
  score_or: number | null
  score_oo: number | null
  score_io: number | null
  score_to: number | null
  score_mo: number | null
  score_po: number | null
}

export interface AsutpFactorOptionIn {
  factor_code: string
  factor_name: string
  option_code: string
  option_description: string
  score_or?: number | null
  score_oo?: number | null
  score_io?: number | null
  score_to?: number | null
  score_mo?: number | null
  score_po?: number | null
}

export interface AsutpModule {
  id: number
  module_code: string
  s_value: number
  sort_order: number
  stage_r_min: number
  stage_r_max: number
  stage_p_min: number
  stage_p_max: number
}

export interface AsutpModulePatch {
  s_value?: number
  stage_r_min?: number
  stage_r_max?: number
  stage_p_min?: number
  stage_p_max?: number
}

export function listAsutpFactors(bookId: number) {
  return request<AsutpFactorOption[]>(`/admin/books/${bookId}/asutp-factors`)
}

export function createAsutpFactor(bookId: number, data: AsutpFactorOptionIn) {
  return request<AsutpFactorOption>(`/admin/books/${bookId}/asutp-factors`, {
    method: 'POST', body: JSON.stringify(data),
  })
}

export function updateAsutpFactor(bookId: number, optionId: number, data: AsutpFactorOptionIn) {
  return request<AsutpFactorOption>(`/admin/books/${bookId}/asutp-factors/${optionId}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
}

export function deleteAsutpFactor(bookId: number, optionId: number) {
  return request<void>(`/admin/books/${bookId}/asutp-factors/${optionId}`, { method: 'DELETE' })
}

export function listAsutpModules(bookId: number) {
  return request<AsutpModule[]>(`/admin/books/${bookId}/asutp-modules`)
}

export function updateAsutpModule(bookId: number, moduleId: number, data: AsutpModulePatch) {
  return request<AsutpModule>(`/admin/books/${bookId}/asutp-modules/${moduleId}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
}

export function computeCalculation(projectId: number, calcId: number) {
  return request<CalculationResult>(`/projects/${projectId}/calculations/${calcId}/compute`, { method: 'POST' })
}

export function downloadExport2PS(projectId: number, calcId: number): Promise<void> {
  return _downloadFile(`/projects/${projectId}/calculations/${calcId}/export`, `2ПС_ИР_${calcId}.xlsx`)
}

export function correctAndCompute(projectId: number, calcId: number, correctionText: string) {
  return request<CalculationResult>(`/projects/${projectId}/calculations/${calcId}/correct-and-compute`, {
    method: 'POST',
    body: JSON.stringify({ correction_text: correctionText }),
  })
}

async function _downloadFile(url: string, fallbackName: string): Promise<void> {
  const token = getToken()
  const res = await fetch(`${BASE}${url}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error((data as { detail?: string }).detail || `HTTP ${res.status}`)
  }
  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  const cd = res.headers.get('Content-Disposition') || ''
  const match = cd.match(/filename\*?=(?:UTF-8'')?(.+)/i)
  a.download = match ? decodeURIComponent(match[1].replace(/"/g, '')) : fallbackName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objectUrl)
}

export function downloadExportKP(projectId: number, calcId: number): Promise<void> {
  return _downloadFile(`/projects/${projectId}/calculations/${calcId}/export-kp`, `КП_${calcId}.docx`)
}

export function downloadExportKPPdf(projectId: number, calcId: number): Promise<void> {
  return _downloadFile(`/projects/${projectId}/calculations/${calcId}/export-kp-pdf`, `КП_${calcId}.pdf`)
}

export function patchEntity(projectId: number, calcId: number, entityIdx: number, patch: Partial<{ x_value: number | null; x_unit: string; deleted: boolean }>) {
  return request<ExtractedEntity>(`/projects/${projectId}/calculations/${calcId}/entities/${entityIdx}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export function patchEntityXValue(projectId: number, calcId: number, entityIdx: number, xValue: number | null, xUnit?: string) {
  return patchEntity(projectId, calcId, entityIdx, { x_value: xValue, ...(xUnit !== undefined ? { x_unit: xUnit } : {}) })
}

export interface UnitCheckItem {
  index: number
  ok: boolean
  note: string
  x_effective?: number
  x_unit_table?: string
  extrapolated?: boolean
}

export function getUnitCheck(projectId: number, calcId: number) {
  return request<UnitCheckItem[]>(`/projects/${projectId}/calculations/${calcId}/unit-check`)
}

export function getIgiBookRows(
  projectId: number, calcId: number, bookCode = 'НЗ-2025-МС281-ИГИ'
) {
  return request<IgiBookRows>(
    `/projects/${projectId}/calculations/${calcId}/igi/book-rows?book_code=${encodeURIComponent(bookCode)}`
  )
}

export function saveGeologicalSurveys(
  projectId: number, calcId: number, surveys: GeologicalSurvey[]
): Promise<CalculationResult> {
  return request<CalculationResult>(
    `/projects/${projectId}/calculations/${calcId}/geological-surveys`,
    { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ geological_surveys: surveys }) }
  )
}

export function listIndices() {
  return request<PriceIndex[]>('/admin/indices')
}

export function createIndex(data: { year: number; quarter: number; index_type: string; index_value: number; source_ref: string }) {
  return request<PriceIndex>('/admin/indices', { method: 'POST', body: JSON.stringify(data) })
}

export function updateIndex(indexId: number, data: Partial<{ year: number; quarter: number; index_value: number; source_ref: string }>) {
  return request<PriceIndex>(`/admin/indices/${indexId}`, { method: 'PATCH', body: JSON.stringify(data) })
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
  calculation_result?: CalculationResult
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
  tz_quote?: string
  x_value_missing_reason?: string
  deleted?: boolean
  section_num?: number
  section_name?: string
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
  calc_method?: string
  price_base_year?: number
}

export interface CalcPosition {
  num: number
  name: string
  row_description: string
  unit: string
  quantity: number
  justification: string
  formula: string
  cost: number
  book_code: string
  table_num: number
  row_num: string
  used_minimum?: boolean
  section_num?: number
  section_name?: string
}

export interface CalculationResult {
  positions: CalcPosition[]
  base_cost: number
  price_index: number
  price_index_period: string
  price_index_justification: string
  stage: string
  stage_factor: number
  current_cost: number
  cost_with_stage: number
  vat_rate: number
  vat_amount: number
  total_with_vat: number
  errors: string[]
}

// ── ИГИ (geological survey) ───────────────────────────────────────────────────

export type IgiWorkCategory = 'field' | 'lab' | 'kameral' | 'program'

export interface IgiItem {
  work_category: IgiWorkCategory
  object_type_name: string
  table_num: number
  row_num: string
  description: string
  volume: number
  x_unit: string
  b: number
  deleted?: boolean
  notes?: string
}

export interface GeologicalSurvey {
  book_id: number
  book_code: string
  complexity_category: number   // 1 | 2 | 3
  k1: number
  winter_pct: number
  k2: number
  items: IgiItem[]
}

export interface IgiBookRow {
  id: number
  row_num: string
  description: string
  x_unit: string
  x_min: number | null
  x_max: number | null
  b: number
}

export interface IgiObjectType {
  object_type_id: number
  object_type_name: string
  table_num: number
  work_category: string
  rows: IgiBookRow[]
}

export interface IgiBookRows {
  book_id: number
  book_code: string
  object_types: IgiObjectType[]
}

export interface PriceIndex {
  id: number
  year: number
  quarter: number
  index_type: string
  index_value: number
  source_ref: string
}

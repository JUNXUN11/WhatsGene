// Single-user auth state. The backend session cookie is the source of
// truth; this only caches /auth/me so the nav and guards agree.
export function useAuth() {
  const status = useState<'unknown' | 'in' | 'out'>('auth-status', () => 'unknown')
  const username = useState<string | null>('auth-user', () => null)
  const { login: apiLogin, logout: apiLogout, me } = useApi()

  async function ensure(): Promise<boolean> {
    if (status.value !== 'unknown') return status.value === 'in'
    try {
      const res = await me()
      status.value = res.authenticated ? 'in' : 'out'
      username.value = res.username || null
    } catch {
      status.value = 'out'
      username.value = null
    }
    return status.value === 'in'
  }

  async function login(name: string, password: string): Promise<void> {
    const res = await apiLogin(name, password)
    status.value = 'in'
    username.value = res.username
  }

  async function logout(): Promise<void> {
    try {
      await apiLogout()
    } catch {
      // Session already gone server-side; still clear local state.
    }
    status.value = 'out'
    username.value = null
  }

  return { status, username, ensure, login, logout }
}

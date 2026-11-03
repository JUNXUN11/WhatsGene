// Auth state. The backend session cookie is the source of truth; this
// only caches /auth/me so the nav and guards agree. auto means
// AUTH_MODE=single signed the owner in: there is nothing to log out of,
// so the nav hides Log out. needsSetup means no account exists yet, so
// the guards open the first-run page (/welcome). signupOpen means the
// login page may offer Create an account.
export function useAuth() {
  const status = useState<'unknown' | 'in' | 'out'>('auth-status', () => 'unknown')
  const username = useState<string | null>('auth-user', () => null)
  const auto = useState<boolean>('auth-auto', () => false)
  const owner = useState<boolean>('auth-owner', () => false)
  const needsSetup = useState<boolean>('auth-needs-setup', () => false)
  const signupOpen = useState<boolean>('auth-signup', () => false)
  const { login: apiLogin, logout: apiLogout, setupOwner, register: apiRegister, me } = useApi()

  async function ensure(): Promise<boolean> {
    if (status.value !== 'unknown') return status.value === 'in'
    try {
      const res = await me()
      status.value = res.authenticated ? 'in' : 'out'
      username.value = res.username || null
      auto.value = !!res.auto
      owner.value = !!res.owner
      needsSetup.value = !!res.needs_setup
      signupOpen.value = !!res.signup
    } catch {
      status.value = 'out'
      username.value = null
      auto.value = false
      owner.value = false
      needsSetup.value = false
      signupOpen.value = false
    }
    return status.value === 'in'
  }

  // Re-read /auth/me, e.g. after adding an account turns auto off.
  async function refresh(): Promise<boolean> {
    status.value = 'unknown'
    return await ensure()
  }

  async function login(name: string, password: string): Promise<void> {
    await apiLogin(name, password)
    await refresh()
  }

  async function setup(name: string, password: string): Promise<void> {
    await setupOwner(name, password)
    await refresh()
  }

  async function register(name: string, password: string): Promise<void> {
    await apiRegister(name, password)
    await refresh()
  }

  async function logout(): Promise<void> {
    try {
      await apiLogout()
    } catch {
      // Session already gone server-side; still clear local state.
    }
    // Re-read /auth/me so the login page knows whether sign-up is open.
    await refresh()
  }

  return { status, username, auto, owner, needsSetup, signupOpen, ensure, refresh, login, setup, register, logout }
}

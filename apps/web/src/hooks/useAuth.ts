import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMe } from '@/lib/api'
import { supabase } from '@/lib/supabase'
import type { UserMe } from '@/types/api'

type Role = 'admin' | 'user'

export function useAuth() {
  const [session, setSession] = useState<{ access_token: string } | null>(null)
  const [user, setUser] = useState<UserMe | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const role: Role | null = user?.app_metadata?.role
    ? (user.app_metadata.role as Role)
    : 'user'

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s ? { access_token: s.access_token } : null)
      if (s?.access_token) {
        getMe(s.access_token)
          .then(setUser)
          .catch(() => setUser(null))
          .finally(() => setLoading(false))
      } else {
        setUser(null)
        setLoading(false)
      }
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, s) => {
      setSession(s ? { access_token: s.access_token } : null)
      if (s?.access_token) {
        try {
          const u = await getMe(s.access_token)
          setUser(u)
        } catch {
          setUser(null)
        }
      } else {
        setUser(null)
      }
      setLoading(false)
    })

    return () => subscription.unsubscribe()
  }, [])

  const signIn = useCallback(
    async (email: string, password: string) => {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      })
      if (error) throw error
      const u = await getMe(data.session!.access_token)
      setUser(u)
      setSession({ access_token: data.session!.access_token })
      const r = (u.app_metadata?.role as Role) || 'user'
      if (r === 'admin') navigate('/admin')
      else navigate('/dashboard')
    },
    [navigate]
  )

  const signOut = useCallback(async () => {
    await supabase.auth.signOut()
    setSession(null)
    setUser(null)
    navigate('/')
  }, [navigate])

  return {
    session,
    user,
    role,
    loading,
    signIn,
    signOut,
    isAuthenticated: !!session,
  }
}

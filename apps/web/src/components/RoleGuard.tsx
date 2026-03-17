import { Navigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

type Role = 'admin' | 'user'

interface RoleGuardProps {
  children: React.ReactNode
  requiredRole: Role
  fallbackTo: string
}

export function RoleGuard({
  children,
  requiredRole,
  fallbackTo,
}: RoleGuardProps) {
  const { role, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-slate-500">Loading…</div>
      </div>
    )
  }

  if (role !== requiredRole) {
    return <Navigate to={fallbackTo} replace />
  }

  return <>{children}</>
}

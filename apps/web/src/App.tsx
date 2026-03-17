import { Routes, Route, Navigate } from 'react-router-dom'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { RoleGuard } from '@/components/RoleGuard'
import { LoginPage } from '@/pages/LoginPage'
import { AdminDashboard } from '@/pages/AdminDashboard'
import { UserDashboard } from '@/pages/UserDashboard'
import { CodebaseOperations } from '@/pages/CodebaseOperations'
import { NotFound } from '@/pages/NotFound'

function App() {
  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route
        path="/admin"
        element={
          <ProtectedRoute>
            <RoleGuard requiredRole="admin" fallbackTo="/dashboard">
              <AdminDashboard />
            </RoleGuard>
          </ProtectedRoute>
        }
      />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <RoleGuard requiredRole="user" fallbackTo="/admin">
              <UserDashboard />
            </RoleGuard>
          </ProtectedRoute>
        }
      >
        <Route index element={null} />
        <Route path="codebases/:id" element={<CodebaseOperations />} />
      </Route>
      <Route path="/404" element={<NotFound />} />
      <Route path="*" element={<Navigate to="/404" replace />} />
    </Routes>
  )
}

export default App

-- Migration: 0010_fix_rls_recursion.sql
-- Fixes infinite recursion between codebase and codebase_access RLS policies.
-- The codebase policy references codebase_access; codebase_access.ca_select_codebase_owner
-- references codebase. Using a SECURITY DEFINER function breaks the cycle.

-- Function bypasses RLS to check ownership (no recursion)
CREATE OR REPLACE FUNCTION public.user_owns_codebase(cb_id uuid, u_id uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (SELECT 1 FROM public.codebase WHERE id = cb_id AND user_id = u_id);
$$;

-- Replace ca_select_codebase_owner to use the function instead of a subquery on codebase
DROP POLICY IF EXISTS "ca_select_codebase_owner" ON public.codebase_access;
CREATE POLICY "ca_select_codebase_owner"
ON public.codebase_access
FOR SELECT
USING (public.user_owns_codebase(codebase_id, auth.uid()));

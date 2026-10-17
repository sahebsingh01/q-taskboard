import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, getToken } from "@/lib/api-client";
import type { PermissionCodename, ProjectPermissions } from "@/types";

export const PERMISSIONS_QUERY_KEY = ["permissions"] as const;

type PermissionsResponse = { projects: Record<string, ProjectPermissions> };

/**
 * Fetches the current user's per-project permissions. The query refetches on
 * every mount and window focus, and is invalidated whenever the API answers
 * 403, so role changes made elsewhere show up without a re-login.
 */
export function usePermissions(projectId?: string) {
  const query = useQuery({
    queryKey: PERMISSIONS_QUERY_KEY,
    queryFn: () => apiFetch<PermissionsResponse>("/api/users/me/permissions"),
    enabled: !!getToken(),
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });

  const project = projectId ? query.data?.projects[projectId] : undefined;

  // Deny by default while loading or when the user has no membership.
  const can = useCallback(
    (codename: PermissionCodename) => !!project?.permissions.includes(codename),
    [project],
  );

  return { can, role: project?.role, isLoading: query.isLoading, refetch: query.refetch };
}

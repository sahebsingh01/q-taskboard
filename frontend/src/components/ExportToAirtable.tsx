import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import { useToast } from "@/components/Toast";
import type { ApiExportJob } from "@/types";

type Props = { projectId: string };

const POLL_MS = 1500;

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function summary(job: ApiExportJob) {
  const parts = [`${plural(job.created, "new task")} exported`];
  if (job.skipped) parts.push(`${job.skipped} already in Airtable`);
  return parts.join(" · ");
}

export function ExportToAirtable({ projectId }: Props) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const queryKey = ["export", projectId];

  const { data } = useQuery({
    queryKey,
    queryFn: () => apiFetch<{ job: ApiExportJob | null }>(`/api/projects/${projectId}/export`),
    refetchInterval: (query) => (query.state.data?.job?.status === "running" ? POLL_MS : false),
  });

  const startExport = useMutation({
    mutationFn: () =>
      apiFetch<{ job: ApiExportJob }>(`/api/projects/${projectId}/export`, { method: "POST" }),
    onSuccess: (res) => queryClient.setQueryData(queryKey, res),
    onError: (err) =>
      toast.show({
        variant: "error",
        title: "Couldn't start the export",
        description: err instanceof Error ? err.message : undefined,
      }),
  });

  const job = data?.job;

  // Toast only when a job we watched running finishes, not for an old
  // finished job that loads with the page.
  const watching = useRef<string | null>(null);
  useEffect(() => {
    if (!job) return;
    if (job.status === "running") {
      watching.current = job.id;
      return;
    }
    if (watching.current !== job.id) return;
    watching.current = null;

    if (job.status === "succeeded") {
      toast.show({ variant: "success", title: "Export complete", description: summary(job) });
    } else if (job.status === "partial") {
      const failedTitles = job.errors.slice(0, 3).map((e) => `"${e.title}"`).join(", ");
      const more = job.failed > 3 ? ` and ${job.failed - 3} more` : "";
      toast.show({
        variant: "warning",
        title: `Export finished with ${plural(job.failed, "failed task")}`,
        description: `${summary(job)}. Failed: ${failedTitles}${more}.`,
      });
    } else {
      toast.show({ variant: "error", title: "Export failed", description: job.error ?? undefined });
    }
  }, [job, toast]);

  const running = job?.status === "running" || startExport.isPending;

  return (
    <button
      onClick={() => startExport.mutate()}
      disabled={running}
      className="border-2 border-accent hover:bg-accent px-4 py-2 rounded-md disabled:opacity-50 disabled:hover:bg-transparent"
    >
      {running ? "exporting…" : "Export"}
    </button>
  );
}

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import type { ApiExportJob } from "@/types";

type Props = { projectId: string };

const POLL_MS = 1500;

export function ExportToAirtable({ projectId }: Props) {
  const queryClient = useQueryClient();
  const queryKey = ["export", projectId];
  const [startError, setStartError] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey,
    queryFn: () => apiFetch<{ job: ApiExportJob | null }>(`/api/projects/${projectId}/export`),
    refetchInterval: (query) => (query.state.data?.job?.status === "running" ? POLL_MS : false),
  });

  const startExport = useMutation({
    mutationFn: () =>
      apiFetch<{ job: ApiExportJob }>(`/api/projects/${projectId}/export`, { method: "POST" }),
    onMutate: () => setStartError(null),
    onSuccess: (res) => queryClient.setQueryData(queryKey, res),
    onError: (err) => setStartError(err instanceof Error ? err.message : "export failed"),
  });

  const job = data?.job;
  const running = job?.status === "running" || startExport.isPending;

  return (
    <div className="flex flex-col items-end gap-1 max-w-sm text-right">
      <button
        onClick={() => startExport.mutate()}
        disabled={running}
        className="border-2 border-accent hover:bg-accent px-4 py-2 rounded-md disabled:opacity-50 disabled:hover:bg-transparent"
      >
        {running ? "exporting…" : "Export"}
      </button>
      {startError && (
        <p className="text-xs text-red-400" role="alert">
          {startError}
        </p>
      )}
      {/* {job && <ExportStatus job={job} />} */}
    </div>
  );
}

function ExportStatus({ job }: { job: ApiExportJob }) {
  const done = job.created + job.skipped + job.failed;
  if (job.status === "running") {
    return (
      <p className="text-xs text-muted" aria-live="polite">
        {job.total ? `${done} / ${job.total} tasks` : "starting…"}
      </p>
    );
  }
  if (job.status === "failed") {
    return (
      <p className="text-xs text-red-400" role="alert">
        export failed: {job.error}
      </p>
    );
  }
  return (
    <div className="text-xs">
      <p className={job.status === "partial" ? "text-amber-400" : "text-muted"}>
        {job.created} new {job.created === 1 ? "task" : "tasks"} exported · {job.skipped} already in Airtable
        {job.failed > 0 && ` · ${job.failed} failed`}
        {job.finishedAt && ` · ${new Date(job.finishedAt).toLocaleString()}`}
      </p>
      {job.errors.length > 0 && (
        <details className="mt-1 text-left">
          <summary className="cursor-pointer text-amber-400">show failed tasks</summary>
          <ul className="mt-1 space-y-1 text-muted">
            {job.errors.map((e) => (
              <li key={e.taskId}>
                <span className="text-white">{e.title}</span>: {e.error}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

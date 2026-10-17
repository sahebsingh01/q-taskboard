import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import { fullDate, timeAgo } from "@/lib/format";
import type { ApiActivity } from "@/types";
import { STATUS_LABELS } from "@/types";

type Props = { projectId: string };

const POLL_MS = 30_000;

function Strong({ children }: { children: ReactNode }) {
  return <span className="text-slate-100 font-medium">{children}</span>;
}

function describe(entry: ApiActivity): ReactNode {
  const task = <Strong>{entry.task.title}</Strong>;
  switch (entry.verb) {
    case "task_created":
      return <>created {task} in {STATUS_LABELS[entry.data.status]}</>;
    case "status_changed":
      return (
        <>
          moved {task} from {STATUS_LABELS[entry.data.from]} to <Strong>{STATUS_LABELS[entry.data.to]}</Strong>
        </>
      );
    case "assignee_changed": {
      const { to, from } = entry.data;
      if (!to) return <>unassigned {from?.name ?? "someone"} from {task}</>;
      return <>assigned {task} to <Strong>{to.name}</Strong></>;
    }
    case "comment_added":
      return (
        <>
          commented on {task}: <span className="italic">“{entry.data.excerpt}”</span>
        </>
      );
  }
}

export function ActivityFeed({ projectId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["activity", projectId],
    queryFn: () => apiFetch<{ activity: ApiActivity[] }>(`/api/projects/${projectId}/activity`),
    refetchInterval: POLL_MS,
  });

  const entries = data?.activity ?? [];

  return (
    <section className="mt-10">
      <h2 className="text-sm font-medium mb-3">recent activity</h2>
      <div className="bg-surface border border-border rounded-lg">
        {isLoading && <p className="px-4 py-3 text-xs text-muted">loading…</p>}
        {error && (
          <p className="px-4 py-3 text-xs text-red-400">
            {error instanceof Error ? error.message : "failed to load activity"}
          </p>
        )}
        {!isLoading && !error && entries.length === 0 && (
          <p className="px-4 py-3 text-xs text-muted italic">no activity yet</p>
        )}
        {entries.length > 0 && (
          <ol className="divide-y divide-border max-h-96 overflow-y-auto">
            {entries.map((e) => (
              <li key={e.id} className="px-4 py-3 flex items-start justify-between gap-4 text-sm">
                <p className="text-muted min-w-0 break-words">
                  <Strong>{e.actor?.name ?? "deleted user"}</Strong> {describe(e)}
                </p>
                <time
                  dateTime={e.createdAt}
                  title={fullDate(e.createdAt)}
                  className="text-xs text-muted whitespace-nowrap shrink-0"
                >
                  {timeAgo(e.createdAt)}
                </time>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

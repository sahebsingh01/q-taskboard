export type Role = "admin" | "member" | "viewer";
export type PermissionCodename =
  | "view_project"
  | "change_project"
  | "delete_project"
  | "add_membership"
  | "change_membership"
  | "delete_membership"
  | "view_membership"
  | "add_task"
  | "change_task"
  | "delete_task"
  | "view_task"
  | "export_task"
  | "add_comment"
  | "view_comment"
  | "view_activity"
  | (string & {});

export type ProjectPermissions = {
  role: Role;
  permissions: PermissionCodename[];
};

export type TaskStatus = "todo" | "in_progress" | "review" | "done";

export type ApiUser = {
  id: string;
  email: string;
  name: string;
};

export type ApiTask = {
  id: string;
  projectId: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  assigneeId: string | null;
  createdById: string;
  position: number;
  createdAt: string;
  updatedAt: string;
  assignee?: ApiUser | null;
};

export type ApiProjectMember = {
  id: string;
  role: Role;
  user: ApiUser;
};

export type ApiProjectDetail = {
  id: string;
  name: string;
  description: string | null;
  ownerId: string;
  owner: ApiUser;
  memberships: ApiProjectMember[];
  tasks: ApiTask[];
  createdAt: string;
  updatedAt: string;
};

export const STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  review: "In review",
  done: "Done",
};

export const STATUS_ORDER: TaskStatus[] = ["todo", "in_progress", "review", "done"];

export type ExportJobStatus = "running" | "succeeded" | "partial" | "failed";

export type ApiExportJob = {
  id: string;
  status: ExportJobStatus;
  total: number;
  created: number;
  skipped: number;
  failed: number;
  errors: { taskId: string; title: string; error: string }[];
  error: string | null;
  startedAt: string;
  finishedAt: string | null;
};

export type ApiComment = {
  id: string;
  taskId: string;
  author: ApiUser;
  body: string;
  createdAt: string;
};

type ActivityUserRef = { id: string; name: string } | null;

type ActivityBase = {
  id: string;
  actor: ActivityUserRef;
  task: { id: string | null; title: string };
  createdAt: string;
};

export type ApiActivity = ActivityBase &
  (
    | { verb: "task_created"; data: { status: TaskStatus } }
    | { verb: "status_changed"; data: { from: TaskStatus; to: TaskStatus } }
    | { verb: "assignee_changed"; data: { from: ActivityUserRef; to: ActivityUserRef } }
    | { verb: "comment_added"; data: { commentId: string; excerpt: string } }
  );

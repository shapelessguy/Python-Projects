import { useCallback, useRef, useState } from "react";
import * as tus from "tus-js-client";

/** Uploading files and whole folders into a browsable folder, resumably.
 *
 *  The files that belong in these folders are films, so an upload that
 *  cannot survive a dropped wifi link is not worth having. This speaks tus
 *  (tus.io) to /api/uploads: the file is sent in chunks, a failed chunk is
 *  retried with a growing delay, and a retry that comes back long after the
 *  connection died asks the server how much it actually has and carries on
 *  from there. See api/services/uploads.py for the other half. */

/** 8 MB: big enough that the per-request overhead disappears against a
 *  multi-gigabyte file, small enough that losing one costs a second and that
 *  the server holds only 8 MB per upload while writing it. */
const CHUNK_BYTES = 8 * 1024 * 1024;

/** Two at a time. More does not go faster on one connection — it just
 *  divides the same bandwidth and makes every file finish late. */
const PARALLEL = 2;

export interface PickedFile {
  file: File;
  /** Path *within what was dropped*: "Subs/eng.srt" for a file inside a
   *  dropped folder, just the filename for a loose one. This is what makes a
   *  dropped release folder land as that folder. */
  relPath: string;
}

export interface UploadJob {
  id: string;
  /** Which drop this came from. A dropped folder is one batch however many
   *  files it held, which is what makes "stop this folder" a single click
   *  rather than three hundred. */
  batch: string;
  batchLabel: string;
  name: string;
  relPath: string;
  folder: string;
  area: string;
  size: number;
  sent: number;
  status: "queued" | "uploading" | "done" | "error" | "cancelled";
  error: string;
}

/** Walk what was dropped.
 *
 *  A dropped folder is not in `dataTransfer.files` — it is an entry tree
 *  that has to be walked. The handles must be taken *synchronously*, before
 *  the first await: the DataTransfer is emptied the moment the drop handler
 *  returns, and an entry read afterwards is null. */
export function entriesFrom(dt: DataTransfer): (FileSystemEntry | null)[] {
  return Array.from(dt.items)
    .filter((item) => item.kind === "file")
    .map((item) => (item.webkitGetAsEntry ? item.webkitGetAsEntry() : null));
}

export async function walkEntries(
  entries: (FileSystemEntry | null)[], dt?: DataTransfer,
): Promise<PickedFile[]> {
  const out: PickedFile[] = [];
  const usable = entries.filter(Boolean) as FileSystemEntry[];
  if (!usable.length) {
    // A browser without the entry API still gives us loose files; folders
    // are simply not available there, which is the browser's limit, not ours.
    for (const file of Array.from(dt?.files ?? [])) {
      out.push({ file, relPath: file.name });
    }
    return out;
  }
  const visit = async (entry: FileSystemEntry, prefix: string): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File | null>((resolve) =>
        (entry as FileSystemFileEntry).file(resolve, () => resolve(null)));
      if (file) out.push({ file, relPath: prefix + entry.name });
      return;
    }
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    // readEntries hands back at most 100 at a time and signals the end with
    // an empty batch — a folder of 300 episodes needs the loop.
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((resolve) =>
        reader.readEntries((r) => resolve(r), () => resolve([])));
      if (!batch.length) break;
      for (const child of batch) await visit(child, prefix + entry.name + "/");
    }
  };
  for (const entry of usable) await visit(entry, "");
  return out;
}

let counter = 0;
let batchCounter = 0;

/** What to call a drop. A folder drop shares a first path segment and is
 *  named after it; anything else is named after the file, or counted. */
function batchLabel(picked: PickedFile[]): string {
  const roots = new Set(picked.map((p) => p.relPath.split("/")[0]));
  if (roots.size === 1) return [...roots][0];
  return `${picked.length} files`;
}

export function useUploads(onFinished: () => void) {
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  // The tus handles, kept out of state: they are not renderable and putting
  // them there would make every progress tick clone them.
  const handles = useRef(new Map<string, tus.Upload>());
  const queue = useRef<string[]>([]);
  const active = useRef(0);
  const pending = useRef(new Map<string, { picked: PickedFile; area: string; folder: string }>());
  // The three callbacks below call each other in a cycle (pump -> start ->
  // done -> pump) and outlive the render that made them, so they reach each
  // other through refs. A useCallback chain here would freeze whichever one
  // was captured first, and with it the listing refresh it closes over --
  // the upload would finish and nothing would appear.
  const finished = useRef(onFinished);
  finished.current = onFinished;
  const pumpRef = useRef<() => void>(() => {});
  // A plain mirror of `jobs`, so the cancel paths can read the list without
  // doing their work inside a state updater — updaters must be pure, and
  // React calls them twice in development to prove it.
  const jobsRef = useRef<UploadJob[]>([]);
  const startRef = useRef<(id: string, item: { picked: PickedFile; area: string; folder: string }) => void>(() => {});

  jobsRef.current = jobs;

  const patch = (id: string, fields: Partial<UploadJob>) =>
    setJobs((all) => all.map((j) => (j.id === id ? { ...j, ...fields } : j)));

  const pump = useCallback(() => {
    while (active.current < PARALLEL && queue.current.length) {
      const id = queue.current.shift()!;
      const item = pending.current.get(id);
      if (!item) continue;
      active.current += 1;
      startRef.current(id, item);
    }
  }, []);
  pumpRef.current = pump;

  const done = useCallback((id: string) => {
    active.current = Math.max(0, active.current - 1);
    handles.current.delete(id);
    pumpRef.current();
  }, []);

  const start = useCallback((id: string, item: { picked: PickedFile; area: string; folder: string }) => {
    const { picked, area, folder } = item;
    const upload = new tus.Upload(picked.file, {
      endpoint: "/api/uploads",
      chunkSize: CHUNK_BYTES,
      // Backs off to half a minute: a router rebooting takes longer than
      // three quick retries, and giving up on a 40 GB file because of it
      // would be the wrong answer.
      retryDelays: [0, 1000, 3000, 5000, 10000, 30000],
      // Same file dropped again after a failure resumes rather than
      // restarting -- the fingerprint is the file's own identity.
      storeFingerprintForResuming: true,
      removeFingerprintOnSuccess: true,
      metadata: {
        area,
        folder,
        relativePath: picked.relPath,
        filename: picked.file.name,
      },
      onProgress: (sent) => patch(id, { sent, status: "uploading" }),
      onError: (error) => {
        // Kept in `pending` on purpose: retry needs it, and it is the only
        // thing standing between a failed 40 GB upload and doing it again.
        patch(id, { status: "error", error: String(error).replace(/^Error:\s*/, "") });
        done(id);
      },
      onSuccess: () => {
        patch(id, { status: "done", sent: picked.file.size, error: "" });
        pending.current.delete(id);
        done(id);
        finished.current();
      },
    });
    handles.current.set(id, upload);
    patch(id, { status: "uploading" });
    upload.start();
  }, [done]);
  startRef.current = start;

  const add = useCallback((picked: PickedFile[], area: string, folder: string) => {
    const fresh: UploadJob[] = [];
    const batch = `b${++batchCounter}`;
    const label = batchLabel(picked);
    for (const item of picked) {
      const id = `u${++counter}`;
      pending.current.set(id, { picked: item, area, folder });
      queue.current.push(id);
      fresh.push({
        id, area, folder, batch, batchLabel: label,
        name: item.file.name,
        relPath: item.relPath,
        size: item.file.size,
        sent: 0,
        status: "queued",
        error: "",
      });
    }
    setJobs((all) => [...all, ...fresh]);
    pumpRef.current();
  }, []);

  const cancel = useCallback((id: string) => {
    const handle = handles.current.get(id);
    // `true` also tells the server to drop the partial, rather than leaving
    // it to be swept up a week later.
    if (handle) handle.abort(true).catch(() => {});
    queue.current = queue.current.filter((q) => q !== id);
    pending.current.delete(id);
    patch(id, { status: "cancelled" });
    done(id);
  }, [done]);

  const retry = useCallback((id: string) => {
    const item = pending.current.get(id);
    if (!item) return;
    patch(id, { status: "queued", error: "", sent: 0 });
    queue.current.push(id);
    pumpRef.current();
  }, []);

  /** Stop a whole drop. The point of batching: a folder of three hundred
   *  episodes is one mistake to undo, not three hundred. */
  const cancelBatch = useCallback((batch: string) => {
    let inFlight = 0;
    for (const job of jobsRef.current) {
      if (job.batch !== batch) continue;
      if (job.status !== "uploading" && job.status !== "queued") continue;
      if (job.status === "uploading") inFlight += 1;
      const handle = handles.current.get(job.id);
      // `true` also tells the server to drop the partial.
      if (handle) handle.abort(true).catch(() => {});
      queue.current = queue.current.filter((q) => q !== job.id);
      pending.current.delete(job.id);
      handles.current.delete(job.id);
    }
    setJobs((all) => all.map((j) =>
      j.batch === batch && (j.status === "uploading" || j.status === "queued")
        ? { ...j, status: "cancelled" as const } : j));
    // Only the slots this actually freed — another batch may still be
    // running in the other one.
    active.current = Math.max(0, active.current - inFlight);
    pumpRef.current();
  }, []);

  /** Forget the finished ones; anything still moving is left alone. */
  const clear = useCallback(() => {
    setJobs((all) => all.filter((j) => j.status === "uploading" || j.status === "queued"));
  }, []);

  return { jobs, add, cancel, cancelBatch, retry, clear };
}

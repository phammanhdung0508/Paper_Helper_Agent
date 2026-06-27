import { notFound } from "next/navigation";
import { getDoc } from "@/lib/store";
import { loadTags } from "@/lib/tags-store";
import FullVisualClient from "./FullVisualClient";

export const runtime = "nodejs";

export default async function VisualPage({
  params,
}: {
  params: Promise<{ docId: string; tagId: string }>;
}) {
  const { docId, tagId } = await params;
  if (!getDoc(docId)) notFound();

  const file = loadTags(docId);
  const tag = file?.tags.find((t) => t.id === tagId);
  if (!tag?.spec) notFound();

  return <FullVisualClient docId={docId} tagId={tagId} label={tag.label} spec={tag.spec} />;
}

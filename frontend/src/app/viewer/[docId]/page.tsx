import ViewerClient from "./viewer-client";

export default async function Page({
  params,
}: {
  params: Promise<{ docId: string }>;
}) {
  const { docId } = await params;
  return <ViewerClient docId={docId} />;
}

import { redirect } from "next/navigation";

export default function PredictMatchPage({
  params,
}: {
  params: { match_id: string };
}) {
  redirect(`/matches/${params.match_id}`);
}

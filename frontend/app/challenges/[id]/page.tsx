import { ChallengeDetail } from "@/components/challenge-detail";
export default async function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ChallengeDetail id={id} />;
}

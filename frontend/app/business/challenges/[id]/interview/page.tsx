import { ChallengeInterview } from "@/components/interview";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <ChallengeInterview id={(await params).id} />;
}

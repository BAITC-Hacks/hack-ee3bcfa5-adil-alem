import { ProposalForm } from "@/components/proposal-form";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { return <ProposalForm id={(await params).id} />; }

import { BusinessProposals } from "@/components/business";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { return <BusinessProposals id={(await params).id} />; }

"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
export function Navigation() {
  const path = usePathname();
  const router = useRouter();
  const business = path.startsWith("/business");
  return <><nav aria-label="Main navigation"><Link href="/" className={!business ? "nav-active" : ""}>Explore Challenges</Link><Link href="/business" className={business ? "nav-active" : ""}>For Business</Link><span className="nav-future" aria-disabled="true">My Proposals <small>Soon</small></span></nav><label className="role-switch">Demo view · no login<select aria-label="Demo role" value={business ? "business" : "student"} onChange={e => router.push(e.target.value === "business" ? "/business" : "/")}><option value="student">Student</option><option value="business">Business</option></select></label></>;
}

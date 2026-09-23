import Link from "next/link";
export function LoadingState() { return <div className="state" role="status"><span className="loading-dot" /><h2>Loading challenges</h2><p>Getting the latest information from the hub.</p></div>; }
export function ErrorState({ retry, notFound = false }: { retry?: () => void; notFound?: boolean }) {
  return <div className="state" role="alert"><div className="state-icon">{notFound ? "?" : "!"}</div><h2>{notFound ? "Challenge unavailable" : "We couldn’t connect to the hub"}</h2>
    <p>{notFound ? "This challenge may be unpublished or the link may have changed." : "The service may be temporarily offline. Please try again in a moment."}</p>
    {retry && !notFound ? <button className="button" onClick={retry}>Try again</button> : <Link className="button" href="/">Explore challenges</Link>}</div>;
}

import { Suspense } from "react";
import ChatHome from "@/components/ChatHome";

export default function HomePage() {
  return (
    <Suspense fallback={<p className="chat-hero muted">Loading…</p>}>
      <ChatHome />
    </Suspense>
  );
}

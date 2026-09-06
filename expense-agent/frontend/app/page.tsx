import { Suspense } from "react";
import ChatHome from "@/components/ChatHome";

export default function HomePage() {
  return (
    <Suspense fallback={null}>
      <ChatHome />
    </Suspense>
  );
}

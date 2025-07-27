'use client';

import dynamic from 'next/dynamic';

const ClientApp = dynamic(() => import('@/components/ClientApp'), {
  ssr: false,
  loading: () => (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-muted-foreground">Loading Fun Path Planner...</p>
      </div>
    </div>
  )
});

export default function Home() {
  return <ClientApp />;
}
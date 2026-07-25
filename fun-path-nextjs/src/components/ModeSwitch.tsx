'use client';

import { Route as RouteIcon, Wind } from 'lucide-react';

export type AppMode = 'spots' | 'routes';

interface ModeSwitchProps {
  mode: AppMode;
  onChange: (mode: AppMode) => void;
}

export default function ModeSwitch({ mode, onChange }: ModeSwitchProps) {
  return (
    <nav className="mode-switch" aria-label="Choose app mode">
      <button aria-label="Smoke spots" className={mode === 'spots' ? 'active' : ''} onClick={() => onChange('spots')}>
        <Wind size={14} /> <span>Spots</span>
      </button>
      <button aria-label="Route planner" className={mode === 'routes' ? 'active' : ''} onClick={() => onChange('routes')}>
        <RouteIcon size={14} /> <span>Routes</span>
      </button>
    </nav>
  );
}

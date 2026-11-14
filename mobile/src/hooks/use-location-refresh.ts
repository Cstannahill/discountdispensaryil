import { useEffect, useRef } from 'react';
import { Alert, AppState } from 'react-native';

import { toast } from '@/components/ui';
import { moveAction, shouldRecheck } from '@/lib/geo';
import { currentFix } from '@/lib/location';
import { getState, setOrigin } from '@/state/store';

/**
 * Keeps a GPS origin honest: every time the app comes to the foreground, a fix older than five minutes is re-read.
 * Small moves are ignored, a move across town swaps quietly, a move to another area asks first. A ZIP or city the user
 * typed is never replaced. Nothing runs in the background and the permission prompt is never shown from here.
 */
export function useLocationRefresh() {
  const busy = useRef(false);
  useEffect(() => {
    const check = async () => {
      const saved = getState().origin;
      if (busy.current || !saved || !shouldRecheck(saved)) return;
      busy.current = true;
      try {
        const fix = await currentFix(false);
        if (!fix.ok) return;
        const now = getState().origin;
        if (!now || now.src !== 'gps') return; // the user picked a place while we were looking
        const action = moveAction(now, fix.origin);
        if (action === 'keep') setOrigin({ ...now, at: Date.now() });
        else if (action === 'swap') { setOrigin(fix.origin); toast(`Location updated to ${fix.origin.place}`); }
        else {
          setOrigin({ ...now, at: Date.now() }); // do not ask again for another five minutes
          Alert.alert('You have moved', `Search near ${fix.origin.place} instead of ${now.place}?`, [
            { text: `Keep ${now.place}`, style: 'cancel' },
            { text: 'Update', onPress: () => setOrigin(fix.origin) },
          ]);
        }
      } finally { busy.current = false; }
    };
    check();
    const sub = AppState.addEventListener('change', (s) => { if (s === 'active') check(); });
    return () => sub.remove();
  }, []);
}

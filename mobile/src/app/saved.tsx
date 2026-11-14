import { useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, FlatList, RefreshControl, StyleSheet, Switch, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { openDirections, openMenu } from '@/components/offer-card';
import { Badge, Button, toast } from '@/components/ui';
import { alertsSupported, disableAlerts, enableAlerts, markSeen } from '@/lib/alerts';
import { money, perUnit, relativeTime, unitLabel } from '@/lib/format';
import { success, tap } from '@/lib/haptics';
import { checkSaved, type Check } from '@/lib/saved-check';
import { C, MONO, WEB_TOP } from '@/lib/theme';
import type { SavedDeal } from '@/lib/types';
import { getState, refreshSaved, removeSaved, setAlerts, useAppState } from '@/state/store';

export default function SavedScreen() {
  const saved = useAppState((s) => s.saved);
  const [checks, setChecks] = useState<Record<string, Check>>({});
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);
  const busy = useRef(false);
  const alerts = useAppState((s) => s.alerts);
  const canAlert = alertsSupported();

  const toggleAlerts = async (on: boolean) => {
    tap();
    if (!on) { setAlerts(false); await disableAlerts(); return; }
    const r = await enableAlerts();
    if (r === 'on') { setAlerts(true); success(); toast('We will notify you when a saved deal drops in price'); }
    else toast(r === 'denied' ? 'Notifications are off for this app. Allow them in Settings.' : r === 'restricted' ? 'Background refresh is off for this app. Turn it on in Settings.' : 'Alerts are not available in this build of the app');
  };

  const recheck = useCallback(async (announce: boolean) => {
    const list = getState().saved;
    if (busy.current || !list.length) return;
    busy.current = true; setChecking(true);
    const out = await checkSaved(list);
    const any = Object.keys(out).length > 0;
    busy.current = false; setChecking(false);
    if (!any) { if (announce) toast('Could not check prices. Are you offline?'); return; }
    setChecks(out); setCheckedAt(Date.now());
    markSeen(list, out); // seen here, so the background check will not notify about the same drop
    const drops = Object.values(out).filter((c) => c.status.kind === 'drop').length;
    if (drops) { success(); toast(`${drops} saved ${drops === 1 ? 'deal' : 'deals'} dropped in price`); }
    else if (announce) toast('Prices checked');
  }, []);

  useFocusEffect(useCallback(() => { recheck(false); }, [recheck]));

  const render = ({ item: d }: { item: SavedDeal }) => {
    const c = checks[d.id];
    const st = c?.status;
    const unit = unitLabel(d.category);
    const now = c?.current;
    return (
      <View style={s.card}>
        <View style={{ flexDirection: 'row', gap: 12 }}>
          <View style={{ flex: 1, gap: 4 }}>
            <Text style={s.brand} numberOfLines={1}>{d.brand || 'Brand not supplied'}</Text>
            <Text style={s.name}>{d.name}</Text>
            <Text style={s.meta}>{d.massLabel} · {d.store_name} · {d.distance_miles.toFixed(1)} mi</Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={s.price}>{money(now ? perUnit(now) : perUnit(d))}<Text style={s.unit}>/{unit}</Text></Text>
            <Text style={s.total}>{money(now ? now.effective_price : d.effective_price)}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
          {st?.kind === 'drop' && <Badge color={C.accent} border={C.accentBorder} bg={C.accentBg}>▼ Dropped {money(st.from - st.to)} (was {money(st.from)})</Badge>}
          {st?.kind === 'rise' && <Badge color={C.warn} border={C.warnBorder} bg={C.warnBg}>▲ Up {money(st.to - st.from)} (was {money(st.from)})</Badge>}
          {st?.kind === 'gone' && <Badge color={C.danger} border={C.warnBorder}>No longer listed</Badge>}
          {st?.kind === 'same' && <Badge color={C.textMuted}>Price unchanged</Badge>}
          <Text style={s.meta}>Saved {relativeTime(d.saved_at)}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {d.source_url ? <Button label="Menu ↗" onPress={() => openMenu(d.source_url!)} style={{ flex: 1 }} a11y={`View ${d.name} on the dispensary menu`} /> : <View style={{ flex: 1 }} />}
          <Button kind="ghost" label="Directions" onPress={() => openDirections(d.store_name)} a11y={`Directions to ${d.store_name}`} />
          {(st?.kind === 'drop' || st?.kind === 'rise') && now && (
            <Button kind="ghost" label="Got it" a11y="Keep watching from the new price" onPress={() => { tap(); refreshSaved(d.id, now); setChecks(({ [d.id]: _x, ...rest }) => rest); }} />
          )}
          <Button kind="ghost" label="Remove" a11y={`Remove ${d.name} from saved deals`} onPress={() => { tap(); removeSaved(d.id); }} />
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <FlatList
        data={saved}
        keyExtractor={(d) => d.id}
        renderItem={render}
        contentContainerStyle={s.content}
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        refreshControl={<RefreshControl refreshing={checking} onRefresh={() => recheck(true)} tintColor={C.accent} colors={[C.accentStrong]} progressBackgroundColor={C.card} />}
        ListHeaderComponent={
          <View style={{ paddingBottom: 12, gap: 4 }}>
            <Text style={s.title} accessibilityRole="header">Saved deals</Text>
            <Text style={s.meta}>
              {saved.length ? (checking ? 'Checking today’s prices…' : checkedAt ? `Prices checked ${relativeTime(checkedAt)}. Pull down to check again.` : 'Pull down to check today’s prices.') : ''}
            </Text>
            {canAlert && (
              <View style={s.alertRow}>
                <View style={{ flex: 1 }}>
                  <Text style={s.alertLabel}>Price-drop alerts</Text>
                  <Text style={s.meta}>Checks your saved deals a few times a day, even when the app is closed.</Text>
                </View>
                <Switch value={alerts} onValueChange={toggleAlerts} trackColor={{ true: C.accentStrong, false: C.border }} accessibilityLabel="Price-drop alerts" />
              </View>
            )}
            {saved.length > 1 && (
              <Button kind="ghost" label="Clear all" style={{ alignSelf: 'flex-start', marginTop: 6 }} onPress={() => Alert.alert('Clear saved deals?', `This removes all ${saved.length} saved deals.`, [{ text: 'Cancel', style: 'cancel' }, { text: 'Clear all', style: 'destructive', onPress: () => saved.forEach((d) => removeSaved(d.id)) }])} />
            )}
          </View>
        }
        ListEmptyComponent={
          <View style={s.empty}>
            <Text style={s.emptyTitle}>Nothing saved yet</Text>
            <Text style={s.emptyText}>Tap ☆ Save on a deal. Each time you open this tab the app checks the current menu and flags price drops.</Text>
          </View>
        }
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg, paddingTop: WEB_TOP },
  content: { padding: 12, paddingBottom: 32, width: '100%', maxWidth: 720, alignSelf: 'center' },
  title: { color: C.text, fontSize: 24, fontWeight: '800' },
  card: { backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 18, padding: 14, gap: 10 },
  brand: { color: C.accent, fontSize: 11, fontWeight: '800', letterSpacing: 0.8, textTransform: 'uppercase' },
  name: { color: C.text, fontSize: 15, fontWeight: '700', lineHeight: 20 },
  meta: { color: C.textMuted, fontSize: 12, lineHeight: 17 },
  price: { color: C.accent, fontSize: 19, fontWeight: '800', fontFamily: MONO, fontVariant: ['tabular-nums'] },
  unit: { color: C.textMuted, fontSize: 11, fontWeight: '400' },
  total: { color: C.textSoft, fontSize: 12, fontWeight: '700', fontFamily: MONO, marginTop: 3 },
  alertRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 8, padding: 12, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card },
  alertLabel: { color: C.text, fontSize: 15, fontWeight: '700' },
  empty: { alignItems: 'center', gap: 10, paddingVertical: 48, paddingHorizontal: 24 },
  emptyTitle: { color: C.text, fontSize: 18, fontWeight: '800' },
  emptyText: { color: C.textMuted, fontSize: 14, lineHeight: 20, textAlign: 'center' },
});

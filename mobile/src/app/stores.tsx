import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { openDirections } from '@/components/offer-card';
import { Button, toast } from '@/components/ui';
import { ApiError, fetchStores } from '@/lib/api';
import { cacheKey, readCache, writeCache } from '@/lib/cache';
import { tap } from '@/lib/haptics';
import { C, WEB_TOP } from '@/lib/theme';
import type { AreaStore } from '@/lib/types';
import { clearHidden, setStoreHidden, useAppState } from '@/state/store';

export default function StoresScreen() {
  const origin = useAppState((s) => s.origin);
  const radius = useAppState((s) => s.filters.radius);
  const license = useAppState((s) => s.filters.license);
  const hidden = useAppState((s) => s.hidden);
  const hiddenNames = useAppState((s) => s.hiddenNames);
  const [stores, setStores] = useState<AreaStore[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');

  useEffect(() => {
    if (!origin) return;
    let live = true;
    const key = 'stores:' + cacheKey({ lat: origin.lat.toFixed(4), lon: origin.lon.toFixed(4), radius: String(radius), license });
    setError(null);
    (async () => {
      const cached = await readCache<AreaStore[]>(key);
      if (live && cached) setStores(cached.data);
      try {
        const items = await fetchStores(origin, radius, license);
        if (!live) return;
        setStores(items); writeCache(key, items);
      } catch (e) {
        if (live) setError(e instanceof ApiError && e.status === 0 ? 'You are offline. Showing the last saved list.' : (e as Error).message);
      }
    })();
    return () => { live = false; };
  }, [origin, radius, license]);

  // Hidden dispensaries outside the current area stay listed, so they can always be shown again.
  const rows = useMemo(() => {
    const inArea = stores ?? [];
    const ids = new Set(inArea.map((x) => x.id));
    const extra = hidden.filter((id) => !ids.has(id)).map((id) => ({ id, name: hiddenNames[id] ?? id, distance_miles: -1 }));
    const t = q.trim().toLowerCase();
    return [...inArea, ...extra].filter((x) => !t || x.name.toLowerCase().includes(t));
  }, [stores, hidden, hiddenNames, q]);

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <FlatList
        data={rows}
        keyExtractor={(x) => x.id}
        contentContainerStyle={s.content}
        keyboardShouldPersistTaps="handled"
        ListHeaderComponent={
          <View style={{ gap: 8, paddingBottom: 12 }}>
            <Text style={s.title} accessibilityRole="header">Dispensaries</Text>
            <Text style={s.meta}>
              {origin ? `${stores?.length ?? '…'} ${license === 'medicinal' ? 'medical' : 'recreational'} within ${radius} mi of ${origin.place}. Switch one off to hide its deals.` : 'Set a location on the Deals tab to list dispensaries near you.'}
            </Text>
            {!!error && <Text style={s.banner} accessibilityRole="alert">{error}</Text>}
            {!!origin && <TextInput value={q} onChangeText={setQ} placeholder="Find a dispensary" placeholderTextColor={C.textFaint} autoCorrect={false} clearButtonMode="while-editing" accessibilityLabel="Find a dispensary" style={s.search} />}
            {hidden.length > 0 && <Button kind="ghost" label={`Show all ${hidden.length} hidden`} style={{ alignSelf: 'flex-start' }} onPress={() => { tap(); clearHidden(); }} />}
          </View>
        }
        ListEmptyComponent={origin && !stores && !error ? <ActivityIndicator color={C.accent} style={{ marginTop: 32 }} /> : undefined}
        renderItem={({ item }) => {
          const off = hidden.includes(item.id);
          return (
            <View style={s.row}>
              <Pressable style={{ flex: 1 }} onPress={() => openDirections(item.name)} accessibilityRole="link" accessibilityLabel={`Directions to ${item.name}`}>
                <Text style={[s.name, off && { color: C.textFaint, textDecorationLine: 'line-through' }]} numberOfLines={2}>{item.name}</Text>
                <Text style={s.meta}>{item.distance_miles >= 0 ? `${item.distance_miles.toFixed(1)} mi · Directions ↗` : 'Outside this search area'}</Text>
              </Pressable>
              <Switch
                value={!off}
                onValueChange={(show) => { tap(); if (!setStoreHidden(item.id, item.name, !show)) toast('You can hide up to 100 dispensaries'); }}
                trackColor={{ true: C.accentStrong, false: C.border }}
                accessibilityLabel={`Show deals from ${item.name}`}
              />
            </View>
          );
        }}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg, paddingTop: WEB_TOP },
  content: { padding: 12, paddingBottom: 32, width: '100%', maxWidth: 720, alignSelf: 'center' },
  title: { color: C.text, fontSize: 24, fontWeight: '800' },
  meta: { color: C.textMuted, fontSize: 12, lineHeight: 17 },
  banner: { color: C.warn, backgroundColor: C.warnBg, borderColor: C.warnBorder, borderWidth: 1, borderRadius: 12, padding: 10, fontSize: 13, overflow: 'hidden' },
  search: { minHeight: 44, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, color: C.text, paddingHorizontal: 14, fontSize: 16 },
  row: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.borderSoft },
  name: { color: C.text, fontSize: 15, fontWeight: '600' },
});

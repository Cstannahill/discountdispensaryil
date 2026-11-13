import { router } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { openDirections } from '@/components/offer-card';
import { StoreMap } from '@/components/store-map';
import { Badge, Button, Chip, toast } from '@/components/ui';
import { ApiError, fetchMapStores, mapParams } from '@/lib/api';
import { cacheKey, readCache, writeCache } from '@/lib/cache';
import { ageLabel, money, unitLabel } from '@/lib/format';
import { tap } from '@/lib/haptics';
import { cheapest } from '@/lib/map';
import { C, MONO, WEB_TOP } from '@/lib/theme';
import { CATEGORIES, CATEGORY_LABEL, type MapStore } from '@/lib/types';
import { setFilters, setStoreHidden, useAppState } from '@/state/store';

export default function MapScreen() {
  const origin = useAppState((s) => s.origin);
  const radius = useAppState((s) => s.filters.radius);
  const license = useAppState((s) => s.filters.license);
  const category = useAppState((s) => s.filters.category);
  const hidden = useAppState((s) => s.hidden);
  const [stores, setStores] = useState<MapStore[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!origin) return;
    let live = true;
    const params = mapParams(origin, radius, license, category);
    const key = 'map:' + cacheKey(params);
    setNote(null);
    (async () => {
      const cached = await readCache<MapStore[]>(key);
      if (live && cached) setStores(cached.data);
      try {
        const items = await fetchMapStores(params);
        if (!live) return;
        setStores(items); writeCache(key, items);
      } catch (e) {
        if (!live) return;
        if (!cached) setStores([]);
        setNote(e instanceof ApiError && e.status === 0 ? (cached ? 'You are offline. Showing the last saved map.' : 'You are offline.')
          : e instanceof ApiError && e.status === 404 ? 'The map needs a newer version of the site. It will work once the latest update is live.'
          : (e as Error).message);
      }
    })();
    return () => { live = false; };
  }, [origin, radius, license, category]);

  const unit = unitLabel(category);
  const top = useMemo(() => cheapest(stores ?? [], hidden), [stores, hidden]);
  const selected = stores?.find((s) => s.id === selectedId) ?? null;
  const center = useMemo(() => (origin ? { lat: origin.lat, lon: origin.lon } : null), [origin]);
  const select = (id: string | null) => { if (id && id !== selectedId) tap(); setSelectedId(id); };

  if (!origin || !center) {
    return (
      <SafeAreaView style={[s.screen, s.center]} edges={['top']}>
        <Text style={s.title}>Map</Text>
        <Text style={s.meta}>Set a location on the Deals tab to see dispensaries around you.</Text>
        <Button label="Go to Deals" onPress={() => router.navigate('/')} />
      </SafeAreaView>
    );
  }

  const withDeals = stores?.filter((x) => x.best).length ?? 0;
  const place = selected ? [selected.address, selected.city, selected.state].filter(Boolean).join(', ') : '';
  const off = selected ? hidden.includes(selected.id) : false;

  return (
    <View style={s.screen}>
      <StoreMap stores={stores ?? []} center={center} radius={radius} unit={unit} selectedId={selectedId} hidden={hidden} showUser={origin.src === 'gps'} bestId={top?.id ?? null} onSelect={select} />

      <SafeAreaView edges={['top']} pointerEvents="box-none" style={s.overlayTop}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chips}>
          {CATEGORIES.map((c) => <Chip key={c} label={CATEGORY_LABEL[c]} active={category === c} onPress={() => setFilters({ category: c })} />)}
        </ScrollView>
        {!!note && <Text style={s.banner} accessibilityRole="alert">{note}</Text>}
        {!stores && <ActivityIndicator color={C.accent} style={{ marginTop: 12 }} accessibilityLabel="Loading dispensaries" />}
      </SafeAreaView>

      <View style={s.overlayBottom} pointerEvents="box-none">
        {selected ? (
          <View style={s.card} accessibilityLiveRegion="polite">
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <View style={{ flex: 1, gap: 3 }}>
                <Text style={s.name}>{selected.name}</Text>
                <Text style={s.meta}>{place ? `${place} · ` : ''}{selected.distance_miles.toFixed(1)} mi</Text>
              </View>
              {selected.best && (
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={s.price}>{money(selected.best.unit_price)}<Text style={s.unit}>/{unit}</Text></Text>
                  <Text style={s.meta}>best of {selected.deals}</Text>
                </View>
              )}
            </View>
            {selected.best ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                <Text style={[s.meta, { color: C.textSoft, flexShrink: 1 }]} numberOfLines={1}>
                  {selected.best.brand ? `${selected.best.brand} · ` : ''}{selected.best.name} · {money(selected.best.effective_price)}
                </Text>
                {selected.best.freshness === 'fresh'
                  ? <Badge color={C.accent} border={C.accentBorder}>fresh</Badge>
                  : <Badge color={C.warn} border={C.warnBorder}>last menu {ageLabel(selected.best.menu_age_hours)}</Badge>}
              </View>
            ) : <Text style={s.meta}>No {CATEGORY_LABEL[category].toLowerCase()} deals listed for this dispensary right now.</Text>}
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <Button label="Directions" style={{ flex: 1 }} a11y={`Directions to ${selected.name}`} onPress={() => openDirections(selected.name, selected)} />
              {selected.deals > 0 && (
                <Button kind="ghost" label="See deals" a11y={`See deals at ${selected.name}`} onPress={() => { if (off) setStoreHidden(selected.id, selected.name, false); setFilters({ q: selected.name }); router.navigate('/'); }} />
              )}
              <Button kind="ghost" label={off ? 'Show' : 'Hide'} a11y={off ? `Show deals from ${selected.name}` : `Hide deals from ${selected.name}`} onPress={() => { tap(); if (!setStoreHidden(selected.id, selected.name, !off)) toast('You can hide up to 100 dispensaries'); }} />
            </View>
          </View>
        ) : stores ? (
          <View style={s.summary}>
            <Text style={s.summaryText} numberOfLines={2}>
              {stores.length
                ? `${stores.length} ${stores.length === 1 ? 'dispensary' : 'dispensaries'} within ${radius} mi of ${origin.place}, ${withDeals} with ${CATEGORY_LABEL[category].toLowerCase()} deals.`
                : note ? 'No dispensaries to show.' : `No dispensaries within ${radius} mi of ${origin.place}.`}
            </Text>
            {top && <Button label={`Best: ${money(top.best!.unit_price)}/${unit}`} a11y={`Show the cheapest dispensary, ${top.name}`} onPress={() => select(top.id)} />}
          </View>
        ) : null}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg, paddingTop: WEB_TOP },
  center: { alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  title: { color: C.text, fontSize: 24, fontWeight: '800' },
  meta: { color: C.textMuted, fontSize: 12, lineHeight: 17 },
  overlayTop: { position: 'absolute', top: WEB_TOP, left: 0, right: 0 },
  chips: { gap: 8, paddingHorizontal: 12, paddingVertical: 8 },
  banner: { marginHorizontal: 12, color: C.warn, backgroundColor: '#1c1917', borderColor: C.warnBorder, borderWidth: 1, borderRadius: 12, padding: 10, fontSize: 13, overflow: 'hidden' },
  overlayBottom: { position: 'absolute', left: 12, right: 12, bottom: 12, maxWidth: 696, alignSelf: 'center' },
  card: { backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 18, padding: 14, gap: 10 },
  name: { color: C.text, fontSize: 16, fontWeight: '800' },
  price: { color: C.accent, fontSize: 20, fontWeight: '800', fontFamily: MONO, fontVariant: ['tabular-nums'] },
  unit: { color: C.textMuted, fontSize: 11, fontWeight: '400' },
  summary: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 16, paddingVertical: 8, paddingHorizontal: 12 },
  summaryText: { color: C.textSoft, fontSize: 13, lineHeight: 18, flex: 1 },
});

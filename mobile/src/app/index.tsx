import { useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { FilterSheet } from '@/components/filter-sheet';
import { LocationSheet } from '@/components/location-sheet';
import { OfferCard } from '@/components/offer-card';
import { Button, Chip } from '@/components/ui';
import { useDeals } from '@/hooks/use-deals';
import { relativeTime } from '@/lib/format';
import { success, tap } from '@/lib/haptics';
import { C, WEB_TOP } from '@/lib/theme';
import { CATEGORIES, CATEGORY_LABEL, DEFAULT_FILTERS, LICENSES, SORT_LABEL, type Category, type Offer } from '@/lib/types';
import { setFilters, useAppState } from '@/state/store';

const keyOf = (o: Offer) => o.id;

export default function DealsScreen() {
  const origin = useAppState((s) => s.origin);
  const filters = useAppState((s) => s.filters);
  const hidden = useAppState((s) => s.hidden);
  const deals = useDeals(origin, filters, hidden);
  const [locOpen, setLocOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [text, setText] = useState(filters.q);
  const list = useRef<FlatList<Offer>>(null);

  // Deep links: discountdispensaryil://?q=rosin&category=concentrate opens straight into that search.
  const link = useLocalSearchParams<{ q?: string; category?: string }>();
  useEffect(() => {
    const category = CATEGORIES.includes(link.category as Category) ? (link.category as Category) : undefined;
    if (link.q != null || category) setFilters({ ...(link.q != null ? { q: link.q.trim() } : {}), ...(category ? { category } : {}) });
  }, [link.q, link.category]);

  // A search set elsewhere (the map's "See deals", a deep link) shows up in the box.
  useEffect(() => { setText((t) => (t.trim() === filters.q ? t : filters.q)); }, [filters.q]);

  // Search as you type, after a short pause.
  useEffect(() => {
    const t = setTimeout(() => { if (text.trim() !== filters.q) setFilters({ q: text.trim() }); }, 400);
    return () => clearTimeout(t);
  }, [text, filters.q]);

  useEffect(() => { list.current?.scrollToOffset({ offset: 0, animated: false }); }, [filters, origin, hidden]);

  const wasRefreshing = useRef(false);
  useEffect(() => {
    if (wasRefreshing.current && !deals.refreshing && !deals.error) success();
    wasRefreshing.current = deals.refreshing;
  }, [deals.refreshing, deals.error]);

  const activeFilters = [filters.sort !== 'value', filters.category === 'flower' && filters.grade !== DEFAULT_FILTERS.grade, !!filters.strain, filters.size !== 'any', filters.stale, filters.unverified].filter(Boolean).length;
  const showingSaved = deals.cachedAt != null && deals.loadedAt == null;

  const header = (
    <View style={{ gap: 10, paddingBottom: 10 }}>
      <View style={s.topRow}>
        <Pressable style={({ pressed }) => [s.loc, pressed && { opacity: 0.7 }]} onPress={() => { tap(); setLocOpen(true); }} accessibilityRole="button" accessibilityLabel={`Search location: ${origin?.place ?? 'not set'}, within ${filters.radius} miles. Change`}>
          <Text style={s.locText} numberOfLines={1}>📍 {origin?.place ?? 'Set location'}</Text>
          <Text style={s.locRadius}>· {filters.radius} mi ▾</Text>
        </Pressable>
        <View style={s.seg} accessibilityRole="radiogroup" accessibilityLabel="License">
          {LICENSES.map((l) => (
            <Pressable key={l} onPress={() => { tap(); setFilters({ license: l }); }} accessibilityRole="radio" accessibilityState={{ selected: filters.license === l }} accessibilityLabel={l === 'medicinal' ? 'Medical' : 'Recreational'} style={[s.segBtn, filters.license === l && s.segOn]}>
              <Text style={[s.segText, filters.license === l && { color: C.accent }]}>{l === 'medicinal' ? 'Med' : 'Rec'}</Text>
            </Pressable>
          ))}
        </View>
      </View>
      <TextInput value={text} onChangeText={setText} placeholder="Search brand, strain or dispensary" placeholderTextColor={C.textFaint} returnKeyType="search" autoCorrect={false} clearButtonMode="while-editing" accessibilityLabel="Search deals" style={s.search} />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {CATEGORIES.map((c) => <Chip key={c} label={CATEGORY_LABEL[c]} active={filters.category === c} onPress={() => setFilters({ category: c })} />)}
        <Chip label={activeFilters ? `Filters · ${activeFilters}` : 'Sort & filter'} active={activeFilters > 0} onPress={() => setFilterOpen(true)} />
      </ScrollView>
      {deals.offline && (
        <Text style={s.banner} accessibilityRole="alert">
          {deals.items.length ? `You are offline. Showing deals saved ${relativeTime(deals.cachedAt)}.` : 'You are offline and this search has not been saved yet.'}
        </Text>
      )}
      {!deals.offline && !!deals.error && <Text style={s.banner} accessibilityRole="alert">{deals.error}. Pull down to try again.</Text>}
      {!!origin && !deals.loading && (
        <Text style={s.count}>
          {deals.total.toLocaleString()} {CATEGORY_LABEL[filters.category].toLowerCase()} {deals.total === 1 ? 'deal' : 'deals'} · {SORT_LABEL[filters.sort].toLowerCase()}
          {showingSaved && !deals.offline ? ' · updating…' : deals.loadedAt ? ` · checked ${relativeTime(deals.loadedAt)}` : ''}
        </Text>
      )}
    </View>
  );

  const empty = !origin ? (
    <View style={s.empty}>
      <Text style={s.emptyTitle}>Find the cheapest deals near you</Text>
      <Text style={s.emptyText}>Use your location or pick a city to compare price per gram across Illinois dispensary menus.</Text>
      <Button label="Set location" onPress={() => setLocOpen(true)} />
    </View>
  ) : deals.loading ? (
    <ActivityIndicator color={C.accent} style={{ marginTop: 40 }} accessibilityLabel="Loading deals" />
  ) : deals.error ? null : (
    <View style={s.empty}>
      <Text style={s.emptyTitle}>No deals match</Text>
      <Text style={s.emptyText}>Try a wider distance, fewer filters, or turn on older menus.</Text>
      <Button label="Sort & filter" kind="ghost" onPress={() => setFilterOpen(true)} />
    </View>
  );

  return (
    <SafeAreaView style={s.screen} edges={['top']}>
      <FlatList
        ref={list}
        data={origin ? deals.items : []}
        keyExtractor={keyOf}
        renderItem={({ item, index }) => <OfferCard o={item} rank={filters.sort === 'value' ? index + 1 : undefined} />}
        ListHeaderComponent={header}
        ListEmptyComponent={empty ?? undefined}
        ListFooterComponent={deals.loadingMore ? <ActivityIndicator color={C.accent} style={{ marginVertical: 16 }} /> : undefined}
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        contentContainerStyle={s.content}
        onEndReached={deals.loadMore}
        onEndReachedThreshold={0.6}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        initialNumToRender={6}
        windowSize={7}
        refreshControl={<RefreshControl refreshing={deals.refreshing} onRefresh={deals.refresh} tintColor={C.accent} colors={[C.accentStrong]} progressBackgroundColor={C.card} />}
      />
      <LocationSheet visible={locOpen} onClose={() => setLocOpen(false)} />
      <FilterSheet visible={filterOpen} onClose={() => setFilterOpen(false)} />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg, paddingTop: WEB_TOP },
  content: { padding: 12, paddingBottom: 32, width: '100%', maxWidth: 720, alignSelf: 'center' },
  topRow: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  loc: { flex: 1, minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card },
  locText: { color: C.text, fontSize: 15, fontWeight: '700', flexShrink: 1 },
  locRadius: { color: C.accent, fontSize: 13, fontWeight: '600' },
  seg: { flexDirection: 'row', borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, overflow: 'hidden' },
  segBtn: { minHeight: 44, minWidth: 52, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 10 },
  segOn: { backgroundColor: C.accentBg },
  segText: { color: C.textMuted, fontSize: 13, fontWeight: '700' },
  search: { minHeight: 44, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, color: C.text, paddingHorizontal: 14, fontSize: 16 },
  banner: { color: C.warn, backgroundColor: C.warnBg, borderColor: C.warnBorder, borderWidth: 1, borderRadius: 12, padding: 10, fontSize: 13, overflow: 'hidden' },
  count: { color: C.textMuted, fontSize: 12 },
  empty: { alignItems: 'center', gap: 12, paddingVertical: 48, paddingHorizontal: 24 },
  emptyTitle: { color: C.text, fontSize: 18, fontWeight: '800', textAlign: 'center' },
  emptyText: { color: C.textMuted, fontSize: 14, lineHeight: 20, textAlign: 'center' },
});
